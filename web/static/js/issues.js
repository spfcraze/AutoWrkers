class Toast {
    static container = null;

    static init() {
        if (!Toast.container) {
            Toast.container = document.createElement('div');
            Toast.container.className = 'toast-container';
            document.body.appendChild(Toast.container);
        }
    }

    static show(type, title, message, duration = 5000) {
        Toast.init();
        const icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <span class="toast-icon">${icons[type] || icons.info}</span>
            <div class="toast-content">
                <div class="toast-title">${Toast.escapeHtml(title)}</div>
                ${message ? `<div class="toast-message">${Toast.escapeHtml(message)}</div>` : ''}
            </div>
            <button class="toast-close" onclick="this.parentElement.remove()">×</button>
        `;
        Toast.container.appendChild(toast);
        if (duration > 0) {
            setTimeout(() => {
                toast.classList.add('toast-hiding');
                setTimeout(() => toast.remove(), 300);
            }, duration);
        }
        return toast;
    }

    static success(title, message, duration) { return Toast.show('success', title, message, duration); }
    static error(title, message, duration = 8000) { return Toast.show('error', title, message, duration); }
    static warning(title, message, duration) { return Toast.show('warning', title, message, duration); }
    static info(title, message, duration) { return Toast.show('info', title, message, duration); }
    static escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

class IssuesManager {
    constructor() {
        this.issues = [];
        this.projects = new Map();
        this.currentView = 'pipeline';
        this.currentFilter = 'all';
        this.searchQuery = '';
        this.pollInterval = null;

        this.init();
    }

    async init() {
        await Promise.all([this.loadProjects(), this.loadIssues()]);
        this.render();
        this.startPolling();
    }

    async loadProjects() {
        try {
            const response = await fetch('/api/projects');
            const data = await response.json();
            this.projects.clear();
            (data.projects || []).forEach(p => this.projects.set(p.id, p));
        } catch (e) {
            console.error('Failed to load projects:', e);
        }
    }

    async loadIssues() {
        try {
            const response = await fetch('/api/issue-sessions');
            const data = await response.json();
            this.issues = data.issue_sessions || [];
            this.updateStats();
        } catch (e) {
            console.error('Failed to load issues:', e);
        }
    }

    startPolling() {
        this.pollInterval = setInterval(() => this.loadIssues().then(() => this.render()), 5000);
    }

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    updateStats() {
        const total = this.issues.length;
        const inProgress = this.issues.filter(i => i.status === 'in_progress').length;
        const prCreated = this.issues.filter(i => i.status === 'pr_created').length;
        const failed = this.issues.filter(i => i.status === 'failed').length;

        document.getElementById('issue-stats').textContent = 
            `${total} issues | ${inProgress} in progress | ${prCreated} PRs | ${failed} failed`;
    }

    setView(view) {
        this.currentView = view;
        document.querySelectorAll('.view-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.view === view);
        });
        document.getElementById('pipeline-view').style.display = view === 'pipeline' ? 'flex' : 'none';
        document.getElementById('list-view').style.display = view === 'list' ? 'flex' : 'none';
        this.render();
    }

    setFilter(filter) {
        this.currentFilter = filter;
        document.querySelectorAll('.list-filters .filter-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.filter === filter);
        });
        this.render();
    }

    handleSearch(query) {
        this.searchQuery = query.toLowerCase();
        this.render();
    }

    getFilteredIssues() {
        let filtered = this.issues;
        if (this.currentFilter !== 'all') {
            filtered = filtered.filter(i => i.status === this.currentFilter);
        }
        if (this.searchQuery) {
            filtered = filtered.filter(i => 
                (i.github_issue_title || '').toLowerCase().includes(this.searchQuery) ||
                String(i.github_issue_number).includes(this.searchQuery) ||
                (this.projects.get(i.project_id)?.name || '').toLowerCase().includes(this.searchQuery)
            );
        }
        return filtered;
    }

    render() {
        if (this.currentView === 'pipeline') {
            this.renderPipeline();
        } else {
            this.renderList();
        }
    }

    renderPipeline() {
        const statusGroups = {
            'pending': [],
            'in_progress': [],
            'verifying': [],
            'pr_created': [],
            'failed': []
        };

        const statusMapping = {
            'pending': 'pending',
            'queued': 'pending',
            'in_progress': 'in_progress',
            'verifying': 'verifying',
            'verification_failed': 'failed',
            'pr_created': 'pr_created',
            'completed': 'pr_created',
            'failed': 'failed',
            'skipped': 'failed'
        };

        this.issues.forEach(issue => {
            const group = statusMapping[issue.status] || 'pending';
            if (statusGroups[group]) {
                statusGroups[group].push(issue);
            }
        });

        Object.keys(statusGroups).forEach(status => {
            const container = document.getElementById(`cards-${status}`);
            const countEl = document.getElementById(`count-${status}`);
            if (!container) return;

            const issues = statusGroups[status];
            countEl.textContent = issues.length;

            if (issues.length === 0) {
                container.innerHTML = '<div class="empty-state"><p>No issues</p></div>';
                return;
            }

            container.innerHTML = issues.map(issue => this.createPipelineCard(issue)).join('');
        });
    }

    createPipelineCard(issue) {
        const project = this.projects.get(issue.project_id);
        const projectName = project ? project.github_repo : 'Unknown';
        const labels = (issue.github_issue_labels || []).slice(0, 2);
        
        const progressSteps = this.getProgressSteps(issue);
        const prLink = issue.pr_url 
            ? `<a href="${issue.pr_url}" target="_blank" class="pr-link" onclick="event.stopPropagation()">🔗 PR #${issue.pr_number}</a>` 
            : '';

        return `
            <div class="issue-card" onclick="issuesManager.showIssueDetail(${issue.id})">
                <div class="issue-card-project">${this.escapeHtml(projectName)}</div>
                <div class="issue-card-header">
                    <span class="issue-card-title">
                        <span class="issue-number">#${issue.github_issue_number}</span>
                        ${this.escapeHtml(issue.github_issue_title || 'Untitled')}
                    </span>
                </div>
                ${labels.length ? `
                    <div class="issue-card-labels">
                        ${labels.map(l => `<span class="issue-label">${this.escapeHtml(l)}</span>`).join('')}
                    </div>
                ` : ''}
                <div class="issue-progress">
                    ${progressSteps}
                </div>
                <div class="issue-card-footer">
                    <span>${issue.attempts > 0 ? `Attempt ${issue.attempts}/${issue.max_attempts}` : ''}</span>
                    <div class="issue-card-actions">
                        ${prLink}
                        ${this.getActionButtons(issue)}
                    </div>
                </div>
            </div>
        `;
    }

    getProgressSteps(issue) {
        const steps = ['analyze', 'fix', 'verify', 'pr'];
        const statusProgress = {
            'pending': 0,
            'queued': 0,
            'in_progress': 1,
            'verifying': 2,
            'verification_failed': 2,
            'pr_created': 4,
            'completed': 4,
            'failed': -1,
            'skipped': -1
        };

        const progress = statusProgress[issue.status] ?? 0;
        const failed = issue.status === 'failed' || issue.status === 'verification_failed';

        return steps.map((step, i) => {
            let className = 'progress-step';
            if (failed && i === progress - 1) {
                className += ' failed';
            } else if (i < progress) {
                className += ' completed';
            } else if (i === progress && !failed) {
                className += ' active';
            }
            return `<div class="${className}" title="${step}"></div>`;
        }).join('');
    }

    getActionButtons(issue) {
        const buttons = [];
        if (issue.status === 'pending' || issue.status === 'failed') {
            buttons.push(`<button class="btn btn-small btn-primary" onclick="event.stopPropagation(); issuesManager.startIssue(${issue.id})">▶</button>`);
        }
        if (issue.status === 'failed') {
            buttons.push(`<button class="btn btn-small" onclick="event.stopPropagation(); issuesManager.retryIssue(${issue.id})">🔄</button>`);
        }
        return buttons.join('');
    }

    renderList() {
        const filtered = this.getFilteredIssues();
        const container = document.getElementById('list-content');

        if (filtered.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">📋</div>
                    <p>No issues found</p>
                </div>
            `;
            return;
        }

        const statusLabels = {
            'pending': 'Pending',
            'queued': 'Queued',
            'in_progress': 'In Progress',
            'verifying': 'Verifying',
            'verification_failed': 'Verification Failed',
            'pr_created': 'PR Created',
            'completed': 'Completed',
            'failed': 'Failed',
            'skipped': 'Skipped'
        };

        container.innerHTML = `
            <table class="list-table">
                <thead>
                    <tr>
                        <th>Issue</th>
                        <th>Project</th>
                        <th>Status</th>
                        <th>Attempts</th>
                        <th>PR</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${filtered.map(issue => {
                        const project = this.projects.get(issue.project_id);
                        return `
                            <tr onclick="issuesManager.showIssueDetail(${issue.id})" style="cursor: pointer;">
                                <td class="issue-title">
                                    <span class="issue-number">#${issue.github_issue_number}</span>
                                    ${this.escapeHtml(issue.github_issue_title || 'Untitled')}
                                </td>
                                <td>${this.escapeHtml(project?.name || 'Unknown')}</td>
                                <td><span class="status-badge status-${issue.status}">${statusLabels[issue.status] || issue.status}</span></td>
                                <td>${issue.attempts}/${issue.max_attempts}</td>
                                <td>${issue.pr_url ? `<a href="${issue.pr_url}" target="_blank" onclick="event.stopPropagation()">PR #${issue.pr_number}</a>` : '-'}</td>
                                <td onclick="event.stopPropagation()">${this.getActionButtons(issue)}</td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        `;
    }

    async startIssue(issueId) {
        try {
            const response = await fetch(`/api/issue-sessions/${issueId}/start`, { method: 'POST' });
            const data = await response.json();
            if (data.success) {
                Toast.success('Issue Started', 'Session started for this issue');
                await this.loadIssues();
                this.render();
            } else {
                Toast.error('Start Failed', data.detail || 'Unknown error');
            }
        } catch (e) {
            console.error('Failed to start issue:', e);
            Toast.error('Start Failed', 'Failed to start issue session');
        }
    }

    async retryIssue(issueId) {
        try {
            const response = await fetch(`/api/issue-sessions/${issueId}/retry`, { method: 'POST' });
            const data = await response.json();
            if (data.success) {
                Toast.success('Retry Queued', 'Issue will be retried');
                await this.loadIssues();
                this.render();
            } else {
                Toast.error('Retry Failed', data.detail || 'Unknown error');
            }
        } catch (e) {
            console.error('Failed to retry issue:', e);
            Toast.error('Retry Failed', 'Failed to retry issue');
        }
    }

    async showIssueDetail(issueId) {
        try {
            const response = await fetch(`/api/issue-sessions/${issueId}`);
            const data = await response.json();
            const issue = data.issue_session;
            const project = this.projects.get(issue.project_id);

            const statusLabels = {
                'pending': 'Pending',
                'queued': 'Queued',
                'in_progress': 'In Progress',
                'verifying': 'Verifying',
                'verification_failed': 'Verification Failed',
                'pr_created': 'PR Created',
                'completed': 'Completed',
                'failed': 'Failed',
                'skipped': 'Skipped'
            };

            const content = document.getElementById('issue-detail-content');
            content.innerHTML = `
                <div class="issue-detail-header">
                    <div class="issue-detail-title">
                        <span class="issue-number">#${issue.github_issue_number}</span>
                        ${this.escapeHtml(issue.github_issue_title || 'Untitled')}
                    </div>
                    <div class="issue-detail-meta">
                        <span class="status-badge status-${issue.status}">${statusLabels[issue.status] || issue.status}</span>
                        <span>Project: ${this.escapeHtml(project?.name || 'Unknown')}</span>
                        ${issue.github_issue_url ? `<a href="${issue.github_issue_url}" target="_blank">View on GitHub</a>` : ''}
                        ${issue.pr_url ? `<a href="${issue.pr_url}" target="_blank">View PR #${issue.pr_number}</a>` : ''}
                    </div>
                </div>

                <div class="issue-detail-body">${this.escapeHtml(issue.github_issue_body || 'No description')}</div>

                ${issue.last_error ? `
                    <div style="background: rgba(248, 81, 73, 0.1); padding: 12px; border-radius: 6px; margin-bottom: 16px;">
                        <strong style="color: var(--accent-red);">Last Error:</strong>
                        <p style="margin-top: 8px;">${this.escapeHtml(issue.last_error)}</p>
                    </div>
                ` : ''}

                ${issue.verification_results && issue.verification_results.length > 0 ? `
                    <div class="verification-results">
                        <h4>Verification Results</h4>
                        ${issue.verification_results.map(r => `
                            <div class="verification-item">
                                <span class="verification-icon">${r.passed ? '✅' : '❌'}</span>
                                <span>${r.check_type}</span>
                                <span style="margin-left: auto; color: var(--text-secondary);">${r.duration_ms}ms</span>
                            </div>
                            ${r.output ? `<div class="verification-output">${this.escapeHtml(r.output)}</div>` : ''}
                        `).join('')}
                    </div>
                ` : ''}

                <div style="margin-top: 16px; display: flex; gap: 8px;">
                    ${issue.status === 'pending' || issue.status === 'failed' ? 
                        `<button class="btn btn-primary" onclick="issuesManager.startIssue(${issue.id}); closeIssueModal();">▶ Start</button>` : ''}
                    ${issue.status === 'failed' ? 
                        `<button class="btn" onclick="issuesManager.retryIssue(${issue.id}); closeIssueModal();">🔄 Retry</button>` : ''}
                </div>
            `;

            document.getElementById('issue-detail-modal').classList.add('open');

        } catch (e) {
            console.error('Failed to load issue detail:', e);
            Toast.error('Load Failed', 'Failed to load issue details');
        }
    }

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

const issuesManager = new IssuesManager();

function closeIssueModal() {
    document.getElementById('issue-detail-modal').classList.remove('open');
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeIssueModal();
});

document.getElementById('issue-detail-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'issue-detail-modal') closeIssueModal();
});
