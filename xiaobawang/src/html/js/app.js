const { createApp, ref, reactive, computed, onMounted } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;

createApp({
    setup() {
        const isLoggedIn = ref(false);
        const loginLoading = ref(false);
        const loading = ref(false);
        const saving = ref(false);
        const showCreate = ref(false);
        const showConditionSelector = ref(false);
        const editingId = ref(null);
        const searchText = ref('');
        const filterEnabled = ref(null);
        
        const form = reactive({
            token: '',
        });
        
        const user = reactive({
            sessionType: '',
            sessionId: '',
            userId: '',
            platform: '',
            bot_id: '',
        });
        
        const subs = ref([]);
        const templates = ref([]);
        const stats = reactive({
            total: 0,
            enabled: 0,
            disabled: 0
        });
        
        const subForm = reactive({
            id: null,
            name: '',
            description: '',
            platform: user.platform,
            bot_id: user.bot_id,
            min_value: 50000000,
            is_enabled: true,
            condition_groups: { logic: 'AND', conditions: [] }
        });
        
        // 格式化的推送最低阈值输入
        const minValueInput = reactive({
            original: 50000000,
            formatted: formatNumberWithComma(50000000)
        });
        const minValueHandler = createNumberInputHandler(minValueInput);
        
        const entitySearchCache = ref({});  // 缓存查询结果
        let entitySearchTimer = null;       // 防抖计时器
        
        // 积分规则和标签数据(从后端加载)
        const scoreRules = reactive({
            entity_scores: {},
            label_scores: {},
            labels: []
        });
        
        const apiUrl = `${window.location.protocol}//${window.location.host}`;

        // 从模板配置中推导最小价值，便于与后端模板兼容
        const deriveMinValueFromTemplate = (config) => {
            if (!config || !Array.isArray(config.conditions)) return null;
            const valueCond = config.conditions.find(c => c.type === 'value' && typeof c.min === 'number');
            return valueCond ? valueCond.min : null;
        };

        const loadTemplates = async () => {
            try {
                const res = await axios.get(`${apiUrl}/sub/templates`);
                const tplMap = res.data || {};
                const tplList = Object.entries(tplMap).map(([key, tpl]) => ({
                    key,
                    name: tpl.name,
                    description: tpl.description,
                    config: tpl.config
                }));
                if (tplList.length === 0) {
                    ElMessage.warning('未获取到模板,使用默认模板');
                    templates.value = Object.entries(DEFAULT_TEMPLATES || {}).map(([key, tpl]) => ({
                        key,
                        ...tpl
                    }));
                } else {
                    templates.value = tplList;
                }
            } catch (e) {
                console.error('加载模板失败:', e);
                ElMessage.warning('加载模板失败,使用默认模板');
                templates.value = Object.entries(DEFAULT_TEMPLATES || {}).map(([key, tpl]) => ({
                    key,
                    ...tpl
                }));
            }
        };
        
        const login = async () => {
            if (!form.token) {
                ElMessage.error('请填写所有字段');
                return;
            }
            
            loginLoading.value = true;
            try {
                const res = await axios.post(`${apiUrl}/auth/login`, {
                    token: form.token
                });

                const data = res.data.data;
                const t = data.token;
                axios.defaults.headers.common['Authorization'] = `${t}`;

                user.userId = data.user.create_id || data.user.user_id;
                user.sessionId = data.user.sessionId || data.user.session_id;
                user.sessionType = data.user.sessionType || data.user.session_type;
                user.platform = data.user.platform;
                user.bot_id = data.user.botId || data.user.bot_id;

                isLoggedIn.value = true;
                await loadScoreRules();  // 加载积分规则
                await loadTemplates();   // 加载模板
                await refreshList();
                ElMessage.success('登录成功');
            } catch (e) {
                ElMessage.error('登录失败: ' + (e.response?.data?.detail || e.message));
            } finally {
                loginLoading.value = false;
            }
        };
        
        const logout = () => {
            isLoggedIn.value = false;
            subs.value = [];
        };
        
        // 加载积分规则
        const loadScoreRules = async () => {
            try {
                const res = await axios.get(`${apiUrl}/sub/score-rules`);
                scoreRules.entity_scores = res.data.entity_scores;
                scoreRules.label_scores = res.data.label_scores;
                scoreRules.labels = res.data.labels;
            } catch (e) {
                console.error('加载积分规则失败:', e);
                ElMessage.warning('加载积分规则失败,使用默认配置');
            }
        };
        
        const refreshList = async () => {
            loading.value = true;
            try {
                const res = await axios.get(`${apiUrl}/sub?page=1&page_size=50`);
                subs.value = res.data.data || [];
                stats.total = res.data.total || 0;
                stats.enabled = subs.value.filter(s => s.is_enabled).length;
                stats.disabled = subs.value.filter(s => !s.is_enabled).length;
            } catch (e) {
                ElMessage.error('加载失败: ' + (e.response?.data?.detail || e.message));
            } finally {
                loading.value = false;
            }
        };
        
        const resetSubForm = () => {
            subForm.id = null;
            subForm.name = '';
            subForm.description = '';
            subForm.platform = user.platform;
            subForm.bot_id = user.bot_id;
            subForm.min_value = 50000000;
            subForm.is_enabled = true;
            subForm.condition_groups = { logic: 'AND', conditions: [] };
            editingId.value = null;
            
            // 重置格式化输入
            minValueInput.original = 50000000;
            minValueInput.formatted = formatNumberWithComma(50000000);
        };
        
        const editSub = (row) => {
            editingId.value = row.id;
            subForm.id = row.id;
            subForm.name = row.name;
            subForm.description = row.description;
            subForm.min_value = row.min_value;
            subForm.is_enabled = row.is_enabled;
            const condGroups = typeof row.condition_groups === 'string' 
                ? JSON.parse(row.condition_groups) 
                : row.condition_groups;
            subForm.condition_groups = JSON.parse(JSON.stringify(condGroups || { logic: 'AND', conditions: [] }));
            
            // 更新格式化输入
            minValueInput.original = row.min_value;
            minValueInput.formatted = formatNumberWithComma(row.min_value);
            
            showCreate.value = true;
        };
        
        const applyTemplate = (tpl) => {
            if (!tpl) {
                ElMessage.warning('模板不存在');
                return;
            }
            const config = tpl.config || { logic: 'AND', conditions: [] };
            const minFromTemplate = deriveMinValueFromTemplate(config);

            subForm.name = tpl.name || '';
            subForm.description = tpl.description || '';
            subForm.min_value = typeof config.min_value === 'number'
                ? config.min_value
                : (minFromTemplate ?? subForm.min_value);
            subForm.condition_groups = JSON.parse(JSON.stringify(config));
            
            // 更新格式化输入
            minValueInput.original = subForm.min_value;
            minValueInput.formatted = formatNumberWithComma(subForm.min_value);
            
            ElMessage.success(`已应用模板: ${tpl.name || '模板'}`);
        };
        
        const addCondition = (type) => {
            const newCond = { type };
            
            if (type === 'entity') {
                newCond.entity_type = 'alliance';
                newCond.entity_id = 0;
                newCond.entity_name = '';
                newCond.role = 'victim';  // 默认角色
                newCond.ship_role = 'victim_ship';  // 默认舰船角色
            } else if (type === 'value') {
                newCond.min = 100000000;
                newCond.max = null;
            } else if (type === 'label') {
                newCond.required_labels = [];
                newCond.excluded_labels = [];
            }
            
            subForm.condition_groups.conditions.push(newCond);
        };
        
        const delCondition = (idx) => {
            subForm.condition_groups.conditions.splice(idx, 1);
        };
        
        const saveSub = async () => {
            if (!subForm.name) {
                ElMessage.error('请输入名称');
                return;
            }
            
            if (!user.sessionId || !user.sessionType) {
                ElMessage.error('用户信息不完整,请重新登录');
                return;
            }
            
            // 保存前同步原始值到 subForm.min_value
            subForm.min_value = minValueInput.original;
            
            saving.value = true;
            try {
                const data = {
                    name: subForm.name,
                    description: subForm.description,
                    platform: user.platform || subForm.platform,
                    bot_id: user.bot_id || subForm.bot_id,
                    session_id: user.sessionId,
                    session_type: user.sessionType,
                    min_value: subForm.min_value,
                    is_enabled: subForm.is_enabled,
                    condition_groups: JSON.stringify(subForm.condition_groups)
                };
                
                if (editingId.value) {
                    await axios.put(`${apiUrl}/sub/${subForm.id}`, data);
                    ElMessage.success('更新成功');
                } else {
                    await axios.post(`${apiUrl}/sub`, data);
                    ElMessage.success('创建成功');
                }
                
                showCreate.value = false;
                resetSubForm();
                await refreshList();
            } catch (e) {
                ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message));
            } finally {
                saving.value = false;
            }
        };
        
        const delSub = async (row) => {
            try {
                await ElMessageBox.confirm(`确定删除 "${row.name}" 吗?`, '确认', { type: 'warning' });
                await axios.delete(`${apiUrl}/sub/${row.id}`);
                ElMessage.success('删除成功');
                await refreshList();
            } catch (e) {
                if (e !== 'cancel') ElMessage.error('删除失败');
            }
        };
        
        const filteredSubs = computed(() => {
            return subs.value.filter(s => {
                if (searchText.value && !s.name.includes(searchText.value)) return false;
                if (filterEnabled.value !== null && s.is_enabled !== filterEnabled.value) return false;
                return true;
            });
        });
        
        // 条件相关方法包装
        const queryEntityWrapper = (queryString, callback) => {
            entitySearchTimer = queryEntity(queryString, callback, apiUrl, entitySearchCache, entitySearchTimer);
        };
        
        const summarizeConditionWrapper = (cond) => {
            return summarizeCondition(cond, scoreRules);
        };
        
        const calcRuleMultiplierWrapper = (condGroups) => {
            return calcRuleMultiplier(condGroups, scoreRules);
        };

        onMounted(() => {
            loadTemplates();
        });
        
        return {
            isLoggedIn, loginLoading, loading, saving, showCreate, showConditionSelector, editingId,
            form, user, subs, templates, stats, subForm, searchText, filterEnabled, filteredSubs,
            CONDITION_TYPES, ENTITY_TYPES, ENTITY_ROLES, SHIP_ROLES, scoreRules,
            login, logout, refreshList, resetSubForm, editSub, applyTemplate, addCondition, delCondition, 
            getCondTypeLabel, getConditionCount, summarizeConditionWrapper, calcRuleMultiplierWrapper,
            saveSub, delSub, queryEntityWrapper, handleEntitySelect, loadScoreRules, loadTemplates,
            formatNumberWithComma, parseNumberWithComma, 
            minValueInput, minValueHandler, createNumberInputHandler
        };
    }
}).use(ElementPlus).mount('#app');
