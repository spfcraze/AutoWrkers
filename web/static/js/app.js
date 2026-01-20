// UltraClaude - Frontend Application

class UltraClaude {
    constructor() {
        this.sessions = new Map();
        this.activeSessionId = null;
        this.ws = null;
        this.outputBuffers = new Map();
        this.currentFilter = 'all';
        this.currentView = 'list';
        this.contextMenuSessionId = null;
        this.draggedSessionId = null;
        this.terminalVisible = true;

        this.init();
    }

    init() {
        this.connectWebSocket();
        this.setupEventListeners();
        this.setupContextMenu();
        this.setupDragAndDrop();
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            } catch (e) {
                console.error('Failed to parse WebSocket message:', e);
            }
        };

        this.ws.onclose = () => {
            console.log('WebSocket disconnected, reconnecting...');
            setTimeout(() => this.connectWebSocket(), 2000);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }

    handleMessage(data) {
        switch (data.type) {
            case 'init':
                this.initSessions(data.sessions);
                break;
            case 'output':
                this.handleOutput(data.session_id, data.data);
                break;
            case 'status':
                this.handleStatusChange(data.session_id, data.status, data.session);
                break;
            case 'session_created':
                this.handleSessionCreated(data.session);
                break;
            case 'error':
                this.handleError(data.message);
                break;
        }
    }

    handleError(message) {
        console.error('Server error:', message);
        alert('Error: ' + message);
    }

    handleSessionCreated(session) {
        console.log('New session created:', session);
        this.sessions.set(session.id, session);
        this.outputBuffers.set(session.id, []);
        this.renderSessions();
        this.updateStats();
    }

    initSessions(sessions) {
        this.sessions.clear();
        sessions.forEach(session => {
            this.sessions.set(session.id, session);
            this.outputBuffers.set(session.id, []);
        });
        this.renderSessions();
        this.updateStats();
    }

    handleOutput(sessionId, data) {
        // Store full screen content (we receive complete screen updates)
        this.outputBuffers.set(sessionId, [data]);

        // Update terminal if this is the active session
        if (sessionId === this.activeSessionId) {
            this.replaceTerminalContent(data);
        }

        // Update session preview
        const session = this.sessions.get(sessionId);
        if (session) {
            session.last_output = data.slice(-200);
            this.updateSessionCard(sessionId);
        }
    }

    handleStatusChange(sessionId, status, sessionData) {
        if (sessionData) {
            this.sessions.set(sessionId, sessionData);
        } else {
            const session = this.sessions.get(sessionId);
            if (session) {
                session.status = status;
            }
        }
        this.updateSessionCard(sessionId);
        this.updateStats();

        // Show notification for needs_attention
        if (status === 'needs_attention') {
            this.showNotification(sessionId);
        }
    }

    showNotification(sessionId) {
        const session = this.sessions.get(sessionId);
        if (!session) return;

        if (Notification.permission === 'granted') {
            new Notification(`UltraClaude - ${session.name}`, {
                body: 'Session needs your attention',
                icon: '/static/icon.png'
            });
        } else if (Notification.permission !== 'denied') {
            Notification.requestPermission();
        }
    }

    renderSessions() {
        const grid = document.getElementById('sessions-grid');
        grid.innerHTML = '';

        const sessionsArray = Array.from(this.sessions.values());
        const filtered = this.filterSessions(sessionsArray);

        if (filtered.length === 0) {
            grid.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">📭</div>
                    <p>No sessions yet</p>
                    <p style="margin-top: 8px; font-size: 12px;">Click "+ New Session" to start</p>
                </div>
            `;
            return;
        }

        // Group sessions: parents first, then their children
        const parentSessions = filtered.filter(s => !s.parent_id);
        const childrenByParent = new Map();

        filtered.forEach(session => {
            if (session.parent_id) {
                if (!childrenByParent.has(session.parent_id)) {
                    childrenByParent.set(session.parent_id, []);
                }
                childrenByParent.get(session.parent_id).push(session);
            }
        });

        // Render parent sessions with their children nested below
        parentSessions.forEach(parent => {
            const group = this.createSessionGroup(parent, childrenByParent.get(parent.id) || []);
            grid.appendChild(group);
        });

        // Render orphan children (parent not in filtered list)
        filtered.forEach(session => {
            if (session.parent_id && !parentSessions.find(p => p.id === session.parent_id)) {
                grid.appendChild(this.createSessionCard(session, true));
            }
        });
    }

    createSessionGroup(parent, children) {
        const group = document.createElement('div');
        group.className = 'session-group';

        // Add parent card
        group.appendChild(this.createSessionCard(parent, false));

        // Add children container if there are children
        if (children.length > 0) {
            const childrenContainer = document.createElement('div');
            childrenContainer.className = 'session-children';

            children.forEach((child, index) => {
                const isLast = index === children.length - 1;
                childrenContainer.appendChild(this.createSessionCard(child, true, isLast));
            });

            group.appendChild(childrenContainer);
        }

        return group;
    }

    filterSessions(sessions) {
        if (this.currentFilter === 'all') return sessions;
        return sessions.filter(s => s.status === this.currentFilter);
    }

    createSessionCard(session, isChild = false, isLast = false) {
        const card = document.createElement('div');
        const childClass = isChild ? 'session-card-child' : '';
        const lastChildClass = isChild && isLast ? 'last-child' : '';
        card.className = `session-card ${childClass} ${lastChildClass} ${session.status === 'needs_attention' ? 'needs-attention' : ''} ${session.status === 'queued' ? 'queued' : ''} ${session.id === this.activeSessionId ? 'active' : ''}`;
        card.dataset.sessionId = session.id;
        card.onclick = () => this.selectSession(session.id);

        const statusLabel = {
            'running': 'Running',
            'needs_attention': 'Needs Attention',
            'stopped': 'Stopped',
            'error': 'Error',
            'starting': 'Starting',
            'queued': 'Queued',
            'completed': 'Completed'
        }[session.status] || session.status;

        const childIndicator = isChild ? '<span class="child-indicator">↳</span>' : '';
        const parentInfo = isChild && session.parent_id ? `<span class="parent-info">child of #${session.parent_id}</span>` : '';

        card.innerHTML = `
            <div class="session-card-header">
                <span class="session-name">
                    ${childIndicator}
                    <span class="session-id">#${session.id}</span>
                    ${this.escapeHtml(session.name)}
                    ${session.status === 'needs_attention' ? '<span class="notification-dot"></span>' : ''}
                </span>
                <span class="status-badge status-${this.escapeHtml(session.status)}">${this.escapeHtml(statusLabel)}</span>
            </div>
            <div class="session-meta">
                <span>📁 ${this.escapeHtml(this.truncatePath(session.working_dir))}</span>
                ${parentInfo}
            </div>
            ${session.last_output ? `<div class="session-preview">${this.escapeHtml(session.last_output.slice(-100))}</div>` : ''}
        `;

        return card;
    }

    updateSessionCard(sessionId) {
        const session = this.sessions.get(sessionId);
        if (!session) return;

        const existingCard = document.querySelector(`[data-session-id="${sessionId}"]`);
        if (existingCard) {
            const newCard = this.createSessionCard(session);
            existingCard.replaceWith(newCard);
        } else {
            this.renderSessions();
        }
    }

    async selectSession(sessionId) {
        this.activeSessionId = sessionId;
        const session = this.sessions.get(sessionId);

        // Update card styles
        document.querySelectorAll('.session-card').forEach(card => {
            card.classList.remove('active');
        });
        const activeCard = document.querySelector(`[data-session-id="${sessionId}"]`);
        if (activeCard) {
            activeCard.classList.add('active');
        }

        // Update terminal title
        document.getElementById('active-session-title').textContent =
            session ? `${session.name} (#${session.id})` : 'Select a session';

        // Load output from API (to get history) and merge with local buffer
        const output = document.getElementById('terminal-output');
        output.innerHTML = '<div class="placeholder">Loading output...</div>';

        try {
            const response = await fetch(`/api/sessions/${sessionId}/output`);
            const data = await response.json();

            if (data.output) {
                // Store in buffer and display
                this.outputBuffers.set(sessionId, [data.output]);
                output.innerHTML = `<div class="terminal-content">${this.ansiToHtml(data.output)}</div>`;
            } else {
                output.innerHTML = '<div class="placeholder">No output yet...</div>';
            }
        } catch (e) {
            console.error('Failed to load session output:', e);
            // Fall back to local buffer
            const buffer = this.outputBuffers.get(sessionId) || [];
            output.innerHTML = buffer.length > 0
                ? `<div class="terminal-content">${this.ansiToHtml(buffer.join(''))}</div>`
                : '<div class="placeholder">No output yet...</div>';
        }

        output.scrollTop = output.scrollHeight;

        // Focus input
        document.getElementById('terminal-input').focus();
    }

    appendToTerminal(data) {
        const output = document.getElementById('terminal-output');
        const placeholder = output.querySelector('.placeholder');

        if (placeholder) {
            output.innerHTML = '';
        }

        let container = output.querySelector('.terminal-content');
        if (!container) {
            container = document.createElement('div');
            container.className = 'terminal-content';
            output.appendChild(container);
        }

        // Append new ANSI-parsed content
        container.innerHTML += this.ansiToHtml(data);
        output.scrollTop = output.scrollHeight;
    }

    replaceTerminalContent(data) {
        const output = document.getElementById('terminal-output');
        output.innerHTML = `<div class="terminal-content">${this.ansiToHtml(data)}</div>`;
        output.scrollTop = output.scrollHeight;
    }

    clearTerminal() {
        if (this.activeSessionId) {
            this.outputBuffers.set(this.activeSessionId, []);
            document.getElementById('terminal-output').innerHTML =
                '<div class="placeholder">Terminal cleared</div>';
        }
    }

    toggleTerminal() {
        this.terminalVisible = !this.terminalVisible;
        const terminalPanel = document.getElementById('terminal-panel');
        const showBtn = document.getElementById('terminal-show-btn');
        const toggleBtn = document.getElementById('terminal-toggle');

        if (this.terminalVisible) {
            terminalPanel.classList.remove('hidden');
            showBtn.classList.remove('visible');
            toggleBtn.innerHTML = '◀';
            toggleBtn.title = 'Hide Terminal';
        } else {
            terminalPanel.classList.add('hidden');
            showBtn.classList.add('visible');
            toggleBtn.innerHTML = '▶';
            toggleBtn.title = 'Show Terminal';
        }
    }

    updateStats() {
        const total = this.sessions.size;
        const attention = Array.from(this.sessions.values())
            .filter(s => s.status === 'needs_attention').length;

        document.getElementById('session-count').textContent =
            `${total} session${total !== 1 ? 's' : ''}`;
        document.getElementById('attention-count').textContent =
            `${attention} need${attention === 1 ? 's' : ''} attention`;
    }

    setupEventListeners() {
        // Filter buttons
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.onclick = () => {
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.currentFilter = btn.dataset.filter;
                this.renderSessions();
            };
        });

        // Request notification permission
        if (Notification.permission === 'default') {
            Notification.requestPermission();
        }
    }

    sendInput(text) {
        if (!this.activeSessionId) {
            console.warn('No active session selected');
            return;
        }

        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.error('WebSocket not connected');
            return;
        }

        const input = text !== undefined ? text : document.getElementById('terminal-input').value;

        this.ws.send(JSON.stringify({
            type: 'input',
            session_id: this.activeSessionId,
            data: input + '\r'
        }));

        document.getElementById('terminal-input').value = '';
    }

    createSession(name, workingDir) {
        this.ws.send(JSON.stringify({
            type: 'create',
            name: name || undefined,
            working_dir: workingDir || undefined
        }));
    }

    stopSession(sessionId) {
        this.ws.send(JSON.stringify({
            type: 'stop',
            session_id: sessionId
        }));
    }

    truncatePath(path) {
        if (!path) return '';
        if (path.length <= 30) return path;
        return '...' + path.slice(-27);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Parse ANSI escape codes and convert to HTML
    ansiToHtml(text) {
        // Remove cursor/mode control sequences
        text = text.replace(/\x1b\[\?[0-9;]*[hlsc]/g, '');
        text = text.replace(/\x1b\[[0-9]*[ABCDEFGJKST]/g, '');
        text = text.replace(/\x1b\[[0-9;]*[Hf]/g, '');
        text = text.replace(/\x1b\]0;[^\x07]*\x07/g, ''); // Window title
        text = text.replace(/\x1b\[\?2026[hl]/g, '');

        // ANSI color map
        const colors = {
            30: '#1e1e1e', 31: '#f85149', 32: '#3fb950', 33: '#d29922',
            34: '#58a6ff', 35: '#a371f7', 36: '#39c5cf', 37: '#e6edf3',
            90: '#8b949e', 91: '#ff7b72', 92: '#7ee787', 93: '#e3b341',
            94: '#79c0ff', 95: '#d2a8ff', 96: '#56d4dd', 97: '#ffffff'
        };

        // 256 color approximation for common colors
        const color256 = (n) => {
            if (n < 16) {
                const basic = ['#000','#800','#080','#880','#008','#808','#088','#ccc',
                              '#888','#f00','#0f0','#ff0','#00f','#f0f','#0ff','#fff'];
                return basic[n];
            }
            if (n >= 232) return `rgb(${(n-232)*10+8},${(n-232)*10+8},${(n-232)*10+8})`;
            n -= 16;
            const r = Math.floor(n/36) * 51;
            const g = Math.floor((n%36)/6) * 51;
            const b = (n%6) * 51;
            return `rgb(${r},${g},${b})`;
        };

        let result = '';
        let currentStyle = {};
        let i = 0;

        while (i < text.length) {
            if (text[i] === '\x1b' && i + 1 < text.length && text[i+1] === '[') {
                // Parse ANSI sequence
                let j = i + 2;
                while (j < text.length && !/[a-zA-Z]/.test(text[j])) j++;
                if (j >= text.length) { i++; continue; } // Incomplete sequence
                const code = text.slice(i+2, j);
                const cmd = text[j];

                if (cmd === 'm') {
                    const parts = code.split(';').map(Number);
                    for (let k = 0; k < parts.length; k++) {
                        const p = parts[k];
                        if (p === 0) currentStyle = {};
                        else if (p === 1) currentStyle.bold = true;
                        else if (p === 2) currentStyle.dim = true;
                        else if (p === 22) { currentStyle.bold = false; currentStyle.dim = false; }
                        else if (p === 7) currentStyle.inverse = true;
                        else if (p === 27) currentStyle.inverse = false;
                        else if (p >= 30 && p <= 37) currentStyle.fg = colors[p];
                        else if (p >= 90 && p <= 97) currentStyle.fg = colors[p];
                        else if (p === 39) delete currentStyle.fg;
                        else if (p === 38 && k + 2 < parts.length && parts[k+1] === 5) { currentStyle.fg = color256(parts[k+2]); k += 2; }
                        else if (p >= 40 && p <= 47) currentStyle.bg = colors[p-10];
                        else if (p === 49) delete currentStyle.bg;
                    }
                }
                i = j + 1;
            } else if (text[i] === '\r') {
                i++;
            } else if (text[i] === '\n') {
                result += '<br>';
                i++;
            } else {
                // Build style string
                let style = '';
                if (currentStyle.fg) style += `color:${currentStyle.fg};`;
                if (currentStyle.bg) style += `background:${currentStyle.bg};`;
                if (currentStyle.bold) style += 'font-weight:bold;';
                if (currentStyle.dim) style += 'opacity:0.6;';

                const char = this.escapeHtml(text[i]);
                if (style) {
                    result += `<span style="${style}">${char}</span>`;
                } else {
                    result += char;
                }
                i++;
            }
        }
        return result;
    }

    // ============== VIEW TOGGLE ==============

    setView(view) {
        this.currentView = view;

        // Update toggle buttons
        document.querySelectorAll('.view-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.view === view);
        });

        // Show/hide views
        const listView = document.getElementById('list-view');
        const kanbanView = document.getElementById('kanban-view');

        if (view === 'list') {
            listView.style.display = 'flex';
            kanbanView.style.display = 'none';
            this.renderSessions();
        } else {
            listView.style.display = 'none';
            kanbanView.style.display = 'flex';
            this.renderKanban();
        }
    }

    // ============== KANBAN BOARD ==============

    renderKanban() {
        const statuses = ['queued', 'running', 'needs_attention', 'completed'];
        const sessionsArray = Array.from(this.sessions.values());

        // Also include stopped/error in completed column
        const statusMap = {
            'queued': 'queued',
            'starting': 'running',
            'running': 'running',
            'needs_attention': 'needs_attention',
            'completed': 'completed',
            'stopped': 'completed',
            'error': 'completed'
        };

        // Group sessions by status, separating parents and children
        const columns = {};
        statuses.forEach(s => columns[s] = { parents: [], children: new Map() });

        sessionsArray.forEach(session => {
            const column = statusMap[session.status] || 'running';
            if (session.parent_id) {
                // It's a child - group under parent
                if (!columns[column].children.has(session.parent_id)) {
                    columns[column].children.set(session.parent_id, []);
                }
                columns[column].children.get(session.parent_id).push(session);
            } else {
                columns[column].parents.push(session);
            }
        });

        // Render each column
        statuses.forEach(status => {
            const container = document.getElementById(`kanban-${status}`);
            const countEl = document.getElementById(`kanban-count-${status}`);
            container.innerHTML = '';

            const { parents, children } = columns[status];
            const totalCount = parents.length + Array.from(children.values()).flat().length;
            countEl.textContent = totalCount;

            // Render parent cards with their children
            parents.forEach(parent => {
                const parentChildren = children.get(parent.id) || [];
                container.appendChild(this.createKanbanCard(parent, parentChildren));
            });

            // Render orphan children (parent in different column)
            children.forEach((childList, parentId) => {
                if (!parents.find(p => p.id === parentId)) {
                    childList.forEach(child => {
                        container.appendChild(this.createKanbanCard(child, [], true));
                    });
                }
            });
        });
    }

    createKanbanCard(session, children = [], isOrphan = false) {
        const card = document.createElement('div');
        card.className = `kanban-card ${session.id === this.activeSessionId ? 'active' : ''}`;
        card.dataset.sessionId = session.id;
        card.draggable = true;

        // Click to select
        card.onclick = (e) => {
            if (!e.target.closest('.kanban-child-card')) {
                this.selectSession(session.id);
            }
        };

        // Right-click for context menu
        card.oncontextmenu = (e) => {
            e.preventDefault();
            this.showContextMenu(e.clientX, e.clientY, session.id);
        };

        const statusBadge = this.getStatusBadge(session.status);
        const outputSnippet = session.last_output
            ? this.stripAnsi(session.last_output).slice(-80).trim()
            : '';

        let childrenHtml = '';
        if (children.length > 0) {
            childrenHtml = `
                <div class="kanban-card-children">
                    ${children.map(child => `
                        <div class="kanban-child-card" data-session-id="${child.id}"
                             onclick="app.selectSession(${child.id})"
                             oncontextmenu="event.preventDefault(); app.showContextMenu(event.clientX, event.clientY, ${child.id})">
                            <div class="kanban-card-name">
                                <span class="kanban-card-id">#${child.id}</span>
                                ${this.escapeHtml(child.name)}
                            </div>
                            ${this.getStatusBadge(child.status)}
                        </div>
                    `).join('')}
                </div>
            `;
        }

        const orphanLabel = isOrphan && session.parent_id
            ? `<span class="parent-info">child of #${session.parent_id}</span>`
            : '';

        card.innerHTML = `
            <div class="kanban-card-header">
                <div class="kanban-card-name">
                    <span class="kanban-card-id">#${session.id}</span>
                    ${this.escapeHtml(session.name)}
                    ${orphanLabel}
                </div>
                ${statusBadge}
            </div>
            ${outputSnippet ? `<div class="kanban-card-output">${this.escapeHtml(outputSnippet)}</div>` : ''}
            ${childrenHtml}
        `;

        return card;
    }

    getStatusBadge(status) {
        const labels = {
            'running': 'Running',
            'needs_attention': 'Attention',
            'stopped': 'Stopped',
            'error': 'Error',
            'starting': 'Starting',
            'queued': 'Queued',
            'completed': 'Completed'
        };
        return `<span class="status-badge status-${status}">${labels[status] || status}</span>`;
    }

    stripAnsi(text) {
        return text.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '').replace(/\x1b\][^\x07]*\x07/g, '');
    }

    // ============== CONTEXT MENU ==============

    setupContextMenu() {
        // Close context menu on click elsewhere
        document.addEventListener('click', () => this.hideContextMenu());
        document.addEventListener('contextmenu', (e) => {
            if (!e.target.closest('.kanban-card') && !e.target.closest('.session-card')) {
                this.hideContextMenu();
            }
        });
    }

    showContextMenu(x, y, sessionId) {
        this.contextMenuSessionId = sessionId;
        const menu = document.getElementById('context-menu');
        menu.style.left = x + 'px';
        menu.style.top = y + 'px';
        menu.classList.add('open');

        // Adjust if off-screen
        const rect = menu.getBoundingClientRect();
        if (rect.right > window.innerWidth) {
            menu.style.left = (x - rect.width) + 'px';
        }
        if (rect.bottom > window.innerHeight) {
            menu.style.top = (y - rect.height) + 'px';
        }
    }

    hideContextMenu() {
        document.getElementById('context-menu').classList.remove('open');
    }

    contextMenuSetParent() {
        this.hideContextMenu();
        this.showParentModal(this.contextMenuSessionId);
    }

    contextMenuRemoveParent() {
        this.hideContextMenu();
        this.updateSessionParent(this.contextMenuSessionId, null);
    }

    contextMenuComplete() {
        this.hideContextMenu();
        this.completeSession(this.contextMenuSessionId);
    }

    contextMenuStop() {
        this.hideContextMenu();
        if (confirm('Are you sure you want to stop this session?')) {
            this.stopSession(this.contextMenuSessionId);
        }
    }

    // ============== PARENT SELECTION MODAL ==============

    showParentModal(sessionId) {
        const session = this.sessions.get(sessionId);
        if (!session) return;

        const options = document.getElementById('parent-options');
        const eligibleParents = Array.from(this.sessions.values())
            .filter(s => s.id !== sessionId && s.parent_id !== sessionId);

        if (eligibleParents.length === 0) {
            options.innerHTML = '<p style="color: var(--text-secondary);">No other sessions available as parents.</p>';
        } else {
            options.innerHTML = eligibleParents.map(parent => `
                <div class="parent-option" onclick="app.selectParent(${sessionId}, ${parent.id})">
                    <span class="parent-option-id">#${parent.id}</span>
                    <span class="parent-option-name">${this.escapeHtml(parent.name)}</span>
                    ${this.getStatusBadge(parent.status)}
                </div>
            `).join('');
        }

        document.getElementById('parent-select-modal').classList.add('open');
    }

    closeParentModal() {
        document.getElementById('parent-select-modal').classList.remove('open');
    }

    selectParent(childId, parentId) {
        this.closeParentModal();
        this.updateSessionParent(childId, parentId);
    }

    async updateSessionParent(sessionId, parentId) {
        try {
            const response = await fetch(`/api/sessions/${sessionId}/parent`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ parent_id: parentId })
            });
            const data = await response.json();
            if (data.success) {
                // Update local session
                const session = this.sessions.get(sessionId);
                if (session) {
                    session.parent_id = parentId;
                    this.renderCurrentView();
                }
            }
        } catch (e) {
            console.error('Failed to update parent:', e);
        }
    }

    async completeSession(sessionId) {
        try {
            await fetch(`/api/sessions/${sessionId}/complete`, { method: 'POST' });
        } catch (e) {
            console.error('Failed to complete session:', e);
        }
    }

    renderCurrentView() {
        if (this.currentView === 'kanban') {
            this.renderKanban();
        } else {
            this.renderSessions();
        }
    }

    // ============== DRAG AND DROP ==============

    setupDragAndDrop() {
        document.addEventListener('dragstart', (e) => {
            const card = e.target.closest('.kanban-card');
            if (card) {
                this.draggedSessionId = parseInt(card.dataset.sessionId);
                card.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
            }
        });

        document.addEventListener('dragend', (e) => {
            const card = e.target.closest('.kanban-card');
            if (card) {
                card.classList.remove('dragging');
                this.draggedSessionId = null;
            }
            document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
            document.querySelectorAll('.column-drag-over').forEach(el => el.classList.remove('column-drag-over'));
        });

        document.addEventListener('dragover', (e) => {
            e.preventDefault();

            // Check if dragging over a card (for parent-child)
            const card = e.target.closest('.kanban-card');
            if (card && this.draggedSessionId && parseInt(card.dataset.sessionId) !== this.draggedSessionId) {
                card.classList.add('drag-over');
                return;
            }

            // Check if dragging over a column (for status change)
            const column = e.target.closest('.kanban-column');
            if (column && this.draggedSessionId) {
                // Remove drag-over from other columns
                document.querySelectorAll('.kanban-column').forEach(c => c.classList.remove('column-drag-over'));
                column.classList.add('column-drag-over');
            }
        });

        document.addEventListener('dragleave', (e) => {
            const card = e.target.closest('.kanban-card');
            if (card) {
                card.classList.remove('drag-over');
            }

            // Check if leaving a column
            const column = e.target.closest('.kanban-column');
            if (column && e.relatedTarget && !column.contains(e.relatedTarget)) {
                column.classList.remove('column-drag-over');
            }
        });

        document.addEventListener('drop', (e) => {
            e.preventDefault();

            // Check if dropping on a card (parent-child relationship)
            const targetCard = e.target.closest('.kanban-card');
            if (targetCard && this.draggedSessionId) {
                const targetId = parseInt(targetCard.dataset.sessionId);
                if (targetId !== this.draggedSessionId) {
                    // Set dragged session as child of target
                    this.updateSessionParent(this.draggedSessionId, targetId);
                }
            } else {
                // Check if dropping on a column (status change)
                const column = e.target.closest('.kanban-column');
                if (column && this.draggedSessionId) {
                    const targetStatus = column.dataset.status;
                    this.moveSessionToStatus(this.draggedSessionId, targetStatus);
                }
            }

            document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
            document.querySelectorAll('.column-drag-over').forEach(el => el.classList.remove('column-drag-over'));
        });
    }

    async moveSessionToStatus(sessionId, targetStatus) {
        const session = this.sessions.get(sessionId);
        if (!session) return;

        // Map target column to action
        switch (targetStatus) {
            case 'completed':
                // Mark as completed
                await this.completeSession(sessionId);
                break;
            case 'running':
                // If queued, we can't manually start it (depends on parent)
                // If stopped/completed, we'd need to restart - not supported yet
                if (session.status === 'queued') {
                    alert('Queued sessions will start automatically when their parent completes.');
                } else if (session.status === 'stopped' || session.status === 'completed') {
                    alert('Cannot restart stopped/completed sessions. Create a new session instead.');
                }
                break;
            case 'queued':
                // Would need a parent to be queued
                alert('To queue a session, set it as a child of a running session using the context menu.');
                break;
            case 'needs_attention':
                // This is system-determined, can't manually set
                alert('Sessions are marked "Needs Attention" automatically when they require input.');
                break;
        }
    }
}

// Initialize app
const app = new UltraClaude();

// Global functions for HTML onclick handlers
function createSession() {
    document.getElementById('new-session-modal').classList.add('open');
    document.getElementById('session-name').focus();
}

function closeModal() {
    document.getElementById('new-session-modal').classList.remove('open');
    document.getElementById('session-name').value = '';
    document.getElementById('session-dir').value = '';
}

function confirmCreateSession() {
    const name = document.getElementById('session-name').value;
    const dir = document.getElementById('session-dir').value;
    app.createSession(name, dir);
    closeModal();
}

function handleInput(event) {
    if (event.key === 'Enter') {
        app.sendInput();
    }
}

function sendInput() {
    app.sendInput();
}

function clearTerminal() {
    app.clearTerminal();
}

function stopActiveSession() {
    if (app.activeSessionId) {
        if (confirm('Are you sure you want to stop this session?')) {
            app.stopSession(app.activeSessionId);
        }
    }
}

// Close modal on escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeModal();
    }
});

// Close modal on outside click
document.getElementById('new-session-modal').addEventListener('click', (e) => {
    if (e.target.id === 'new-session-modal') {
        closeModal();
    }
});
