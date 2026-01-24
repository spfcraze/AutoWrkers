# UltraClaude

Multi-session Claude Code manager with GitHub Issues integration. Automatically works on GitHub issues, verifies fixes (lint/test/build), and creates pull requests.

## Features

- **GitHub Issue Automation**: Syncs issues from repositories, automatically assigns Claude to work on them
- **Multi-Session Management**: Run multiple Claude Code sessions concurrently with parent/child dependencies
- **Verification Pipeline**: Runs lint, test, and build commands before creating PRs
- **Auto PR Creation**: Creates pull requests with proper descriptions when verification passes
- **Complexity Analysis**: Scores issues by complexity to flag ones needing human review
- **Real-time Dashboard**: WebSocket-powered UI showing session output and status
- **Recovery & Checkpointing**: Resumes interrupted sessions on restart

## Quick Start

```bash
# Clone and setup
cd ultraclaude
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start the server
python main.py start

# Open dashboard
open http://localhost:8420
```

## Configuration

### Adding a Project

1. Go to http://localhost:8420/projects
2. Click "Add Project"
3. Fill in:
   - **Name**: Display name for the project
   - **GitHub Repo**: Format `owner/repo`
   - **GitHub Token**: Personal access token with `repo` scope
   - **Working Directory**: Local path to the cloned repository
   - **Verification Commands** (optional): `lint_command`, `test_command`, `build_command`

### GitHub Token Permissions

Create a token at https://github.com/settings/tokens with:
- `repo` (full control of private repositories)
- Or `public_repo` for public repositories only

## Architecture

```
GitHub Issue
    ↓
Sync to UltraClaude
    ↓
Complexity Analysis (score issue)
    ↓
Create tmux Session
    ↓
Claude Code works on issue
    ↓
Claude types "/complete"
    ↓
Detection triggers verification
    ↓
Run lint → test → build
    ↓
If pass: Create PR, comment on issue
If fail: Retry with feedback (up to 3 attempts)
```

## API Reference

### Health Check
```
GET /health
```
Returns component status for monitoring.

### Sessions
```
GET  /api/sessions              # List all sessions
POST /api/sessions              # Create new session
GET  /api/sessions/{id}         # Get session details
POST /api/sessions/{id}/input   # Send input to session
POST /api/sessions/{id}/stop    # Stop session
POST /api/sessions/{id}/complete # Mark session completed
```

### Projects
```
GET    /api/projects              # List projects
POST   /api/projects              # Create project
GET    /api/projects/{id}         # Get project
PUT    /api/projects/{id}         # Update project
DELETE /api/projects/{id}         # Delete project
POST   /api/projects/{id}/sync    # Sync issues from GitHub
```

### Issue Sessions
```
GET  /api/issue-sessions              # List issue sessions
GET  /api/issue-sessions/{id}         # Get issue session
POST /api/issue-sessions/{id}/start   # Start working on issue
POST /api/issue-sessions/{id}/retry   # Retry failed issue
POST /api/issue-sessions/{id}/skip    # Skip issue
```

### Automation
```
POST /api/projects/{id}/automation/start  # Start automation loop
POST /api/projects/{id}/automation/stop   # Stop automation loop
```

### WebSocket
```
WS /ws
```
Real-time updates for session output, status changes, and automation events.

## Production Deployment

### Using systemd

```bash
# Install service
sudo cp deploy/ultraclaude.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ultraclaude
sudo systemctl start ultraclaude

# View logs
sudo journalctl -u ultraclaude -f

# Check status
sudo systemctl status ultraclaude
```

Or use the install script:
```bash
sudo ./deploy/install.sh
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ULTRACLAUDE_HOST` | Server bind address | `127.0.0.1` |
| `ULTRACLAUDE_PORT` | Server port | `8420` |
| `ULTRACLAUDE_USE_SQLITE` | Use SQLite database (0=JSON, 1=SQLite) | `1` |
| `ULTRACLAUDE_LOG_LEVEL` | Log level (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `ULTRACLAUDE_LOG_JSON` | Output logs as JSON (0=text, 1=JSON) | `0` |
| `ULTRACLAUDE_LOG_FILE` | Log file path (optional) | None |

### Database Migration

UltraClaude uses SQLite by default. To migrate from older JSON-based storage:

```bash
python main.py migrate
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_complexity_analyzer.py -v
```

## Project Structure

```
ultraclaude/
├── src/
│   ├── automation.py      # AutomationController, VerificationRunner, PRCreator
│   ├── session_manager.py # Tmux session management, completion detection
│   ├── models.py          # Project, IssueSession, VerificationResult
│   ├── github_client.py   # GitHub API client with rate limiting
│   ├── server.py          # FastAPI server
│   └── ...
├── web/
│   ├── templates/         # Jinja2 HTML templates
│   └── static/            # CSS, JS assets
├── tests/                 # Unit tests
├── deploy/                # systemd service files
├── main.py               # CLI entry point
└── requirements.txt
```

## Issue Session Status Flow

```
PENDING → QUEUED → IN_PROGRESS → VERIFYING → PR_CREATED → COMPLETED
                       ↓              ↓
                   NEEDS_REVIEW    FAILED (retry up to max_attempts)
```

## Completion Detection

Claude signals completion by typing `/complete` or `/done` followed by newline/space. This triggers:
1. Mark session completed
2. Run verification commands
3. Create PR if all checks pass
4. Retry with feedback if checks fail

## License

MIT
