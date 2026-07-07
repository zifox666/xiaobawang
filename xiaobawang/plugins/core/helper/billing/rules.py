"""
计费规则 —— 单价表 + 复杂度因子计算

计费公式: 单次推送扣费 = 单价(unit_price) × 复杂度因子(complexity_factor)

设计原则:
  - 订阅越「宽」（匹配多）：单条便宜但量大
  - 订阅越「精」（条件复杂）：单条贵但量小
  总成本趋于均衡，鼓励精确订阅而非全量轰炸。

复杂度因子复用现有 ScoreRules（zkb/score_rules.py）的 entity/label 权重，
在订阅创建/更新时计算并快照到 subscription.complexity_factor，推送时直接读不重算。
"""

from typing import Any

from ..zkb.score_rules import ScoreRules


class BillingRules:
    """计费规则定义"""

    # 按推送类型的单价（积分/条），可通过 config.billing_unit_price 覆盖
    UNIT_PRICE: dict[str, int] = {
        "eve_status": 1,   # 极低频（状态翻转才推），近乎免费
        "structure": 2,    # 文本推送，中频
        "killmail": 5,     # 图片渲染成本高，高频
    }

    # 每日免费额度（在该额度内不扣费，仅消费免费配额）
    FREE_QUOTA_DAILY: dict[str, int] = {
        "eve_status": 50,
        "structure": 20,
        "killmail": 0,
    }

    # ========================================================================
    # 单价
    # ========================================================================

    @classmethod
    def get_unit_price(cls, sub_type: str) -> int:
        """获取某类型的单价，未知名类型返回 0（不计费）"""
        from ...config import plugin_config
        override = getattr(plugin_config, "billing_unit_price", None) or {}
        merged = {**cls.UNIT_PRICE, **override}
        return int(merged.get(sub_type, 0))

    # ========================================================================
    # 复杂度因子
    # ========================================================================

    @classmethod
    def calc_complexity(cls, sub_type: str, config: dict[str, Any] | None) -> float:
        """
        根据订阅配置计算复杂度因子。

        Args:
            sub_type: 推送类型
            config: 订阅配置（killmail 为 condition_groups dict；structure 为 {"categories":[...]}）
        Returns:
            复杂度因子，>= 1.0
        """
        if config is None:
            config = {}
        if sub_type == "eve_status":
            return 1.0
        if sub_type == "structure":
            cats = config.get("categories", []) if isinstance(config, dict) else []
            n = len(cats) if isinstance(cats, list) else 0
            return round(1.0 + 0.1 * max(0, n - 1), 2)
        if sub_type == "killmail":
            return cls._calc_killmail_complexity(config)
        return 1.0

    @classmethod
    def _calc_killmail_complexity(cls, condition_groups: dict | str | None) -> float:
        """
        killmail 条件组复杂度：
            entity_factor = 1 + 0.04 × max(entity_score)
            label_factor  = 1 + 0.05 × label_count
            depth_factor  = 1 + 0.1  × max_nest_depth
            factor = entity_factor × label_factor × depth_factor
        """
        import json

        if condition_groups is None:
            return 1.0
        if isinstance(condition_groups, str):
            try:
                condition_groups = json.loads(condition_groups)
            except (json.JSONDecodeError, TypeError):
                return 1.0
        if not isinstance(condition_groups, dict):
            return 1.0

        max_entity_score = 0
        label_count = 0
        max_depth = 0

        def walk(node: dict, depth: int) -> None:
            nonlocal max_entity_score, label_count, max_depth
            if not isinstance(node, dict):
                return
            max_depth = max(max_depth, depth)
            for cond in node.get("conditions", []) or []:
                if not isinstance(cond, dict):
                    continue
                ctype = cond.get("type") or cond.get("condition_type") or ""
                if ctype == "entity":
                    etype = cond.get("entity_type") or cond.get("target_type") or ""
                    max_entity_score = max(max_entity_score, ScoreRules.get_entity_score(etype))
                elif ctype == "label":
                    label_count += 1
            for g in node.get("groups", []) or []:
                walk(g, depth + 1)

        walk(condition_groups, 0)

        entity_factor = 1.0 + 0.04 * max_entity_score
        label_factor = 1.0 + 0.05 * label_count
        depth_factor = 1.0 + 0.1 * max_depth
        return round(entity_factor * label_factor * depth_factor, 2)

    # ========================================================================
    # 扣费计算
    # ========================================================================

    @classmethod
    def calc_charge(
        cls,
        sub_type: str,
        unit_price: int | None = None,
        factor: float = 1.0,
        count: int = 1,
    ) -> int:
        """
        计算实际扣费额。

        Args:
            sub_type: 推送类型
            unit_price: 单价（None 时按类型默认单价）
            factor: 复杂度因子
            count: 推送条数
        Returns:
            扣费额（>=1 当计费类型且 count>0）
        """
        if unit_price is None:
            unit_price = cls.get_unit_price(sub_type)
        if unit_price <= 0:
            return 0
        per = max(1, round(unit_price * factor))
        return per * max(1, count)

    @classmethod
    def to_dict(cls) -> dict:
        """规则总览，供 /api/credit/rules 展示"""
        return {
            "unit_price": dict(cls.UNIT_PRICE),
            "free_quota_daily": dict(cls.FREE_QUOTA_DAILY),
            "complexity": {
                "eve_status": "固定 1.0",
                "structure": "1.0 + 0.1 × (categories数 - 1)",
                "killmail": "(1 + 0.04×max_entity_score) × (1 + 0.05×label数) × (1 + 0.1×嵌套深度)",
            },
        }
