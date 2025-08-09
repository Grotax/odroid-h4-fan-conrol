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

1. Clone or download the script:
   ```bash
   wget https://raw.githubusercontent.com/your-repo/fan-control.py
   # or
   git clone https://github.com/your-repo/odroid-h4-fan-control.git
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

## Running as a Service

Create a systemd service file:

```bash
sudo nano /etc/systemd/system/fan-control.service
```

```ini
[Unit]
Description=Odroid H4 Fan Control
After=multi-user.target

[Service]
Type=simple
ExecStart=/path/to/fan-control.py --log-level INFO
Restart=always
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable fan-control.service
sudo systemctl start fan-control.service
```

## Troubleshooting

### Fan Not Working
1. Check if it87 kernel module is loaded: `lsmod | grep it87`
2. Load the module: `sudo modprobe it87`
3. Run interactive configuration: `sudo ./fan-control.py --configure`

### Permissions Issues
- Fan control requires root privileges
- Use `sudo` for all fan control operations
- Information commands (--info, --status) don't require root

### Temperature Not Detected
- Install lm-sensors: `sudo apt install lm-sensors`
- Run sensors-detect: `sudo sensors-detect`
- For HDD temperatures, install smartmontools: `sudo apt install smartmontools`

### Debug Information
Run with debug logging to see detailed information:
```bash
sudo ./fan-control.py --debug --info
```

## Hardware Support

Tested on:
- Odroid H4 with it8613 sensor chip
- Similar systems using it87 family sensors

Should work on any system with:
- PWM-controllable fans
- Hardware monitoring via hwmon interface
- Compatible sensor chips (it87 family)

## License

This script is provided as-is for educational and practical use. Modify as needed for your system.
