let currentConversationId = null;
let conversations = {};
let installedSkills = [];
let isRequestLoading = false;
let currentAbortController = null;
let currentLoadingIndicator = null;
let autoScrollEnabled = true;
let currentSidebarView = 'chat';
let isMenuSidebarCollapsed = false;
let currentSkillDetail = null;
let currentSkillSearchResults = [];
let currentSkillSources = null;
let currentSkillSearchQuery = '';
let hasSkillSearchRun = false;
let installingSkillRefs = new Set();

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
    switchSidebarView('chat');
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

function switchSidebarView(view) {
    currentSidebarView = view;

    document.querySelectorAll('.nav-item').forEach((item) => {
        item.classList.toggle('active', item.dataset.view === view);
    });

    document.getElementById('chat-workspace').classList.toggle('active', view === 'chat');
    document.getElementById('skills-workspace').classList.toggle('active', view === 'skills');

    if (view === 'skills') {
        loadSkills();
    }

    lucide.createIcons();
}

function toggleMenuSidebar() {
    isMenuSidebarCollapsed = !isMenuSidebarCollapsed;
    document.body.classList.toggle('sidebar-collapsed', isMenuSidebarCollapsed);

    const toggleIcon = document.querySelector('.menu-toggle i');
    if (toggleIcon) {
        toggleIcon.setAttribute('data-lucide', isMenuSidebarCollapsed ? 'panel-left-open' : 'panel-left-close');
    }

    lucide.createIcons();
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
    switchSidebarView('chat');
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

function renderSkillsList() {
    const listDiv = document.getElementById('skills-list');
    if (!listDiv) return;

    listDiv.innerHTML = '';

    const sectionHeader = document.createElement('div');
    sectionHeader.className = 'skills-section-header installed-section-header';
    sectionHeader.innerHTML = `
        <div class="section-heading-group">
            <h3>${currentSkillSearchQuery ? '已安装匹配' : '已安装技能'}</h3>
            <p>${currentSkillSearchQuery ? `当前关键词“${escapeHtml(currentSkillSearchQuery)}”在本地命中的结果。` : '当前项目中已经安装并可直接使用的技能。'}</p>
        </div>
        <div class="section-header-actions">
            <span class="section-count-badge">${installedSkills.length}</span>
            ${currentSkillSearchQuery ? '<button class="icon-button subtle-action-button" onclick="clearSkillSearch()" title="清空搜索"><i data-lucide="x"></i></button>' : ''}
        </div>
    `;
    listDiv.appendChild(sectionHeader);

    if (!installedSkills.length) {
        const emptyState = document.createElement('div');
        emptyState.className = 'sidebar-empty-state';
        emptyState.innerHTML = `
            <i data-lucide="blocks"></i>
            <h3>${currentSkillSearchQuery ? '没有本地匹配结果' : '暂无已安装技能'}</h3>
            <p>${currentSkillSearchQuery ? `当前项目里没有和“${escapeHtml(currentSkillSearchQuery)}”匹配的已安装技能。你可以看看上面的远程搜索结果。` : '当前项目的 `skills/` 目录下还没有可用技能。'}</p>
        `;
        listDiv.appendChild(emptyState);
        lucide.createIcons();
        return;
    }

    installedSkills.forEach((skill) => {
        const skillItem = document.createElement('div');
        skillItem.className = 'skill-item';
        skillItem.onclick = () => openSkillPreview(skill.name);

        const tags = (skill.tags || []).map((tag) => `<span class="skill-tag">${tag}</span>`).join('');
        const version = skill.version ? `<span class="skill-version">v${skill.version}</span>` : '';
        const source = skill.source ? `<div class="skill-meta-row">来源: ${skill.source}</div>` : '';
        const requirements = skill.requirements && !skill.requirements.ready
            ? `<div class="skill-meta-row skill-warning">环境检查: ${skill.requirements.summary}</div>`
            : '';

        skillItem.innerHTML = `
            <div class="skill-item-header">
                <div class="skill-title-row">
                    <i data-lucide="sparkles"></i>
                    <span class="skill-name">${skill.name}</span>
                </div>
                <div class="skill-item-actions">
                    ${version}
                    <button class="icon-button skill-action-button" onclick="event.stopPropagation(); updateSkill(decodeURIComponent('${encodeURIComponent(skill.name)}'))" title="更新技能">
                        <i data-lucide="refresh-cw"></i>
                    </button>
                    <button class="icon-button skill-action-button danger" onclick="event.stopPropagation(); removeSkill(decodeURIComponent('${encodeURIComponent(skill.name)}'))" title="移除技能">
                        <i data-lucide="trash-2"></i>
                    </button>
                </div>
            </div>
            <p class="skill-description">${skill.description || '暂无描述'}</p>
            <div class="skill-meta-row">目录: <code>${skill.path}</code></div>
            ${source}
            ${requirements}
            ${tags ? `<div class="skill-tags">${tags}</div>` : ''}
        `;
        listDiv.appendChild(skillItem);
    });

    lucide.createIcons();
}

function escapeHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function formatSkillError(error) {
    const message = String(error?.message || error || '').trim();
    if (!message) {
        return '发生了一点小问题，请稍后再试。';
    }
    return message
        .replace(/^HTTP error!\s*Status:\s*/i, '请求失败，状态码：')
        .replace(/^Skill not found$/i, '没有找到对应的技能')
        .replace(/^Error:\s*/i, '');
}

function showSkillsFeedback(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toastIcons = {
        success: 'circle-check-big',
        error: 'circle-alert',
        info: 'info',
    };
    const iconName = toastIcons[type] || toastIcons.info;

    const toast = document.createElement('div');
    toast.className = `toast-message ${type}`;
    toast.innerHTML = `
        <div class="toast-content">
            <div class="toast-icon">
                <i data-lucide="${iconName}"></i>
            </div>
            <div class="toast-body">${escapeHtml(message)}</div>
        </div>
        <button class="toast-close" type="button" aria-label="关闭提示">
            <i data-lucide="x"></i>
        </button>
    `;

    const removeToast = () => {
        if (!toast.parentNode) return;
        toast.classList.add('leaving');
        window.setTimeout(() => {
            toast.remove();
        }, 220);
    };

    toast.querySelector('.toast-close')?.addEventListener('click', removeToast);
    container.appendChild(toast);
    lucide.createIcons();

    window.setTimeout(removeToast, type === 'error' ? 5000 : 3200);
}

function clearSkillsFeedback() {
    const container = document.getElementById('toast-container');
    if (!container) return;
    container.innerHTML = '';
}

function renderRemoteSkillResults(results = [], remoteError = null) {
    const container = document.getElementById('skill-remote-results');
    if (!container) return;

    if (remoteError) {
        container.className = 'skills-remote-results';
        container.innerHTML = `
            <div class="sidebar-empty-state">
                <i data-lucide="triangle-alert"></i>
                <h3>远程搜索失败</h3>
                <p>${escapeHtml(remoteError)}</p>
            </div>
        `;
        lucide.createIcons();
        return;
    }

    if (!results.length && !hasSkillSearchRun) {
        container.classList.add('hidden');
        container.innerHTML = '';
        return;
    }

    if (!results.length) {
        container.className = 'skills-remote-results';
        container.innerHTML = `
            <div class="skills-section-header">
                <div class="section-heading-group">
                    <h3>${currentSkillSearchQuery ? '远程搜索结果' : '远程推荐结果'}</h3>
                    <p>${currentSkillSearchQuery ? `没有找到和“${escapeHtml(currentSkillSearchQuery)}”匹配的远程技能。` : '当前没有可展示的远程推荐结果。'}</p>
                </div>
                <div class="section-header-actions">
                    <span class="section-count-badge">0</span>
                </div>
            </div>
            <div class="sidebar-empty-state">
                <i data-lucide="search-x"></i>
                <h3>${currentSkillSearchQuery ? '没有远程匹配结果' : '暂无远程推荐'}</h3>
                <p>${currentSkillSearchQuery ? '可以换个关键词再试，或者直接输入 ClawHub 标识或页面链接来安装。' : '可以稍后重试，或者直接输入已知的 ClawHub 标识或页面链接来安装。'}</p>
            </div>
        `;
        lucide.createIcons();
        return;
    }

    container.className = 'skills-remote-results';
    container.innerHTML = `
        <div class="skills-section-header">
            <div class="section-heading-group">
                <h3>${currentSkillSearchQuery ? '远程搜索结果' : '远程推荐结果'}</h3>
                <p>${currentSkillSearchQuery ? `来自 ClawHub 的“${escapeHtml(currentSkillSearchQuery)}”相关结果，可直接安装到当前项目。` : '来自 ClawHub 的可安装技能推荐。'}</p>
            </div>
            <div class="section-header-actions">
                <span class="section-count-badge">${results.length}</span>
            </div>
        </div>
        <div class="remote-skill-list">
            ${results.map((skill) => `
                <div class="remote-skill-item">
                    <div>
                        <div class="remote-skill-title-row">
                            <div class="remote-skill-name">${escapeHtml(skill.name || skill.slug || '未命名技能')}</div>
                            ${skill.installed ? `<span class="installed-pill">已安装</span>` : ''}
                        </div>
                        <div class="skill-meta-row">${escapeHtml(skill.slug || '')}</div>
                        ${skill.installed && skill.installed_skill_name ? `<div class="skill-meta-row">本地对应: ${escapeHtml(skill.installed_skill_name)}</div>` : ''}
                        <p class="skill-description">${escapeHtml(skill.summary || '暂无描述')}</p>
                        ${skill.page_url ? `<a class="skill-link" href="${escapeHtml(skill.page_url)}" target="_blank" rel="noreferrer">打开来源页</a>` : ''}
                    </div>
                    ${skill.installed
                        ? `<button class="icon-button remote-installed-button" disabled title="这个技能已经安装">
                            <i data-lucide="check"></i>
                        </button>`
                        : installingSkillRefs.has(skill.slug || skill.page_url || '')
                            ? `<button class="icon-button remote-installing-button" disabled title="正在安装">
                                <i data-lucide="loader-circle"></i>
                            </button>`
                        : `<button class="icon-button" onclick="installSkill(decodeURIComponent('${encodeURIComponent(skill.slug || skill.page_url || '')}'))" title="安装技能">
                            <i data-lucide="download"></i>
                        </button>`
                    }
                </div>
            `).join('')}
        </div>
    `;
    lucide.createIcons();
}

function clearSkillSearch() {
    currentSkillSearchQuery = '';
    currentSkillSearchResults = [];
    hasSkillSearchRun = false;
    const searchInput = document.getElementById('skill-search-input');
    if (searchInput) {
        searchInput.value = '';
    }
    renderRemoteSkillResults([], null);
    clearSkillsFeedback();
    loadSkills();
}

function renderSkillSourcesPanel() {
    const panel = document.getElementById('skill-sources-panel');
    if (!panel) return;
    if (!currentSkillSources) {
        panel.classList.add('hidden');
        panel.innerHTML = '';
        return;
    }

    panel.className = 'skills-info-panel';
    panel.innerHTML = `
        <div class="skills-section-header">
            <h3>技能来源</h3>
            <p>安装和读取路径都在这里集中展示。</p>
        </div>
        <div class="skill-sources-grid">
            ${(currentSkillSources.roots || []).map((root) => `
                <div class="source-card">
                    <div class="source-card-title">${escapeHtml(root.name)}</div>
                    <div class="skill-meta-row"><code>${escapeHtml(root.path)}</code></div>
                    <div class="skill-meta-row">${root.mutable ? '可写目录' : '只读目录'}</div>
                    <div class="skill-meta-row">${escapeHtml(root.description || '')}</div>
                </div>
            `).join('')}
            <div class="source-card">
                <div class="source-card-title">${escapeHtml(currentSkillSources.remote?.name || '远程来源')}</div>
                <div class="skill-meta-row">
                    <a class="skill-link" href="${escapeHtml(currentSkillSources.remote?.site || '#')}" target="_blank" rel="noreferrer">
                        ${escapeHtml(currentSkillSources.remote?.site || '未配置')}
                    </a>
                </div>
            </div>
        </div>
    `;
    lucide.createIcons();
}

async function fetchSkillSources() {
    const response = await fetch('/api/skills/manage/sources');
    if (!response.ok) {
        throw new Error(`请求失败，状态码：${response.status}`);
    }
    currentSkillSources = await response.json();
    renderSkillSourcesPanel();
}

async function toggleSkillSources() {
    const panel = document.getElementById('skill-sources-panel');
    if (!panel) return;

    if (!panel.classList.contains('hidden')) {
        panel.classList.add('hidden');
        return;
    }

    if (!currentSkillSources) {
        showSkillsFeedback('正在加载技能来源信息...', 'info');
        try {
            await fetchSkillSources();
            clearSkillsFeedback();
        } catch (e) {
            console.error("加载技能来源失败", e);
            showSkillsFeedback(`加载技能来源失败：${formatSkillError(e)}`, 'error');
            return;
        }
    }

    panel.classList.remove('hidden');
}

async function searchSkills() {
    const input = document.getElementById('skill-search-input');
    const query = input?.value?.trim() || '';
    if (!query) {
        hasSkillSearchRun = false;
        currentSkillSearchQuery = '';
        currentSkillSearchResults = [];
        renderRemoteSkillResults([], null);
        showSkillsFeedback('先输入关键词，再开始搜索技能。', 'info');
        input?.focus();
        return;
    }

    currentSkillSearchQuery = query;
    hasSkillSearchRun = true;
    showSkillsFeedback(`正在为你搜索“${query}”相关技能...`, 'info');

    try {
        const response = await fetch('/api/skills/manage/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, include_installed: true })
        });
        if (!response.ok) {
            throw new Error(`请求失败，状态码：${response.status}`);
        }

        const data = await response.json();
        currentSkillSearchResults = data.remote || [];
        installedSkills = data.installed || installedSkills;
        renderSkillsList();
        renderRemoteSkillResults(currentSkillSearchResults, data.remote_error);
        showSkillsFeedback(
            currentSkillSearchResults.length
                ? `搜索完成，找到了 ${currentSkillSearchResults.length} 个远程结果。`
                : `搜索完成，但暂时没有找到和“${query}”匹配的远程结果。`,
            currentSkillSearchResults.length ? 'success' : 'info'
        );
    } catch (e) {
        console.error("搜索技能失败", e);
        showSkillsFeedback(`搜索技能时出了点问题：${formatSkillError(e)}`, 'error');
    }
}

function handleSkillSearchKeydown(event) {
    if (event.key === 'Enter') {
        event.preventDefault();
        searchSkills();
    }
}

async function installSkill(skillRef) {
    const normalizedRef = (skillRef || '').trim();
    if (!normalizedRef) {
        showSkillsFeedback('请输入要安装的技能标识或页面链接。', 'error');
        return;
    }

    if (installingSkillRefs.has(normalizedRef)) {
        return;
    }

    installingSkillRefs.add(normalizedRef);
    renderRemoteSkillResults(currentSkillSearchResults, null);
    showSkillsFeedback('正在为你安装技能，请稍等片刻...', 'info');
    try {
        const response = await fetch('/api/skills/manage/install', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ skill_ref: normalizedRef, force: false })
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || `请求失败，状态码：${response.status}`);
        }

        installedSkills = data.skills || [];
        const installedMatch = installedSkills.find((installedSkill) => {
            const slug = (installedSkill.clawhub_slug || '').trim();
            return slug === normalizedRef || installedSkill.name === normalizedRef || installedSkill.dir_name === normalizedRef;
        });
        currentSkillSearchResults = currentSkillSearchResults.map((skill) => {
            const skillKey = (skill.slug || skill.page_url || '').trim();
            if (skillKey !== normalizedRef) {
                return skill;
            }

            return {
                ...skill,
                installed: true,
                installed_skill_name: installedMatch?.name || skill.installed_skill_name || skill.name || skill.slug || '',
            };
        });
        renderSkillsList();
        renderRemoteSkillResults(currentSkillSearchResults, null);
        showSkillsFeedback('安装完成，技能已经加入当前项目的已安装列表。', 'success');
        const installInput = document.getElementById('skill-install-input');
        if (installInput) installInput.value = '';
    } catch (e) {
        console.error("安装技能失败", e);
        showSkillsFeedback(`安装没有成功：${formatSkillError(e)}`, 'error');
    } finally {
        installingSkillRefs.delete(normalizedRef);
        renderRemoteSkillResults(currentSkillSearchResults, null);
    }
}

async function installSkillFromInput() {
    const input = document.getElementById('skill-install-input');
    await installSkill(input?.value || '');
}

function handleSkillInstallKeydown(event) {
    if (event.key === 'Enter') {
        event.preventDefault();
        installSkillFromInput();
    }
}

async function updateSkill(skillName) {
    showSkillsFeedback(`正在更新“${skillName}”，请稍等...`, 'info');
    try {
        const response = await fetch('/api/skills/manage/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ skill_name: skillName, force: true })
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || `请求失败，状态码：${response.status}`);
        }

        installedSkills = data.skills || [];
        renderSkillsList();
        showSkillsFeedback(`更新完成，“${skillName}”已经是最新状态。`, 'success');
    } catch (e) {
        console.error("更新技能失败", e);
        showSkillsFeedback(`更新没有成功：${formatSkillError(e)}`, 'error');
    }
}

async function removeSkill(skillName) {
    if (!confirm(`确定要移除技能“${skillName}”吗？`)) {
        return;
    }

    showSkillsFeedback(`正在移除“${skillName}”...`, 'info');
    try {
        const response = await fetch(`/api/skills/manage/${encodeURIComponent(skillName)}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || `请求失败，状态码：${response.status}`);
        }

        installedSkills = data.skills || [];
        renderSkillsList();
        showSkillsFeedback(`已经移除“${skillName}”。`, 'success');
        if (currentSkillDetail?.name === skillName) {
            closeSkillPreview();
        }
    } catch (e) {
        console.error("移除技能失败", e);
        showSkillsFeedback(`移除没有成功：${formatSkillError(e)}`, 'error');
    }
}

async function openSkillPreview(skillName) {
    const modal = document.getElementById('skill-preview-modal');
    const title = document.getElementById('skill-preview-title');
    const meta = document.getElementById('skill-preview-meta');
    const content = document.getElementById('skill-preview-content');

    title.textContent = skillName;
    meta.textContent = '正在加载...';
    content.innerHTML = '<div class="sidebar-loading">正在加载技能说明...</div>';
    modal.classList.remove('hidden');
    document.body.classList.add('modal-open');

    try {
        const response = await fetch(`/api/skills/${encodeURIComponent(skillName)}`);
        if (!response.ok) {
            throw new Error(`请求失败，状态码：${response.status}`);
        }

        currentSkillDetail = await response.json();
        title.textContent = currentSkillDetail.name;

        const metaParts = [
            currentSkillDetail.version ? `v${currentSkillDetail.version}` : null,
            currentSkillDetail.path || null,
        ].filter(Boolean);
        meta.textContent = metaParts.join(' · ');
        content.innerHTML = marked.parse(currentSkillDetail.instructions || '_暂无内容_');
    } catch (e) {
        console.error("加载技能详情失败", e);
        meta.textContent = '';
        content.innerHTML = `<div class="sidebar-loading">加载失败：${formatSkillError(e)}</div>`;
    }

    lucide.createIcons();
}

function closeSkillPreview(event = null) {
    if (event && event.target !== event.currentTarget) {
        return;
    }

    const modal = document.getElementById('skill-preview-modal');
    modal.classList.add('hidden');
    document.body.classList.remove('modal-open');
    currentSkillDetail = null;
}

async function loadSkills(forceRefresh = false) {
    const listDiv = document.getElementById('skills-list');
    if (!listDiv) return;

    if (!forceRefresh && installedSkills.length > 0) {
        renderSkillsList();
        return;
    }

    listDiv.innerHTML = '<div class="sidebar-loading">正在加载技能列表...</div>';
    clearSkillsFeedback();

    try {
        if (forceRefresh) {
            const reloadResponse = await fetch('/api/skills/manage/reload', {
                method: 'POST'
            });
            if (!reloadResponse.ok) {
                throw new Error(`请求失败，状态码：${reloadResponse.status}`);
            }
        }

        const response = await fetch('/api/skills');
        if (!response.ok) {
            throw new Error(`请求失败，状态码：${response.status}`);
        }

        const data = await response.json();
        installedSkills = data.skills || [];
        renderSkillsList();
        if (forceRefresh) {
            showSkillsFeedback('技能列表已经刷新完成。', 'success');
        }
    } catch (e) {
        console.error("加载技能列表失败", e);
        listDiv.innerHTML = `
            <div class="sidebar-empty-state">
                <i data-lucide="triangle-alert"></i>
                <h3>技能列表加载失败</h3>
                <p>${formatSkillError(e)}</p>
            </div>
        `;
        lucide.createIcons();
        showSkillsFeedback(`加载技能列表失败：${formatSkillError(e)}`, 'error');
    }
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
                                const parentSubThreadId = data.parent_sub_thread_id || null;
                                const parentLevel = parentSubThreadId
                                    ? containerStack.find(l => l.sub_thread_id === parentSubThreadId) || containerStack[0]
                                    : containerStack[0];

                                // 子任务容器挂到显式父线程下，而不是当前栈顶。
                                const { wrapper, content } = createSubAgentWrapper("执行子任务", data.task, parentLevel.container);
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

document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
        closeSkillPreview();
    }
});

lucide.createIcons();
async function initApp() {
    await updateConversationList();
    await loadSkills();
    updateNewSessionUI(true);
    switchSidebarView('chat');

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
