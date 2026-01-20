# Troubleshooting Guide

This guide covers common issues and their solutions when using UltraClaude.

## Table of Contents

- [Installation Issues](#installation-issues)
- [Server Issues](#server-issues)
- [Session Issues](#session-issues)
- [GitHub Integration Issues](#github-integration-issues)
- [Git Repository Issues](#git-repository-issues)
- [LLM Provider Issues](#llm-provider-issues)
- [Performance Issues](#performance-issues)
- [Getting Help](#getting-help)

---

## Installation Issues

### "ModuleNotFoundError: No module named 'xxx'"

**Cause**: Python dependencies not installed or virtual environment not activated.

**Solution**:
```bash
# Activate virtual environment
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# Reinstall dependencies
pip install -r requirements.txt
```

### "Command not found: tmux"

**Cause**: tmux is not installed.

**Solution**:
```bash
# Ubuntu/Debian
sudo apt install tmux

# macOS
brew install tmux

# Fedora
sudo dnf install tmux

# Arch
sudo pacman -S tmux
```

### "Command not found: claude"

**Cause**: Claude Code CLI is not installed.

**Solution**:
```bash
# Install Node.js first if needed
# Then install Claude Code CLI
npm install -g @anthropic-ai/claude-code

# Verify installation
claude --version
```

### Python version errors

**Cause**: Python version is too old.

**Solution**:
```bash
# Check version
python --version

# If < 3.9, install newer Python
# Ubuntu
sudo apt install python3.11

# macOS
brew install python@3.11
```

---

## Server Issues

### "Port 8420 is already in use"

**Cause**: Another process is using the port.

**Solution**:
```bash
# Find process using port
lsof -i :8420  # Linux/macOS
netstat -ano | findstr :8420  # Windows

# Kill the process or use different port
python -m src.server --port 8421
```

### "Address already in use" on restart

**Cause**: Previous server didn't shut down cleanly.

**Solution**:
```bash
# Wait a moment for socket to release
sleep 5
python -m src.server

# Or kill any lingering processes
pkill -f "python -m src.server"
```

### Server crashes on startup

**Cause**: Missing dependencies or corrupted data files.

**Solution**:
```bash
# Check for errors
python -c "from src.server import app"

# If data corruption, backup and remove
mv data data.backup
mkdir data

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

### WebSocket connection failed

**Cause**: Browser blocking or network issue.

**Solution**:
1. Check browser console for errors
2. Try a different browser
3. Ensure no firewall blocking port 8420
4. Check if using HTTPS (WebSocket needs matching protocol)

---

## Session Issues

### "tmux session not found"

**Cause**: Session was terminated externally or tmux crashed.

**Solution**:
```bash
# List existing tmux sessions
tmux list-sessions

# Kill orphaned sessions
tmux kill-server

# Restart UltraClaude server
python -m src.server
```

### Session stuck in "running" state

**Cause**: Claude completed but completion not detected.

**Solution**:
1. Check session output for `/complete`
2. Manually mark as complete via API:
   ```bash
   curl -X POST http://localhost:8420/api/sessions/{id}/complete
   ```
3. Stop and retry the session

### No output appearing

**Cause**: Output buffer or WebSocket issue.

**Solution**:
1. Refresh the page
2. Check WebSocket connection in browser dev tools
3. Check server logs for errors
4. Verify tmux session exists:
   ```bash
   tmux attach -t ultraclaude_{session_id}
   ```

### Session not starting

**Cause**: Various issues with tmux or working directory.

**Solution**:
```bash
# Check tmux is working
tmux new-session -d -s test
tmux kill-session -t test

# Verify working directory exists
ls -la /path/to/working/dir

# Check permissions
touch /path/to/working/dir/test && rm /path/to/working/dir/test
```

---

## GitHub Integration Issues

### "Invalid GitHub token"

**Cause**: Token is expired, invalid, or missing scopes.

**Solution**:
1. Generate a new token at https://github.com/settings/tokens
2. Ensure `repo` scope is selected (classic tokens)
3. For fine-grained tokens, verify repository access
4. Update token in project settings

### "Cannot access repository"

**Cause**: Token doesn't have access to the repository.

**Solution**:
1. Verify repository exists and name is correct
2. For private repos, ensure token has `repo` scope
3. For fine-grained tokens:
   - Repository must be selected
   - Contents permission must be Read/Write

### "Rate limit exceeded"

**Cause**: Too many GitHub API requests.

**Solution**:
1. Wait for rate limit to reset (usually 1 hour)
2. Check rate limit status:
   ```bash
   curl -H "Authorization: token YOUR_TOKEN" \
     https://api.github.com/rate_limit
   ```
3. Reduce sync frequency
4. Use authenticated requests (higher limits)

### "Pull request creation failed"

**Cause**: Various PR-related issues.

**Solution**:
1. Verify token has `repo` scope
2. Check branch doesn't already exist
3. Verify base branch exists
4. Check for branch protection rules
5. Review error message in logs

### Issues not syncing

**Cause**: Filter configuration or API issues.

**Solution**:
1. Verify filter labels exist in repository
2. Check issues are open (not closed)
3. Test API directly:
   ```bash
   curl -H "Authorization: token YOUR_TOKEN" \
     "https://api.github.com/repos/owner/repo/issues"
   ```

---

## Git Repository Issues

### "Cannot clone repository"

**Cause**: Authentication or network issues.

**Solution**:
1. Verify token has Contents: Read permission
2. Check URL is correct: `owner/repo` format
3. Test manually:
   ```bash
   git clone https://x-access-token:TOKEN@github.com/owner/repo.git
   ```
4. Check firewall allows GitHub access

### "Working directory not found"

**Cause**: Directory doesn't exist or wrong path.

**Solution**:
1. Verify the path exists
2. Create parent directories:
   ```bash
   mkdir -p /path/to/projects
   ```
3. Check path permissions
4. Update working directory in project settings

### "Permission denied" during git operations

**Cause**: File permission or token issue.

**Solution**:
```bash
# Check directory ownership
ls -la /path/to/repo

# Fix permissions
sudo chown -R $USER:$USER /path/to/repo

# Verify git config
cd /path/to/repo
git config --list
```

### "Branch already exists"

**Cause**: Previous session created the branch.

**Solution**:
1. Delete the branch:
   ```bash
   git branch -D fix/issue-123
   git push origin --delete fix/issue-123
   ```
2. Or skip the issue in UltraClaude

### Git merge conflicts

**Cause**: Parallel changes to same files.

**Solution**:
1. Pull latest changes first
2. Resolve conflicts manually
3. Use "Pull Latest" in UltraClaude

---

## LLM Provider Issues

### Ollama: "Cannot connect"

**Cause**: Ollama server not running.

**Solution**:
```bash
# Start Ollama
ollama serve

# Verify it's running
curl http://localhost:11434/api/tags

# Check for port conflicts
lsof -i :11434
```

### Ollama: "Model not found"

**Cause**: Model not downloaded.

**Solution**:
```bash
# List available models
ollama list

# Download model
ollama pull llama3.2:latest

# Verify model
ollama run llama3.2:latest "Hello"
```

### LM Studio: "Connection refused"

**Cause**: Local server not started.

**Solution**:
1. Open LM Studio
2. Go to "Local Server" tab
3. Load a model
4. Click "Start Server"
5. Note the port (default: 1234)

### OpenRouter: "Invalid API key"

**Cause**: Wrong or expired API key.

**Solution**:
1. Go to https://openrouter.ai/keys
2. Generate a new key
3. Verify key starts with `sk-or-`
4. Check you have credits

### OpenRouter: "Insufficient credits"

**Cause**: No credits remaining.

**Solution**:
1. Add credits at https://openrouter.ai/credits
2. Check pricing for your model
3. Consider cheaper models

### Tool calling not working

**Cause**: Model doesn't support function calling.

**Solution**:
1. Use a model with tool support:
   - Ollama: `llama3.2:latest`, `mistral:latest`
   - OpenRouter: Most Claude, GPT-4 models
2. Check model documentation for tool support

---

## Performance Issues

### Slow session startup

**Cause**: tmux or file system delays.

**Solution**:
1. Check disk I/O
2. Ensure working directory is local (not network mount)
3. Reduce output buffer size

### High memory usage

**Cause**: Many sessions or large output buffers.

**Solution**:
1. Stop unused sessions
2. Clear completed sessions
3. Restart server periodically
4. Check for memory leaks in logs

### WebSocket lag

**Cause**: Network or browser issues.

**Solution**:
1. Use wired connection
2. Close unused browser tabs
3. Try different browser
4. Check server-side logs

---

## Getting Help

### Gathering Information

Before asking for help, collect:

1. **Environment info**:
   ```bash
   python --version
   pip list | grep -E "fastapi|uvicorn"
   tmux -V
   uname -a
   ```

2. **Server logs**: Run with debug mode
3. **Browser console**: F12 > Console tab
4. **Error messages**: Full text of any errors

### Where to Get Help

1. **GitHub Issues**: For bugs and feature requests
   - https://github.com/yourusername/ultraclaude/issues

2. **Discussions**: For questions and ideas
   - https://github.com/yourusername/ultraclaude/discussions

### Reporting Bugs

Include in your report:

```markdown
## Environment
- OS:
- Python:
- Browser:

## Steps to Reproduce
1.
2.
3.

## Expected Behavior


## Actual Behavior


## Logs
```
paste logs here
```

## Screenshots
(if applicable)
```

---

## Quick Fixes Reference

| Problem | Quick Fix |
|---------|-----------|
| Server won't start | `pip install -r requirements.txt` |
| No tmux | `sudo apt install tmux` |
| Session stuck | Manually mark complete via API |
| Token invalid | Generate new token with `repo` scope |
| Clone fails | Verify token and repo name |
| Ollama offline | Run `ollama serve` |
| WebSocket error | Refresh page, check console |
