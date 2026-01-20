# Usage Guide

This guide covers how to use UltraClaude effectively for managing Claude Code sessions and automating GitHub workflows.

## Table of Contents

- [Dashboard Overview](#dashboard-overview)
- [Managing Sessions](#managing-sessions)
- [Working with Projects](#working-with-projects)
- [Automation Workflows](#automation-workflows)
- [Using Local LLMs](#using-local-llms)
- [Best Practices](#best-practices)

---

## Dashboard Overview

### Sessions Page

The main dashboard shows all Claude Code sessions:

| Section | Description |
|---------|-------------|
| **Header** | Navigation and "New Session" button |
| **Session Cards** | Live session status and controls |
| **Output Panel** | Real-time terminal output |

### Session States

| State | Color | Description |
|-------|-------|-------------|
| Running | Green | Session is active |
| Queued | Yellow | Waiting for parent to complete |
| Completed | Blue | Session finished successfully |
| Stopped | Gray | Session was stopped |
| Failed | Red | Session encountered an error |

### Projects Page

Shows all configured projects:

| Section | Description |
|---------|-------------|
| **Project Cards** | Project status and quick actions |
| **Detail Panel** | Issues, automation status, logs |

---

## Managing Sessions

### Creating a New Session

1. Click **"+ New Session"** in the header
2. Fill in the form:
   - **Name**: Descriptive session name
   - **Working Directory**: Path to your project
   - **Initial Prompt**: (Optional) Starting prompt for Claude
3. Click **"Create"**

### Sending Input

When a session is running:

1. Click on the session card to select it
2. Type in the input field at the bottom
3. Press Enter or click Send

### Session Controls

| Button | Action |
|--------|--------|
| ▶ Play | Start a queued session |
| ⏹ Stop | Stop a running session |
| ✓ Complete | Mark session as completed |
| 🗑 Delete | Remove session |

### Session Dependencies

Create workflows by setting parent sessions:

1. Create the first session
2. Create a second session
3. Set the first session as the parent
4. The second session starts automatically when the first completes

**Example Workflow:**
```
Session 1: "Set up project structure"
    ↓ (completes)
Session 2: "Implement feature A" (parent: Session 1)
    ↓ (completes)
Session 3: "Add tests" (parent: Session 2)
```

---

## Working with Projects

### Creating a Project

1. Navigate to **Projects** page
2. Click **"+ New Project"**
3. Enter project details:
   - **Name**: Display name
   - **Repository**: `owner/repo` or full GitHub URL
   - **Token**: GitHub Personal Access Token
   - **Working Directory**: Local clone path

4. Configure optional settings:
   - **Issue Filters**: Labels to include/exclude
   - **Verification Commands**: Lint, test, build
   - **LLM Provider**: Claude Code or alternatives

5. Click **"Create Project"**

### Project Workflow

#### Step 1: Clone Repository

After creating a project:

1. Click on the project card
2. Click **"Clone Repository"** in the git status bar
3. Wait for cloning to complete

#### Step 2: Sync Issues

1. Click **"Sync Issues"**
2. Issues matching your filters appear in the list
3. Each issue becomes a potential work item

#### Step 3: Start Automation (Optional)

For automatic processing:

1. Click **"Start Automation"**
2. UltraClaude will:
   - Process pending issues one by one
   - Create branches for each issue
   - Send prompts to Claude
   - Run verification commands
   - Create pull requests

### Manual Issue Processing

To work on a single issue:

1. Find the issue in the list
2. Click **"▶ Start"** on the issue card
3. A new Claude session is created
4. Monitor progress in real-time
5. When Claude says `/complete`, verification runs
6. If verification passes, a PR is created

### Issue States

| State | Description | Actions |
|-------|-------------|---------|
| Pending | Not started | Start, Skip |
| In Progress | Being worked on | - |
| Verifying | Running checks | - |
| PR Created | Work complete | View PR |
| Failed | Error occurred | Retry, Skip |
| Skipped | Manually skipped | - |

---

## Automation Workflows

### How Automation Works

1. **Sync Phase**: Fetches issues from GitHub
2. **Filter Phase**: Applies label filters
3. **Branch Phase**: Creates feature branch (`fix/issue-N`)
4. **Prompt Phase**: Sends issue details to Claude
5. **Work Phase**: Claude works on the issue
6. **Verify Phase**: Runs lint, test, build commands
7. **PR Phase**: Creates pull request

### Automation Settings

| Setting | Description |
|---------|-------------|
| Auto-sync | Periodically fetch new issues |
| Auto-start | Begin work automatically |
| Max Concurrent | Parallel sessions limit |

### Monitoring Automation

The project detail view shows:

- **Status**: Running or stopped
- **Stats**: Processed, completed, failed counts
- **Activity Log**: Recent actions and events

### Stopping Automation

Click **"Stop"** to:
- Prevent new sessions from starting
- Allow current sessions to complete
- Keep existing work intact

---

## Using Local LLMs

### When to Use Local LLMs

Consider local LLMs when:

- You want to avoid API costs
- You need offline capability
- You have privacy requirements
- You're experimenting with different models

### Provider Comparison

| Provider | Pros | Cons |
|----------|------|------|
| **Claude Code** | Best coding, native tools | Requires subscription |
| **Ollama** | Free, offline, many models | Requires good hardware |
| **LM Studio** | GUI, easy setup | Single model at a time |
| **OpenRouter** | Many models, pay-per-use | Requires API costs |

### Recommended Models for Coding

| Model | Size | Best For |
|-------|------|----------|
| `llama3.2:latest` | 3B | Quick tasks, limited RAM |
| `codellama:13b` | 13B | General coding |
| `deepseek-coder:33b` | 33B | Complex tasks |
| `qwen2.5-coder:32b` | 32B | Advanced coding |

### Memory Requirements

| Model Size | Minimum RAM | Recommended |
|------------|-------------|-------------|
| 7B | 8GB | 16GB |
| 13B | 16GB | 32GB |
| 33B+ | 32GB | 64GB |

---

## Best Practices

### Issue Writing

For best results with automation:

1. **Clear Title**: Describe the change needed
   ```
   Good: "Add user authentication to login page"
   Bad: "Fix login"
   ```

2. **Detailed Description**: Include context
   - What's the current behavior?
   - What should change?
   - Any specific requirements?

3. **Acceptance Criteria**: Define "done"
   ```markdown
   ## Acceptance Criteria
   - [ ] Users can log in with email/password
   - [ ] Invalid credentials show error message
   - [ ] Successful login redirects to dashboard
   ```

### Verification Commands

Set up commands that catch issues:

```bash
# Lint: Catch style issues
npm run lint

# Test: Verify functionality
npm test

# Build: Ensure it compiles
npm run build
```

### Token Security

1. Use fine-grained tokens with minimal permissions
2. Set token expiration (90 days recommended)
3. Rotate tokens regularly
4. Never commit tokens to version control

### Session Management

1. **Name sessions descriptively**
   - Good: "Issue #42: Add dark mode toggle"
   - Bad: "test session"

2. **Use dependencies** for related work
3. **Monitor running sessions** for issues
4. **Stop stuck sessions** if Claude loops

### Handling Failures

When a session fails:

1. Check the error message
2. Review the session output
3. Fix the underlying issue
4. Click **"Retry"** to try again

Common failure causes:
- Missing dependencies
- Incorrect working directory
- GitHub API rate limits
- Invalid token permissions

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Enter` | Send input |
| `Esc` | Close modal |
| `r` | Refresh sessions |

---

## Tips and Tricks

### Faster Issue Processing

1. Set up verification commands correctly
2. Use specific issue labels
3. Keep issues focused and atomic

### Debugging Sessions

1. Check the output panel for errors
2. Look at the activity log
3. Verify git status is clean

### Improving Results

1. Write detailed issue descriptions
2. Include code examples in issues
3. Reference related files/functions

---

## Next Steps

- [API Reference](API.md) - Programmatic access
- [Troubleshooting](TROUBLESHOOTING.md) - Common issues
- [Configuration](CONFIGURATION.md) - Advanced settings
