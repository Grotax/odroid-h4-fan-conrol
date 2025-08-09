# Odroid H4 Fan Control Script v2.0

Advanced fan control script for Odroid H4 and similar systems with automatic temperature monitoring and incremental speed adjustment.

## Features

- 🌡️ **Temperature Monitoring**: CPU via lm-sensors, HDDs via smartctl
- 🔄 **Incremental Speed Control**: Smooth fan speed transitions with hysteresis
- 🔍 **Auto-Discovery**: Automatic PWM path detection with interactive configuration
- 📊 **Comprehensive Logging**: Configurable log levels (DEBUG, INFO, WARNING, ERROR)
- ⚙️ **Flexible Configuration**: Multiple ways to configure PWM paths
- 🧪 **Testing Tools**: Built-in fan testing and system information display

## Requirements

- Python 3.x
- `lm-sensors` package (`sensors` command)
- `smartmontools` package (`smartctl` command)
- `it87` kernel module (for Odroid H4)
- Root privileges for fan control

## Installation

### Quick Install (Recommended)

1. Clone the repository:
   ```bash
   git clone https://github.com/Grotax/odroid-h4-fan-control.git
   cd odroid-h4-fan-control
   ```

2. Run the installation script:
   ```bash
   ./install.sh
   ```

The installation script works with both regular users (using sudo when needed) and root users (common on server systems like Proxmox). It will automatically:
- Install required dependencies
- Load and configure kernel modules  
- Test the fan control functionality
- Set up the systemd service
- Guide you through PWM configuration
- Start the service

### Manual Installation

1. Clone or download the script:
   ```bash
   git clone https://github.com/Grotax/odroid-h4-fan-control.git
   # or download individual files
   ```

2. Make it executable:
   ```bash
   chmod +x fan-control.py
   ```

3. Install dependencies:
   ```bash
   sudo apt update
   sudo apt install lm-sensors smartmontools
   sudo modprobe it87  # Load kernel module
   ```

### Uninstallation

To completely remove the fan control service:

```bash
./uninstall.sh
```

This will:
- Stop and disable the systemd service
- Remove the service file and script
- Clean up systemd configuration
- Optionally remove kernel module configuration

## Quick Start

### 1. Interactive Configuration (Recommended)
```bash
sudo ./fan-control.py --configure
```
This will guide you through finding the correct PWM path for your system.

### 2. Test Your Configuration
```bash
sudo ./fan-control.py --test-fan
```

### 3. Check System Status
```bash
./fan-control.py --status
```

### 4. Run Fan Control
```bash
sudo ./fan-control.py --log-level INFO
```

## Usage Examples

```bash
# Basic operation with auto-detection
sudo ./fan-control.py

# Run with informational logging
sudo ./fan-control.py --log-level INFO

# Force specific PWM path
sudo ./fan-control.py --pwm-path /sys/class/hwmon/hwmon3/pwm2

# Show detailed system information
./fan-control.py --info

# Check current temperatures and fan status
./fan-control.py --status

# Test fan control functionality
sudo ./fan-control.py --test-fan

# Interactive PWM path configuration
sudo ./fan-control.py --configure

# Debug mode for troubleshooting
sudo ./fan-control.py --debug
```

## Configuration

### Method 1: Interactive Configuration
Run `sudo ./fan-control.py --configure` and follow the prompts.

### Method 2: Manual Configuration
Edit the `MANUAL_PWM_PATH` variable in the script:
```python
MANUAL_PWM_PATH = '/sys/class/hwmon/hwmon3/pwm2'  # Your PWM path
```

### Method 3: Command Line Override
Use `--pwm-path` for temporary override:
```bash
sudo ./fan-control.py --pwm-path /sys/class/hwmon/hwmon3/pwm2
```

## Temperature Thresholds

Edit these values in the script to customize temperature control:

```python
TEMP_MIN = 35          # Minimum temperature (fan at minimum speed)
TEMP_MAX = 70          # Maximum temperature (fan at maximum speed)
TEMP_TARGET = 50       # Target temperature to maintain
FAN_SPEED_MIN = 80     # Minimum fan speed (safety)
FAN_SPEED_MAX = 255    # Maximum fan speed
```

### Fan PWM Behavior Notes

Different fans have different PWM stop values:
- **Most fans**: Stop at PWM 0
- **Some fans (e.g., Noctua)**: Stop at PWM 1 or 2
- **Server fans**: May require higher minimum values

Use `sudo ./fan-control.py --test-fan` to discover your fan's behavior and adjust `FAN_SPEED_MIN` accordingly. The test will show you the exact PWM value where your fan stops.

## Running as a Service

### Automatic Installation (Recommended)

Use the provided installation script for easy setup:

```bash
./install.sh
```

This script will:
1. Install required dependencies (lm-sensors, smartmontools)
2. Load and configure the it87 kernel module
3. Test the fan control script
4. Install the script to `/usr/local/bin/`
5. Set up the systemd service
6. Guide you through PWM configuration
7. Enable and start the service

### Manual Installation

#### 1. Install the Script and Service

```bash
# Copy script to system location
sudo cp fan-control.py /usr/local/bin/
sudo chmod 755 /usr/local/bin/fan-control.py

# Install service file
sudo cp odroid-fan-control.service /etc/systemd/system/
sudo chmod 644 /etc/systemd/system/odroid-fan-control.service
```

#### 2. Configure PWM Path

```bash
# Run interactive configuration
sudo /usr/local/bin/fan-control.py --configure

# Or edit the script manually
sudo nano /usr/local/bin/fan-control.py
# Set: MANUAL_PWM_PATH = '/sys/class/hwmon/hwmon3/pwm2'
```

#### 3. Enable and Start Service

```bash
# Reload systemd configuration
sudo systemctl daemon-reload

# Enable service (start automatically on boot)
sudo systemctl enable odroid-fan-control

# Start service now
sudo systemctl start odroid-fan-control
```

### Service Management

#### Basic Commands
```bash
# Check service status
sudo systemctl status odroid-fan-control

# Start service
sudo systemctl start odroid-fan-control

# Stop service
sudo systemctl stop odroid-fan-control

# Restart service
sudo systemctl restart odroid-fan-control

# Enable autostart on boot
sudo systemctl enable odroid-fan-control

# Disable autostart
sudo systemctl disable odroid-fan-control
```

#### Viewing Logs
```bash
# View recent logs
sudo journalctl -u odroid-fan-control

# Follow logs in real-time
sudo journalctl -u odroid-fan-control -f

# View logs from last boot
sudo journalctl -u odroid-fan-control -b

# View logs with timestamps
sudo journalctl -u odroid-fan-control --since "1 hour ago"
```

#### Configuration Changes
After modifying the script configuration:
```bash
# Restart the service to apply changes
sudo systemctl restart odroid-fan-control

# Check if service is running properly
sudo systemctl status odroid-fan-control
```

### Service Features

The systemd service includes:
- **Automatic restart**: Service restarts if it crashes
- **Boot integration**: Starts automatically after system boot
- **Security hardening**: Runs with minimal privileges
- **Resource limits**: Memory and CPU usage constraints
- **Dependency management**: Waits for required services
- **Proper logging**: Integrates with systemd journal

### Service Security

The service file includes security hardening:
- `NoNewPrivileges=true`: Cannot gain new privileges
- `ProtectSystem=strict`: Read-only access to most system files
- `ProtectHome=true`: No access to user home directories
- `ReadWritePaths=/sys/class/hwmon`: Only hwmon access allowed
- `MemoryMax=64M`: Memory usage limit
- `CPUQuota=10%`: CPU usage limit

### Uninstalling the Service

```bash
# Stop and disable service
sudo systemctl stop odroid-fan-control
sudo systemctl disable odroid-fan-control

# Remove service file
sudo rm /etc/systemd/system/odroid-fan-control.service

# Remove script
sudo rm /usr/local/bin/fan-control.py

# Reload systemd
sudo systemctl daemon-reload
```

## Troubleshooting

### Fan Not Working
1. Check if it87 kernel module is loaded: `lsmod | grep it87`
2. Load the module: `sudo modprobe it87`
3. Run interactive configuration: `sudo ./fan-control.py --configure`
4. Test fan behavior: `sudo ./fan-control.py --test-fan`

### Fan Behavior Issues
- **Fan won't stop**: Some fans (like Noctua) stop at PWM 1 instead of 0
- **Fan minimum speed too low**: Adjust `FAN_SPEED_MIN` based on your fan's characteristics
- **Fan stuttering**: Usually caused by PWM value too close to fan's stop threshold

**Finding your fan's stop value:**
```bash
# Test manually (replace hwmon3/pwm2 with your path)
echo "0" > /sys/class/hwmon/hwmon3/pwm2  # Try 0
echo "1" > /sys/class/hwmon/hwmon3/pwm2  # Try 1  
echo "2" > /sys/class/hwmon/hwmon3/pwm2  # Try 2
# Use the lowest value where fan completely stops
```

### Permissions Issues
- Fan control requires root privileges
- Use `sudo` for all fan control operations
- Information commands (--info, --status) don't require root

### Temperature Not Detected
- Install lm-sensors: `sudo apt install lm-sensors`
- Run sensors-detect: `sudo sensors-detect`
- For HDD temperatures, install smartmontools: `sudo apt install smartmontools`

### Service Issues

#### Service Won't Start
```bash
# Check service status for errors
sudo systemctl status odroid-fan-control

# Check detailed logs
sudo journalctl -u odroid-fan-control --no-pager

# Check if script is executable and in correct location
ls -la /usr/local/bin/fan-control.py

# Test script manually
sudo /usr/local/bin/fan-control.py --status
```

#### Service Keeps Restarting
```bash
# Check logs for error messages
sudo journalctl -u odroid-fan-control -f

# Common issues:
# - PWM path not configured correctly
# - Missing kernel module (it87)
# - Hardware not supported
# - Script syntax errors
```

#### High CPU Usage
```bash
# Check if debug logging is enabled (causes high log volume)
sudo journalctl -u odroid-fan-control | grep DEBUG

# Service is configured with 10% CPU quota limit
# Check resource usage:
sudo systemctl show odroid-fan-control --property=CPUUsageNSec
```

#### Memory Issues
```bash
# Service has 64MB memory limit
# Check memory usage:
sudo systemctl show odroid-fan-control --property=MemoryCurrent
```

#### Service Logs
```bash
# View all logs
sudo journalctl -u odroid-fan-control

# View errors only
sudo journalctl -u odroid-fan-control -p err

# Clear old logs (if disk space is an issue)
sudo journalctl --vacuum-time=7d
```

### Debug Information
Run with debug logging to see detailed information:
```bash
sudo ./fan-control.py --debug --info
```

### Testing Service Configuration
```bash
# Test script before installing as service
sudo ./fan-control.py --test-fan

# Check systemd service file syntax
sudo systemctl cat odroid-fan-control

# Validate service file
sudo systemd-analyze verify /etc/systemd/system/odroid-fan-control.service
```

## Hardware Support

Tested on:
- Odroid H4 with it8613 sensor chip
- Proxmox VE hosts (root-only environments)
- Similar systems using it87 family sensors

Should work on any system with:
- PWM-controllable fans
- Hardware monitoring via hwmon interface
- Compatible sensor chips (it87 family)

**Note for Proxmox Users**: The installation scripts automatically detect if you're running as root (common on Proxmox hosts) and work without requiring sudo.

## License

This script is provided as-is for educational and practical use. Modify as needed for your system.
