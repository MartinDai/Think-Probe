let currentConversationId = null;
let conversations = {};
let isRequestLoading = false;
let currentAbortController = null;
let currentLoadingIndicator = null;
let autoScrollEnabled = true;

function scrollToBottom(force = false) {
    const messagesDiv = document.getElementById('messages');
    if (!messagesDiv) return;
    
    if (force) {
        autoScrollEnabled = true;
    }
    
    if (autoScrollEnabled) {
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
}

function scrollToTop() {
    const messagesDiv = document.getElementById('messages');
    if (messagesDiv) {
        autoScrollEnabled = false;
        messagesDiv.scrollTo({ top: 0, behavior: 'smooth' });
    }
}




function updateNewSessionUI(isEmpty) {
    const container = document.getElementById('chat-container');
    const welcome = document.getElementById('welcome-screen');
    if (isEmpty) {
        container.classList.add('new-session');
        welcome.classList.remove('hidden');
    } else {
        container.classList.remove('new-session');
        welcome.classList.add('hidden');
    }
    lucide.createIcons();
}

function getFormattedTimestamp() {
    const now = new Date();
    const pad = (num, len = 2) => String(num).padStart(len, '0');
    return pad(now.getFullYear(), 4) +
        pad(now.getMonth() + 1) +
        pad(now.getDate()) +
        pad(now.getHours()) +
        pad(now.getMinutes()) +
        pad(now.getSeconds()) +
        pad(now.getMilliseconds(), 3);
}

function newConversation() {
    currentConversationId = 'conv_' + getFormattedTimestamp();
    conversations[currentConversationId] = {
        messages: [],
        timestamp: Date.now(),
        title: '新会话'
    };
    document.getElementById('conversation-title').textContent = '新会话';
    document.getElementById('conversation-id').textContent = currentConversationId;
    document.getElementById('messages').innerHTML = '';
    updateConversationList();
    updateNewSessionUI(true);
}

async function editConversationTitle() {
    if (!currentConversationId) return;
    const currentTitle = document.getElementById('conversation-title').textContent || '新会话';
    const newTitle = prompt('请输入新的会话标题:', currentTitle);
    if (newTitle && newTitle.trim()) {
        try {
            const response = await fetch(`/api/conversations/${currentConversationId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: newTitle.trim() })
            });
            if (response.ok) {
                document.getElementById('conversation-title').textContent = newTitle.trim();
                updateConversationList();
            }
        } catch (e) {
            console.error("更新标题失败", e);
        }
    }
}

async function loadConversation(convId) {
    currentConversationId = convId;
    const messagesDiv = document.getElementById('messages');
    messagesDiv.innerHTML = '<div style="padding: 20px; color: #666; text-align: center;">加载中...</div>';

    // 尝试从后端加载完整的带有子agent嵌套的时间轴记录
    try {
        const response = await fetch(`/api/conversations/${convId}`);
        if (response.ok) {
            const data = await response.json();
            if (data.messages) {
                if (!conversations[convId]) {
                    conversations[convId] = { timestamp: Date.now(), title: '新会话' };
                }
                conversations[convId].messages = data.messages;
            }
        }
    } catch (e) {
        console.error("加载完整会话历史记录失败", e);
    }

    const conversation = conversations[convId];
    const title = conversation?.title ||
        (conversation?.messages?.[0]?.content?.substring(0, 30) + '...' || '新会话');
    document.getElementById('conversation-title').textContent = title;
    document.getElementById('conversation-id').textContent = convId;

    messagesDiv.innerHTML = '';
    renderMessagesList(conversation?.messages || [], messagesDiv);
    updateNewSessionUI(!(conversation?.messages?.length > 0));
    updateConversationList();

    // 增加一个微小延时，确保 Markdown 和图标解析完成后的实际高度被计算
    setTimeout(() => {
        scrollToBottom(true);
    }, 50);
}


function renderMessagesList(messages, container, isSubAgent = false) {
    let lastAiToolCalls = {}; // 用于匹配工具执行和它的参数

    messages.forEach((msg, index) => {
        if (isSubAgent && index === 0 && (msg.role === 'human' || msg.role === 'user')) {
            return; // 跳过子 Agent 内部的第一条人类消息（任务已经在 Header 展示了）
        }
        if (msg.role === 'human' || msg.role === 'user') {
            addMessageComponent('user', msg.content, container);
        } else if (msg.role === 'ai' || msg.role === 'assistant') {
            const aiMsg = addMessageComponent('assistant', '', container);
            if (msg.reasoning_content) {
                const thoughtDiv = addMessageComponent('thought', msg.reasoning_content, aiMsg);
                thoughtDiv.classList.add('collapsed');
            }
            if (msg.content) {
                const contentArea = document.createElement('div');
                contentArea.className = 'content-area';
                contentArea.innerHTML = marked.parse(msg.content);
                aiMsg.appendChild(contentArea);
            }
            // 记住上一个 AI 回复中的工具调用定义，以便在接下来的 tool 消息中显示参数
            if (msg.tool_calls) {
                msg.tool_calls.forEach(tc => {
                    const id = tc.id || tc.tool_call_id;
                    lastAiToolCalls[id] = tc;
                });
            }
        } else if (msg.role === 'tool') {
            const toolCall = lastAiToolCalls[msg.tool_call_id];
            const args = toolCall ? (toolCall.args || toolCall.arguments) : null;
            const displayName = (msg.name || 'tool').replace(/^transfer_to_/, '');

            if (msg.sub_agent_messages && msg.sub_agent_messages.length > 0) {
                const { wrapper, content } = createSubAgentWrapper("执行子任务", args ? (typeof args === 'object' ? args.task : null) : null, container, false);
                if (args && !args.task) {
                    const argDiv = document.createElement('div');
                    argDiv.style.padding = '12px 20px';
                    argDiv.style.fontSize = '13px';
                    argDiv.style.borderBottom = '1px solid var(--border-color)';
                    argDiv.style.background = 'rgba(88, 166, 255, 0.03)';
                    argDiv.innerHTML = `<strong>参数:</strong> <code style="background: rgba(0,0,0,0.2); padding: 2px 4px;">${typeof args === 'string' ? args : JSON.stringify(args)}</code>`;
                    wrapper.insertBefore(argDiv, content);
                }

                // 递归渲染内部交互
                renderMessagesList(msg.sub_agent_messages, content, true);

                // 最后显示工具汇总的最终结果 (始终可见)
                if (msg.content) {
                    renderSubAgentResult(wrapper, msg.content);
                }
            } else {
                // 普通工具调用
                renderToolCall(msg, args, container);
            }
        }
    });
    lucide.createIcons();
    scrollToBottom();
}


function createSubAgentWrapper(displayName, task, container, expanded = true) {
    const wrapper = document.createElement('div');
    wrapper.className = 'sub-agent-wrapper' + (expanded ? ' expanded' : '');

    const header = document.createElement('div');
    header.className = 'sub-agent-header';
    header.innerHTML = `<div style="display: flex; align-items: center; gap: 8px;"><i data-lucide="cpu" style="width: 16px; height: 16px;"></i><span>${displayName}</span></div><i data-lucide="chevron-down" class="toggle-icon" style="width: 16px; height: 16px;"></i>`;

    const content = document.createElement('div');
    content.className = 'sub-agent-content' + (expanded ? '' : ' hidden');

    header.onclick = () => {
        content.classList.toggle('hidden');
        wrapper.classList.toggle('expanded');
    };

    wrapper.appendChild(header);
    wrapper.appendChild(content);
    container.appendChild(wrapper);

    if (task) {
        const argDiv = document.createElement('div');
        argDiv.style.padding = '12px 20px';
        argDiv.style.fontSize = '13px';
        argDiv.style.borderBottom = '1px solid var(--border-color)';
        argDiv.style.background = 'rgba(88, 166, 255, 0.03)';
        argDiv.innerHTML = `<div style="color: var(--text-primary); font-weight: 500; margin-bottom: 4px;">🚀 任务:</div><div style="color: var(--text-muted); line-height: 1.5;">${task}</div>`;
        wrapper.insertBefore(argDiv, content);
    }

    lucide.createIcons();
    return { wrapper, content };
}

function renderSubAgentResult(wrapper, content) {
    const finalResult = document.createElement('div');
    finalResult.className = 'sub-agent-result';
    finalResult.style.padding = '15px 20px';
    finalResult.style.borderTop = '1px solid var(--border-color)';
    finalResult.style.background = 'rgba(46, 160, 67, 0.05)';
    finalResult.innerHTML = `<strong style="color: #2ea043; display: flex; align-items: center; gap: 8px;"><i data-lucide="sparkle" style="width: 14px; height: 14px;"></i> 最终结果:</strong><div style="margin-top: 10px;">${marked.parse(content)}</div>`;
    wrapper.appendChild(finalResult);
    lucide.createIcons();
    scrollToBottom();
}


function renderToolCall(msg, args, container, expanded = false) {
    const displayName = (msg.name || msg.type).replace(/^transfer_to_/, '');
    const toolCallDiv = document.createElement('div');
    toolCallDiv.className = 'tool-call-container' + (expanded ? ' expanded' : '');

    const header = document.createElement('div');
    header.className = 'tool-call-header';
    header.innerHTML = `
        <div class="tool-call-title">
            <i data-lucide="wrench" style="width: 14px; height: 14px;"></i>
            <span>工具执行: ${displayName}</span>
        </div>
        <i data-lucide="chevron-down" class="toggle-icon"></i>
    `;

    const body = document.createElement('div');
    body.className = 'tool-call-body' + (expanded ? '' : ' hidden');

    header.onclick = () => {
        body.classList.toggle('hidden');
        toolCallDiv.classList.toggle('expanded');
    };

    // 参数部分
    if (args) {
        const argsSection = document.createElement('div');
        argsSection.className = 'tool-section';
        const argsStr = typeof args === 'string' ? args : JSON.stringify(args, null, 2);
        argsSection.innerHTML = `
            <div class="tool-section-label">
                <span>输入参数</span>
                <button class="copy-btn" onclick="copyToClipboard(this)">
                    <i data-lucide="copy" style="width: 12px; height: 12px;"></i> 复制
                </button>
            </div>
            <div class="tool-section-content">${argsStr}</div>
        `;
        argsSection.querySelector('.copy-btn')._copyContent = argsStr;
        body.appendChild(argsSection);
    }

    // 结果部分
    if (msg.content || msg.result) {
        const resultSection = document.createElement('div');
        resultSection.className = 'tool-section';
        const resultContent = msg.content || msg.result;
        resultSection.innerHTML = `
            <div class="tool-section-label">
                <span>执行结果</span>
                <button class="copy-btn" onclick="copyToClipboard(this)">
                    <i data-lucide="copy" style="width: 12px; height: 12px;"></i> 复制
                </button>
            </div>
            <div class="tool-section-content">${resultContent}</div>
        `;
        resultSection.querySelector('.copy-btn')._copyContent = resultContent;
        body.appendChild(resultSection);
    }

    toolCallDiv.appendChild(header);
    toolCallDiv.appendChild(body);
    container.appendChild(toolCallDiv);
    lucide.createIcons();
    scrollToBottom();
}


function copyToClipboard(btn) {
    let content = btn._copyContent;
    if (!content) return;

    navigator.clipboard.writeText(content).then(() => {
        const originalHTML = btn.innerHTML;
        btn.innerHTML = '<i data-lucide="check" style="width: 12px; height: 12px;"></i> 已复制';
        btn.classList.add('copied');
        lucide.createIcons();
        setTimeout(() => {
            btn.innerHTML = originalHTML;
            btn.classList.remove('copied');
            lucide.createIcons();
        }, 2000);
    }).catch(err => {
        console.error('复制失败: ', err);
    });
}


function addMessageComponent(sender, text, container) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;

    if (sender === 'thought') {
        const header = document.createElement('div');
        header.className = 'thought-header';
        header.innerHTML = '<span>🤔 思考过程</span><i data-lucide="chevron-down" class="toggle-icon" style="width: 14px; height: 14px;"></i>';
        header.onclick = () => {
            messageDiv.classList.toggle('collapsed');
        };

        const content = document.createElement('div');
        content.className = 'thought-content';

        messageDiv.appendChild(header);
        messageDiv.appendChild(content);
        container.appendChild(messageDiv);

        if (text) {
            content.innerHTML = marked.parse(text);
        }
        lucide.createIcons();
        return messageDiv;
    }

    if (sender === 'assistant' || sender === 'ai' || sender === 'tool') {
        if (text) {
            const contentArea = document.createElement('div');
            contentArea.className = 'content-area';
            let renderedContent = marked.parse(text);
            renderedContent = renderedContent.replace(
                /<pre>/g,
                '<pre style="max-width: 100%; overflow-x: auto;">'
            );
            renderedContent = renderedContent.replace(
                /<table>/g,
                '<table style="max-width: 100%; overflow-x: auto; display: block;">'
            );
            contentArea.innerHTML = renderedContent;
            messageDiv.appendChild(contentArea);
        }
    } else {
        messageDiv.textContent = text;
    }
    container.appendChild(messageDiv);
    lucide.createIcons();
    return messageDiv;
}

// 适配现有的流式聊天中添加临时消息块
function addMessage(sender, text) {
    const messagesDiv = document.getElementById('messages');
    const el = addMessageComponent(sender, text, messagesDiv);
    scrollToBottom();
    return el;
}


function setLoadingState(isLoading) {
    isRequestLoading = isLoading;
    const input = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-button');
    const stopBtn = document.getElementById('stop-button');
    const wrapper = input.parentElement;

    if (isLoading) {
        input.contentEditable = 'false';
        sendBtn.classList.add('hidden');
        stopBtn.classList.remove('hidden');
        wrapper.classList.add('loading');
    } else {
        input.contentEditable = 'true';
        sendBtn.classList.remove('hidden');
        stopBtn.classList.add('hidden');
        wrapper.classList.remove('loading');
        // 恢复焦点
        input.focus();
    }
    lucide.createIcons();
}

function showLoadingIndicator(container = null) {
    hideLoadingIndicator();
    const target = container || document.getElementById('messages');
    currentLoadingIndicator = document.createElement('div');
    currentLoadingIndicator.className = 'typing-indicator';
    currentLoadingIndicator.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
    target.appendChild(currentLoadingIndicator);
    scrollToBottom();
    
    // 如果是在主消息区域，也确保滚动
    if (!container) {
        scrollToBottom();
    }
}


function hideLoadingIndicator() {
    if (currentLoadingIndicator && currentLoadingIndicator.parentElement) {
        currentLoadingIndicator.parentElement.removeChild(currentLoadingIndicator);
    }
    currentLoadingIndicator = null;
}

async function stopMessage() {
    if (!currentConversationId || !isRequestLoading) return;
    
    // 立即释放 UI 状态
    setLoadingState(false);
    
    if (currentAbortController) {
        currentAbortController.abort();
    }

    try {
        await fetch(`/api/conversations/${currentConversationId}/stop`, {
            method: 'POST'
        });
    } catch (e) {
        console.error("停止请求后端通知失败", e);
    }
}

function saveMessage(role, content, reasoning_content = null) {
    if (!conversations[currentConversationId]) {
        conversations[currentConversationId] = { messages: [], timestamp: Date.now(), title: '新会话' };
    }
    const msg = { role, content };
    if (reasoning_content) msg.reasoning_content = reasoning_content;
    conversations[currentConversationId].messages.push(msg);
    conversations[currentConversationId].timestamp = Date.now();
}

async function sendMessage() {
    if (isRequestLoading) return;
    const input = document.getElementById('message-input');
    const message = input.innerText.trim();
    if (!message) return;

    if (!currentConversationId) {
        newConversation();
    }

    updateNewSessionUI(false);
    addMessage('user', message);
    saveMessage('user', message);
    input.innerText = '';
    input.style.overflowY = 'hidden';

    setLoadingState(true);
    scrollToBottom(true); // 发送新消息时强制开启并执行滚动
    showLoadingIndicator();

    currentAbortController = new AbortController();

    try {
        const response = await fetch(`/api/conversations/${currentConversationId}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            signal: currentAbortController.signal,
            body: JSON.stringify({
                messages: [{ role: "user", content: message }]
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');

        // 容器栈，用于支持嵌套渲染 (子 Agent)
        const containerStack = [{
            sub_thread_id: null,
            container: document.getElementById('messages'),
            subAgentWrapper: null,
            currentAIMessageContainer: null,
            accumulatedThought: "",
            accumulatedText: "",
            responseContainer: null,
            thoughtContainer: null,
            _pendingTool: null
        }];

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const jsonData = JSON.parse(line.substring(6));
                        
                        // 确定当前应该渲染到的容器
                        let targetLevel = containerStack[containerStack.length - 1];
                        if (jsonData.sub_thread_id) {
                            // 如果显式指定了子线程 ID，尝试在栈中找到它
                            const found = containerStack.find(l => l.sub_thread_id === jsonData.sub_thread_id);
                            if (found) {
                                targetLevel = found;
                            }
                        }

                        if (jsonData.type === 'step_done') {
                            const mainLevel = containerStack[0];
                            if (mainLevel.accumulatedText || mainLevel.accumulatedThought) {
                                saveMessage('assistant', mainLevel.accumulatedText, mainLevel.accumulatedThought);
                            }
                            mainLevel.accumulatedText = "";
                            mainLevel.accumulatedThought = "";
                            mainLevel.responseContainer = null;
                            mainLevel.thoughtContainer = null;
                            mainLevel.currentAIMessageContainer = null;
                        } else if (jsonData.type === 'error') {
                            addMessage('assistant', `❌ 错误: ${jsonData.data.message || '未知错误'}`);
                        } else if (jsonData.type) {
                            const data = jsonData.data || {};

                            // 1. 处理结构化事件 (子 Agent 开始/结束，工具开始/结束)
                            if (jsonData.type === 'sub_agent_start') {
                                hideLoadingIndicator();
                                // 名称不再重要，使用统一标题。传入 sub_thread_id 以便追踪。
                                const { wrapper, content } = createSubAgentWrapper("执行子任务", data.task, targetLevel.container);
                                containerStack.push({
                                    sub_thread_id: jsonData.sub_thread_id,
                                    container: content,
                                    subAgentWrapper: wrapper,
                                    currentAIMessageContainer: null,
                                    accumulatedThought: "",
                                    accumulatedText: "",
                                    responseContainer: null,
                                    thoughtContainer: null,
                                    _pendingTool: null
                                });
                                showLoadingIndicator(content);
                                continue;
                            }

                            if (jsonData.type === 'sub_agent_end') {
                                // 查找并弹出匹配的子任务层
                                const index = containerStack.findIndex(l => l.sub_thread_id === jsonData.sub_thread_id);
                                if (index !== -1) {
                                    const [target] = containerStack.splice(index, 1);
                                    if (target.subAgentWrapper) {
                                        if (data.result) {
                                            renderSubAgentResult(target.subAgentWrapper, data.result);
                                        }
                                        target.subAgentWrapper.classList.remove('expanded');
                                        target.container.classList.add('hidden');
                                    }
                                }
                                
                                const currentLevel = containerStack[containerStack.length - 1];
                                if (currentLevel) {
                                    showLoadingIndicator(currentLevel.container);
                                }
                                continue;
                            }

                            if (jsonData.type === 'tool_start') {
                                hideLoadingIndicator();
                                targetLevel._pendingTool = data;
                                continue;
                            }

                            if (jsonData.type === 'tool_end') {
                                const toolStart = targetLevel._pendingTool || { name: data.name };
                                renderToolCall({ name: toolStart.name, result: data.result }, toolStart.args, targetLevel.container);
                                targetLevel._pendingTool = null;
                                
                                targetLevel.currentAIMessageContainer = null;
                                targetLevel.responseContainer = null;
                                targetLevel.thoughtContainer = null;
                                targetLevel.accumulatedThought = "";
                                targetLevel.accumulatedText = "";
                                
                                showLoadingIndicator(targetLevel.container);
                                continue;
                            }

                            // 2. 处理流式内容 (思考和正文)
                            if (!targetLevel.currentAIMessageContainer && (jsonData.type === 'reasoning' || jsonData.type === 'content')) {
                                hideLoadingIndicator();
                                targetLevel.currentAIMessageContainer = addMessageComponent('assistant', '', targetLevel.container);
                                targetLevel.responseContainer = null;
                                targetLevel.thoughtContainer = null;
                                targetLevel.accumulatedThought = "";
                                targetLevel.accumulatedText = "";
                            }

                            // 处理思考过程
                            if (jsonData.type === 'reasoning') {
                                if (!targetLevel.thoughtContainer) {
                                    targetLevel.thoughtContainer = addMessageComponent('thought', '', targetLevel.currentAIMessageContainer);
                                }
                                targetLevel.accumulatedThought += data.text || '';
                                const contentArea = targetLevel.thoughtContainer.querySelector('.thought-content');
                                contentArea.innerHTML = marked.parse(targetLevel.accumulatedThought);
                            }

                            // 处理正式回复内容
                            if (jsonData.type === 'content') {
                                if (targetLevel.thoughtContainer && !targetLevel.thoughtContainer.classList.contains('collapsed')) {
                                    targetLevel.thoughtContainer.classList.add('collapsed');
                                }
                                if (!targetLevel.responseContainer) {
                                    targetLevel.responseContainer = targetLevel.currentAIMessageContainer.querySelector('.content-area') || document.createElement('div');
                                    if (!targetLevel.responseContainer.classList.contains('content-area')) {
                                        targetLevel.responseContainer.className = 'content-area';
                                        targetLevel.currentAIMessageContainer.appendChild(targetLevel.responseContainer);
                                    }
                                }
                                targetLevel.accumulatedText += data.text || '';
                                targetLevel.responseContainer.innerHTML = marked.parse(targetLevel.accumulatedText);
                            }

                            // 统一滚动到底部
                            scrollToBottom();
                        }
                    } catch (e) {

                        console.error("JSON parse error:", e);
                    }
                }
            }
        }

        const mainLevel = containerStack[0];
        if (mainLevel.accumulatedText || mainLevel.accumulatedThought) {
            saveMessage('assistant', mainLevel.accumulatedText, mainLevel.accumulatedThought);
        }

        if (!conversations[currentConversationId].title || conversations[currentConversationId].title === '新会话') {
            const newTitle = message.substring(0, 30).trim() + (message.length > 30 ? '...' : '');
            conversations[currentConversationId].title = newTitle;
            document.getElementById('conversation-title').textContent = newTitle;

            // 异步同步到后端，不需要等待
            fetch(`/api/conversations/${currentConversationId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: newTitle })
            }).catch(err => console.error("自动更新标题同步失败", err));
        }

        // 当一次交互完成时，重新全量加载该对话获取准确的嵌套 Timeline
        await loadConversation(currentConversationId);

    } catch (err) {
        if (err.name === 'AbortError') {
            console.log("用户请求停止生成");
        } else {
            console.error("发送消息失败:", err);
            addMessage('assistant', `❌ 发送错误: ${err.message}`);
        }
    } finally {
        setLoadingState(false);
        hideLoadingIndicator();
        currentAbortController = null;
    }
}

async function deleteConversation(convId) {
    if (confirm('确定要删除这个会话吗？此操作不可撤销。')) {
        try {
            const response = await fetch(`/api/conversations/${convId}`, {
                method: 'DELETE'
            });
            if (!response.ok) {
                console.error("后端删除会话记录失败");
            }
        } catch (e) {
            console.error("删除会话请求异常", e);
        }

        delete conversations[convId];
        if (currentConversationId === convId) {
            currentConversationId = null;
            document.getElementById('conversation-title').textContent = '新会话';
            document.getElementById('conversation-id').textContent = '';
            document.getElementById('messages').innerHTML = '';
            updateNewSessionUI(true);
        }
        updateConversationList();
    }
}

async function updateConversationList() {
    const listDiv = document.getElementById('conversation-list');

    try {
        const response = await fetch('/api/conversations');
        if (response.ok) {
            const data = await response.json();
            const backendConversations = data.conversations || [];

            listDiv.innerHTML = '';
            backendConversations.forEach(conv => {
                const convId = conv.id;
                // 同步内存中的 conversations 对象（可选，主要为了保持某些逻辑兼容）
                if (!conversations[convId]) {
                    conversations[convId] = { messages: [] };
                }
                conversations[convId].title = conv.title;
                conversations[convId].timestamp = new Date(conv.updated_at).getTime();

                const convItem = document.createElement('div');
                convItem.className = `conversation-item ${convId === currentConversationId ? 'active' : ''}`;

                const iconSpan = document.createElement('i');
                iconSpan.setAttribute('data-lucide', 'message-square');
                iconSpan.style.width = '14px';
                iconSpan.style.height = '14px';
                iconSpan.style.marginRight = '8px';
                convItem.appendChild(iconSpan);

                const textSpan = document.createElement('span');
                textSpan.className = 'conversation-text';
                textSpan.textContent = conv.title || '新会话';
                convItem.appendChild(textSpan);

                const deleteBtn = document.createElement('span');
                deleteBtn.className = 'delete-btn';
                deleteBtn.innerHTML = '<i data-lucide="trash-2" style="width: 14px; height: 14px;"></i>';
                deleteBtn.onclick = (e) => {
                    e.stopPropagation();
                    deleteConversation(convId);
                };
                convItem.appendChild(deleteBtn);

                convItem.onclick = (e) => {
                    if (e.target !== deleteBtn && !deleteBtn.contains(e.target)) loadConversation(convId);
                };
                convItem.title = convId;
                listDiv.appendChild(convItem);
            });
            lucide.createIcons();
        }
    } catch (e) {
        console.error("加载会话列表失败", e);
    }
}

function handleEnter(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

document.getElementById('message-input').addEventListener('paste', (e) => {
    e.preventDefault();
    const text = e.clipboardData.getData('text/plain');
    document.execCommand('insertText', false, text);
});

// 确保在删除内容时，输入框能彻底清空以触发 :empty 伪类显示占位符
document.getElementById('message-input').addEventListener('input', function () {
    if (this.innerText.trim() === "") {
        this.innerHTML = "";
    }
});

lucide.createIcons();
async function initApp() {
    await updateConversationList();
    updateNewSessionUI(true);

    const messagesDiv = document.getElementById('messages');
    const scrollTopBtn = document.getElementById('scroll-top-btn');
    
    messagesDiv.addEventListener('scroll', () => {
        const isAtBottom = messagesDiv.scrollHeight - messagesDiv.scrollTop <= messagesDiv.clientHeight + 50;
        autoScrollEnabled = isAtBottom;
        
        // 显示/隐藏返回顶部按钮 (滚动超过 300px 显示)
        if (messagesDiv.scrollTop > 300) {
            scrollTopBtn.classList.remove('hidden');
        } else {
            scrollTopBtn.classList.add('hidden');
        }
    });
    
    lucide.createIcons();
}



initApp();
