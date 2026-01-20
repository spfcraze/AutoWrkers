# Installation Guide

This guide covers the complete installation process for UltraClaude on different operating systems.

## Table of Contents

- [System Requirements](#system-requirements)
- [Linux Installation](#linux-installation)
- [macOS Installation](#macos-installation)
- [Windows (WSL) Installation](#windows-wsl-installation)
- [Docker Installation](#docker-installation)
- [Verifying Installation](#verifying-installation)

---

## System Requirements

### Minimum Requirements

- **OS**: Linux, macOS, or Windows with WSL2
- **Python**: 3.9 or higher
- **RAM**: 4GB minimum (8GB+ recommended for local LLMs)
- **Disk**: 500MB for application + space for repositories
- **Network**: Internet access for GitHub integration

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.9+ | Core application |
| pip | Latest | Package management |
| Git | 2.0+ | Repository operations |
| tmux | 3.0+ | Claude Code session management |
| Node.js | 18+ | Claude Code CLI (optional) |

---

## Linux Installation

### Ubuntu/Debian

```bash
# Update package manager
sudo apt update && sudo apt upgrade -y

# Install system dependencies
sudo apt install -y python3 python3-pip python3-venv git tmux curl

# Install Node.js (for Claude Code CLI)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Install Claude Code CLI (optional - for Claude Code provider)
npm install -g @anthropic-ai/claude-code

# Clone UltraClaude
git clone https://github.com/yourusername/ultraclaude.git
cd ultraclaude

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Start the server
python -m src.server
```

### Fedora/RHEL/CentOS

```bash
# Install system dependencies
sudo dnf install -y python3 python3-pip git tmux curl

# Install Node.js
sudo dnf install -y nodejs

# Install Claude Code CLI
npm install -g @anthropic-ai/claude-code

# Clone and setup
git clone https://github.com/yourusername/ultraclaude.git
cd ultraclaude
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start server
python -m src.server
```

### Arch Linux

```bash
# Install dependencies
sudo pacman -S python python-pip git tmux nodejs npm

# Install Claude Code CLI
npm install -g @anthropic-ai/claude-code

# Clone and setup
git clone https://github.com/yourusername/ultraclaude.git
cd ultraclaude
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start server
python -m src.server
```

---

## macOS Installation

### Using Homebrew

```bash
# Install Homebrew if not present
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install dependencies
brew install python@3.11 git tmux node

# Install Claude Code CLI
npm install -g @anthropic-ai/claude-code

# Clone UltraClaude
git clone https://github.com/yourusername/ultraclaude.git
cd ultraclaude

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start server
python -m src.server
```

### Apple Silicon (M1/M2/M3) Notes

The application works natively on Apple Silicon. If you encounter any issues with dependencies:

```bash
# Install Rosetta 2 (if needed for some packages)
softwareupdate --install-rosetta

# For ARM-native Python
arch -arm64 brew install python@3.11
```

---

## Windows (WSL) Installation

UltraClaude runs on Windows through WSL2 (Windows Subsystem for Linux).

### Step 1: Install WSL2

```powershell
# Run in PowerShell as Administrator
wsl --install

# Restart your computer when prompted
```

### Step 2: Install Ubuntu in WSL

```powershell
# Install Ubuntu
wsl --install -d Ubuntu

# Launch Ubuntu and complete initial setup
```

### Step 3: Install Dependencies in WSL

```bash
# Update packages
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3 python3-pip python3-venv git tmux curl

# Install Node.js
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Install Claude Code CLI
npm install -g @anthropic-ai/claude-code
```

### Step 4: Clone and Run

```bash
# Clone UltraClaude
cd ~
git clone https://github.com/yourusername/ultraclaude.git
cd ultraclaude

# Setup virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start server
python -m src.server
```

### Accessing from Windows

Open your browser and navigate to `http://localhost:8420`

The WSL network is accessible from Windows at localhost.

---

## Docker Installation

### Using Docker Compose (Recommended)

Create a `docker-compose.yml`:

```yaml
version: '3.8'

services:
  ultraclaude:
    build: .
    ports:
      - "8420:8420"
    volumes:
      - ./data:/app/data
      - ~/.ssh:/root/.ssh:ro  # For git operations
    environment:
      - PYTHONUNBUFFERED=1
    restart: unless-stopped
```

Create a `Dockerfile`:

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    tmux \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose port
EXPOSE 8420

# Run server
CMD ["python", "-m", "src.server"]
```

Run with Docker Compose:

```bash
docker-compose up -d
```

### Using Docker Only

```bash
# Build image
docker build -t ultraclaude .

# Run container
docker run -d \
  --name ultraclaude \
  -p 8420:8420 \
  -v $(pwd)/data:/app/data \
  ultraclaude
```

---

## Verifying Installation

### 1. Check Python Environment

```bash
# Activate virtual environment
source venv/bin/activate

# Verify Python version
python --version  # Should be 3.9+

# Check installed packages
pip list | grep -E "fastapi|uvicorn|websockets|httpx"
```

### 2. Verify tmux

```bash
# Check tmux is installed
tmux -V  # Should show version 3.0+

# Test creating a session
tmux new-session -d -s test
tmux list-sessions
tmux kill-session -t test
```

### 3. Verify Claude Code CLI (Optional)

```bash
# Check Claude Code is installed
claude --version

# Test authentication
claude auth status
```

### 4. Start the Server

```bash
# Start server
python -m src.server

# You should see:
# INFO:     Started server process [xxxxx]
# INFO:     Waiting for application startup.
# INFO:     Application startup complete.
# INFO:     Uvicorn running on http://0.0.0.0:8420
```

### 5. Test Web Interface

1. Open browser to `http://localhost:8420`
2. You should see the UltraClaude dashboard
3. Navigate to Projects page

### 6. Test API

```bash
# Test API endpoint
curl http://localhost:8420/api/sessions

# Should return:
# {"sessions":[]}
```

---

## Troubleshooting Installation

### "ModuleNotFoundError: No module named 'xxx'"

```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### "tmux: command not found"

```bash
# Ubuntu/Debian
sudo apt install tmux

# macOS
brew install tmux

# Fedora
sudo dnf install tmux
```

### "Permission denied" when cloning repositories

```bash
# Set up SSH key for GitHub
ssh-keygen -t ed25519 -C "your_email@example.com"
cat ~/.ssh/id_ed25519.pub
# Add this key to GitHub: Settings > SSH and GPG keys

# Or use HTTPS with token (configured in UltraClaude)
```

### Port 8420 already in use

```bash
# Find process using port
lsof -i :8420

# Kill process or use different port
python -m src.server --port 8421
```

### WSL: "Cannot connect to localhost"

```bash
# Check WSL network
wsl hostname -I

# Use the IP address shown instead of localhost
```

---

## Next Steps

After successful installation:

1. [Configure GitHub Tokens](CONFIGURATION.md#github-token-setup)
2. [Create Your First Project](CONFIGURATION.md#creating-a-project)
3. [Set Up Local LLMs](CONFIGURATION.md#local-llm-configuration) (optional)

---

## Updating UltraClaude

```bash
# Navigate to directory
cd ultraclaude

# Pull latest changes
git pull origin main

# Update dependencies
source venv/bin/activate
pip install -r requirements.txt

# Restart server
```
