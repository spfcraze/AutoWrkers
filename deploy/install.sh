#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Installing Autowrkers service..."

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo ./install.sh)"
    exit 1
fi

cp "$SCRIPT_DIR/autowrkers.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable autowrkers
systemctl start autowrkers

echo "Autowrkers service installed and started."
echo ""
echo "Commands:"
echo "  sudo systemctl status autowrkers  - Check status"
echo "  sudo systemctl restart autowrkers - Restart service"
echo "  sudo journalctl -u autowrkers -f  - View logs"
echo ""
echo "Dashboard: http://localhost:8420"
