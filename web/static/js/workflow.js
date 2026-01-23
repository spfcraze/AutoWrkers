const workflowApp = {
    executions: [],
    templates: [],
    selectedExecution: null,
    ws: null,
    currentFilter: 'all',

    async init() {
        await this.loadTemplates();
        await this.loadExecutions();
        this.updateStats();
    },

    async loadTemplates() {
        try {
            const response = await fetch('/api/workflow/templates');
            const data = await response.json();
            this.templates = data.templates || [];
            this.populateTemplateSelect();
        } catch (error) {
            console.error('Failed to load templates:', error);
        }
    },

    async loadExecutions() {
        try {
            const response = await fetch('/api/workflow/executions?limit=100');
            const data = await response.json();
            this.executions = data.executions || [];
            this.renderExecutionList();
        } catch (error) {
            console.error('Failed to load executions:', error);
        }
    },

    populateTemplateSelect() {
        const select = document.getElementById('workflow-template');
        select.innerHTML = '<option value="">Select a template...</option>';
        
        this.templates.forEach(template => {
            const option = document.createElement('option');
            option.value = template.id;
            option.textContent = template.name;
            if (template.is_default) {
                option.selected = true;
            }
            select.appendChild(option);
        });
    },

    renderExecutionList() {
        const container = document.getElementById('execution-list');
        const filtered = this.filterExecutionList(this.executions);
        
        if (filtered.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">⚙</div>
                    <p>No workflows yet</p>
                </div>
            `;
            return;
        }

        container.innerHTML = filtered.map(exec => `
            <div class="execution-card ${this.selectedExecution?.id === exec.id ? 'active' : ''}" 
                 onclick="workflowApp.selectExecution('${exec.id}')">
                <div class="execution-card-header">
                    <span class="execution-card-title" title="${exec.task_description || 'Workflow'}">
                        ${this.truncate(exec.task_description || 'Workflow', 25)}
                    </span>
                    <span class="execution-card-status status-${exec.status}">${exec.status}</span>
                </div>
                <div class="execution-card-meta">
                    <span>${this.formatDate(exec.created_at)}</span>
                    <span>${exec.phases_completed || 0}/${exec.phases_total || 0} phases</span>
                </div>
            </div>
        `).join('');
    },

    filterExecutionList(executions) {
        if (this.currentFilter === 'all') return executions;
        if (this.currentFilter === 'running') {
            return executions.filter(e => e.status === 'running' || e.status === 'pending');
        }
        if (this.currentFilter === 'completed') {
            return executions.filter(e => e.status === 'completed' || e.status === 'failed');
        }
        return executions;
    },

    filterExecutions(filter) {
        this.currentFilter = filter;
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.filter === filter);
        });
        this.renderExecutionList();
    },

    async selectExecution(executionId) {
        try {
            const response = await fetch(`/api/workflow/executions/${executionId}`);
            const data = await response.json();
            this.selectedExecution = data.execution;
            
            this.renderExecutionList();
            this.renderPipeline(data.execution, data.artifacts);
            this.renderBudget(data.budget);
            this.connectWebSocket(executionId);
        } catch (error) {
            console.error('Failed to load execution:', error);
        }
    },

    renderPipeline(execution, artifacts) {
        const header = document.getElementById('pipeline-header');
        const view = document.getElementById('pipeline-view');
        
        document.getElementById('pipeline-title').textContent = 
            this.truncate(execution.task_description || 'Workflow', 50);
        
        const statusEl = document.getElementById('pipeline-status');
        statusEl.className = `pipeline-status status-${execution.status}`;
        statusEl.textContent = execution.status;

        const actionsEl = document.getElementById('pipeline-actions');
        actionsEl.innerHTML = this.renderActions(execution);

        if (!execution.phase_executions || execution.phase_executions.length === 0) {
            view.innerHTML = `
                <div class="pipeline-placeholder">
                    <div class="placeholder-icon">⚙</div>
                    <p>No phases configured</p>
                </div>
            `;
            return;
        }

        const phases = this.groupPhases(execution.phase_executions);
        view.innerHTML = `<div class="pipeline-container">${phases}</div>`;
    },

    groupPhases(phases) {
        const sorted = [...phases].sort((a, b) => (a.order || 0) - (b.order || 0));
        let html = '';
        let i = 0;

        while (i < sorted.length) {
            const phase = sorted[i];
            const parallel = sorted.filter(p => p.parallel_with === phase.phase_id);
            
            if (parallel.length > 0) {
                html += `<div class="pipeline-phase">
                    <div class="parallel-group">
                        ${this.renderPhaseCard(phase)}
                        ${parallel.map(p => this.renderPhaseCard(p)).join('')}
                    </div>
                    ${i < sorted.length - parallel.length - 1 ? '<div class="phase-connector"></div>' : ''}
                </div>`;
                i += parallel.length + 1;
            } else if (!sorted.some(p => p.parallel_with === phase.phase_id)) {
                html += `<div class="pipeline-phase">
                    ${this.renderPhaseCard(phase)}
                    ${i < sorted.length - 1 ? '<div class="phase-connector"></div>' : ''}
                </div>`;
                i++;
            } else {
                i++;
            }
        }

        return html;
    },

    renderPhaseCard(phase) {
        const providerType = phase.provider_type || 'claude';
        const statusIcon = this.getStatusIcon(phase.status);
        const duration = phase.duration_seconds 
            ? this.formatDuration(phase.duration_seconds) 
            : '--:--';

        return `
            <div class="phase-card phase-${phase.status}" onclick="workflowApp.showPhaseDetails('${phase.id}')">
                <div class="phase-header">
                    <span class="phase-name">${phase.phase_name || phase.name}</span>
                    <span class="phase-status-icon">${statusIcon}</span>
                </div>
                <div class="phase-provider">
                    <span class="provider-badge provider-${providerType}">${providerType}</span>
                    <span>${phase.model_name || ''}</span>
                </div>
                <div class="phase-meta">
                    <span>${phase.role || ''}</span>
                    <span class="phase-duration">${duration}</span>
                </div>
            </div>
        `;
    },

    renderActions(execution) {
        const actions = [];
        
        if (execution.status === 'pending') {
            actions.push(`<button class="btn btn-primary" onclick="workflowApp.runExecution('${execution.id}')">Run</button>`);
        }
        if (execution.status === 'running') {
            actions.push(`<button class="btn btn-danger" onclick="workflowApp.cancelExecution('${execution.id}')">Cancel</button>`);
        }
        if (execution.status === 'paused') {
            actions.push(`<button class="btn btn-primary" onclick="workflowApp.resumeExecution('${execution.id}')">Resume</button>`);
            actions.push(`<button class="btn btn-danger" onclick="workflowApp.cancelExecution('${execution.id}')">Cancel</button>`);
        }
        if (['completed', 'failed', 'cancelled'].includes(execution.status)) {
            actions.push(`<button class="btn" onclick="workflowApp.showArtifacts('${execution.id}')">View Artifacts</button>`);
        }

        return actions.join('');
    },

    renderBudget(budget) {
        if (!budget) return;
        
        const fill = document.getElementById('budget-fill');
        const text = document.getElementById('budget-text');
        
        const used = budget.total_cost || 0;
        const limit = budget.limit || 0;
        const percent = limit > 0 ? Math.min((used / limit) * 100, 100) : 0;
        
        fill.style.width = limit > 0 ? `${percent}%` : '0%';
        fill.className = 'budget-fill';
        if (percent > 80) fill.classList.add('danger');
        else if (percent > 50) fill.classList.add('warning');
        
        text.textContent = limit > 0 
            ? `$${used.toFixed(2)} / $${limit.toFixed(2)}`
            : `$${used.toFixed(2)}`;
    },

    async runExecution(executionId) {
        try {
            await fetch(`/api/workflow/executions/${executionId}/run`, { method: 'POST' });
            await this.selectExecution(executionId);
        } catch (error) {
            console.error('Failed to run execution:', error);
        }
    },

    async cancelExecution(executionId) {
        try {
            await fetch(`/api/workflow/executions/${executionId}/cancel`, { method: 'POST' });
            await this.selectExecution(executionId);
        } catch (error) {
            console.error('Failed to cancel execution:', error);
        }
    },

    async resumeExecution(executionId) {
        try {
            await fetch(`/api/workflow/executions/${executionId}/resume`, { method: 'POST' });
            await this.selectExecution(executionId);
        } catch (error) {
            console.error('Failed to resume execution:', error);
        }
    },

    connectWebSocket(executionId) {
        if (this.ws) {
            this.ws.close();
        }

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.ws = new WebSocket(`${protocol}//${window.location.host}/api/workflow/ws/${executionId}`);

        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleWebSocketMessage(data);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    },

    handleWebSocketMessage(data) {
        if (data.type === 'phase_update' || data.type === 'execution_update') {
            this.selectExecution(this.selectedExecution.id);
        }
        if (data.type === 'init') {
            this.renderPipeline(data.execution, []);
        }
    },

    showPhaseDetails(phaseId) {
        const phase = this.selectedExecution?.phase_executions?.find(p => p.id === phaseId);
        if (!phase) return;

        const detailsPanel = document.getElementById('workflow-details');
        const content = document.getElementById('details-content');
        
        content.innerHTML = `
            <div class="detail-section">
                <div class="detail-section-title">Phase Info</div>
                <div class="detail-row">
                    <span class="detail-label">Name</span>
                    <span class="detail-value">${phase.phase_name || phase.name}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Status</span>
                    <span class="detail-value">${phase.status}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Provider</span>
                    <span class="detail-value">${phase.provider_type || 'N/A'}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Model</span>
                    <span class="detail-value">${phase.model_name || 'N/A'}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Duration</span>
                    <span class="detail-value">${phase.duration_seconds ? this.formatDuration(phase.duration_seconds) : 'N/A'}</span>
                </div>
            </div>
            ${phase.tokens_used ? `
            <div class="detail-section">
                <div class="detail-section-title">Usage</div>
                <div class="detail-row">
                    <span class="detail-label">Input Tokens</span>
                    <span class="detail-value">${phase.tokens_used.input || 0}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Output Tokens</span>
                    <span class="detail-value">${phase.tokens_used.output || 0}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Cost</span>
                    <span class="detail-value">$${(phase.cost || 0).toFixed(4)}</span>
                </div>
            </div>` : ''}
            ${phase.error ? `
            <div class="detail-section">
                <div class="detail-section-title">Error</div>
                <pre style="color: var(--accent-red); font-size: 12px; white-space: pre-wrap;">${phase.error}</pre>
            </div>` : ''}
        `;

        detailsPanel.classList.add('open');
    },

    closeDetails() {
        document.getElementById('workflow-details').classList.remove('open');
    },

    async showArtifacts(executionId) {
        try {
            const response = await fetch(`/api/workflow/executions/${executionId}/artifacts`);
            const data = await response.json();
            
            const detailsPanel = document.getElementById('workflow-details');
            const content = document.getElementById('details-content');
            
            if (!data.artifacts || data.artifacts.length === 0) {
                content.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">📄</div>
                        <p>No artifacts</p>
                    </div>
                `;
            } else {
                content.innerHTML = `
                    <div class="detail-section">
                        <div class="detail-section-title">Artifacts (${data.artifacts.length})</div>
                        <div class="artifact-list">
                            ${data.artifacts.map(a => `
                                <div class="artifact-item" onclick="workflowApp.viewArtifact('${a.id}')">
                                    <div class="artifact-name">${a.name || a.artifact_type}</div>
                                    <div class="artifact-type">${a.artifact_type} - ${a.phase_name || ''}</div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            }

            detailsPanel.classList.add('open');
        } catch (error) {
            console.error('Failed to load artifacts:', error);
        }
    },

    async viewArtifact(artifactId) {
        try {
            const response = await fetch(`/api/workflow/artifacts/${artifactId}/content`);
            const data = await response.json();
            
            document.getElementById('artifact-title').textContent = `Artifact: ${artifactId}`;
            document.getElementById('artifact-content').innerHTML = `<pre>${this.escapeHtml(data.content || '')}</pre>`;
            document.getElementById('artifact-modal').classList.add('open');
        } catch (error) {
            console.error('Failed to load artifact:', error);
        }
    },

    closeArtifactModal() {
        document.getElementById('artifact-modal').classList.remove('open');
    },

    openNewWorkflowModal() {
        document.getElementById('new-workflow-modal').classList.add('open');
    },

    closeNewWorkflowModal() {
        document.getElementById('new-workflow-modal').classList.remove('open');
    },

    async createWorkflow() {
        const task = document.getElementById('workflow-task').value.trim();
        const path = document.getElementById('workflow-path').value.trim();
        const templateId = document.getElementById('workflow-template').value;
        const budget = document.getElementById('workflow-budget').value;
        const interactive = document.getElementById('workflow-interactive').checked;

        if (!task) {
            alert('Please enter a task description');
            return;
        }

        try {
            const response = await fetch('/api/workflow/executions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    task_description: task,
                    project_path: path,
                    template_id: templateId || null,
                    budget_limit: budget ? parseFloat(budget) : null,
                    interactive_mode: interactive
                })
            });

            const data = await response.json();
            
            if (data.success) {
                this.closeNewWorkflowModal();
                await this.loadExecutions();
                await this.selectExecution(data.execution.id);
                
                await fetch(`/api/workflow/executions/${data.execution.id}/run`, { method: 'POST' });
                await this.selectExecution(data.execution.id);
            } else {
                alert('Failed to create workflow: ' + (data.detail || 'Unknown error'));
            }
        } catch (error) {
            console.error('Failed to create workflow:', error);
            alert('Failed to create workflow');
        }
    },

    updateStats() {
        const total = this.executions.length;
        const running = this.executions.filter(e => e.status === 'running').length;
        
        document.getElementById('workflow-count').textContent = `${total} workflow${total !== 1 ? 's' : ''}`;
        document.getElementById('running-count').textContent = `${running} running`;
    },

    getStatusIcon(status) {
        const icons = {
            pending: '○',
            running: '◐',
            completed: '●',
            failed: '✕',
            skipped: '−',
            cancelled: '◌'
        };
        return icons[status] || '○';
    },

    formatDate(dateStr) {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    },

    formatDuration(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    },

    truncate(str, len) {
        if (!str) return '';
        return str.length > len ? str.substring(0, len) + '...' : str;
    },

    escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    },

    currentBrowsePath: '~',

    async openBrowseModal() {
        document.getElementById('browse-modal').classList.add('open');
        await this.browseTo('~');
    },

    closeBrowseModal() {
        document.getElementById('browse-modal').classList.remove('open');
    },

    async browseTo(path) {
        try {
            const response = await fetch(`/api/browse-dirs?path=${encodeURIComponent(path)}`);
            const data = await response.json();
            
            if (data.error) {
                console.error('Browse error:', data.error);
            }
            
            this.currentBrowsePath = data.path;
            document.getElementById('browse-current-path').textContent = data.path;
            
            const list = document.getElementById('browse-list');
            
            if (data.dirs.length === 0) {
                list.innerHTML = '<div class="browse-empty">No subdirectories</div>';
                return;
            }
            
            list.innerHTML = data.dirs.map(dir => `
                <div class="browse-item" ondblclick="workflowApp.browseTo('${dir.path.replace(/'/g, "\\'")}')">
                    <span class="browse-item-icon">${dir.is_git ? '📁' : '📂'}</span>
                    <span class="browse-item-name">${dir.name}</span>
                    ${dir.is_git ? '<span class="browse-item-git">git</span>' : ''}
                </div>
            `).join('');
        } catch (error) {
            console.error('Failed to browse:', error);
        }
    },

    async browseUp() {
        const response = await fetch(`/api/browse-dirs?path=${encodeURIComponent(this.currentBrowsePath)}`);
        const data = await response.json();
        if (data.parent) {
            await this.browseTo(data.parent);
        }
    },

    selectCurrentPath() {
        document.getElementById('workflow-path').value = this.currentBrowsePath;
        this.closeBrowseModal();
    }
};

document.addEventListener('DOMContentLoaded', () => {
    workflowApp.init();
});
