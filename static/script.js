let currentConversationId = null;
let conversations = {};

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

function newConversation() {
    currentConversationId = 'conv_' + Date.now();
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
            const response = await fetch(`/v1/conversation/${currentConversationId}/title`, {
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
        const response = await fetch(`/v1/conversation/${convId}/timeline`);
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
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }, 50);
}

function renderMessagesList(messages, container) {
    messages.forEach(msg => {
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
        } else if (msg.role === 'tool') {
            if (msg.sub_agent_messages && msg.sub_agent_messages.length > 0) {
                // 渲染可折叠的子 Agent 调用时间轴
                const wrapper = document.createElement('div');
                wrapper.className = 'sub-agent-wrapper';

                const header = document.createElement('div');
                header.className = 'sub-agent-header';
                header.innerHTML = `<div style="display: flex; align-items: center; gap: 8px;"><i data-lucide="cpu" style="width: 16px; height: 16px;"></i><span>子 Agent 调用: ${msg.name}</span></div><span>▼</span>`;

                const content = document.createElement('div');
                content.className = 'sub-agent-content hidden';

                header.onclick = () => content.classList.toggle('hidden');

                wrapper.appendChild(header);
                wrapper.appendChild(content);
                container.appendChild(wrapper);

                // 递归渲染内部交互
                renderMessagesList(msg.sub_agent_messages, content);

                // 最后显示工具汇总的最终结果
                if (msg.content) {
                    const finalResult = document.createElement('div');
                    finalResult.style.marginTop = '15px';
                    finalResult.style.borderTop = '1px solid var(--border-color)';
                    finalResult.style.paddingTop = '15px';
                    finalResult.innerHTML = `<strong style="color: var(--accent-cyan); display: flex; align-items: center; gap: 8px;"><i data-lucide="sparkle" style="width: 14px; height: 14px;"></i> 最终结果:</strong><div style="margin-top: 10px;">${marked.parse(msg.content)}</div>`;
                    content.appendChild(finalResult);
                }
            } else if (msg.content) {
                // 没有内部细节的普通工具调用
                addMessageComponent('tool', `🔧 工具执行 (${msg.name}):\n${msg.content}`, container);
            }
        }
    });
    lucide.createIcons();
    container.scrollTop = container.scrollHeight;
}

function addMessageComponent(sender, text, container) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;

    if (sender === 'thought') {
        const header = document.createElement('div');
        header.className = 'thought-header';
        header.innerHTML = '<span>🤔 思考过程</span><span class="toggle-icon">▼</span>';
        header.onclick = () => messageDiv.classList.toggle('collapsed');

        const content = document.createElement('div');
        content.className = 'thought-content';

        messageDiv.appendChild(header);
        messageDiv.appendChild(content);
        container.appendChild(messageDiv);

        if (text) {
            content.innerHTML = marked.parse(text);
        }
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
    return messageDiv;
}

// 适配现有的流式聊天中添加临时消息块
function addMessage(sender, text) {
    const messagesDiv = document.getElementById('messages');
    const el = addMessageComponent(sender, text, messagesDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    return el;
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

    let currentAIMessageContainer = null;
    let accumulatedText = "";
    let forceNewMessageDiv = true;

    const response = await fetch('/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            messages: [{ role: "user", content: message }],
            conversation_id: currentConversationId
        })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');

    let thoughtContainer = null;
    let accumulatedThought = "";
    let responseContainer = null;

    while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
            if (line.startsWith('data: ')) {
                try {
                    const jsonData = JSON.parse(line.substring(6));
                    if (jsonData.object === 'chat.completion.step.done') {
                        if (accumulatedText || accumulatedThought) {
                            saveMessage('assistant', accumulatedText, accumulatedThought);
                        }
                        forceNewMessageDiv = true;
                        accumulatedText = "";
                        accumulatedThought = "";
                        responseContainer = null;
                        thoughtContainer = null;
                        currentAIMessageContainer = null;
                    } else if (jsonData.choices && jsonData.choices[0].delta) {
                        const delta = jsonData.choices[0].delta;

                        // 所有的回复流公用同一个大的 AI 容器
                        if (!currentAIMessageContainer && (delta.reasoning_content || delta.content)) {
                            currentAIMessageContainer = addMessageComponent('assistant', '', document.getElementById('messages'));
                        }

                        // 处理思考过程
                        if (delta.reasoning_content) {
                            if (!thoughtContainer) {
                                thoughtContainer = addMessageComponent('thought', '', currentAIMessageContainer);
                            }
                            accumulatedThought += delta.reasoning_content;
                            const contentArea = thoughtContainer.querySelector('.thought-content');
                            contentArea.innerHTML = marked.parse(accumulatedThought);
                            document.getElementById('messages').scrollTop = document.getElementById('messages').scrollHeight;
                        }

                        // 处理正式回复内容
                        if (delta.content) {
                            // 刚开始输出正式内容时，说明思考过程结束了，折叠它
                            if (thoughtContainer && !thoughtContainer.classList.contains('collapsed')) {
                                thoughtContainer.classList.add('collapsed');
                            }
                            if (!responseContainer) {
                                // 在 AI 容器中查找或创建 content-area
                                responseContainer = currentAIMessageContainer.querySelector('.content-area') ||
                                    document.createElement('div');
                                if (!responseContainer.classList.contains('content-area')) {
                                    responseContainer.className = 'content-area';
                                    currentAIMessageContainer.appendChild(responseContainer);
                                }
                                accumulatedText = "";
                            }
                            accumulatedText += delta.content;
                            responseContainer.innerHTML = marked.parse(accumulatedText);
                            forceNewMessageDiv = false;
                        }
                    }
                } catch (e) {
                    console.error("JSON parse error:", e);
                }
            }
        }
    }

    if ((accumulatedText || accumulatedThought) && !forceNewMessageDiv) {
        saveMessage('assistant', accumulatedText, accumulatedThought);
    }

    if (!conversations[currentConversationId].title || conversations[currentConversationId].title === '新会话') {
        const newTitle = message.substring(0, 30).trim() + (message.length > 30 ? '...' : '');
        conversations[currentConversationId].title = newTitle;
        document.getElementById('conversation-title').textContent = newTitle;
        
        // 异步同步到后端，不需要等待
        fetch(`/v1/conversation/${currentConversationId}/title`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: newTitle })
        }).catch(err => console.error("自动更新标题同步失败", err));
    }

    // 当一次交互完成时，重新全量加载该对话获取准确的嵌套 Timeline
    await loadConversation(currentConversationId);
}

async function deleteConversation(convId) {
    if (confirm('确定要删除这个会话吗？此操作不可撤销。')) {
        try {
            const response = await fetch(`/v1/conversation/${convId}`, {
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
        const response = await fetch('/v1/conversations');
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
document.getElementById('message-input').addEventListener('input', function() {
    if (this.innerText.trim() === "") {
        this.innerHTML = "";
    }
});

lucide.createIcons();
async function initApp() {
    await updateConversationList();
    const list = document.getElementById('conversation-list');
    const firstItem = list.querySelector('.conversation-item');
    if (firstItem) {
        const convId = firstItem.title;
        loadConversation(convId);
    }
}
initApp();
