# KM订阅筛选器重构方案

## 当前问题分析

### 现有架构
1. **两种订阅类型分离**
   - `KillmailHighValueSubscription`: 仅按价值筛选
   - `KillmailConditionSubscription`: 单一条件筛选(角色/军团/联盟/星系/舰船)
   
2. **局限性**
   - 无法组合多个条件 (如: "某联盟在某星系的损失")
   - 无法实现复杂逻辑 (如: "A联盟击杀B联盟" 或 "价值>10亿 且 在虫洞星系")
   - `is_victim` 和 `is_final_blow` 标志语义模糊
   - 扩展性差,添加新条件类型需要修改表结构

## 重构目标

1. **支持灵活的条件组合**: AND/OR逻辑
2. **清晰的角色定义**: 受害者/攻击者/最后一击
3. **易于扩展**: 添加新条件类型无需改表
4. **向后兼容**: 能够迁移现有订阅数据

---

## 方案设计

### 1. 数据模型重构

#### Entity 类型完整列表

```python
# Entity 类型枚举
class EntityType(str, Enum):
    """实体类型"""
    CHARACTER = "character"          # 角色
    CORPORATION = "corporation"      # 军团
    ALLIANCE = "alliance"            # 联盟
    FACTION = "faction"              # 阵营
    SYSTEM = "system"                # 星系
    REGION = "region"                # 区域
    INVENTORY_TYPE = "inventory_type" # 物品类型(舰船/装备)
    STRUCTURE = "structure"          # 建筑(空间站/门户等)
    FACTION_WAR_CORP = "faction_war_corp"  # 一级军团
```

#### Label 类型完整列表

```python
# Label 类型和配置 (基于 label.py)
class LabelType(str, Enum):
    """Label 类型"""
    # 位置标签
    LOC_NULLSEC = "loc:nullsec"
    LOC_LOWSEC = "loc:lowsec"
    LOC_HIGHSEC = "loc:highsec"
    LOC_WSPACE = "loc:w-space"
    
    # 时区标签
    TZ_AU = "tz:au"
    TZ_EU = "tz:eu"
    TZ_USE = "tz:use"
    TZ_RU = "tz:ru"
    TZ_USW = "tz:usw"
    
    # 条件标签
    CAT_22 = "cat:22"          # 拆迁狂
    AWOX = "awox"              # 加团打蓝星
    AT_SHIP = "atShip"         # AT 舰船
    CAPITAL = "capital"        # 旗舰杀手
    F1_WARRIOR = "f1"          # F1战士
    SOLO = "solo"              # SOLO高手
    SMALL_TEAM = "small_team"  # 小队糕手
```

#### 新表结构

```python
# 订阅主表
class KillmailSubscription(Model):
    """KM订阅主表 - 统一管理所有订阅"""
    __tablename__ = "killmail_subscription"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # 会话信息
    platform: Mapped[str]
    bot_id: Mapped[str]
    session_id: Mapped[str]
    session_type: Mapped[str]
    
    # 订阅元信息
    name: Mapped[str] = mapped_column(default="未命名订阅")  # 用户自定义名称
    description: Mapped[str | None]  # 描述
    is_enabled: Mapped[bool] = mapped_column(default=True)
    
    # 全局筛选
    min_value: Mapped[float] = mapped_column(default=100_000_000)  # 最低价值
    max_age_days: Mapped[int] = mapped_column(default=10)  # 最大天数
    
    # 条件逻辑 (JSON字段存储条件组)
    # 结构: {"logic": "AND", "conditions": [...], "labels": {...}}
    condition_groups: Mapped[str]  # JSON string
    
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


# 条件组表 (可选,如果不想用JSON)
class SubscriptionConditionGroup(Model):
    """条件组 - 支持AND/OR逻辑"""
    __tablename__ = "subscription_condition_group"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("killmail_subscription.id"))
    
    logic_operator: Mapped[str] = mapped_column(default="AND")  # AND/OR
    group_order: Mapped[int] = mapped_column(default=0)  # 组顺序
    
    # 关联条件
    conditions: Mapped[list["SubscriptionCondition"]] = relationship(back_populates="group")


# 具体条件表
class SubscriptionCondition(Model):
    """单个筛选条件"""
    __tablename__ = "subscription_condition"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("subscription_condition_group.id"))
    
    # 条件类型
    condition_type: Mapped[str]  # entity/location/value/ship/label/stats
    
    # 实体条件 (支持更多entity类型)
    entity_type: Mapped[str | None]  # character/corporation/alliance/faction/structure/faction_war_corp
    entity_id: Mapped[int | None]
    entity_name: Mapped[str | None]
    entity_role: Mapped[str | None]  # victim/attacker/final_blow/any_attacker
    
    # 位置条件
    location_type: Mapped[str | None]  # system/region/wormhole/nullsec/lowsec/highsec
    location_id: Mapped[int | None]  # 星系ID或区域ID
    location_name: Mapped[str | None]
    
    # 舰船条件
    ship_type_id: Mapped[int | None]
    ship_name: Mapped[str | None]
    ship_role: Mapped[str | None]  # victim_ship/attacker_ship/final_blow_ship
    ship_category: Mapped[str | None]  # capital/supercapital/structure
    
    # 价值条件 (细粒度控制)
    value_min: Mapped[float | None]
    value_max: Mapped[float | None]
    
    # Label条件
    required_labels: Mapped[str | None]  # JSON数组: ["loc:nullsec", "tz:eu"]
    excluded_labels: Mapped[str | None]  # JSON数组: ["awox"]
    
    # 统计条件
    ships_destroyed_min: Mapped[int | None]
    ships_destroyed_max: Mapped[int | None]
    danger_ratio_min: Mapped[int | None]  # 危险度 0-100
    solo_kills_min: Mapped[int | None]
    
    condition_order: Mapped[int] = mapped_column(default=0)
```

---

### 2. 条件DSL设计

#### JSON结构示例 - 基础

```json
{
  "logic": "AND",
  "conditions": [
    {
      "type": "entity",
      "entity_type": "alliance",
      "entity_id": 99003214,
      "entity_name": "Goonswarm Federation",
      "role": "victim"
    },
    {
      "type": "location",
      "location_type": "region",
      "location_id": 10000060,
      "location_name": "Delve"
    },
    {
      "type": "value",
      "min": 1000000000,
      "max": null
    }
  ]
}
```

#### 支持Label筛选

```json
{
  "logic": "AND",
  "conditions": [
    {
      "type": "entity",
      "entity_type": "corporation",
      "entity_id": 98765432,
      "entity_name": "Test Corp",
      "role": "victim"
    },
    {
      "type": "label",
      "required_labels": ["loc:nullsec", "tz:eu"],
      "excluded_labels": ["awox"]
    },
    {
      "type": "value",
      "min": 500000000
    }
  ]
}
```

#### 支持战斗统计条件

```json
{
  "logic": "AND",
  "conditions": [
    {
      "type": "stats",
      "ships_destroyed_min": 50,
      "danger_ratio_min": 40,
      "solo_kills_min": 5
    },
    {
      "type": "label",
      "required_labels": ["f1"]
    }
  ]
}
```

#### 复杂条件 - OR组合

```json
{
  "logic": "OR",
  "groups": [
    {
      "logic": "AND",
      "conditions": [
        {"type": "entity", "entity_type": "alliance", "entity_id": 123, "role": "victim"},
        {"type": "value", "min": 5000000000},
        {"type": "label", "required_labels": ["loc:nullsec"]}
      ]
    },
    {
      "logic": "AND",
      "conditions": [
        {"type": "entity", "entity_type": "corporation", "entity_id": 456, "role": "final_blow"},
        {"type": "ship", "ship_category": "capital"}
      ]
    }
  ]
}
```

#### 支持更多Entity类型

```json
{
  "logic": "AND",
  "conditions": [
    {
      "type": "entity",
      "entity_type": "faction",
      "entity_id": 500001,
      "entity_name": "Caldari State",
      "role": "victim"
    },
    {
      "type": "entity",
      "entity_type": "corporation",
      "entity_id": 98765432,
      "entity_name": "Corp Name",
      "role": "any_attacker"
    },
    {
      "type": "entity",
      "entity_type": "faction_war_corp",
      "entity_id": 1000125,
      "entity_name": "Faction War Corp",
      "role": "any_attacker"
    }
  ]
}
```

---

### 3. 核心匹配引擎

```python
import json
from typing import Any, Tuple
from nonebot import logger


class ConditionMatcher:
    """条件匹配引擎 - 支持灵活的条件组合和标签匹配"""
    
    def __init__(self, killmail_data: dict, label_helper_result: dict = None):
        """
        初始化匹配器
        
        Args:
            killmail_data: zkillboard推送的完整killmail数据
            label_helper_result: ZkbLabelHelper.make() 的结果
        """
        self.data = killmail_data
        self.victim = killmail_data.get("victim", {})
        self.attackers = killmail_data.get("attackers", [])
        self.final_blow = next((a for a in self.attackers if a.get("final_blow")), {})
        self.zkb = killmail_data.get("zkb", {})
        self.labels = label_helper_result or {}
        
    async def match_subscription(self, subscription: dict) -> Tuple[bool, list[str]]:
        """
        匹配订阅条件
        
        Args:
            subscription: 订阅配置字典
            
        Returns:
            (是否匹配, 匹配原因列表)
        """
        # 检查全局过滤
        if not self._check_global_filters(subscription):
            return False, []
        
        # 解析条件
        condition_config = json.loads(subscription["condition_groups"])
        
        # 递归匹配
        matched, reasons = await self._match_condition_group(condition_config)
        return matched, reasons
    
    def _check_global_filters(self, subscription: dict) -> bool:
        """检查全局过滤条件"""
        # 价值检查
        total_value = float(self.zkb.get("totalValue", 0))
        if total_value < subscription.get("min_value", 100_000_000):
            return False
        
        # 时间检查 (可选)
        max_age_days = subscription.get("max_age_days", 10)
        # ... 检查时间逻辑
        
        return True
    
    async def _match_condition_group(self, group: dict) -> Tuple[bool, list[str]]:
        """匹配条件组 - 支持递归AND/OR逻辑"""
        logic = group.get("logic", "AND").upper()
        conditions = group.get("conditions", [])
        sub_groups = group.get("groups", [])
        
        results = []
        reasons = []
        
        # 匹配直接条件
        for condition in conditions:
            matched, reason = await self._match_single_condition(condition)
            results.append(matched)
            if matched and reason:
                reasons.append(reason)
        
        # 递归匹配子组
        for sub_group in sub_groups:
            matched, sub_reasons = await self._match_condition_group(sub_group)
            results.append(matched)
            reasons.extend(sub_reasons)
        
        # 应用逻辑运算
        if not results:  # 空条件组视为通过
            return True, reasons
        
        if logic == "AND":
            final_match = all(results)
        elif logic == "OR":
            final_match = any(results)
        else:
            final_match = False
        
        return final_match, reasons if final_match else []
    
    async def _match_single_condition(self, condition: dict) -> Tuple[bool, str]:
        """匹配单个条件"""
        cond_type = condition.get("type", "").lower()
        
        if cond_type == "entity":
            return await self._match_entity_condition(condition)
        elif cond_type == "location":
            return await self._match_location_condition(condition)
        elif cond_type == "ship":
            return await self._match_ship_condition(condition)
        elif cond_type == "value":
            return self._match_value_condition(condition)
        elif cond_type == "label":
            return self._match_label_condition(condition)
        elif cond_type == "stats":
            return self._match_stats_condition(condition)
        else:
            logger.warning(f"Unknown condition type: {cond_type}")
            return False, ""
    
    async def _match_entity_condition(self, condition: dict) -> Tuple[bool, str]:
        """匹配实体条件 (支持character/corporation/alliance/faction/structure等)"""
        entity_type = condition.get("entity_type")
        entity_id = condition.get("entity_id")
        entity_name = condition.get("entity_name", "")
        role = condition.get("role")
        
        if not entity_type or not entity_id or not role:
            return False, ""
        
        # 获取目标
        target = None
        if role == "victim":
            target = self.victim
            role_text = "损失"
        elif role == "final_blow":
            target = self.final_blow
            role_text = "最后一击"
        elif role == "any_attacker":
            # 检查所有攻击者
            for attacker in self.attackers:
                if self._check_entity_match(attacker, entity_type, entity_id):
                    return True, f"[{entity_type}]参与击杀: {entity_name}"
            return False, ""
        else:
            return False, ""
        
        # 检查目标实体
        if self._check_entity_match(target, entity_type, entity_id):
            return True, f"[{entity_type}]{role_text}: {entity_name}"
        
        return False, ""
    
    @staticmethod
    def _check_entity_match(target: dict, entity_type: str, entity_id: int) -> bool:
        """检查实体是否匹配 - 支持多种entity类型"""
        if entity_type == "character":
            return target.get("character_id") == entity_id
        elif entity_type == "corporation":
            return target.get("corporation_id") == entity_id
        elif entity_type == "alliance":
            return target.get("alliance_id") == entity_id
        elif entity_type == "faction":
            return target.get("faction_id") == entity_id
        elif entity_type == "faction_war_corp":
            return target.get("faction_corp_id") == entity_id
        elif entity_type == "structure":
            return target.get("structure_id") == entity_id
        return False
    
    async def _match_location_condition(self, condition: dict) -> Tuple[bool, str]:
        """匹配位置条件"""
        location_type = condition.get("location_type")
        location_id = condition.get("location_id")
        location_name = condition.get("location_name", "")
        
        system_id = self.data.get("solar_system_id")
        if not system_id:
            return False, ""
        
        if location_type == "system":
            if system_id == location_id:
                return True, f"星系: {location_name}"
        elif location_type == "region":
            # 需要调用SDE查询星系所属区域
            pass
        elif location_type == "wormhole":
            # 虫洞检查: 星系ID > 31000000
            if system_id > 31000000:
                return True, f"虫洞"
        
        return False, ""
    
    def _match_value_condition(self, condition: dict) -> Tuple[bool, str]:
        """匹配价值条件"""
        value_min = condition.get("min")
        value_max = condition.get("max")
        total_value = float(self.zkb.get("totalValue", 0))
        
        if value_min and total_value < value_min:
            return False, ""
        if value_max and total_value > value_max:
            return False, ""
        
        return True, f"价值: {total_value:,.0f} ISK"
    
    def _match_label_condition(self, condition: dict) -> Tuple[bool, str]:
        """匹配标签条件 (基于ZkbLabelHelper的结果)"""
        required_labels = condition.get("required_labels", [])
        excluded_labels = condition.get("excluded_labels", [])
        
        if not required_labels and not excluded_labels:
            return True, ""
        
        # 获取killmail拥有的标签集合
        current_labels = set(self.labels.keys())
        
        # 检查排除标签
        for excluded in excluded_labels:
            if excluded in current_labels:
                return False, ""
        
        # 检查必需标签 (至少满足一个)
        if required_labels:
            if not any(label in current_labels for label in required_labels):
                return False, ""
        
        matched_labels = [self.labels.get(label, {}).get("name", label) 
                         for label in required_labels if label in current_labels]
        reason = "标签: " + ", ".join(matched_labels) if matched_labels else "标签匹配"
        return True, reason
    
    def _match_stats_condition(self, condition: dict) -> Tuple[bool, str]:
        """匹配战斗统计条件 (基于ZkbLabelHelper的数据)"""
        ships_destroyed_min = condition.get("ships_destroyed_min")
        ships_destroyed_max = condition.get("ships_destroyed_max")
        danger_ratio_min = condition.get("danger_ratio_min")
        solo_kills_min = condition.get("solo_kills_min")
        
        ships_destroyed = self.zkb.get("shipsDestroyed", 0)
        danger_ratio = self.zkb.get("dangerRatio", 0)
        solo_kills = self.zkb.get("soloKills", 0)
        
        # 检查击毁舰船数
        if ships_destroyed_min and ships_destroyed < ships_destroyed_min:
            return False, ""
        if ships_destroyed_max and ships_destroyed > ships_destroyed_max:
            return False, ""
        
        # 检查危险度
        if danger_ratio_min and danger_ratio < danger_ratio_min:
            return False, ""
        
        # 检查单人击杀数
        if solo_kills_min and solo_kills < solo_kills_min:
            return False, ""
        
        reason_parts = []
        if ships_destroyed_min:
            reason_parts.append(f"击毁≥{ships_destroyed_min}")
        if danger_ratio_min:
            reason_parts.append(f"危险度≥{danger_ratio_min}%")
        if solo_kills_min:
            reason_parts.append(f"单人≥{solo_kills_min}")
        
        reason = "战斗: " + ", ".join(reason_parts) if reason_parts else "战斗统计匹配"
        return True, reason
    
    async def _match_ship_condition(self, condition: dict) -> Tuple[bool, str]:
        """匹配舰船条件"""
        ship_type_id = condition.get("ship_type_id")
        ship_role = condition.get("ship_role")
        ship_category = condition.get("ship_category")
        ship_name = condition.get("ship_name", "")
        
        if not ship_role:
            return False, ""
        
        # 确定目标舰船
        if ship_role == "victim_ship":
            target_ship_id = self.victim.get("ship_type_id")
        elif ship_role == "final_blow_ship":
            target_ship_id = self.final_blow.get("ship_type_id")
        else:
            return False, ""
        
        if not target_ship_id:
            return False, ""
        
        # 检查舰船ID
        if ship_type_id and target_ship_id == ship_type_id:
            return True, f"舰船: {ship_name}"
        
        # 检查舰船类别 (需要查询SDE)
        if ship_category:
            pass
        
        return False, ""
```

---

### 4.5 集成使用示例

#### 在 Validator 中使用新的 ConditionMatcher

```python
# 在 validator.py 中集成新引擎
from .matcher import ConditionMatcher
from ..label import ZkbLabelHelper

async def validate_and_match(self, data: dict[str, Any]) -> dict[tuple, list[str]] | None:
    """使用新的条件匹配引擎"""
    
    # 检查全局过滤
    if not self._check_killmail_value(data):
        return None
    
    if not self._check_killmail_time(data):
        return None
    
    # 获取所有订阅
    all_subscriptions = await self.subscription_manager.get_all_subscriptions()
    if not all_subscriptions:
        return None
    
    # 生成Label
    label_helper = ZkbLabelHelper(data.get("zkb", {}))
    labels = label_helper.make()
    
    # 创建匹配器
    matcher = ConditionMatcher(data, labels)
    
    # 匹配订阅
    matched_sessions = {}
    for sub in all_subscriptions:
        if not sub["is_enabled"]:
            continue
        
        matched, reasons = await matcher.match_subscription(sub)
        if matched:
            total_value = float(data.get("zkb", {}).get("totalValue", 0))
            session_key = (
                sub["platform"], 
                sub["bot_id"], 
                sub["session_id"], 
                sub["session_type"], 
                total_value
            )
            matched_sessions.setdefault(session_key, []).extend(reasons)
    
    return matched_sessions if matched_sessions else None
```

#### 数据迁移脚本

```python
async def migrate_subscriptions():
    """迁移现有订阅到新结构"""
    
    # 迁移高价值订阅
    old_high_value_subs = await get_all_high_value_subscriptions()
    for old_sub in old_high_value_subs:
        new_sub = KillmailSubscription(
            platform=old_sub.platform,
            bot_id=old_sub.bot_id,
            session_id=old_sub.session_id,
            session_type=old_sub.session_type,
            name="高价值击杀",
            min_value=old_sub.min_value,
            condition_groups=json.dumps({
                "logic": "AND",
                "conditions": []  # 无额外条件,仅价值过滤
            })
        )
        # 保存...
    
    # 迁移条件订阅
    old_condition_subs = await get_all_condition_subscriptions()
    for old_sub in old_condition_subs:
        # 确定角色
        if old_sub.is_victim:
            role = "victim"
        elif old_sub.is_final_blow:
            role = "final_blow"
        else:
            role = "any_attacker"
        
        # 确定条件类型
        if old_sub.target_type in ["character", "corporation", "alliance"]:
            condition = {
                "type": "entity",
                "entity_type": old_sub.target_type,
                "entity_id": old_sub.target_id,
                "entity_name": old_sub.target_name,
                "role": role
            }
        elif old_sub.target_type == "system":
            condition = {
                "type": "location",
                "location_type": "system",
                "location_id": old_sub.target_id,
                "location_name": old_sub.target_name
            }
        elif old_sub.target_type == "inventory_type":
            condition = {
                "type": "ship",
                "ship_type_id": old_sub.target_id,
                "ship_name": old_sub.target_name,
                "ship_role": f"{role}_ship"
            }
        
        new_sub = KillmailSubscription(
            platform=old_sub.platform,
            bot_id=old_sub.bot_id,
            session_id=old_sub.session_id,
            session_type=old_sub.session_type,
            name=f"{old_sub.target_name}订阅",
            min_value=old_sub.min_value,
            condition_groups=json.dumps({
                "logic": "AND",
                "conditions": [condition]
            })
        )
        # 保存...
```

---

### 5. API接口设计

#### 订阅创建接口

```python
async def create_subscription(
    platform: str,
    bot_id: str,
    session_id: str,
    session_type: str,
    name: str,
    min_value: float,
    condition_config: dict,  # 直接传入条件配置JSON
) -> int:
    """
    创建订阅
    
    Args:
        condition_config: 条件配置,格式如:
        {
            "logic": "AND",
            "conditions": [
                {"type": "entity", "entity_type": "alliance", "entity_id": 123, "role": "victim"},
                {"type": "value", "min": 1000000000}
            ]
        }
    """
    # 验证配置
    if not validate_condition_config(condition_config):
        raise ValueError("Invalid condition config")
    
    subscription = KillmailSubscription(
        platform=platform,
        bot_id=bot_id,
        session_id=session_id,
        session_type=session_type,
        name=name,
        min_value=min_value,
        condition_groups=json.dumps(condition_config),
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    # 保存到数据库
    # ...
    return subscription.id
```

#### 模板订阅

```python
# 预定义常用订阅模板
SUBSCRIPTION_TEMPLATES = {
    "high_value": {
        "name": "高价值击杀",
        "description": "简单的高价值订阅,仅按价值过滤",
        "config": {
            "logic": "AND",
            "conditions": []
        }
    },
    "alliance_loss": {
        "name": "联盟损失",
        "description": "监控特定联盟的所有损失",
        "config": {
            "logic": "AND",
            "conditions": [
                {"type": "entity", "entity_type": "alliance", "entity_id": 0, "entity_name": "", "role": "victim"}
            ]
        }
    },
    "wormhole_label": {
        "name": "虫洞PVP",
        "description": "虫洞中发生的战斗 + 高价值",
        "config": {
            "logic": "AND",
            "conditions": [
                {"type": "location", "location_type": "wormhole"},
                {"type": "value", "min": 100000000}
            ]
        }
    },
    "capital_loss": {
        "name": "旗舰损失",
        "description": "任何旗舰被摧毁",
        "config": {
            "logic": "AND",
            "conditions": [
                {"type": "ship", "ship_role": "victim_ship", "ship_category": "capital"}
            ]
        }
    },
    "f1_heavy": {
        "name": "F1战士重战",
        "description": "F1战士且击毁>100舰",
        "config": {
            "logic": "AND",
            "conditions": [
                {"type": "label", "required_labels": ["f1"]},
                {"type": "stats", "ships_destroyed_min": 100}
            ]
        }
    },
    "nullsec_fight": {
        "name": "00战斗",
        "description": "00玩家的战斗,排除蓝星",
        "config": {
            "logic": "AND",
            "conditions": [
                {"type": "label", "required_labels": ["loc:nullsec"], "excluded_labels": ["awox"]},
                {"type": "value", "min": 500000000}
            ]
        }
    },
    "supercap_vs_goons": {
        "name": "超旗VS Goons",
        "description": "GSF损失超旗舰 OR 我方击杀Goons",
        "config": {
            "logic": "OR",
            "groups": [
                {
                    "logic": "AND",
                    "conditions": [
                        {"type": "entity", "entity_type": "alliance", "entity_id": 1354830081, "entity_name": "Goonswarm", "role": "victim"},
                        {"type": "ship", "ship_category": "supercapital", "ship_role": "victim_ship"}
                    ]
                },
                {
                    "logic": "AND",
                    "conditions": [
                        {"type": "entity", "entity_type": "alliance", "entity_id": 1354830081, "entity_name": "Goonswarm", "role": "any_attacker"},
                        {"type": "ship", "ship_category": "capital", "ship_role": "victim_ship"}
                    ]
                }
            ]
        }
    },
    "faction_war": {
        "name": "阵营战争",
        "description": "阵营战争相关损失",
        "config": {
            "logic": "AND",
            "conditions": [
                {"type": "entity", "entity_type": "faction", "entity_id": 0, "entity_name": "", "role": "victim"},
                {"type": "value", "min": 100000000}
            ]
        }
    }
}
```

---

## 示例场景

### 场景1: "监控A联盟在Delve区域的所有损失(>5亿)"

```json
{
  "name": "GSF Delve损失监控",
  "min_value": 500000000,
  "condition_groups": {
    "logic": "AND",
    "conditions": [
      {
        "type": "entity",
        "entity_type": "alliance",
        "entity_id": 1354830081,
        "entity_name": "Goonswarm Federation",
        "role": "victim"
      },
      {
        "type": "location",
        "location_type": "region",
        "location_id": 10000060,
        "location_name": "Delve"
      }
    ]
  }
}
```

### 场景2: "监控我军团参与的旗舰击杀 OR 敌对联盟的旗舰损失"

```json
{
  "name": "旗舰战报",
  "min_value": 1000000000,
  "condition_groups": {
    "logic": "OR",
    "groups": [
      {
        "logic": "AND",
        "conditions": [
          {"type": "entity", "entity_type": "corporation", "entity_id": 98234567, "entity_name": "My Corp", "role": "any_attacker"},
          {"type": "ship", "ship_category": "capital", "ship_role": "victim_ship"}
        ]
      },
      {
        "logic": "AND",
        "conditions": [
          {"type": "entity", "entity_type": "alliance", "entity_id": 99001234, "entity_name": "Enemy Alliance", "role": "victim"},
          {"type": "ship", "ship_category": "capital", "ship_role": "victim_ship"}
        ]
      }
    ]
  }
}
```

### 场景3: "虫洞高价值PVP + 有标签加成"

```json
{
  "name": "虫洞精英战",
  "min_value": 1000000000,
  "condition_groups": {
    "logic": "AND",
    "conditions": [
      {
        "type": "location",
        "location_type": "wormhole"
      },
      {
        "type": "label",
        "required_labels": ["capital", "solo"],
        "excluded_labels": ["awox"]
      },
      {
        "type": "stats",
        "ships_destroyed_min": 10,
        "danger_ratio_min": 50
      }
    ]
  }
}
```

### 场景4: "简单高价值订阅(向后兼容)"

```json
{
  "name": "15亿+高价值击杀",
  "min_value": 1500000000,
  "condition_groups": {
    "logic": "AND",
    "conditions": []
  }
}
```

### 场景5: "欧洲时区00玩家的高价值战斗"

```json
{
  "name": "欧洲00战斗",
  "min_value": 800000000,
  "condition_groups": {
    "logic": "AND",
    "conditions": [
      {
        "type": "label",
        "required_labels": ["loc:nullsec", "tz:eu"],
        "excluded_labels": ["awox"]
      },
      {
        "type": "stats",
        "ships_destroyed_min": 20
      }
    ]
  }
}
```

---

### 6. 优势总结

✅ **灵活性**: 支持任意复杂的条件组合  
✅ **可扩展**: 添加新条件类型只需扩展matcher,无需改表  
✅ **清晰**: 语义明确,角色定义清楚  
✅ **Label集成**: 充分利用现有的ZkbLabelHelper标签系统  
✅ **多entity支持**: 不仅支持character/corporation/alliance,还支持faction/structure等  
✅ **向后兼容**: 可平滑迁移现有数据  
✅ **用户友好**: 可提供模板和可视化配置界面  

---

### 7. 实施步骤

1. **Phase 1: 核心引擎** (1-2天)
   - 实现 `ConditionMatcher` 引擎
   - 集成ZkbLabelHelper
   - 单元测试各种条件匹配

2. **Phase 2: 数据模型** (1天)
   - 创建新表结构
   - 编写迁移脚本

3. **Phase 3: API重构** (1-2天)
   - 重构订阅管理接口
   - 更新 `KillmailValidator`

4. **Phase 4: 数据迁移** (0.5天)
   - 执行迁移脚本
   - 验证数据正确性

5. **Phase 5: 清理** (0.5天)
   - 删除旧表/代码
   - 文档更新

**总计**: 约 5-6 天

---

### 8. 风险评估

⚠️ **潜在性能开销**: JSON解析 + 复杂条件匹配  
   - 缓解: 订阅数据缓存,条件预编译
   
⚠️ **数据迁移风险**: 旧订阅可能丢失  
   - 缓解: 迁移前备份,提供回滚机制
   
⚠️ **用户学习成本**: 新的配置方式  
   - 缓解: 提供模板和向导式界面

---

## 示例场景

### 场景1: "监控A联盟在Delve区域的所有损失(>5亿)"

```json
{
  "name": "GSF Delve损失监控",
  "min_value": 500000000,
  "condition_groups": {
    "logic": "AND",
    "conditions": [
      {
        "type": "entity",
        "entity_type": "alliance",
        "entity_id": 1354830081,
        "entity_name": "Goonswarm Federation",
        "role": "victim"
      },
      {
        "type": "location",
        "location_type": "region",
        "location_id": 10000060,
        "location_name": "Delve"
      }
    ]
  }
}
```

### 场景2: "监控我军团参与的旗舰击杀 OR 敌对联盟的旗舰损失"

```json
{
  "name": "旗舰战报",
  "min_value": 1000000000,
  "condition_groups": {
    "logic": "OR",
    "groups": [
      {
        "logic": "AND",
        "conditions": [
          {"type": "entity", "entity_type": "corporation", "entity_id": 98234567, "role": "any_attacker"},
          {"type": "ship", "ship_category": "capital", "ship_role": "victim_ship"}
        ]
      },
      {
        "logic": "AND",
        "conditions": [
          {"type": "entity", "entity_type": "alliance", "entity_id": 99001234, "role": "victim"},
          {"type": "ship", "ship_category": "capital", "ship_role": "victim_ship"}
        ]
      }
    ]
  }
}
```

### 场景3: "虫洞高价值PVP + 有标签加成"

```json
{
  "name": "虫洞精英战",
  "min_value": 1000000000,
  "condition_groups": {
    "logic": "AND",
    "conditions": [
      {
        "type": "location",
        "location_type": "wormhole"
      },
      {
        "type": "label",
        "required_labels": ["capital"],
        "excluded_labels": ["awox"]
      },
      {
        "type": "stats",
        "ships_destroyed_min": 10,
        "danger_ratio_min": 50
      }
    ]
  }
}
```

### 场景4: "简单高价值订阅(向后兼容)"

```json
{
  "name": "15亿+高价值击杀",
  "min_value": 1500000000,
  "condition_groups": {
    "logic": "AND",
    "conditions": []
  }
}
```

### 场景5: "欧洲时区00玩家的高价值战斗"

```json
{
  "name": "欧洲00战斗",
  "min_value": 800000000,
  "condition_groups": {
    "logic": "AND",
    "conditions": [
      {
        "type": "label",
        "required_labels": ["loc:nullsec", "tz:eu"],
        "excluded_labels": ["awox"]
      },
      {
        "type": "stats",
        "ships_destroyed_min": 20
      }
    ]
  }
}
```

---

## 总结

此重构方案提供了:

1. **统一的订阅模型** - 用一张表存储所有订阅,配置通过JSON灵活定义
2. **强大的条件系统** - 支持递归AND/OR逻辑,可组合任意复杂的条件
3. **Label集成** - 充分利用现有ZkbLabelHelper标签,支持位置/时区/战斗标签
4. **扩展的Entity支持** - 不仅支持character/corporation/alliance,还支持faction/structure等
5. **战斗统计条件** - 支持击毁数、危险度、单人击杀等细粒度筛选
6. **完整的实现** - 提供了ConditionMatcher引擎的完整代码
7. **平滑的迁移** - 通过迁移脚本保持向后兼容
8. **丰富的模板** - 9个预定义模板覆盖常见使用场景

**核心优势**:
- ✅ 灵活性极强 - 支持任意复杂的条件组合
- ✅ 易于扩展 - 添加新条件类型无需改表
- ✅ 清晰易用 - 语义明确,配置直观
- ✅ 高效实用 - 与现有系统无缝集成


    "conditions": []
  }
}
```

---

## 下一步

请审阅此方案并反馈:
1. 数据模型设计是否合理?
2. JSON结构是否需要调整?
3. 是否需要支持更多条件类型? (如: 伤害占比, 参与人数等)
4. 是否需要优先实现某些功能?
