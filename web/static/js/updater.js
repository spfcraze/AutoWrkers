const UpdateChecker = {
    updateInfo: null,
    checkInterval: null,

    async init() {
        await this.checkForUpdates();
        this.checkInterval = setInterval(() => this.checkForUpdates(), 3600000);
    },

    async checkForUpdates() {
        try {
            const response = await fetch('/api/update/check');
            const data = await response.json();
            this.updateInfo = data;
            this.updateUI();
        } catch (error) {
            console.error('Failed to check for updates:', error);
        }
    },

    updateUI() {
        let indicator = document.getElementById('update-indicator');
        
        if (!indicator) {
            indicator = document.createElement('div');
            indicator.id = 'update-indicator';
            indicator.className = 'update-indicator';
            indicator.onclick = () => this.showUpdateModal();
            
            const header = document.querySelector('.header');
            if (header) {
                const logo = header.querySelector('.logo');
                if (logo) {
                    logo.parentNode.insertBefore(indicator, logo.nextSibling);
                }
            }
        }

        if (!this.updateInfo) {
            indicator.style.display = 'none';
            return;
        }

        const update = this.updateInfo.update;
        
        if (update.update_available) {
            indicator.style.display = 'flex';
            indicator.innerHTML = `
                <span class="update-dot"></span>
                <span class="update-text">Update available: v${update.latest_version}</span>
            `;
            indicator.className = 'update-indicator has-update';
        } else {
            indicator.style.display = 'flex';
            indicator.innerHTML = `
                <span class="update-version">v${update.current_version}</span>
            `;
            indicator.className = 'update-indicator';
        }
    },

    showUpdateModal() {
        let modal = document.getElementById('update-modal');
        
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'update-modal';
            modal.className = 'modal';
            modal.innerHTML = `
                <div class="modal-content modal-medium">
                    <div class="modal-header">
                        <h3>Software Update</h3>
                        <button class="btn btn-small" onclick="UpdateChecker.closeModal()">×</button>
                    </div>
                    <div class="update-modal-body" id="update-modal-body"></div>
                    <div class="modal-actions" id="update-modal-actions"></div>
                </div>
            `;
            document.body.appendChild(modal);
        }

        this.renderModalContent();
        modal.classList.add('open');
    },

    closeModal() {
        const modal = document.getElementById('update-modal');
        if (modal) {
            modal.classList.remove('open');
        }
    },

    renderModalContent() {
        const body = document.getElementById('update-modal-body');
        const actions = document.getElementById('update-modal-actions');
        
        if (!this.updateInfo) {
            body.innerHTML = '<p>Checking for updates...</p>';
            actions.innerHTML = '<button class="btn" onclick="UpdateChecker.closeModal()">Close</button>';
            return;
        }

        const update = this.updateInfo.update;
        const git = this.updateInfo.git;

        let statusHtml = '';
        
        if (update.error) {
            statusHtml = `
                <div class="update-status update-error">
                    <span class="update-icon">⚠</span>
                    <div>
                        <div class="update-status-title">Could not check for updates</div>
                        <div class="update-status-detail">${this.escapeHtml(update.error)}</div>
                    </div>
                </div>
            `;
        } else if (update.update_available) {
            statusHtml = `
                <div class="update-status update-available">
                    <span class="update-icon">↑</span>
                    <div>
                        <div class="update-status-title">Update available!</div>
                        <div class="update-status-detail">
                            v${update.current_version} → v${update.latest_version}
                        </div>
                    </div>
                </div>
            `;
            
            if (update.release_notes) {
                statusHtml += `
                    <div class="update-notes">
                        <div class="update-notes-title">Release Notes</div>
                        <div class="update-notes-content">${this.escapeHtml(update.release_notes)}</div>
                    </div>
                `;
            }
        } else {
            statusHtml = `
                <div class="update-status update-current">
                    <span class="update-icon">✓</span>
                    <div>
                        <div class="update-status-title">You're up to date</div>
                        <div class="update-status-detail">Version ${update.current_version}</div>
                    </div>
                </div>
            `;
        }

        if (git.is_git) {
            statusHtml += `
                <div class="update-git-info">
                    <div class="update-git-row">
                        <span class="update-git-label">Branch:</span>
                        <span class="update-git-value">${git.branch || 'unknown'}</span>
                    </div>
                    <div class="update-git-row">
                        <span class="update-git-label">Commit:</span>
                        <span class="update-git-value">${git.local_commit || 'unknown'}</span>
                    </div>
                    ${git.has_uncommitted_changes ? `
                        <div class="update-git-warning">
                            ⚠ You have uncommitted changes
                        </div>
                    ` : ''}
                </div>
            `;
        } else {
            statusHtml += `
                <div class="update-git-info">
                    <div class="update-git-row">
                        <span class="update-git-label">Install Type:</span>
                        <span class="update-git-value">Standalone (no git)</span>
                    </div>
                    <div class="update-git-info-note">
                        Updates will be downloaded directly from GitHub.
                        Your data and settings will be preserved.
                    </div>
                </div>
            `;
        }

        body.innerHTML = statusHtml;

        let actionsHtml = '';

        if (update.update_available) {
            // Show install button for both git and non-git installations
            actionsHtml = `
                <button class="btn" onclick="UpdateChecker.closeModal()">Later</button>
                <button class="btn btn-primary" onclick="UpdateChecker.confirmAndInstall()" id="update-install-btn">
                    Download & Install Update
                </button>
            `;
        } else {
            actionsHtml = `
                <button class="btn" onclick="UpdateChecker.checkForUpdates(); UpdateChecker.renderModalContent();">
                    Check Again
                </button>
                <button class="btn btn-primary" onclick="UpdateChecker.closeModal()">Close</button>
            `;
        }

        actions.innerHTML = actionsHtml;
    },

    confirmAndInstall() {
        const git = this.updateInfo?.git;
        const isGit = git?.is_git;

        // Show warning modal
        const body = document.getElementById('update-modal-body');
        const actions = document.getElementById('update-modal-actions');

        body.innerHTML = `
            <div class="update-warning">
                <div class="update-warning-icon">⚠️</div>
                <div class="update-warning-title">Ready to Update</div>
                <div class="update-warning-text">
                    ${isGit ?
                        'This will pull the latest changes from GitHub.' :
                        'This will download and install the latest version from GitHub.'
                    }
                </div>
                <div class="update-preserve-info">
                    <div class="update-preserve-title">✓ The following will be preserved:</div>
                    <ul class="update-preserve-list">
                        <li>Database files (*.db, *.sqlite)</li>
                        <li>Configuration files (.env, config.*)</li>
                        <li>Session data (sessions.json)</li>
                        <li>Virtual environment (venv/)</li>
                        <li>Backup files (backups/)</li>
                    </ul>
                </div>
                <div class="update-backup-note">
                    A backup will be created before updating.
                </div>
            </div>
        `;

        actions.innerHTML = `
            <button class="btn" onclick="UpdateChecker.renderModalContent()">Cancel</button>
            <button class="btn btn-primary" onclick="UpdateChecker.installUpdate()" id="update-install-btn">
                Confirm & Install
            </button>
        `;
    },

    async installUpdate() {
        const btn = document.getElementById('update-install-btn');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Downloading & Installing...';
        }

        try {
            const response = await fetch('/api/update/install', { method: 'POST' });
            const data = await response.json();

            const body = document.getElementById('update-modal-body');
            const actions = document.getElementById('update-modal-actions');

            if (data.success) {
                if (data.already_up_to_date) {
                    body.innerHTML = `
                        <div class="update-status update-current">
                            <span class="update-icon">✓</span>
                            <div>
                                <div class="update-status-title">Already up to date</div>
                            </div>
                        </div>
                    `;
                    actions.innerHTML = '<button class="btn btn-primary" onclick="UpdateChecker.closeModal()">Close</button>';
                } else {
                    let detailText = 'Please restart the server to apply changes.';
                    if (data.method === 'download') {
                        detailText = `${data.message || 'Update complete.'} Please restart the server.`;
                    }
                    if (data.backup_path) {
                        detailText += `<br><small>Backup saved to: ${this.escapeHtml(data.backup_path)}</small>`;
                    }

                    body.innerHTML = `
                        <div class="update-status update-success">
                            <span class="update-icon">✓</span>
                            <div>
                                <div class="update-status-title">Update installed successfully!</div>
                                <div class="update-status-detail">${detailText}</div>
                            </div>
                        </div>
                    `;
                    actions.innerHTML = `
                        <button class="btn btn-primary" onclick="location.reload()">Reload Page</button>
                    `;
                }
            } else {
                body.innerHTML = `
                    <div class="update-status update-error">
                        <span class="update-icon">✕</span>
                        <div>
                            <div class="update-status-title">Update failed</div>
                            <div class="update-status-detail">${this.escapeHtml(data.error || 'Unknown error')}</div>
                        </div>
                    </div>
                `;
                actions.innerHTML = `
                    <button class="btn" onclick="UpdateChecker.renderModalContent()">Back</button>
                    <button class="btn btn-primary" onclick="UpdateChecker.installUpdate()" id="update-install-btn">
                        Retry
                    </button>
                `;
            }
        } catch (error) {
            console.error('Update failed:', error);
            const body = document.getElementById('update-modal-body');
            const actions = document.getElementById('update-modal-actions');

            body.innerHTML = `
                <div class="update-status update-error">
                    <span class="update-icon">✕</span>
                    <div>
                        <div class="update-status-title">Update failed</div>
                        <div class="update-status-detail">Network error: ${this.escapeHtml(error.message)}</div>
                    </div>
                </div>
            `;
            actions.innerHTML = `
                <button class="btn" onclick="UpdateChecker.renderModalContent()">Back</button>
                <button class="btn btn-primary" onclick="UpdateChecker.installUpdate()" id="update-install-btn">
                    Retry
                </button>
            `;
        }
    },

    escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
};

document.addEventListener('DOMContentLoaded', () => {
    UpdateChecker.init();
});
