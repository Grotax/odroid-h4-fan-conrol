#!/bin/bash
#
# Installation script for Odroid H4 Fan Control Service
# This script installs the fan control script as a systemd service
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="fan-control.py"
SERVICE_NAME="odroid-fan-control.service"
INSTALL_PATH="/usr/local/bin/fan-control.py"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"

echo -e "${BLUE}Odroid H4 Fan Control Service Installer${NC}"
echo "========================================"

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo -e "${YELLOW}Running as root user${NC}"
   SUDO=""
else
   echo -e "${YELLOW}Running as regular user (will use sudo when needed)${NC}"
   SUDO="sudo"
fi

# Check if script exists
if [[ ! -f "${SCRIPT_DIR}/${SCRIPT_NAME}" ]]; then
    echo -e "${RED}Error: ${SCRIPT_NAME} not found in current directory${NC}"
    exit 1
fi

# Check if service file exists
if [[ ! -f "${SCRIPT_DIR}/${SERVICE_NAME}" ]]; then
    echo -e "${RED}Error: ${SERVICE_NAME} not found in current directory${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 1: Installing dependencies...${NC}"
$SUDO apt update
$SUDO apt install -y lm-sensors smartmontools python3

echo -e "${YELLOW}Step 2: Loading it87 kernel module...${NC}"
if ! lsmod | grep -q it87; then
    $SUDO modprobe it87 || echo -e "${YELLOW}Warning: Could not load it87 module${NC}"
    # Add to /etc/modules for permanent loading
    if ! grep -q "it87" /etc/modules; then
        echo "it87" | $SUDO tee -a /etc/modules
        echo -e "${GREEN}Added it87 to /etc/modules for permanent loading${NC}"
    fi
else
    echo -e "${GREEN}it87 module already loaded${NC}"
fi

echo -e "${YELLOW}Step 3: Testing fan control script...${NC}"
# Make script executable
chmod +x "${SCRIPT_DIR}/${SCRIPT_NAME}"

# Test script
echo "Testing script functionality..."
python3 "${SCRIPT_DIR}/${SCRIPT_NAME}" --status
echo -e "${GREEN}Script test completed${NC}"

echo -e "${YELLOW}Step 4: Installing script and service...${NC}"
# Copy script to system location
$SUDO cp "${SCRIPT_DIR}/${SCRIPT_NAME}" "${INSTALL_PATH}"
$SUDO chown root:root "${INSTALL_PATH}"
$SUDO chmod 755 "${INSTALL_PATH}"
echo -e "${GREEN}Installed script to ${INSTALL_PATH}${NC}"

# Copy service file
$SUDO cp "${SCRIPT_DIR}/${SERVICE_NAME}" "${SERVICE_PATH}"
$SUDO chown root:root "${SERVICE_PATH}"
$SUDO chmod 644 "${SERVICE_PATH}"
echo -e "${GREEN}Installed service file to ${SERVICE_PATH}${NC}"

echo -e "${YELLOW}Step 5: Configuring PWM path...${NC}"
echo "You need to configure the PWM path for your system."
echo "Choose one of the following options:"
echo ""
echo "1) Run interactive configuration (recommended)"
echo "2) Skip configuration (configure manually later)"
echo ""
read -p "Enter your choice (1-2): " choice

case $choice in
    1)
        echo -e "${BLUE}Running interactive PWM configuration...${NC}"
        $SUDO python3 "${INSTALL_PATH}" --configure
        ;;
    2)
        echo -e "${YELLOW}Skipping configuration. You can configure later with:${NC}"
        echo "$SUDO ${INSTALL_PATH} --configure"
        ;;
    *)
        echo -e "${YELLOW}Invalid choice. Skipping configuration.${NC}"
        ;;
esac

echo -e "${YELLOW}Step 6: Enabling and starting service...${NC}"
# Reload systemd
$SUDO systemctl daemon-reload

# Enable service
$SUDO systemctl enable "${SERVICE_NAME%.service}"
echo -e "${GREEN}Service enabled${NC}"

# Start service
$SUDO systemctl start "${SERVICE_NAME%.service}"
echo -e "${GREEN}Service started${NC}"

echo ""
echo -e "${GREEN}Installation completed successfully!${NC}"
echo ""
echo -e "${BLUE}Service Management Commands:${NC}"
echo "  Status:  $SUDO systemctl status ${SERVICE_NAME%.service}"
echo "  Stop:    $SUDO systemctl stop ${SERVICE_NAME%.service}"
echo "  Start:   $SUDO systemctl start ${SERVICE_NAME%.service}"
echo "  Restart: $SUDO systemctl restart ${SERVICE_NAME%.service}"
echo "  Logs:    $SUDO journalctl -u ${SERVICE_NAME%.service} -f"
echo ""
echo -e "${BLUE}Configuration:${NC}"
echo "  Configure PWM: $SUDO ${INSTALL_PATH} --configure"
echo "  Test fan:      $SUDO ${INSTALL_PATH} --test-fan"
echo "  Show status:   ${INSTALL_PATH} --status"
echo ""
echo -e "${YELLOW}The service is now running and will start automatically on boot.${NC}"
echo -e "${YELLOW}Check the status with: $SUDO systemctl status ${SERVICE_NAME%.service}${NC}"
