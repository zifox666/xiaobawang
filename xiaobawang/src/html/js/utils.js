// 工具函数集合

/**
 * 数字格式化 - 添加千分位分隔符
 * 移除所有非数字和小数点,然后添加千分位分隔符
 * @param {number|string} value 输入数值
 * @returns {string} 格式化后的字符串
 */
function formatNumberWithComma(value) {
    if (!value && value !== 0) return '';
    
    // 转换为字符串并移除所有非数字和小数点
    let num = String(value).replace(/[^\d.]/g, '');
    if (!num) return '';
    
    // 分离整数和小数部分
    let parts = num.split('.');
    let integerPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ','); // 千分位分割整数部分
    let decimalPart = parts.length > 1 ? '.' + parts[1] : '';
    
    return integerPart + decimalPart;
}

/**
 * 数字解析 - 移除千分位分隔符,返回纯数值
 * @param {string} value 包含分隔符的字符串
 * @returns {number} 解析后的数值
 */
function parseNumberWithComma(value) {
    if (!value && value !== 0) return 0;
    // 移除所有逗号
    let cleanValue = String(value).replace(/,/g, '');
    // 返回数值
    return Number(cleanValue) || 0;
}

/**
 * 创建数字输入处理器
 * 用于处理带千分位格式化的数字输入
 * @param {Object} refObj - Vue reactive 对象,包含 original(原始值) 和 formatted(格式化值)
 * @returns {Object} 包含 handleInput 和 handleBlur 方法的对象
 */
function createNumberInputHandler(refObj) {
    return {
        /**
         * 处理输入事件
         * @param {string} value - 输入的值
         */
        handleInput(value) {
            // 格式化显示值
            refObj.formatted = formatNumberWithComma(value);
            // 同时更新原始值,用于后续计算
            refObj.original = parseNumberWithComma(value);
        },
        
        /**
         * 处理失焦事件
         */
        handleBlur() {
            // 失去焦点时,再次格式化一次,确保完整性
            refObj.formatted = formatNumberWithComma(refObj.original);
        }
    };
}

/**
 * 获取条件类型标签
 */
function getCondTypeLabel(type) {
    const t = CONDITION_TYPES.find(x => x.value === type);
    return t ? t.label.split('(')[0].trim() : type;
}

/**
 * 获取条件数量
 */
function getConditionCount(condGroups) {
    if (!condGroups) return 0;
    const conds = condGroups.conditions || [];
    return conds.length;
}

/**
 * 条件摘要生成
 */
function summarizeCondition(cond, scoreRules) {
    if (!cond) return '';
    
    if (cond.type === 'entity') {
        const role = cond.role || cond.ship_role || 'victim';
        return `${cond.entity_name || '#'+cond.entity_id || '未选'} [${cond.entity_type}] (${role}) x${scoreRules.entity_scores[cond.entity_type] || 1}`;
    }
    
    if (cond.type === 'label') {
        const req = (cond.required_labels || []).join(', ') || '任意';
        const ex = (cond.excluded_labels || []).join(', ');
        return `标签 包含: ${req}${ex ? ` 排除: ${ex}` : ''}`;
    }
    
    if (cond.type === 'value') {
        const min = cond.min ? (cond.min/1e9).toFixed(2)+'亿' : '不限';
        const max = cond.max ? (cond.max/1e9).toFixed(2)+'亿' : '不限';
        return `价值 ${min} - ${max}`;
    }
    
    return '';
}

/**
 * 简单预估积分倍率
 */
function calcRuleMultiplier(condGroups, scoreRules) {
    if (!condGroups || !condGroups.conditions) return 1;
    
    let m = 0;
    for (const c of condGroups.conditions) {
        if (c.type === 'entity' && c.entity_type) {
            m += scoreRules.entity_scores[c.entity_type] || 1;
        }
        if (c.type === 'label') {
            (c.required_labels || []).forEach(l => { 
                m += (scoreRules.label_scores[l] || 1); 
            });
        }
        if (c.type === 'value') {
            m += 1;
        }
    }
    
    return m;
}

/**
 * 处理实体选择
 */
function handleEntitySelect(item, cond) {
    cond.entity_name = item.name;
    cond.entity_id = item.id;
    cond.entity_type = item.type === 'ship' ? 'ship' : item.type;
}

/**
 * Zkillboard 自动完成查询(带防抖)
 */
function queryEntity(queryString, callback, apiUrl, entitySearchCache, entitySearchTimer) {
    if (!queryString || queryString.length < 2) {
        callback([]);
        return;
    }
    
    // 清除之前的计时器
    if (entitySearchTimer) {
        clearTimeout(entitySearchTimer);
    }
    
    // 检查缓存
    if (entitySearchCache.value && entitySearchCache.value[queryString]) {
        callback(entitySearchCache.value[queryString]);
        return;
    }
    
    // 设置新的防抖计时器
    entitySearchTimer = setTimeout(async () => {
        try {
            // 调用本地代理接口而不是直接调用 zkillboard
            const res = await axios.get(`${apiUrl}/autocomplete/${encodeURIComponent(queryString)}`);
            const results = (res.data.data || []).map(item => ({
                ...item,
                value: item.name
            }));
            
            // 缓存结果
            if (entitySearchCache.value) {
                entitySearchCache.value[queryString] = results;
            }
            callback(results);
        } catch (e) {
            console.error('查询实体失败:', e);
            callback([]);
        }
    }, 300);  // 300ms 防抖延迟
    
    return entitySearchTimer;
}
