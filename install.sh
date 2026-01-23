#!/bin/bash
set -e

# UltraClaude Installation Script
# ================================
# This script installs UltraClaude and all its dependencies.
# Supports: Linux (Debian/Ubuntu, Fedora, Arch), macOS, WSL

REPO_URL="https://github.com/yourusername/ultraclaude.git"
INSTALL_DIR="${ULTRACLAUDE_DIR:-$HOME/ultraclaude}"
PORT="${ULTRACLAUDE_PORT:-8420}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_banner() {
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║                                                               ║"
    echo "║   ⚡ UltraClaude - Multi-Session Claude Code Manager          ║"
    echo "║                                                               ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

check_command() {
    if command -v "$1" &> /dev/null; then
        return 0
    else
        return 1
    fi
}

detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if [ -f /etc/debian_version ]; then
            echo "debian"
        elif [ -f /etc/fedora-release ]; then
            echo "fedora"
        elif [ -f /etc/arch-release ]; then
            echo "arch"
        else
            echo "linux"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    else
        echo "unknown"
    fi
}

install_system_deps() {
    local os=$(detect_os)
    info "Detected OS: $os"
    
    case $os in
        debian)
            info "Installing system dependencies (apt)..."
            sudo apt-get update -qq
            sudo apt-get install -y -qq python3 python3-pip python3-venv git tmux curl
            ;;
        fedora)
            info "Installing system dependencies (dnf)..."
            sudo dnf install -y -q python3 python3-pip git tmux curl
            ;;
        arch)
            info "Installing system dependencies (pacman)..."
            sudo pacman -Sy --noconfirm python python-pip git tmux curl
            ;;
        macos)
            if ! check_command brew; then
                info "Installing Homebrew..."
                /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            fi
            info "Installing system dependencies (brew)..."
            brew install python@3.11 git tmux curl
            ;;
        *)
            warn "Unknown OS. Please install manually: python3, pip, git, tmux, curl"
            ;;
    esac
}

install_nodejs() {
    if check_command node; then
        local node_version=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
        if [ "$node_version" -ge 18 ]; then
            success "Node.js $(node --version) already installed"
            return 0
        fi
    fi
    
    local os=$(detect_os)
    info "Installing Node.js..."
    
    case $os in
        debian)
            curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
            sudo apt-get install -y -qq nodejs
            ;;
        fedora)
            sudo dnf install -y -q nodejs
            ;;
        arch)
            sudo pacman -S --noconfirm nodejs npm
            ;;
        macos)
            brew install node
            ;;
        *)
            warn "Please install Node.js 18+ manually"
            ;;
    esac
}

install_claude_cli() {
    if check_command claude; then
        success "Claude Code CLI already installed"
        return 0
    fi
    
    info "Installing Claude Code CLI..."
    if check_command npm; then
        npm install -g @anthropic-ai/claude-code 2>/dev/null || {
            warn "Could not install Claude CLI globally. You may need sudo or to configure npm prefix."
            warn "Run: npm install -g @anthropic-ai/claude-code"
        }
    else
        warn "npm not found. Claude Code CLI not installed."
        warn "Install Node.js and run: npm install -g @anthropic-ai/claude-code"
    fi
}

clone_or_update_repo() {
    if [ -d "$INSTALL_DIR" ]; then
        info "UltraClaude directory exists, updating..."
        cd "$INSTALL_DIR"
        git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || warn "Could not pull updates"
    else
        info "Cloning UltraClaude..."
        git clone "$REPO_URL" "$INSTALL_DIR" 2>/dev/null || {
            info "Repository not available, assuming local install..."
            if [ -f "$(dirname "$0")/requirements.txt" ]; then
                INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
                info "Using local directory: $INSTALL_DIR"
            else
                error "Could not find UltraClaude source"
            fi
        }
    fi
    cd "$INSTALL_DIR"
}

setup_venv() {
    info "Setting up Python virtual environment..."
    
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    
    source venv/bin/activate
    
    info "Upgrading pip..."
    pip install --upgrade pip -q
    
    info "Installing Python dependencies..."
    pip install -r requirements.txt -q
    
    success "Python environment ready"
}

create_start_script() {
    info "Creating start script..."
    
    cat > "$INSTALL_DIR/start.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate

PORT="${ULTRACLAUDE_PORT:-8420}"
HOST="${ULTRACLAUDE_HOST:-0.0.0.0}"

echo "Starting UltraClaude on http://$HOST:$PORT"
echo "Press Ctrl+C to stop"
echo ""

python -m uvicorn src.server:app --host "$HOST" --port "$PORT"
EOF
    
    chmod +x "$INSTALL_DIR/start.sh"
    success "Created start.sh"
}

create_systemd_service() {
    if [[ "$(detect_os)" == "macos" ]]; then
        return 0
    fi
    
    if [ ! -d /etc/systemd/system ]; then
        return 0
    fi
    
    info "Creating systemd service (optional)..."
    
    local service_file="/etc/systemd/system/ultraclaude.service"
    local user=$(whoami)
    
    sudo tee "$service_file" > /dev/null << EOF
[Unit]
Description=UltraClaude - Multi-Session Claude Code Manager
After=network.target

[Service]
Type=simple
User=$user
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python -m uvicorn src.server:app --host 0.0.0.0 --port $PORT
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
    
    success "Created systemd service"
    info "To enable auto-start: sudo systemctl enable ultraclaude"
    info "To start now: sudo systemctl start ultraclaude"
}

verify_installation() {
    info "Verifying installation..."
    
    cd "$INSTALL_DIR"
    source venv/bin/activate
    
    python -c "from src.server import app; print('Server imports OK')" || error "Server import failed"
    
    success "Installation verified"
}

print_summary() {
    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║              Installation Complete!                           ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "Installation directory: ${BLUE}$INSTALL_DIR${NC}"
    echo ""
    echo -e "${YELLOW}Quick Start:${NC}"
    echo "  cd $INSTALL_DIR"
    echo "  ./start.sh"
    echo ""
    echo "  Then open: http://localhost:$PORT"
    echo ""
    echo -e "${YELLOW}Optional - Claude Code CLI:${NC}"
    if check_command claude; then
        echo -e "  ${GREEN}✓${NC} Claude Code CLI is installed"
        echo "  Run 'claude auth' to authenticate with Anthropic"
    else
        echo "  npm install -g @anthropic-ai/claude-code"
        echo "  claude auth"
    fi
    echo ""
    echo -e "${YELLOW}Optional - Local LLMs:${NC}"
    echo "  Ollama:    curl -fsSL https://ollama.ai/install.sh | sh"
    echo "  LM Studio: https://lmstudio.ai"
    echo ""
    echo -e "${YELLOW}Documentation:${NC}"
    echo "  $INSTALL_DIR/docs/INSTALLATION.md"
    echo "  $INSTALL_DIR/docs/CONFIGURATION.md"
    echo "  $INSTALL_DIR/docs/WORKFLOWS.md"
    echo ""
}

main() {
    print_banner
    
    info "Starting UltraClaude installation..."
    echo ""
    
    install_system_deps
    install_nodejs
    install_claude_cli
    clone_or_update_repo
    setup_venv
    create_start_script
    create_systemd_service
    verify_installation
    
    print_summary
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
