# GitHub Issues Integration Plan for Autowrkers

## Overview

Integrate GitHub Issues with Autowrkers to automatically create sessions that work on issues, verify fixes, and create pull requests.

---

## Core Workflow

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  GitHub Issues  │────▶│  Autowrkers     │────▶│  Pull Requests  │
│  (Auto-sync)    │     │  Sessions        │     │  (Auto-create)  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                       │                        │
        │                       ▼                        │
        │               ┌──────────────────┐             │
        │               │  Verification    │             │
        │               │  (Tests/Lint)    │             │
        │               └──────────────────┘             │
        │                       │                        │
        └───────────────────────┴────────────────────────┘
                         Feedback Loop
```

---

## Feature Components

### 1. Projects (New Concept)

A **Project** is a container that links Autowrkers to a GitHub repository.

```python
@dataclass
class Project:
    id: int
    name: str
    github_repo: str          # e.g., "owner/repo"
    github_token: str         # encrypted
    working_dir: str          # local clone path
    default_branch: str       # main/master
    issue_filter: dict        # labels, assignees, milestones
    auto_sync: bool           # auto-fetch new issues
    auto_start: bool          # auto-start sessions for new issues
    verification_command: str # e.g., "npm test"
    max_concurrent: int       # max parallel sessions
    created_at: str
```

**UI Addition:**
- Projects panel/page to manage projects
- Link repo, configure settings
- View all issues and their session status

---

### 2. GitHub Integration Layer

**Authentication Options:**
1. Personal Access Token (simpler)
2. GitHub App (more secure, org-level)
3. OAuth flow (user-level)

**API Capabilities Needed:**
```python
class GitHubClient:
    async def get_issues(repo, filters) -> List[Issue]
    async def get_issue(repo, issue_number) -> Issue
    async def create_comment(repo, issue_number, body)
    async def create_pr(repo, head, base, title, body) -> PR
    async def get_pr_status(repo, pr_number) -> Status
    async def update_issue_labels(repo, issue_number, labels)
    async def close_issue(repo, issue_number)
```

**Webhook Support (Optional but recommended):**
- Listen for new issues
- Listen for issue updates
- Listen for PR reviews

---

### 3. Issue-to-Session Mapping

**IssueSession Model:**
```python
@dataclass
class IssueSession:
    id: int
    project_id: int
    github_issue_number: int
    github_issue_title: str
    github_issue_body: str
    session_id: int           # Autowrkers session
    status: IssueStatus       # pending, in_progress, verifying, pr_created, completed, failed
    branch_name: str          # feature/issue-123
    pr_number: int            # created PR number
    attempts: int             # retry count
    last_error: str
    created_at: str
    completed_at: str
```

**Status Flow:**
```
pending → in_progress → verifying → pr_created → completed
                ↓            ↓           ↓
              failed ←──────←───────────←
                ↓
            retry (max 3)
```

---

### 4. Prompt Engineering

**Issue Context Template:**
```markdown
You are working on issue #{{issue_number}} in the {{repo}} repository.

## Issue Title
{{issue_title}}

## Issue Description
{{issue_body}}

## Labels
{{labels}}

## Related Files (auto-detected)
{{related_files}}

## Instructions
1. Understand the issue and identify the root cause
2. Implement a fix following the project's coding standards
3. Write/update tests if applicable
4. Run the verification command: `{{verification_command}}`
5. When complete, type: /complete

## Important
- Create commits with clear messages referencing the issue
- Do not modify unrelated code
- If you need clarification, explain what's unclear
```

**Context Enhancement:**
- Search codebase for files mentioned in issue
- Include recent commits related to affected files
- Include relevant test files

---

### 5. Verification System

**Verification Steps:**
1. **Lint Check** - Code style/formatting
2. **Type Check** - TypeScript/mypy etc.
3. **Unit Tests** - Run test suite
4. **Build Check** - Ensure project builds
5. **Custom Checks** - Project-specific validation

**Verification Runner:**
```python
class VerificationRunner:
    async def run_verification(session_id, project) -> VerificationResult:
        results = []

        # Run configured checks
        if project.lint_command:
            results.append(await run_command(project.lint_command))

        if project.test_command:
            results.append(await run_command(project.test_command))

        if project.build_command:
            results.append(await run_command(project.build_command))

        return VerificationResult(
            passed=all(r.success for r in results),
            details=results
        )
```

---

### 6. Automation Controller

**AutomationController:**
```python
class AutomationController:
    async def process_project(project_id):
        """Main automation loop for a project"""
        project = get_project(project_id)

        while True:
            # Sync issues from GitHub
            await sync_issues(project)

            # Get pending issues
            pending = get_pending_issues(project_id)

            # Start sessions up to max_concurrent
            running = get_running_sessions(project_id)
            available_slots = project.max_concurrent - len(running)

            for issue in pending[:available_slots]:
                await start_issue_session(issue)

            # Check completed sessions
            for session in get_completed_sessions(project_id):
                await handle_completed_session(session)

            await asyncio.sleep(30)  # Poll interval

    async def handle_completed_session(issue_session):
        """Handle a session that Claude marked as complete"""
        # Run verification
        result = await verify_fix(issue_session)

        if result.passed:
            # Create PR
            pr = await create_pull_request(issue_session)
            issue_session.status = IssueStatus.PR_CREATED
            issue_session.pr_number = pr.number

            # Comment on issue
            await github.create_comment(
                issue_session.github_issue_number,
                f"🤖 Fix implemented in PR #{pr.number}"
            )
        else:
            # Retry or fail
            if issue_session.attempts < 3:
                issue_session.attempts += 1
                await retry_session(issue_session, result.error)
            else:
                issue_session.status = IssueStatus.FAILED
                await github.create_comment(
                    issue_session.github_issue_number,
                    f"🤖 Unable to fix after {issue_session.attempts} attempts"
                )
```

---

## Pain Points & Solutions

### 1. Authentication & Security

**Problem:** Storing GitHub tokens securely

**Solutions:**
- Encrypt tokens at rest using system keyring
- Support environment variables for tokens
- Implement token refresh for OAuth
- Never log or expose tokens

```python
# Use encryption for stored tokens
from cryptography.fernet import Fernet

class SecureStorage:
    def store_token(project_id, token):
        encrypted = fernet.encrypt(token.encode())
        save_to_db(project_id, encrypted)

    def get_token(project_id):
        encrypted = load_from_db(project_id)
        return fernet.decrypt(encrypted).decode()
```

---

### 2. Context Limitations

**Problem:** Claude needs sufficient context to fix issues

**Solutions:**
- **Smart File Detection:** Parse issue for file paths, function names, error messages
- **Codebase Indexing:** Pre-index repo structure for quick lookup
- **Related Files:** Include test files, configs, types
- **Git History:** Show recent changes to affected files

```python
class ContextBuilder:
    def build_context(issue, repo_path):
        context = []

        # Extract file references from issue
        files = extract_file_references(issue.body)

        # Find related test files
        for f in files:
            test_file = find_test_file(f)
            if test_file:
                files.append(test_file)

        # Add relevant configs
        context.extend(find_config_files(repo_path))

        # Include type definitions if TypeScript
        if is_typescript_project(repo_path):
            context.extend(find_type_files(files))

        return context
```

---

### 3. Verification Challenges

**Problem:** Not all repos have tests, tests may not cover the issue

**Solutions:**
- **Graceful Degradation:** If no tests, rely on build + lint
- **Test Generation:** Ask Claude to write tests for the fix
- **Manual Review Flag:** Mark PRs as needing review
- **Smoke Test:** Basic sanity checks (app starts, no crashes)

```python
class AdaptiveVerification:
    def get_verification_strategy(project):
        strategies = []

        # Always try build
        strategies.append(BuildCheck())

        # Add lint if configured
        if project.lint_command:
            strategies.append(LintCheck(project.lint_command))

        # Add tests if they exist
        if has_test_files(project.working_dir):
            strategies.append(TestCheck(project.test_command))
        else:
            # No tests - require manual review
            strategies.append(ManualReviewRequired())

        return strategies
```

---

### 4. Rate Limiting

**Problem:** GitHub and Claude API rate limits

**Solutions:**
- **Request Queuing:** Queue all API calls
- **Exponential Backoff:** Retry with increasing delays
- **Rate Tracking:** Monitor remaining quota
- **Prioritization:** Important issues first

```python
class RateLimitedClient:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.rate_limit_remaining = 5000
        self.rate_limit_reset = None

    async def request(self, method, *args):
        # Check rate limit
        if self.rate_limit_remaining < 100:
            await self.wait_for_reset()

        # Execute with backoff
        for attempt in range(5):
            try:
                result = await method(*args)
                self.update_rate_limit(result.headers)
                return result
            except RateLimitError:
                await asyncio.sleep(2 ** attempt)

        raise RateLimitExceeded()
```

---

### 5. Complex Issues

**Problem:** Some issues are too complex or need human input

**Solutions:**
- **Complexity Detection:** Estimate issue complexity from labels, description length
- **Human-in-the-Loop:** Flag for review, allow manual intervention
- **Issue Splitting:** Suggest breaking down large issues
- **Skip Criteria:** Auto-skip issues with certain labels (e.g., "needs-discussion")

```python
class ComplexityAnalyzer:
    def analyze(issue):
        score = 0

        # Long description = more complex
        score += len(issue.body) / 1000

        # Multiple files mentioned
        files = extract_file_references(issue.body)
        score += len(files) * 2

        # Certain labels indicate complexity
        complex_labels = ['breaking-change', 'architecture', 'security']
        score += sum(5 for l in issue.labels if l in complex_labels)

        # Questions in issue = unclear requirements
        score += issue.body.count('?') * 2

        return ComplexityLevel.from_score(score)
```

---

### 6. State Management & Recovery

**Problem:** Handling restarts, partial completions, failures

**Solutions:**
- **Persistent State:** Save all state to database/JSON
- **Idempotent Operations:** Safe to retry any operation
- **Transaction Log:** Record all actions for replay
- **Health Checks:** Detect and recover stuck sessions

```python
class StateManager:
    def save_checkpoint(issue_session):
        checkpoint = {
            'issue_session_id': issue_session.id,
            'status': issue_session.status,
            'branch': issue_session.branch_name,
            'commits': get_commits(issue_session.branch_name),
            'timestamp': datetime.now().isoformat()
        }
        save_to_disk(f'checkpoints/{issue_session.id}.json', checkpoint)

    def recover_from_checkpoint(issue_session_id):
        checkpoint = load_from_disk(f'checkpoints/{issue_session_id}.json')

        # Restore branch state
        checkout_branch(checkpoint['branch'])

        # Resume from last status
        return checkpoint['status']
```

---

## Database Schema Additions

```sql
-- Projects table
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    github_repo TEXT NOT NULL,
    github_token_encrypted BLOB,
    working_dir TEXT NOT NULL,
    default_branch TEXT DEFAULT 'main',
    issue_filter JSON,
    auto_sync BOOLEAN DEFAULT true,
    auto_start BOOLEAN DEFAULT false,
    verification_command TEXT,
    lint_command TEXT,
    build_command TEXT,
    max_concurrent INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Issue sessions table
CREATE TABLE issue_sessions (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    github_issue_number INTEGER NOT NULL,
    github_issue_title TEXT,
    github_issue_body TEXT,
    github_issue_labels JSON,
    session_id INTEGER REFERENCES sessions(id),
    status TEXT DEFAULT 'pending',
    branch_name TEXT,
    pr_number INTEGER,
    attempts INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    UNIQUE(project_id, github_issue_number)
);

-- Verification results table
CREATE TABLE verification_results (
    id INTEGER PRIMARY KEY,
    issue_session_id INTEGER REFERENCES issue_sessions(id),
    check_type TEXT,
    passed BOOLEAN,
    output TEXT,
    duration_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## API Endpoints to Add

```python
# Project management
POST   /api/projects                    # Create project
GET    /api/projects                    # List projects
GET    /api/projects/{id}               # Get project details
PUT    /api/projects/{id}               # Update project
DELETE /api/projects/{id}               # Delete project

# GitHub integration
POST   /api/projects/{id}/sync          # Sync issues from GitHub
GET    /api/projects/{id}/issues        # List issues for project
POST   /api/projects/{id}/issues/{num}/start  # Start working on issue

# Issue sessions
GET    /api/issue-sessions              # List all issue sessions
GET    /api/issue-sessions/{id}         # Get issue session details
POST   /api/issue-sessions/{id}/retry   # Retry failed session
POST   /api/issue-sessions/{id}/skip    # Skip/cancel issue

# Automation control
POST   /api/projects/{id}/automation/start   # Start automation
POST   /api/projects/{id}/automation/stop    # Stop automation
GET    /api/projects/{id}/automation/status  # Get automation status
```

---

## UI Additions

### Projects Page
```
┌─────────────────────────────────────────────────────────────┐
│ Projects                                    [+ New Project] │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 📦 my-app                           ▶ Running           │ │
│ │ github.com/user/my-app                                  │ │
│ │ 12 issues │ 3 in progress │ 8 completed │ 1 failed     │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 📦 api-server                       ⏸ Paused            │ │
│ │ github.com/user/api-server                              │ │
│ │ 5 issues │ 0 in progress │ 2 completed │ 0 failed      │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Project Detail / Issues View
```
┌─────────────────────────────────────────────────────────────┐
│ ← my-app                    [Sync] [Settings] [▶ Start All] │
├─────────────────────────────────────────────────────────────┤
│ Filter: [All ▼] [bug ▼] [good-first-issue ▼]               │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ #123 Fix login timeout          🟢 PR Created (#145)    │ │
│ │ bug, authentication             Attempt 1 │ 15 min      │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ #124 Add dark mode toggle       🔵 In Progress          │ │
│ │ enhancement, ui                 Attempt 1 │ 8 min       │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ #125 Database connection leak   🔴 Failed (3 attempts)  │ │
│ │ bug, critical                   [Retry] [Skip] [View]   │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Foundation (Week 1-2)
- [ ] Create Project model and database schema
- [ ] Build GitHub API client with auth
- [ ] Add project CRUD API endpoints
- [ ] Basic UI for project management
- [ ] Manual issue sync (fetch issues on demand)

### Phase 2: Issue-Session Integration (Week 2-3)
- [ ] IssueSession model and schema
- [ ] Convert issue to session with context template
- [ ] Track issue-session relationship
- [ ] Basic status flow (pending → in_progress → completed)
- [ ] UI to view issues and start sessions

### Phase 3: Verification System (Week 3-4)
- [ ] Verification runner framework
- [ ] Lint, test, build checks
- [ ] Verification result storage
- [ ] Retry logic on failure
- [ ] UI for verification results

### Phase 4: PR Automation (Week 4-5)
- [ ] Branch creation per issue
- [ ] Auto-commit with issue reference
- [ ] PR creation with description
- [ ] Comment on GitHub issue
- [ ] Link PR back to issue session

### Phase 5: Full Automation (Week 5-6)
- [ ] Automation controller loop
- [ ] Concurrent session management
- [ ] Auto-sync with webhooks
- [ ] Rate limiting and queuing
- [ ] Recovery and checkpointing

### Phase 6: Polish & Advanced Features (Week 6+)
- [ ] Complexity analysis
- [ ] Smart context building
- [ ] Manual review workflow
- [ ] Analytics dashboard
- [ ] Notifications (Slack, email)

---

## Future Enhancements

1. **Multi-repo Projects** - One project spans multiple repos
2. **Custom Workflows** - Define custom verification pipelines
3. **AI-Powered Triage** - Auto-label and prioritize issues
4. **Learning from Failures** - Improve prompts based on past failures
5. **Team Features** - Assign issues to human + AI pairs
6. **Integration Hub** - Jira, Linear, GitLab support
7. **Metrics Dashboard** - Success rate, time-to-fix, cost tracking

---

## Technical Decisions Needed

1. **Database:** SQLite (current) vs PostgreSQL (for scale)?
2. **Auth:** PAT only vs full OAuth flow?
3. **Webhooks:** Poll vs GitHub webhooks vs GitHub App?
4. **Queue:** In-memory vs Redis vs database-backed?
5. **Git Operations:** CLI vs GitPython vs dulwich?

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Claude makes breaking changes | High | Verification + PR review required |
| Token exposure | Critical | Encryption + audit logging |
| Rate limit exhaustion | Medium | Queuing + backoff + alerts |
| Stuck automation loops | Medium | Health checks + timeouts |
| Cost overruns (API usage) | Medium | Usage limits + monitoring |

---

## Success Metrics

- **Fix Rate:** % of issues successfully fixed
- **First-Attempt Success:** % fixed on first try
- **Time to Fix:** Average time from issue to PR
- **Verification Pass Rate:** % passing all checks
- **PR Merge Rate:** % of auto-PRs merged without changes
