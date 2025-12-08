"""
订阅条件积分规则表

定义所有条件类型的积分倍率（权重）
积分计算方案: 基础分数为 1，每个匹配的规则叠加倍率，最终积分 = 基础 * 倍率1 * 倍率2 * ...

注意：本文件仅定义规则，积分计算功能暂未实现
"""


class ScoreRules:
    """订阅条件积分规则定义"""

    # ============================================================================
    # Entity (实体) 类型的积分倍率
    # ============================================================================
    ENTITY_SCORE = {
        "character": 1,          # 角色
        "corporation": 5,        # 公司
        "alliance": 15,          # 联盟
        "ship": 25,              # 舰船
        "system": 15,            # 星系
        "region": 25,            # 区域
        "constellation": 20,     # 星座
    }

    # ============================================================================
    # Label (标签) 类型的积分倍率
    # ============================================================================
    LABEL_SCORE = {
        # 击杀数量标签
        "#:1": 1,
        "#:2+": 1,
        "#:5+": 1,
        "#:10+": 1,
        "#:25+": 1,
        "#:50+": 1,
        "#:100+": 1,
        "#:1000+": 1,

        # 舱室分类标签
        "cat:6": 1,              # 工业舰
        "cat:18": 1,             # 轰炸舰
        "cat:22": 1,             # 重型突击巡洋舰
        "cat:23": 1,             # 航母
        "cat:40": 1,             # 泰坦
        "cat:46": 1,             # 超级航母
        "cat:65": 1,             # 信号压制舰
        "cat:87": 1,             # 虚空舰

        # 位置标签
        "loc:highsec": 1,        # 高安
        "loc:lowsec": 1,         # 低安
        "loc:nullsec": 1,        # 零安
        "loc:w-space": 1,        # 虫洞
        "loc:abyssal": 1,        # 深渊
        "loc:drifter": 1,        # 漂泊者

        # 价值标签
        "isk:1b+": 1,            # 10亿+
        "isk:5b+": 1,            # 50亿+
        "isk:10b+": 1,           # 100亿+
        "isk:100b+": 1,          # 1000亿+
        "isk:1t+": 1,            # 1万亿+

        # 特殊标签
        "bigisk": 1,             # 大额ISK
        "extremeisk": 1,         # 极端大额ISK

        # 时区标签
        "tz:au": 1,              # 澳大利亚时区
        "tz:eu": 1,              # 欧洲时区
        "tz:ru": 1,              # 俄罗斯时区
        "tz:use": 1,             # 美国东部时区
        "tz:usw": 1,             # 美国西部时区

        # 战争标签
        "fw:amarr": 1,           # 阿玛尔方阵
        "fw:caldari": 1,         # 加达里方阵
        "fw:gallente": 1,        # 盖伦特方阵
        "fw:minmatar": 1,        # 米玛塔方阵
        "fw:amamin": 1,          # 阿玛尔-米玛塔战争
        "fw:calgal": 1,          # 加达里-盖伦特战争

        # PVP 相关标签
        "pvp": 1,                # PVP击杀
        "solo": 1,               # 单人击杀
        "awox": 1,               # 背叛击杀
        "ganked": 1,             # 被盖劫
        "atShip": 1,             # 在飞船中

        # 特殊事件标签
        "concord": 1,            # CONCORD击杀
    }

    # ============================================================================
    # Value (价值范围) 类型的积分倍率
    # ============================================================================
    # 价值范围不设置固定倍率，仅作为过滤条件

    @classmethod
    def get_entity_score(cls, entity_type: str) -> int:
        """
        获取实体类型的积分倍率
        
        Args:
            entity_type: 实体类型 (character/corporation/alliance/ship/system/region/constellation)
            
        Returns:
            积分倍率，默认返回 1
        """
        return cls.ENTITY_SCORE.get(entity_type.lower(), 1)

    @classmethod
    def get_label_score(cls, label: str) -> int:
        """
        获取标签的积分倍率
        
        Args:
            label: 标签名称
            
        Returns:
            积分倍率，默认返回 1
        """
        return cls.LABEL_SCORE.get(label, 1)

    @classmethod
    def get_all_entity_types(cls) -> list[str]:
        """获取所有实体类型"""
        return list(cls.ENTITY_SCORE.keys())

    @classmethod
    def get_all_labels(cls) -> list[str]:
        """获取所有标签"""
        return list(cls.LABEL_SCORE.keys())

    @classmethod
    def is_valid_entity_type(cls, entity_type: str) -> bool:
        """检查是否为有效的实体类型"""
        return entity_type.lower() in cls.ENTITY_SCORE

    @classmethod
    def is_valid_label(cls, label: str) -> bool:
        """检查是否为有效的标签"""
        return label in cls.LABEL_SCORE
