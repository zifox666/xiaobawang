const CONDITION_TYPES = [
    { label: '实体条件', value: 'entity', desc: '角色/军团/联盟/舰船/星系/区域/星座/建筑' },
    { label: '标签过滤', value: 'label', desc: '按位置/时区/战斗标签筛选' },
    { label: '价值范围', value: 'value', desc: '按击杀价值ISK筛选' }
];

const ENTITY_TYPES = [
    { label: '角色', value: 'character' },
    { label: '军团', value: 'corporation' },
    { label: '联盟', value: 'alliance' },
    { label: '舰船', value: 'ship' },
    { label: '星系', value: 'system' },
    { label: '区域', value: 'region' },
    { label: '星座', value: 'constellation' }
];

const ENTITY_ROLES = [
    { label: '受害者', value: 'victim' },
    { label: '最后一击', value: 'final_blow' },
    { label: '任意攻击者', value: 'any_attacker' }
];

const SHIP_ROLES = [
    { label: '受害舰船', value: 'victim_ship' },
    { label: '最后一击舰船', value: 'final_blow_ship' }
];

// 前端默认模板
const DEFAULT_TEMPLATES = {};
