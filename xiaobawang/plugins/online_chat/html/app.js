const { createApp, ref, computed, nextTick, onMounted, onUnmounted } = Vue;

createApp({
    setup() {
        // WebSocket 连接
        const ws = ref(null);
        const wsConnected = ref(false);
        const wsConnecting = ref(false);
        
        // 用户配置
        const userConfig = ref({
            qq: '',
            nickname: '访客',
        });
        
        // 消息列表
        const messages = ref([]);
        const inputMessage = ref('');
        const messageContainer = ref(null);
        
        // 回复的目标消息
        const replyingTo = ref(null);
        
        // 命令提示
        const showCommandSuggestions = ref(false);
        const availableCommands = ref([]);
        const filteredCommands = computed(() => {
            if (!inputMessage.value.startsWith('/')) {
                return availableCommands.value;
            }
            const search = inputMessage.value.toLowerCase();
            return availableCommands.value.filter(cmd => 
                cmd.cmd.toLowerCase().includes(search)
            );
        });
        
        // 浏览器通知
        const notificationPermission = ref(Notification.permission);
        const isWindowFocused = ref(true);
        
        // 请求通知权限
        const requestNotificationPermission = () => {
            if ('Notification' in window && Notification.permission === 'default') {
                Notification.requestPermission().then(permission => {
                    notificationPermission.value = permission;
                    console.log('通知权限:', permission);
                });
            }
        };
        
        // 发送浏览器通知
        const sendNotification = (title, body, icon) => {
            if ('Notification' in window && Notification.permission === 'granted' && !isWindowFocused.value) {
                const notification = new Notification(title, {
                    body: body,
                    icon: icon || '/favicon.ico',
                    badge: icon || '/favicon.ico',
                    tag: 'xiaobawang-message',
                    requireInteraction: false
                });
                
                // 点击通知时聚焦窗口
                notification.onclick = () => {
                    window.focus();
                    notification.close();
                };
                
                // 5秒后自动关闭
                setTimeout(() => notification.close(), 5000);
            }
        };
        
        // 监听窗口焦点状态
        const handleWindowFocus = () => {
            isWindowFocused.value = true;
        };
        
        const handleWindowBlur = () => {
            isWindowFocused.value = false;
        };
        
        // 消息 ID 计数器
        let messageIdCounter = 1;
        let segmentIdCounter = 1;
        
        // 快捷命令
        const quickCommands = ref([
            '/help',
            '/价格查询',
            '/zkb',
            '/虫洞',
        ]);
        
        // 连接状态
        const connectionStatusClass = computed(() => {
            if (wsConnected.value) return 'status-connected';
            if (wsConnecting.value) return 'status-connecting';
            return 'status-disconnected';
        });
        
        const connectionStatusText = computed(() => {
            if (wsConnected.value) return '已连接';
            if (wsConnecting.value) return '连接中...';
            return '未连接';
        });
        
        // 处理图片 URL
        const getImageUrl = (file) => {
            if (!file) return '';
            // 如果是 base64:// 开头,转换为标准 data URI
            if (file.startsWith('base64://')) {
                return 'data:image/jpeg;base64,' + file.substring(9);
            }
            // 其他情况直接返回
            return file;
        };
        
        // 从 Cookie 加载配置
        const loadConfig = () => {
            const savedQQ = getCookie('user_qq');
            const savedNickname = getCookie('user_nickname');
            
            if (savedQQ) userConfig.value.qq = savedQQ;
            if (savedNickname) userConfig.value.nickname = savedNickname;
        };
        
        // 保存配置到 Cookie
        const saveConfig = () => {
            setCookie('user_qq', userConfig.value.qq, 365);
            setCookie('user_nickname', userConfig.value.nickname, 365);
        };
        
        // Cookie 操作
        const getCookie = (name) => {
            const value = `; ${document.cookie}`;
            const parts = value.split(`; ${name}=`);
            if (parts.length === 2) return parts.pop().split(';').shift();
            return '';
        };
        
        const setCookie = (name, value, days) => {
            const expires = new Date(Date.now() + days * 864e5).toUTCString();
            document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/`;
        };
        
        // 生成随机 QQ 号
        const generateRandomQQ = () => {
            return Math.floor(100000000 + Math.random() * 900000000).toString();
        };
        
        // 获取 QQ 头像
        const getQQAvatar = (qq) => {
            return `https://q1.qlogo.cn/g?b=qq&nk=${qq}&s=640`;
        };
        
        // 获取可用命令列表
        const fetchCommands = async () => {
            try {
                const response = await fetch('/chat/get/cmds');
                if (response.ok) {
                    availableCommands.value = await response.json();
                    console.log('获取命令列表:', availableCommands.value);
                }
            } catch (error) {
                console.error('获取命令列表失败:', error);
            }
        };
        
        // 选择命令
        const selectCommand = (cmd) => {
            inputMessage.value = cmd.cmd + ' ';
            showCommandSuggestions.value = false;
            // 聚焦输入框
            nextTick(() => {
                const input = document.querySelector('.el-input__inner');
                if (input) input.focus();
            });
        };
        
        // 处理输入框聚焦
        const handleInputFocus = () => {
            if (availableCommands.value.length > 0) {
                showCommandSuggestions.value = true;
            }
        };
        
        // 处理输入框失焦
        const handleInputBlur = () => {
            // 延迟隐藏,以便点击命令时能响应
            setTimeout(() => {
                showCommandSuggestions.value = false;
            }, 200);
        };
        
        // 连接 WebSocket
        const connect = () => {
            if (wsConnecting.value || wsConnected.value) return;
            
            // 如果没有输入 QQ 号,生成随机的
            if (!userConfig.value.qq) {
                userConfig.value.qq = generateRandomQQ();
            }
            
            // 保存配置
            saveConfig();
            
            wsConnecting.value = true;
            
            // 构建 WebSocket URL - 连接到我们自己的 WebSocket 端点
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/chat/ws`;
            
            try {
                ws.value = new WebSocket(wsUrl);
                
                ws.value.onopen = () => {
                    wsConnected.value = true;
                    wsConnecting.value = false;
                    ElementPlus.ElMessage.success('连接成功!');
                    
                    // 请求通知权限
                    requestNotificationPermission();
                    
                    // 添加系统消息
                    addSystemMessage('已连接到聊天室,开始聊天吧!');
                };
                
                ws.value.onmessage = (event) => {
                    handleWebSocketMessage(event.data);
                };
                
                ws.value.onerror = (error) => {
                    console.error('WebSocket 错误:', error);
                    ElementPlus.ElMessage.error('连接出错');
                    wsConnecting.value = false;
                };
                
                ws.value.onclose = () => {
                    wsConnected.value = false;
                    wsConnecting.value = false;
                    ElementPlus.ElMessage.warning('连接已断开');
                    addSystemMessage('连接已断开');
                };
            } catch (error) {
                console.error('连接失败:', error);
                ElementPlus.ElMessage.error('连接失败');
                wsConnecting.value = false;
            }
        };
        
        // 断开连接
        const disconnect = () => {
            if (ws.value) {
                ws.value.close();
                ws.value = null;
            }
        };
        
        // 处理 WebSocket 消息
        const handleWebSocketMessage = (data) => {
            try {
                const message = JSON.parse(data);
                console.log('收到消息:', message);
                
                // 处理机器人发送的消息
                if (message.action === 'send_msg') {
                    const messageId = addBotMessage(message.params.message);
                    
                    // 立即返回响应
                    if (message.echo) {
                        const response = {
                            status: 'ok',
                            retcode: 0,
                            data: {
                                message_id: messageId
                            },
                            echo: message.echo
                        };
                        sendToWebSocket(response);
                        console.log('发送 send_msg 响应:', response);
                    }
                }
                // 处理 get_msg API 请求
                else if (message.action === 'get_msg') {
                    handleGetMsg(message.params, message.echo);
                }
            } catch (error) {
                console.error('解析消息失败:', error, data);
            }
        };
        
        // 发送消息到 WebSocket
        const sendToWebSocket = (data) => {
            if (ws.value && ws.value.readyState === WebSocket.OPEN) {
                ws.value.send(JSON.stringify(data));
                console.log('发送消息:', data);
            }
        };
        
        // 发送消息
        const sendMessage = () => {
            if (!inputMessage.value.trim() || !wsConnected.value) return;
            
            const messageText = inputMessage.value.trim();
            
            // 使用时间戳作为消息ID,确保唯一性
            const uniqueMessageId = Date.now();
            
            // 添加用户消息到界面,传入消息ID
            addUserMessage(messageText, uniqueMessageId);
            
            // 构建消息段数组
            const messageSegments = [];
            
            // 如果有回复,添加回复消息段
            if (replyingTo.value) {
                messageSegments.push({
                    type: 'reply',
                    data: {
                        id: String(replyingTo.value.messageId)
                    }
                });
            }
            
            // 添加文本消息段
            messageSegments.push({
                type: 'text',
                data: {
                    text: messageText
                }
            });
            
            // 构建 OneBot v11 消息格式
            const message = {
                time: Math.floor(Date.now() / 1000),
                self_id: parseInt(userConfig.value.qq),
                post_type: 'message',
                message_type: 'private',
                sub_type: 'friend',
                user_id: parseInt(userConfig.value.qq),
                message_id: uniqueMessageId,
                message: messageSegments,
                raw_message: messageText,
                font: 0,
                sender: {
                    user_id: parseInt(userConfig.value.qq),
                    nickname: userConfig.value.nickname,
                    sex: 'unknown',
                    age: 0
                }
            };
            
            // 发送到 WebSocket
            sendToWebSocket(message);
            
            // 清空输入框和回复状态
            inputMessage.value = '';
            replyingTo.value = null;
        };
        
        // 添加用户消息
        const addUserMessage = (text, messageId = null) => {
            const textSegment = {
                id: segmentIdCounter++,
                type: 'text',
                data: { text }
            };
            
            const newMessage = {
                id: messageIdCounter++,
                messageId: messageId || Date.now(),
                timestamp: Math.floor(Date.now() / 1000),  // 添加 Unix 时间戳
                isBot: false,
                nickname: userConfig.value.nickname,
                avatar: getQQAvatar(userConfig.value.qq),
                time: formatTime(new Date()),
                segments: [textSegment],
                replyTo: replyingTo.value ? {
                    nickname: replyingTo.value.nickname,
                    content: replyingTo.value.segments
                        .filter(s => s.type === 'text')
                        .map(s => s.data.text)
                        .join('') || '[消息]'
                } : null
            };
            
            messages.value.push(newMessage);
            scrollToBottom();
        };
        
        // 添加机器人消息
        const addBotMessage = (message) => {
            // 解析消息内容
            console.log('收到机器人消息:', message);
            const segments = parseMessage(message);
            console.log('解析后的消息段:', segments);
            
            // 检查是否有回复消息段
            let replyTo = null;
            const replySegment = segments.find(seg => seg.type === 'reply');
            if (replySegment) {
                const replyId = parseInt(replySegment.data.id);
                const repliedMsg = messages.value.find(m => m.messageId === replyId);
                if (repliedMsg) {
                    replyTo = {
                        nickname: repliedMsg.nickname,
                        content: repliedMsg.segments
                            .filter(s => s.type === 'text')
                            .map(s => s.data.text)
                            .join('') || '[消息]'
                    };
                }
            }
            
            const newMessage = {
                id: messageIdCounter++,
                messageId: Date.now(), // 用于回复时引用
                timestamp: Math.floor(Date.now() / 1000),  // 添加 Unix 时间戳
                isBot: true,
                nickname: '小霸王',
                avatar: getQQAvatar('2382766384'),
                time: formatTime(new Date()),
                segments: segments.filter(s => s.type !== 'reply'), // 过滤掉 reply 段
                replyTo
            };
            
            messages.value.push(newMessage);
            scrollToBottom();
            
            // 发送浏览器通知
            const textContent = newMessage.segments
                .filter(s => s.type === 'text')
                .map(s => s.data.text)
                .join('');
            
            if (textContent) {
                sendNotification(
                    '小霸王机器人',
                    textContent.length > 50 ? textContent.substring(0, 50) + '...' : textContent,
                    getQQAvatar('2382766384')
                );
            } else if (newMessage.segments.some(s => s.type === 'image')) {
                sendNotification(
                    '小霸王机器人',
                    '[图片]',
                    getQQAvatar('2382766384')
                );
            }
            
            // 返回消息 ID
            return newMessage.messageId;
        };
        
        // 添加系统消息
        const addSystemMessage = (text) => {
            messages.value.push({
                id: messageIdCounter++,
                messageId: Date.now(),
                timestamp: Math.floor(Date.now() / 1000),
                isBot: true,
                nickname: '系统',
                avatar: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="%23409eff"/><text x="50" y="50" text-anchor="middle" dy=".3em" fill="white" font-size="40">系统</text></svg>',
                time: formatTime(new Date()),
                segments: [{
                    id: segmentIdCounter++,
                    type: 'text',
                    data: { text }
                }]
            });
            scrollToBottom();
        };
        
        // 解析消息内容
        const parseMessage = (message) => {
            if (typeof message === 'string') {
                return [{
                    id: segmentIdCounter++,
                    type: 'text',
                    data: { text: message }
                }];
            }
            
            if (Array.isArray(message)) {
                return message.map(seg => {
                    const newSeg = {
                        id: segmentIdCounter++,
                        type: seg.type,
                        data: { ...seg.data }
                    };
                    
                    // 处理图片 URL
                    if (newSeg.type === 'image' && newSeg.data && newSeg.data.file) {
                        const file = newSeg.data.file;
                        // 如果是 base64:// 开头,转换为标准 data URI
                        if (file.startsWith('base64://')) {
                            newSeg.data.file = 'data:image/jpeg;base64,' + file.substring(9);
                        }
                        // 如果已经是 data: 开头,保持不变
                        // 如果是 http:// 或 https://,保持不变
                    }
                    
                    return newSeg;
                });
            }
            
            return [{
                id: segmentIdCounter++,
                type: 'text',
                data: { text: String(message) }
            }];
        };
        
        // 处理图片选择
        const handleImageSelect = (file) => {
            if (!wsConnected.value) return;
            
            const reader = new FileReader();
            reader.onload = (e) => {
                const base64 = e.target.result;
                
                // 添加图片消息到界面
                messages.value.push({
                    id: messageIdCounter++,
                    messageId: Date.now(),
                    timestamp: Math.floor(Date.now() / 1000),
                    isBot: false,
                    nickname: userConfig.value.nickname,
                    avatar: getQQAvatar(userConfig.value.qq),
                    time: formatTime(new Date()),
                    segments: [{
                        id: segmentIdCounter++,
                        type: 'image',
                        data: { file: base64 }
                    }]
                });
                
                // 使用时间戳作为消息ID,确保唯一性
                const uniqueMessageId = Date.now();
                
                // 构建消息发送到 WebSocket
                const message = {
                    time: Math.floor(Date.now() / 1000),
                    self_id: parseInt(userConfig.value.qq),
                    post_type: 'message',
                    message_type: 'private',
                    sub_type: 'friend',
                    user_id: parseInt(userConfig.value.qq),
                    message_id: uniqueMessageId,
                    message: [{
                        type: 'image',
                        data: {
                            file: base64
                        }
                    }],
                    raw_message: '[图片]',
                    font: 0,
                    sender: {
                        user_id: parseInt(userConfig.value.qq),
                        nickname: userConfig.value.nickname,
                        sex: 'unknown',
                        age: 0
                    }
                };
                
                sendToWebSocket(message);
                scrollToBottom();
            };
            reader.readAsDataURL(file.raw);
        };
        
        // 格式化时间
        const formatTime = (date) => {
            const hours = String(date.getHours()).padStart(2, '0');
            const minutes = String(date.getMinutes()).padStart(2, '0');
            return `${hours}:${minutes}`;
        };
        
        // 回复消息
        const replyToMessage = (message) => {
            replyingTo.value = message;
            // 聚焦输入框
            nextTick(() => {
                const input = document.querySelector('.el-input__inner');
                if (input) input.focus();
            });
        };
        
        // 处理 get_msg API 请求
        const handleGetMsg = (params, echo) => {
            const messageId = parseInt(params.message_id);
            const msg = messages.value.find(m => m.messageId === messageId);
            
            if (msg) {
                // 构造符合 OneBot v11 格式的消息对象
                const response = {
                    status: 'ok',
                    retcode: 0,
                    data: {
                        time: msg.timestamp || Math.floor(Date.now() / 1000),  // 使用 timestamp 字段
                        message_type: msg.isBot ? 'private' : 'private',
                        message_id: msg.messageId,
                        real_id: msg.messageId,
                        sender: {
                            user_id: msg.isBot ? 25677921 : parseInt(userConfig.value.qq),
                            nickname: msg.nickname,
                            sex: 'unknown',
                            age: 0
                        },
                        message: msg.segments.map(seg => ({
                            type: seg.type,
                            data: seg.data
                        }))
                    },
                    echo: echo
                };
                sendToWebSocket(response);
                console.log('返回消息详情:', response);
            } else {
                // 消息不存在
                const response = {
                    status: 'failed',
                    retcode: 1404,
                    data: {
                        message: '消息不存在'
                    },
                    echo: echo
                };
                sendToWebSocket(response);
                console.log('消息不存在:', messageId);
            }
        };
        
        // 滚动到底部
        const scrollToBottom = () => {
            nextTick(() => {
                if (messageContainer.value) {
                    messageContainer.value.scrollTop = messageContainer.value.scrollHeight;
                }
            });
        };
        
        // 生命周期
        onMounted(() => {
            loadConfig();
            fetchCommands();
            
            // 监听窗口焦点状态
            window.addEventListener('focus', handleWindowFocus);
            window.addEventListener('blur', handleWindowBlur);
        });
        
        onUnmounted(() => {
            disconnect();
            
            // 移除焦点监听
            window.removeEventListener('focus', handleWindowFocus);
            window.removeEventListener('blur', handleWindowBlur);
        });
        
        return {
            ws,
            wsConnected,
            wsConnecting,
            userConfig,
            messages,
            inputMessage,
            messageContainer,
            quickCommands,
            connectionStatusClass,
            connectionStatusText,
            getImageUrl,
            replyingTo,
            showCommandSuggestions,
            availableCommands,
            filteredCommands,
            connect,
            disconnect,
            sendMessage,
            handleImageSelect,
            replyToMessage,
            selectCommand,
            handleInputFocus,
            handleInputBlur,
        };
    }
}).use(ElementPlus).mount('#app');
