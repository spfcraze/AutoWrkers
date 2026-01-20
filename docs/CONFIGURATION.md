# Configuration Guide

This guide covers all configuration options for UltraClaude, including GitHub token setup, project configuration, and LLM provider settings.

## Table of Contents

- [GitHub Token Setup](#github-token-setup)
  - [Classic Personal Access Token](#classic-personal-access-token)
  - [Fine-Grained Personal Access Token](#fine-grained-personal-access-token)
  - [Token Permissions Reference](#token-permissions-reference)
- [Creating a Project](#creating-a-project)
- [Project Settings](#project-settings)
- [Local LLM Configuration](#local-llm-configuration)
  - [Ollama Setup](#ollama-setup)
  - [LM Studio Setup](#lm-studio-setup)
  - [OpenRouter Setup](#openrouter-setup)
- [Issue Filters](#issue-filters)
- [Verification Commands](#verification-commands)
- [Advanced Configuration](#advanced-configuration)

---

## GitHub Token Setup

UltraClaude requires a GitHub Personal Access Token to:
- Read repository information
- Fetch and manage issues
- Create branches and commits
- Open pull requests

### Classic Personal Access Token

**Recommended for simplicity and full access.**

#### Step 1: Generate Token

1. Go to GitHub: **Settings** > **Developer settings** > **Personal access tokens** > **Tokens (classic)**
2. Click **"Generate new token"** > **"Generate new token (classic)"**
3. Give it a descriptive name: `UltraClaude Access`
4. Set expiration (recommend 90 days or custom)

#### Step 2: Select Scopes

Check the following scopes:

| Scope | Required | Description |
|-------|----------|-------------|
| `repo` | **Yes** | Full control of private repositories |
| `repo:status` | Included | Access commit status |
| `repo_deployment` | Included | Access deployment status |
| `public_repo` | Included | Access public repositories |
| `repo:invite` | Included | Access repository invitations |
| `workflow` | Optional | Update GitHub Action workflows |

![Classic Token Scopes](images/classic-token-scopes.png)

#### Step 3: Generate and Copy

1. Click **"Generate token"**
2. **IMPORTANT**: Copy the token immediately - you won't see it again!
3. Store it securely (password manager recommended)

#### Example Token Format
```
ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

### Fine-Grained Personal Access Token

**Recommended for better security with granular permissions.**

#### Step 1: Generate Token

1. Go to GitHub: **Settings** > **Developer settings** > **Personal access tokens** > **Fine-grained tokens**
2. Click **"Generate new token"**
3. Set token name: `UltraClaude Access`
4. Set expiration

#### Step 2: Configure Repository Access

Choose one option:

**Option A: All repositories** (easier, less secure)
- Select "All repositories"

**Option B: Selected repositories** (recommended)
- Select "Only select repositories"
- Choose the specific repositories you want UltraClaude to access

#### Step 3: Set Permissions

Configure these repository permissions:

| Permission | Access Level | Purpose |
|------------|--------------|---------|
| **Contents** | Read and write | Clone, read files, create branches, push commits |
| **Issues** | Read and write | Fetch issues, add comments |
| **Pull requests** | Read and write | Create and manage PRs |
| **Metadata** | Read-only | Basic repository info (auto-selected) |

Optional permissions:

| Permission | Access Level | Purpose |
|------------|--------------|---------|
| Commit statuses | Read-only | View CI/CD status |
| Actions | Read-only | View workflow runs |

![Fine-Grained Token Permissions](images/fine-grained-permissions.png)

#### Step 4: Generate and Copy

1. Click **"Generate token"**
2. Copy and store the token securely

#### Example Token Format
```
github_pat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

---

### Token Permissions Reference

#### Minimum Required Permissions

For UltraClaude to function properly, your token needs:

| Action | Classic Scope | Fine-Grained Permission |
|--------|---------------|------------------------|
| Clone repository | `repo` | Contents: Read |
| Read files | `repo` | Contents: Read |
| Create branches | `repo` | Contents: Write |
| Push commits | `repo` | Contents: Write |
| Read issues | `repo` | Issues: Read |
| Comment on issues | `repo` | Issues: Write |
| Create pull requests | `repo` | Pull requests: Write |

#### Testing Your Token

After adding the token to a project:

1. Click the **Settings** button on your project
2. Click **"Test Token"** (if available)
3. Check the results:
   - ✅ Auth successful
   - ✅ Repository accessible
   - ✅ Required scopes present

Or test manually:
```bash
curl -H "Authorization: token YOUR_TOKEN" \
  https://api.github.com/repos/owner/repo
```

---

## Creating a Project

### Step 1: Navigate to Projects

1. Open UltraClaude at `http://localhost:8420`
2. Click **"Projects"** in the navigation
3. Click **"+ New Project"**

### Step 2: Basic Information

| Field | Description | Example |
|-------|-------------|---------|
| Project Name | Display name for the project | `My Web App` |
| GitHub Repository | Owner/repo format or full URL | `myuser/myrepo` |
| GitHub Token | Your personal access token | `ghp_xxx...` |
| Working Directory | Local path for git clone | `/home/user/projects/myrepo` |
| Default Branch | Main branch name | `main` or `master` |

### Step 3: Save and Clone

1. Click **"Create Project"**
2. The project card appears in the list
3. Click on the project to view details
4. Click **"Clone Repository"** if working directory is empty

---

## Project Settings

### General Settings

| Setting | Description | Default |
|---------|-------------|---------|
| Project Name | Display name | Required |
| Working Directory | Local clone path | Required |
| Default Branch | Branch for PRs | `main` |
| Max Concurrent | Parallel sessions | `1` |

### Automation Settings

| Setting | Description | Default |
|---------|-------------|---------|
| Auto-sync | Periodically fetch issues | `true` |
| Auto-start | Start sessions automatically | `false` |

### Verification Commands

Commands run after Claude completes work:

| Command | Purpose | Example |
|---------|---------|---------|
| Lint Command | Code style check | `npm run lint` |
| Test Command | Run tests | `npm test` |
| Build Command | Build project | `npm run build` |

---

## Local LLM Configuration

UltraClaude supports alternative LLM providers for users who prefer local models or different APIs.

### Ollama Setup

[Ollama](https://ollama.ai) runs LLMs locally on your machine.

#### Step 1: Install Ollama

```bash
# Linux
curl -fsSL https://ollama.ai/install.sh | sh

# macOS
brew install ollama

# Windows (via WSL)
curl -fsSL https://ollama.ai/install.sh | sh
```

#### Step 2: Download a Model

```bash
# Recommended models for coding
ollama pull llama3.2:latest          # General purpose
ollama pull codellama:13b            # Code-focused
ollama pull deepseek-coder:6.7b      # Code generation
ollama pull qwen2.5-coder:7b         # Latest coding model
```

#### Step 3: Start Ollama Server

```bash
ollama serve
# Server runs at http://localhost:11434
```

#### Step 4: Configure in UltraClaude

1. Edit or create a project
2. Under **LLM Provider**, select **"Ollama"**
3. Settings:
   - **API URL**: `http://localhost:11434`
   - **Model**: `llama3.2:latest`
   - **Context Length**: `8192` (adjust based on model)
   - **Temperature**: `0.1` (lower for coding)

4. Click **"Fetch Models"** to see available models
5. Click **"Test Connection"** to verify

---

### LM Studio Setup

[LM Studio](https://lmstudio.ai) provides a GUI for running local models.

#### Step 1: Install LM Studio

1. Download from https://lmstudio.ai
2. Install for your platform

#### Step 2: Download a Model

1. Open LM Studio
2. Go to the **Discover** tab
3. Search and download a model (e.g., `CodeLlama-7b-GGUF`)

#### Step 3: Start Local Server

1. Go to the **Local Server** tab
2. Select your downloaded model
3. Click **"Start Server"**
4. Note the URL (default: `http://localhost:1234`)

#### Step 4: Configure in UltraClaude

1. Under **LLM Provider**, select **"LM Studio"**
2. Settings:
   - **API URL**: `http://localhost:1234/v1`
   - **Model**: (auto-detected from server)
   - **Context Length**: Based on model
   - **Temperature**: `0.1`

3. Click **"Test Connection"** to verify

---

### OpenRouter Setup

[OpenRouter](https://openrouter.ai) provides access to many models via a single API.

#### Step 1: Get API Key

1. Go to https://openrouter.ai
2. Sign up or log in
3. Navigate to **Keys** section
4. Create a new API key
5. Copy the key (starts with `sk-or-`)

#### Step 2: Add Credits

1. Go to **Credits** in OpenRouter
2. Add payment method or credits
3. Most models charge per token

#### Step 3: Configure in UltraClaude

1. Under **LLM Provider**, select **"OpenRouter"**
2. Settings:
   - **API URL**: `https://openrouter.ai/api/v1`
   - **API Key**: `sk-or-v1-xxxxx`
   - **Model**: e.g., `anthropic/claude-3.5-sonnet`
   - **Context Length**: Based on model
   - **Temperature**: `0.1`

3. Click **"Fetch Models"** to see available options
4. Click **"Test Connection"** to verify

#### Recommended Models for Coding

| Model ID | Provider | Notes |
|----------|----------|-------|
| `anthropic/claude-3.5-sonnet` | Anthropic | Excellent coding |
| `anthropic/claude-3-opus` | Anthropic | Most capable |
| `openai/gpt-4-turbo` | OpenAI | Strong reasoning |
| `meta-llama/llama-3.1-70b-instruct` | Meta | Good balance |
| `deepseek/deepseek-coder` | DeepSeek | Code-focused |

---

## Issue Filters

Configure which issues UltraClaude should process:

### Include Labels

Only process issues with these labels:
```
bug, enhancement, feature
```

### Exclude Labels

Skip issues with these labels:
```
wontfix, duplicate, question, documentation
```

### Example Filter Configuration

For a project that only fixes bugs and adds features:

| Setting | Value |
|---------|-------|
| Include Labels | `bug, feature, enhancement` |
| Exclude Labels | `wontfix, duplicate, needs-discussion` |

---

## Verification Commands

Commands that run after Claude completes work to verify quality:

### Common Configurations

#### Node.js / npm

```
Lint: npm run lint
Test: npm test
Build: npm run build
```

#### Python

```
Lint: flake8 . && black --check .
Test: pytest
Build: python setup.py build
```

#### Go

```
Lint: golint ./...
Test: go test ./...
Build: go build ./...
```

#### Rust

```
Lint: cargo clippy
Test: cargo test
Build: cargo build
```

### Verification Behavior

1. After Claude says `/complete`, verification runs
2. If **all commands pass**: PR is created
3. If **any command fails**: Session marked as verification failed
4. Failed sessions can be retried from the UI

---

## Advanced Configuration

### Environment Variables

UltraClaude can be configured via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `ULTRACLAUDE_HOST` | Server bind address | `0.0.0.0` |
| `ULTRACLAUDE_PORT` | Server port | `8420` |
| `ULTRACLAUDE_DATA_DIR` | Data storage path | `./data` |

### Custom Server Port

```bash
python -m src.server --port 8080
```

### Data Storage

All data is stored in the `data/` directory:

```
data/
├── projects.json      # Project configurations
├── sessions.json      # Session state
├── issue_sessions.json # Issue tracking
└── sessions/          # Session logs
```

### Security Considerations

1. **Tokens are encrypted** at rest using Fernet encryption
2. **Never commit** the `data/` directory to version control
3. **Use fine-grained tokens** with minimal permissions
4. **Rotate tokens** periodically (every 90 days recommended)

---

## Troubleshooting Configuration

### "Invalid GitHub token"

- Verify token hasn't expired
- Check token has `repo` scope
- For fine-grained tokens, ensure repository is selected

### "Cannot clone repository"

- Verify working directory path is writable
- Check parent directory exists
- Ensure token has Contents: Read/Write

### "LLM connection failed"

- For Ollama: Verify `ollama serve` is running
- For LM Studio: Check server is started
- For OpenRouter: Verify API key and credits

### "Verification command failed"

- Test commands manually in the working directory
- Ensure all dependencies are installed
- Check command syntax is correct

---

## Next Steps

- [Usage Guide](USAGE.md) - Learn how to use UltraClaude effectively
- [API Reference](API.md) - Integrate with UltraClaude programmatically
- [Troubleshooting](TROUBLESHOOTING.md) - Common issues and solutions
