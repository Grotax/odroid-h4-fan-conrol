#!/bin/bash
#
# Uninstallation script for Odroid H4 Fan Control Service
# This script removes the fan control service and script
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script paths
SERVICE_NAME="odroid-fan-control"
INSTALL_PATH="/usr/local/bin/fan-control.py"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

echo -e "${BLUE}Odroid H4 Fan Control Service Uninstaller${NC}"
echo "============================================"

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo -e "${YELLOW}Running as root user${NC}"
   SUDO=""
else
   echo -e "${YELLOW}Running as regular user (will use sudo when needed)${NC}"
   SUDO="sudo"
fi

echo -e "${YELLOW}This will remove the Odroid H4 fan control service and script.${NC}"
read -p "Are you sure you want to continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Uninstallation cancelled."
    exit 0
fi

echo -e "${YELLOW}Step 1: Stopping and disabling service...${NC}"
# Stop service if running
if systemctl is-active --quiet "${SERVICE_NAME}"; then
    $SUDO systemctl stop "${SERVICE_NAME}"
    echo -e "${GREEN}Service stopped${NC}"
fi

# Disable service if enabled
if systemctl is-enabled --quiet "${SERVICE_NAME}"; then
    $SUDO systemctl disable "${SERVICE_NAME}"
    echo -e "${GREEN}Service disabled${NC}"
fi

echo -e "${YELLOW}Step 2: Removing service file...${NC}"
if [[ -f "${SERVICE_PATH}" ]]; then
    $SUDO rm "${SERVICE_PATH}"
    echo -e "${GREEN}Removed ${SERVICE_PATH}${NC}"
else
    echo -e "${YELLOW}Service file not found${NC}"
fi

echo -e "${YELLOW}Step 3: Removing script...${NC}"
if [[ -f "${INSTALL_PATH}" ]]; then
    $SUDO rm "${INSTALL_PATH}"
    echo -e "${GREEN}Removed ${INSTALL_PATH}${NC}"
else
    echo -e "${YELLOW}Script file not found${NC}"
fi

echo -e "${YELLOW}Step 4: Reloading systemd configuration...${NC}"
$SUDO systemctl daemon-reload
$SUDO systemctl reset-failed
echo -e "${GREEN}Systemd configuration reloaded${NC}"

echo -e "${YELLOW}Step 5: Optional cleanup...${NC}"
echo "The following items were NOT removed and may be cleaned up manually if desired:"
echo "  - it87 kernel module (still loaded)"
echo "  - lm-sensors package"
echo "  - smartmontools package"
echo "  - /etc/modules entry for it87"
echo ""

read -p "Remove it87 from /etc/modules? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    $SUDO sed -i '/^it87$/d' /etc/modules
    echo -e "${GREEN}Removed it87 from /etc/modules${NC}"
    echo -e "${YELLOW}Note: it87 module will remain loaded until next reboot${NC}"
fi

echo ""
echo -e "${GREEN}Uninstallation completed successfully!${NC}"
echo ""
echo -e "${BLUE}What was removed:${NC}"
echo "  ✓ Systemd service (${SERVICE_NAME})"
echo "  ✓ Fan control script (${INSTALL_PATH})"
echo "  ✓ Service configuration"
echo ""
echo -e "${YELLOW}The fan control service has been completely removed from your system.${NC}"
