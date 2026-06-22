"""
建筑通知类别定义及 ESI 通知分类

通知类别:
- structure: 建筑状态/攻击/燃料等
- moonmining: 月矿开采相关
- sovereignty: 主权相关
- tower: POS 塔相关
- skyhook: Skyhook 相关
"""

# ── 建筑大类到 ESI type 的映射 ───────────────────────────────
NOTIFICATION_CATEGORIES: dict[str, list[str]] = {
    "structure": [
        "StructureAnchoring",
        "StructureDestroyed",
        "StructureFuelAlert",
        "StructureImpendingAbandonmentAssetsAtRisk",
        "StructureItemsDelivered",
        "StructureItemsMovedToSafety",
        "StructureLostArmor",
        "StructureLostShields",
        "StructureLowReagentsAlert",
        "StructureNoReagentsAlert",
        "StructureOnline",
        "StructurePaintPurchased",
        "StructureServicesOffline",
        "StructureUnanchoring",
        "StructureUnderAttack",
        "StructureWentHighPower",
        "StructureWentLowPower",
        "StructuresCourierContractChanged",
        "StructuresJobsCancelled",
        "StructuresJobsPaused",
        "StructuresReinforcementChanged",
        "CorpStructLostMsg",
        "AllAnchoringMsg",
        "AllMaintenanceBillMsg",
        "AllStrucInvulnerableMsg",
        "AllStructVulnerableMsg",
        "OwnershipTransferred",
    ],
    "moonmining": [
        "MoonminingAutomaticFracture",
        "MoonminingExtractionCancelled",
        "MoonminingExtractionFinished",
        "MoonminingExtractionStarted",
        "MoonminingLaserFired",
    ],
    "sovereignty": [
        "SovAllClaimAquiredMsg",
        "SovAllClaimLostMsg",
        "SovCommandNodeEventStarted",
        "SovCorpBillLateMsg",
        "SovCorpClaimFailMsg",
        "SovDisruptorMsg",
        "SovStationEnteredFreeport",
        "SovStructureDestroyed",
        "SovStructureReinforced",
        "SovStructureSelfDestructCancel",
        "SovStructureSelfDestructFinished",
        "SovStructureSelfDestructRequested",
        "SovereigntyIHDamageMsg",
        "SovereigntySBUDamageMsg",
        "SovereigntyTCUDamageMsg",
        "EntosisCaptureStarted",
        "IHubDestroyedByBillFailure",
        "InfrastructureHubBillAboutToExpire",
    ],
    "tower": [
        "TowerAlertMsg",
        "TowerResourceAlertMsg",
    ],
    "skyhook": [
        "SkyhookDeployed",
        "SkyhookDestroyed",
        "SkyhookLostShields",
        "SkyhookOnline",
        "SkyhookUnderAttack",
    ],
}

# 反向映射: ESI type -> category
TYPE_TO_CATEGORY: dict[str, str] = {}
for _cat, _types in NOTIFICATION_CATEGORIES.items():
    for _t in _types:
        TYPE_TO_CATEGORY[_t] = _cat

# 所有受关注的通知 type 集合
ALL_STRUCTURE_TYPES: set[str] = set(TYPE_TO_CATEGORY.keys())

# 分类友好名称
CATEGORY_LABELS: dict[str, str] = {
    "structure": "建筑状态",
    "moonmining": "月矿开采",
    "sovereignty": "主权设施",
    "tower": "POS 控制塔",
    "skyhook": "Skyhook",
}

# 通知类型友好名称 (用于推送消息)
TYPE_LABELS: dict[str, str] = {
    "StructureUnderAttack": "🔴 建筑遭到攻击",
    "StructureLostShields": "🟠 建筑护盾消失",
    "StructureLostArmor": "🟠 建筑装甲消失",
    "StructureDestroyed": "💀 建筑被摧毁",
    "StructureFuelAlert": "⛽ 建筑燃料警告",
    "StructureLowReagentsAlert": "⚠️ 建筑试剂不足",
    "StructureNoReagentsAlert": "🚨 建筑试剂耗尽",
    "StructureServicesOffline": "⚠️ 建筑服务离线",
    "StructureAnchoring": "🔧 建筑锚定中",
    "StructureOnline": "✅ 建筑已上线",
    "StructureUnanchoring": "🔧 建筑解锚中",
    "StructureWentHighPower": "⬆️ 建筑进入高能模式",
    "StructureWentLowPower": "⬇️ 建筑进入低能模式",
    "StructuresReinforcementChanged": "🔄 建筑加固时间变更",
    "StructureImpendingAbandonmentAssetsAtRisk": "⚠️ 建筑即将废弃",
    "CorpStructLostMsg": "💀 军团建筑丢失",
    "MoonminingExtractionStarted": "🌙 月矿开始开采",
    "MoonminingExtractionFinished": "🌙 月矿开采完成",
    "MoonminingExtractionCancelled": "🌙 月矿开采取消",
    "MoonminingAutomaticFracture": "🌙 月矿自动裂解",
    "MoonminingLaserFired": "🌙 月矿激光发射",
    "SovStructureReinforced": "🏴 主权建筑被加固",
    "SovStructureDestroyed": "💀 主权建筑被摧毁",
    "TowerAlertMsg": "🗼 POS 警报",
    "TowerResourceAlertMsg": "🗼 POS 资源警报",
    "SkyhookUnderAttack": "🔴 Skyhook 遭到攻击",
    "SkyhookDestroyed": "💀 Skyhook 被摧毁",
    "SkyhookLostShields": "🟠 Skyhook 护盾消失",
    "SkyhookOnline": "✅ Skyhook 已上线",
    "SkyhookDeployed": "🔧 Skyhook 已部署",
    "EntosisCaptureStarted": "⚠️ 主权遭到攻击"
}


KEY_IDS: dict[str, dict] = {
    "charID": "角色名称",
    "oldOwnerCorpID": "转移的军团",
    "newOwnerCorpID": "收到的军团",
    "solarSystemID": "星系",
    "structureName": "建筑名称",
    "structureTypeID" : "建筑类型",
    "moonID": "月亮"

}


def get_type_label(notification_type: str) -> str:
    """获取通知类型的友好名称"""
    return TYPE_LABELS.get(notification_type, notification_type)
