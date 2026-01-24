#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Installing UltraClaude service..."

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo ./install.sh)"
    exit 1
fi

cp "$SCRIPT_DIR/ultraclaude.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable ultraclaude
systemctl start ultraclaude

echo "UltraClaude service installed and started."
echo ""
echo "Commands:"
echo "  sudo systemctl status ultraclaude  - Check status"
echo "  sudo systemctl restart ultraclaude - Restart service"
echo "  sudo journalctl -u ultraclaude -f  - View logs"
echo ""
echo "Dashboard: http://localhost:8420"
