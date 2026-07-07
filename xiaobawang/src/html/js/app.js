const { createApp, ref, reactive, computed, onMounted, watch } = Vue;
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
        
        // ── 验证码登录状态 ─────────────────────────────────────────
        const verifyCode = ref('');
        const verifyCodeExpiry = ref(300);
        const verifyCodeStatus = ref('loading'); // loading | pending | expired
        let _pollTimer = null;
        let _countdownTimer = null;

        const _stopPolling = () => { if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; } };
        const _stopCountdown = () => { if (_countdownTimer) { clearInterval(_countdownTimer); _countdownTimer = null; } };

        const fetchVerifyCode = async () => {
            _stopPolling();
            _stopCountdown();
            verifyCodeStatus.value = 'loading';
            try {
                const res = await axios.get(`${apiUrl}/auth/verify-code`);
                verifyCode.value = res.data.code;
                verifyCodeExpiry.value = res.data.expires_in;
                verifyCodeStatus.value = 'pending';

                // 倒计时
                _countdownTimer = setInterval(() => {
                    verifyCodeExpiry.value--;
                    if (verifyCodeExpiry.value <= 0) {
                        _stopCountdown();
                        _stopPolling();
                        verifyCodeStatus.value = 'expired';
                    }
                }, 1000);

                // 轮询状态
                _pollTimer = setInterval(async () => {
                    try {
                        const r = await axios.get(`${apiUrl}/auth/verify-code/${verifyCode.value}/status`);
                        if (r.data.status === 'done') {
                            _stopPolling();
                            _stopCountdown();
                            const { token, user: u } = r.data;
                            axios.defaults.headers.common['Authorization'] = token;
                            user.userId = u.qq;
                            user.sessionId = u.session_id;
                            user.sessionType = u.session_type;
                            user.platform = u.platform;
                            user.bot_id = u.bot_id;
                            isLoggedIn.value = true;
                            await loadScoreRules();
                            await loadTemplates();
                            await refreshList();
                            await loadBalance();
                            await loadActiveTabData();
                            ElMessage.success('验证成功，已自动登录');
                        } else if (r.data.status === 'expired') {
                            _stopPolling();
                            _stopCountdown();
                            verifyCodeStatus.value = 'expired';
                        }
                    } catch (_) { /* ignore poll errors */ }
                }, 2000);
            } catch (e) {
                ElMessage.error('获取验证码失败: ' + e.message);
                verifyCodeStatus.value = 'expired';
            }
        };

        const refreshVerifyCode = () => fetchVerifyCode();

        const copyVerifyCode = () => {
            navigator.clipboard.writeText(`/verify ${verifyCode.value}`).then(
                () => ElMessage.success('已复制'),
                () => ElMessage.warning('复制失败，请手动复制')
            );
        };
        
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

        // ── 聚合页 Tab + 积分余额 ───────────────────────────────────
        const activeTab = ref('killmail');
        const balance = reactive({ value: 0, loading: false });

        // ── structure / eve_status / 流水 ──────────────────────────
        const structSubs = ref([]);
        const structCharacters = ref([]);
        const structCategories = ref([]);
        const showStructCreate = ref(false);
        const structForm = reactive({ character_id: null, character_name: '', categories: ['structure'] });
        const eveStatusSub = reactive({ exists: false, is_enabled: false, loading: false });
        const transactions = ref([]);
        const txPage = ref(1);
        const txTotal = ref(0);
        const rechargeForm = reactive({ amount: 1000, description: '管理员充值' });
        const isAdmin = ref(false);
        const structLoading = ref(false);
        const structAuthLoading = ref(false);
        const txLoading = ref(false);
        let structAuthPopup = null;

        // ── 充值（ESI 钱包） ────────────────────────────────────
        const paymentSetting = reactive({ wallet_character_name: '', wallet_character_id: null, isk_per_1b: 500 });
        const rechargeOrder = reactive({ code: '', isk_amount: 0, credit_amount: 0, status: '', wallet_character_name: '' });
        const rechargeIsk = ref(1e9);
        const rechargeCreating = ref(false);
        const rechargeVerifying = ref(false);
        
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
        
        const logout = () => {
            isLoggedIn.value = false;
            subs.value = [];
            delete axios.defaults.headers.common['Authorization'];
            fetchVerifyCode();
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

        // 加载积分余额
        const loadBalance = async () => {
            balance.loading = true;
            try {
                const res = await axios.get(`${apiUrl}/api/credit/balance`);
                balance.value = res.data?.data?.balance ?? 0;
            } catch (e) {
                console.error('加载余额失败:', e);
                balance.value = 0;
            } finally {
                balance.loading = false;
            }
        };

        // ── structure 订阅 ──────────────────────────────────────
        const loadStructSubs = async () => {
            structLoading.value = true;
            try {
                const res = await axios.get(`${apiUrl}/api/subscriptions/structure`);
                structSubs.value = res.data?.data || [];
            } catch (e) { console.error('加载建筑订阅失败:', e); }
            finally { structLoading.value = false; }
        };

        const loadStructCharacters = async () => {
            try {
                const res = await axios.get(`${apiUrl}/api/subscriptions/structure/characters`);
                structCharacters.value = res.data?.data || [];
            } catch (e) { console.error('加载角色失败:', e); }
        };

        const loadStructCategories = async () => {
            try {
                const res = await axios.get(`${apiUrl}/api/subscriptions/structure/categories`);
                structCategories.value = res.data?.data || [];
            } catch (e) { console.error('加载类别失败:', e); }
        };

        const startStructOAuth = async () => {
            structAuthLoading.value = true;
            try {
                const res = await axios.post(`${apiUrl}/api/subscriptions/structure/auth/url`);
                const authUrl = res.data?.data?.auth_url;
                if (!authUrl) {
                    ElMessage.error('创建授权链接失败');
                    return;
                }
                structAuthPopup = window.open(authUrl, 'xbw_structure_oauth', 'width=720,height=820');
                if (!structAuthPopup) {
                    ElMessage.warning('浏览器拦截了弹窗，请允许弹窗后重试');
                    return;
                }
                ElMessage.info('请在弹出的 EVE 登录窗口完成授权');
            } catch (e) {
                ElMessage.error('创建授权链接失败: ' + (e.response?.data?.detail || e.message));
            } finally {
                structAuthLoading.value = false;
            }
        };

        const handleStructOAuthMessage = async (event) => {
            if (event.origin !== window.location.origin) return;
            const payload = event.data || {};
            if (payload.type !== 'structure-oauth-complete') return;
            if (payload.success) {
                ElMessage.success(`EVE 角色授权成功: ${payload.character_name || payload.character_id || ''}`);
                await loadStructCharacters();
                if (payload.character_id) {
                    structForm.character_id = Number(payload.character_id);
                }
                showStructCreate.value = true;
            } else {
                ElMessage.error('EVE 授权失败: ' + (payload.error || '未知错误'));
            }
        };

        const saveStructSub = async () => {
            if (!structForm.character_id) { ElMessage.error('请选择 EVE 角色'); return; }
            if (!structForm.categories.length) { ElMessage.error('请选择通知类别'); return; }
            const char = structCharacters.value.find(c => c.character_id === structForm.character_id);
            try {
                await axios.post(`${apiUrl}/api/subscriptions/structure`, {
                    character_id: structForm.character_id,
                    character_name: char?.character_name || '',
                    categories: structForm.categories,
                });
                ElMessage.success('创建成功');
                showStructCreate.value = false;
                structForm.categories = ['structure'];
                await loadStructSubs();
            } catch (e) {
                ElMessage.error('创建失败: ' + (e.response?.data?.detail || e.message));
            }
        };

        const toggleStructSub = async (row) => {
            try {
                await axios.put(`${apiUrl}/api/subscriptions/structure/${row.id}`, { is_enabled: !row.is_enabled });
                row.is_enabled = !row.is_enabled;
            } catch (e) { ElMessage.error('更新失败'); }
        };

        const delStructSub = async (row) => {
            try {
                await ElMessageBox.confirm('确定删除该角色的建筑订阅?', '确认', { type: 'warning' });
                await axios.delete(`${apiUrl}/api/subscriptions/structure/${row.id}`);
                ElMessage.success('已删除');
                await loadStructSubs();
            } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败'); }
        };

        // ── eve_status ──────────────────────────────────────────
        const loadEveStatus = async () => {
            eveStatusSub.loading = true;
            try {
                const res = await axios.get(`${apiUrl}/api/subscriptions/eve_status`);
                const d = res.data?.data || {};
                eveStatusSub.exists = d.exists || false;
                eveStatusSub.is_enabled = d.is_enabled || false;
            } catch (e) { console.error('加载状态订阅失败:', e); }
            finally { eveStatusSub.loading = false; }
        };

        const toggleEveStatus = async (val) => {
            try {
                await axios.put(`${apiUrl}/api/subscriptions/eve_status`, { is_enabled: val });
                eveStatusSub.is_enabled = val;
                eveStatusSub.exists = true;
                ElMessage.success(val ? '已启用服务器状态推送' : '已禁用');
            } catch (e) { ElMessage.error('操作失败'); }
        };

        // ── 流水 + 充值 ─────────────────────────────────────────
        const loadTransactions = async () => {
            txLoading.value = true;
            try {
                const res = await axios.get(`${apiUrl}/api/credit/transactions`, { params: { page: txPage.value, page_size: 20 } });
                const d = res.data?.data || {};
                transactions.value = d.items || [];
                txTotal.value = d.total || 0;
            } catch (e) { console.error('加载流水失败:', e); }
            finally { txLoading.value = false; }
        };

        const doRecharge = async () => {
            if (rechargeForm.amount <= 0) { ElMessage.error('金额需大于 0'); return; }
            try {
                await axios.post(`${apiUrl}/api/credit/recharge`, {
                    amount: rechargeForm.amount,
                    description: rechargeForm.description,
                });
                ElMessage.success('充值成功');
                await loadBalance();
                await loadTransactions();
            } catch (e) {
                ElMessage.error('充值失败: ' + (e.response?.data?.detail || e.message));
            }
        };

        // ── 充值（ESI 钱包） ────────────────────────────────────
        const loadPaymentSetting = async () => {
            try {
                const res = await axios.get(`${apiUrl}/api/payment/setting`);
                Object.assign(paymentSetting, res.data?.data || {});
            } catch (e) { console.error('加载支付配置失败:', e); }
        };

        const createRechargeOrder = async () => {
            rechargeCreating.value = true;
            try {
                const res = await axios.post(`${apiUrl}/api/payment/order`, { isk_amount: rechargeIsk.value });
                const d = res.data?.data || {};
                rechargeOrder.code = d.payment_code;
                rechargeOrder.isk_amount = d.isk_amount;
                rechargeOrder.credit_amount = d.credit_amount;
                rechargeOrder.status = d.status;
                rechargeOrder.wallet_character_name = d.wallet_character_name || paymentSetting.wallet_character_name;
                ElMessage.success('订单已创建，请按指引转账');
            } catch (e) {
                ElMessage.error('创建订单失败: ' + (e.response?.data?.detail || e.message));
            } finally { rechargeCreating.value = false; }
        };

        const verifyRecharge = async () => {
            if (!rechargeOrder.code) return;
            rechargeVerifying.value = true;
            try {
                const res = await axios.post(`${apiUrl}/api/payment/order/${rechargeOrder.code}/verify`);
                const d = res.data?.data || {};
                if (res.data?.success) {
                    ElMessage.success(`充值成功 +${d.credit_amount} 积分`);
                    rechargeOrder.status = 'paid';
                    await loadBalance();
                } else {
                    ElMessage.warning(d.reason || '未到账，请稍后重试');
                }
            } catch (e) {
                ElMessage.error('核销失败: ' + (e.response?.data?.detail || e.message));
            } finally { rechargeVerifying.value = false; }
        };

        const copyText = (text, label = '内容') => {
            navigator.clipboard.writeText(text).then(
                () => ElMessage.success(`已复制${label}`),
                () => ElMessage.warning('复制失败，请手动复制')
            );
        };

        const loadActiveTabData = async () => {
            if (!isLoggedIn.value) return;
            if (activeTab.value === 'structure') {
                await Promise.all([loadStructSubs(), loadStructCharacters(), loadStructCategories()]);
            } else if (activeTab.value === 'eve_status') {
                await loadEveStatus();
            } else if (activeTab.value === 'balance') {
                await Promise.all([loadTransactions(), loadBalance()]);
            } else if (activeTab.value === 'recharge') {
                await loadPaymentSetting();
            }
        };

        // ── Tab 切换懒加载 ──────────────────────────────────────
        watch(activeTab, () => { loadActiveTabData(); });

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

        onMounted(async () => {
            const params = new URLSearchParams(window.location.search);
            const initialTab = params.get('tab');
            if (initialTab && ['killmail', 'structure', 'eve_status', 'balance', 'recharge'].includes(initialTab)) {
                activeTab.value = initialTab;
            }
            window.addEventListener('message', handleStructOAuthMessage);
            await fetchVerifyCode();
        });
        
        return {
            isLoggedIn, loginLoading, loading, saving, showCreate, showConditionSelector, editingId,
            user, subs, templates, stats, subForm, searchText, filterEnabled, filteredSubs, activeTab, balance,
            structSubs, structCharacters, structCategories, showStructCreate, structForm, structLoading, structAuthLoading,
            eveStatusSub, transactions, txPage, txTotal, txLoading, rechargeForm,
            paymentSetting, rechargeOrder, rechargeIsk, rechargeCreating, rechargeVerifying,
            CONDITION_TYPES, ENTITY_TYPES, ENTITY_ROLES, SHIP_ROLES, scoreRules,
            verifyCode, verifyCodeExpiry, verifyCodeStatus, fetchVerifyCode, refreshVerifyCode, copyVerifyCode,
            logout, refreshList, resetSubForm, editSub, applyTemplate, addCondition, delCondition,
            getCondTypeLabel, getConditionCount, summarizeConditionWrapper, calcRuleMultiplierWrapper,
            saveSub, delSub, queryEntityWrapper, handleEntitySelect, loadScoreRules, loadTemplates, loadBalance,
            loadStructSubs, loadStructCharacters, loadStructCategories, startStructOAuth, saveStructSub, toggleStructSub, delStructSub,
            loadEveStatus, toggleEveStatus, loadTransactions, doRecharge,
            loadPaymentSetting, createRechargeOrder, verifyRecharge, copyText,
            formatNumberWithComma, parseNumberWithComma,
            minValueInput, minValueHandler, createNumberInputHandler
        };
    }
}).use(ElementPlus).mount('#app');
