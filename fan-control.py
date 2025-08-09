# fan_control_script.py

import subprocess
import time
import re
import sys
import os
import glob

# fan_control_script.py

import subprocess
import time
import re
import sys
import os
import glob
import json
import argparse
import logging

# Configure logging
logger = logging.getLogger(__name__)

def setup_logging(debug=False):
    """Setup logging configuration."""
    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # Set log level
    if debug:
        logger.setLevel(logging.DEBUG)
        console_handler.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.WARNING)
        console_handler.setLevel(logging.WARNING)
    
    # Add handler to logger
    logger.addHandler(console_handler)

# --- Configuration ---
# Temperature and fan speed configuration
# The script will smoothly adjust fan speed based on temperature

# Temperature range configuration
TEMP_MIN = 35          # Minimum temperature (fan at minimum speed)
TEMP_MAX = 70          # Maximum temperature (fan at maximum speed)
TEMP_TARGET = 50       # Target temperature to maintain

# Fan speed configuration (0-255 PWM values)
FAN_SPEED_MIN = 80     # Minimum fan speed (never go below this for safety)
FAN_SPEED_MAX = 255    # Maximum fan speed

# Control behavior
FAN_STEP_SIZE = 10     # How much to change fan speed per adjustment
TEMP_HYSTERESIS = 2    # Temperature hysteresis to prevent oscillation
UPDATE_INTERVAL = 30   # Seconds between temperature checks

# Auto-discover drives - no need to manually specify them
# The script will automatically find all physical drives

def check_kernel_module():
    """
    Check if the it87 kernel module is loaded.
    Returns True if loaded, False otherwise.
    """
    try:
        logger.debug("Checking if it87 kernel module is loaded...")
        result = subprocess.run(['lsmod'], capture_output=True, text=True, check=True)
        if 'it87' in result.stdout:
            logger.debug("it87 kernel module is loaded")
            return True
        else:
            logger.warning("it87 kernel module is not loaded")
            logger.warning("To load it87 module, run: sudo modprobe it87")
            return False
    except subprocess.CalledProcessError as e:
        logger.debug(f"lsmod command failed: {e}")
        logger.error(f"Error checking kernel modules: {e}")
        return False

def find_fan_control_path():
    """
    Dynamically finds the correct PWM control path for the fan.
    For Odroid H4, pwm2 is typically the correct one, but we check for functionality.
    Returns the path if found, None otherwise.
    """
    logger.debug("Searching for fan control PWM paths...")
    # Look for PWM controls in all hwmon directories
    pwm_paths = glob.glob('/sys/class/hwmon/hwmon*/pwm*')
    logger.debug(f"Found PWM paths: {pwm_paths}")
    
    # For Odroid H4, pwm2 is typically the CPU fan, but let's be smart about detection
    # Prioritize based on known working configurations
    preferred_pwm_names = ['pwm2', 'pwm1', 'pwm3', 'pwm4', 'pwm5']
    
    # First, try to find preferred PWM controls and test functionality
    for pwm_name in preferred_pwm_names:
        for path in pwm_paths:
            if path.endswith(pwm_name):
                logger.debug(f"Checking preferred PWM path: {path}")
                
                # Check if PWM is writable first
                if not os.access(path, os.W_OK):
                    logger.debug(f"PWM path {path} is not writable")
                    continue
                
                # Test if this PWM actually controls a fan by checking fan input
                hwmon_dir = os.path.dirname(path)
                fan_input = os.path.join(hwmon_dir, pwm_name.replace('pwm', 'fan') + '_input')
                
                # Get hwmon device name for context
                name_file = os.path.join(hwmon_dir, 'name')
                hwmon_name = "unknown"
                try:
                    with open(name_file, 'r') as f:
                        hwmon_name = f.read().strip()
                        logger.debug(f"Hwmon device name: {hwmon_name}")
                except Exception as e:
                    logger.debug(f"Could not read hwmon name: {e}")
                
                # Try to read current fan speed
                current_fan_speed = None
                try:
                    if os.path.exists(fan_input):
                        with open(fan_input, 'r') as f:
                            current_fan_speed = int(f.read().strip())
                            logger.debug(f"Current fan speed at {fan_input}: {current_fan_speed} RPM")
                    else:
                        logger.debug(f"No corresponding fan input found for {path}")
                except Exception as e:
                    logger.debug(f"Could not read fan input {fan_input}: {e}")
                
                # Test PWM functionality by briefly changing it (if fan is currently running)
                pwm_functional = False
                try:
                    # Read current PWM value
                    with open(path, 'r') as f:
                        current_pwm = int(f.read().strip())
                        logger.debug(f"Current PWM value at {path}: {current_pwm}")
                    
                    # If we have a good baseline (fan running or PWM > 0), this is likely the right one
                    if current_fan_speed and current_fan_speed > 0:
                        logger.debug(f"Fan is currently running at {current_fan_speed} RPM - this PWM is likely functional")
                        pwm_functional = True
                    elif current_pwm > 0:
                        logger.debug(f"PWM is set to {current_pwm} - this PWM is likely functional")
                        pwm_functional = True
                    else:
                        # For Odroid H4, pwm2 is known to work, so prioritize it even if fan is off
                        if pwm_name == 'pwm2' and hwmon_name in ['it87', 'it8721']:
                            logger.debug(f"This is pwm2 on it87 - likely the correct PWM for Odroid H4")
                            pwm_functional = True
                        else:
                            logger.debug(f"PWM shows 0 and fan is off - may not be the active PWM")
                    
                except Exception as e:
                    logger.debug(f"Could not read current PWM value: {e}")
                
                if pwm_functional:
                    logger.info(f"Selected fan control path: {path} (hwmon: {hwmon_name}, PWM: {pwm_name})")
                    if current_fan_speed:
                        logger.info(f"Fan currently running at {current_fan_speed} RPM")
                    return path
                else:
                    logger.debug(f"PWM {path} doesn't appear to be functional")
    
    # If no preferred PWM found with active fan, try any writable PWM as fallback
    logger.debug("No clearly functional PWM found, trying any writable PWM control...")
    for path in pwm_paths:
        if os.access(path, os.W_OK):
            logger.debug(f"Fallback: checking PWM path: {path}")
            hwmon_dir = os.path.dirname(path)
            name_file = os.path.join(hwmon_dir, 'name')
            
            try:
                with open(name_file, 'r') as f:
                    hwmon_name = f.read().strip()
                    logger.debug(f"Hwmon device name: {hwmon_name}")
                    
                logger.warning(f"Using fallback fan control path: {path} (hwmon: {hwmon_name})")
                return path
            except Exception as e:
                logger.debug(f"Could not read hwmon name: {e}")
                logger.warning(f"Using fallback fan control path: {path}")
                return path
    
    logger.error("No writable PWM control path found")
    return None

def discover_drives():
    """
    Automatically discovers all physical drives (HDDs and SSDs) in the system.
    Returns a list of device paths that support SMART monitoring.
    """
    drives = []
    
    logger.debug("Starting drive discovery...")
    # Look for block devices that are physical drives
    try:
        # Use lsblk to get all block devices
        logger.debug("Running lsblk command...")
        output = subprocess.run(['lsblk', '-d', '-n', '-o', 'NAME,TYPE'], 
                              capture_output=True, text=True, check=True)
        
        logger.debug(f"lsblk output: {output.stdout}")
        for line in output.stdout.strip().split('\n'):
            if line.strip():
                parts = line.split()
                if len(parts) >= 2:
                    device_name, device_type = parts[0], parts[1]
                    logger.debug(f"Found device: {device_name}, type: {device_type}")
                    # Only include actual disks (not partitions, loops, etc.)
                    if device_type == 'disk':
                        device_path = f'/dev/{device_name}'
                        logger.debug(f"Testing SMART support for: {device_path}")
                        # Check if the device supports SMART monitoring
                        try:
                            result = subprocess.run(['smartctl', '-i', device_path], 
                                                  capture_output=True, text=True, check=True)
                            if 'SMART support is:' in result.stdout:
                                drives.append(device_path)
                                logger.debug(f"Added drive with SMART support: {device_path}")
                                logger.info(f"Found drive with SMART support: {device_path}")
                            else:
                                logger.debug(f"SMART not supported for: {device_path}")
                        except subprocess.CalledProcessError as e:
                            logger.debug(f"smartctl failed for {device_path}: {e}")
                            # Device doesn't support SMART or smartctl failed
                            pass
                            
    except subprocess.CalledProcessError as e:
        logger.debug(f"lsblk command failed: {e}")
        logger.error(f"Error discovering drives: {e}")
    
    logger.debug(f"Drive discovery complete. Found {len(drives)} drives: {drives}")
    return drives

# --- Functions to get sensor data ---

def get_cpu_temp():
    """
    Reads and returns the CPU package temperature in Celsius.
    This function requires the 'lm-sensors' package to be installed.
    """
    try:
        logger.debug("Getting CPU temperature using sensors command...")
        # Use subprocess to run the 'sensors' command with JSON output
        output = subprocess.run(['sensors', '-j'], capture_output=True, text=True, check=True)
        # Parse the JSON output
        data = json.loads(output.stdout)
        logger.debug(f"Sensors data keys: {list(data.keys())}")
        
        # Find the coretemp adapter and get the package temperature
        for key, adapter in data.items():
            if 'coretemp' in key:
                logger.debug(f"Found coretemp adapter: {key}")
                package_data = adapter.get('Package id 0')
                if package_data:
                    logger.debug(f"Package data: {package_data}")
                    package_temp = package_data.get('temp1_input')
                    if package_temp:
                        logger.debug(f"CPU package temperature: {package_temp}°C")
                        return package_temp
                else:
                    logger.debug("No 'Package id 0' found in coretemp adapter")
        
        logger.warning("Could not find CPU package temperature data from 'sensors'.")
        return None

    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.debug(f"Sensors command failed: {e}")
        logger.error(f"Error getting CPU temperature: {e}")
        return None

def get_hdd_temp(device_path):
    """
    Reads and returns the temperature of a hard drive device using smartctl.
    This function requires the 'smartmontools' package to be installed.
    """
    try:
        logger.debug(f"Getting temperature for drive: {device_path}")
        # Use subprocess to run 'smartctl' command and get the output
        output = subprocess.run(['smartctl', '-A', device_path], capture_output=True, text=True, check=True)
        
        logger.debug(f"smartctl output sample for {device_path}: {output.stdout[:300]}...")
        
        # Use regex to find Temperature_Celsius line and extract the temperature value
        # Format examples:
        # 194 Temperature_Celsius     0x0022   112   104   000    Old_age   Always       -       35
        # 194 Temperature_Celsius     0x0022   100   100   000    Old_age   Always       -       42 (Min/Max 19/56)
        match = re.search(r'Temperature_Celsius.*?-\s+(\d+)', output.stdout)
        if match:
            temp = int(match.group(1))
            logger.debug(f"Drive {device_path} temperature: {temp}°C")
            return temp
        else:
            logger.debug(f"No Temperature_Celsius attribute found for drive: {device_path}")
            logger.warning(f"Could not find temperature data for drive {device_path}.")
            return None
            
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.debug(f"smartctl command failed for {device_path}: {e}")
        logger.error(f"Error getting HDD temperature for {device_path}: {e}")
        return None

def calculate_fan_speed(current_temp, previous_speed=None):
    """
    Calculate the appropriate fan speed based on current temperature.
    Uses incremental adjustment for smoother operation.
    
    Args:
        current_temp: Current temperature in Celsius
        previous_speed: Previous fan speed (for incremental adjustment)
    
    Returns:
        Tuple of (new_speed, speed_description)
    """
    if current_temp is None:
        logger.debug("No temperature data, returning minimum fan speed")
        return FAN_SPEED_MIN, "MIN (no temp data)"
    
    # Calculate target speed based on temperature curve
    if current_temp <= TEMP_MIN:
        target_speed = FAN_SPEED_MIN
    elif current_temp >= TEMP_MAX:
        target_speed = FAN_SPEED_MAX
    else:
        # Linear interpolation between min and max
        temp_ratio = (current_temp - TEMP_MIN) / (TEMP_MAX - TEMP_MIN)
        target_speed = int(FAN_SPEED_MIN + (FAN_SPEED_MAX - FAN_SPEED_MIN) * temp_ratio)
    
    logger.debug(f"Temperature {current_temp}°C -> target speed: {target_speed}")
    
    # If we have a previous speed, use incremental adjustment
    if previous_speed is not None:
        speed_diff = target_speed - previous_speed
        
        # Apply hysteresis to prevent oscillation
        if abs(speed_diff) < FAN_STEP_SIZE and abs(current_temp - TEMP_TARGET) < TEMP_HYSTERESIS:
            logger.debug(f"Within hysteresis range, keeping current speed: {previous_speed}")
            return previous_speed, f"STABLE ({previous_speed})"
        
        # Incremental adjustment
        if speed_diff > FAN_STEP_SIZE:
            new_speed = previous_speed + FAN_STEP_SIZE
            direction = "INCREASING"
        elif speed_diff < -FAN_STEP_SIZE:
            new_speed = previous_speed - FAN_STEP_SIZE
            direction = "DECREASING"
        else:
            new_speed = target_speed
            direction = "ADJUSTING"
    else:
        # No previous speed, jump to target
        new_speed = target_speed
        direction = "INITIAL"
    
    # Ensure we stay within bounds
    new_speed = max(FAN_SPEED_MIN, min(FAN_SPEED_MAX, new_speed))
    
    # Determine speed description
    if new_speed <= FAN_SPEED_MIN + 20:
        speed_desc = "LOW"
    elif new_speed >= FAN_SPEED_MAX - 20:
        speed_desc = "HIGH"
    else:
        speed_desc = "MEDIUM"
    
    logger.debug(f"Fan speed: {previous_speed} -> {new_speed} ({direction}, {speed_desc})")
    
    return new_speed, f"{speed_desc} ({new_speed})"

def set_fan_speed(speed, pwm_path_override=None):
    """
    Sets the fan speed by writing a value to the control file.
    This usually requires root privileges.
    """
    logger.debug(f"Attempting to set fan speed to: {speed}")
    
    if pwm_path_override:
        fan_control_path = pwm_path_override
        logger.debug(f"Using override PWM path: {fan_control_path}")
    else:
        fan_control_path = find_fan_control_path()
    
    if not fan_control_path:
        logger.error("No writable fan control path found")
        return False
        
    try:
        logger.debug(f"Writing speed {speed} to {fan_control_path}")
        with open(fan_control_path, 'w') as f:
            f.write(str(speed))
        logger.info(f"Set fan speed to {speed} via {fan_control_path}")
        logger.debug(f"Successfully set fan speed to {speed}")
        return True
    except IOError as e:
        logger.debug(f"Failed to write to fan control file: {e}")
        logger.error(f"Error setting fan speed: {e}. Are you running as root?")
        return False

def show_system_info(pwm_path_override=None):
    """
    Display system information including temperatures, fans, and drives.
    """
    print("=== System Information ===")
    
    # Check kernel module
    print(f"it87 kernel module loaded: {check_kernel_module()}")
    
    # Show CPU temperature
    cpu_temp = get_cpu_temp()
    print(f"CPU temperature: {cpu_temp}°C" if cpu_temp else "CPU temperature: Not available")
    
    # Show drives and temperatures
    drives = discover_drives()
    if drives:
        print(f"Found {len(drives)} drive(s) with SMART support:")
        for drive in drives:
            temp = get_hdd_temp(drive)
            print(f"  {drive}: {temp}°C" if temp else f"  {drive}: Temperature not available")
    else:
        print("No drives with SMART support found")
    
    # Show PWM information
    print("\n=== Fan Control Information ===")
    if pwm_path_override:
        print(f"Using override PWM path: {pwm_path_override}")
        if os.path.exists(pwm_path_override):
            try:
                with open(pwm_path_override, 'r') as f:
                    current_pwm = f.read().strip()
                print(f"Current PWM value: {current_pwm}")
            except:
                print("Could not read current PWM value")
        else:
            print("Override PWM path does not exist!")
    else:
        pwm_paths = glob.glob('/sys/class/hwmon/hwmon*/pwm*')
        print(f"Available PWM paths:")
        for path in pwm_paths:
            writable = "✓" if os.access(path, os.W_OK) else "✗"
            hwmon_dir = os.path.dirname(path)
            name_file = os.path.join(hwmon_dir, 'name')
            hwmon_name = "unknown"
            try:
                with open(name_file, 'r') as f:
                    hwmon_name = f.read().strip()
            except:
                pass
            
            # Try to read current PWM value
            current_pwm = "?"
            try:
                with open(path, 'r') as f:
                    current_pwm = f.read().strip()
            except:
                pass
            
            # Check for corresponding fan input
            fan_input = path.replace('pwm', 'fan') + '_input'
            fan_rpm = "N/A"
            if os.path.exists(fan_input):
                try:
                    with open(fan_input, 'r') as f:
                        fan_rpm = f.read().strip() + " RPM"
                except:
                    pass
            
            print(f"  {path} ({hwmon_name}) - Writable: {writable}, PWM: {current_pwm}, Fan: {fan_rpm}")
        
        detected_path = find_fan_control_path()
        print(f"\nAuto-detected fan control path: {detected_path}")

def test_fan_control(pwm_path_override=None):
    """
    Test fan control by cycling through different speeds.
    """
    print("=== Fan Control Test ===")
    
    if pwm_path_override:
        fan_control_path = pwm_path_override
        print(f"Using override PWM path: {fan_control_path}")
    else:
        fan_control_path = find_fan_control_path()
        print(f"Auto-detected PWM path: {fan_control_path}")
    
    if not fan_control_path:
        print("ERROR: No fan control path found!")
        return
    
    if not os.access(fan_control_path, os.W_OK):
        print(f"ERROR: PWM path {fan_control_path} is not writable!")
        return
    
    # Read original speed
    try:
        with open(fan_control_path, 'r') as f:
            original_speed = int(f.read().strip())
        print(f"Original fan speed: {original_speed}")
    except Exception as e:
        print(f"Could not read original fan speed: {e}")
        original_speed = 128  # Default fallback
    
    # Test different speeds
    test_speeds = [FAN_SPEED_MIN, FAN_SPEED_MIN + 50, FAN_SPEED_MIN + 100, FAN_SPEED_MAX, original_speed]
    
    for speed in test_speeds:
        print(f"Setting fan speed to {speed}...")
        if set_fan_speed(speed, fan_control_path):
            time.sleep(3)  # Wait 3 seconds between changes to hear the difference
        else:
            print(f"Failed to set speed {speed}")
            break
    
    print("Fan test complete!")

def main(pwm_path_override=None):
    """
    Main loop to monitor temperatures and adjust fan speed incrementally.
    """
    # Check if it87 kernel module is loaded
    if not check_kernel_module():
        logger.error("it87 kernel module is not loaded. Fan control may not work.")
        logger.error("Please load the module with: sudo modprobe it87")
        logger.error("You may also need to add 'it87' to /etc/modules for permanent loading")
    
    # Discover drives once at startup
    drives = discover_drives()
    if drives:
        logger.info(f"Monitoring {len(drives)} drive(s): {', '.join(drives)}")
    else:
        logger.info("No drives with SMART support found. Only monitoring CPU temperature.")
    
    # Initialize fan speed tracking
    current_fan_speed = None
    
    # Get initial fan speed if possible
    try:
        if pwm_path_override:
            fan_control_path = pwm_path_override
        else:
            fan_control_path = find_fan_control_path()
        
        if fan_control_path and os.access(fan_control_path, os.R_OK):
            with open(fan_control_path, 'r') as f:
                current_fan_speed = int(f.read().strip())
                logger.info(f"Current fan speed at startup: {current_fan_speed}")
    except Exception as e:
        logger.debug(f"Could not read initial fan speed: {e}")
    
    logger.info(f"Fan control configuration:")
    logger.info(f"  Temperature range: {TEMP_MIN}°C - {TEMP_MAX}°C")
    logger.info(f"  Target temperature: {TEMP_TARGET}°C")
    logger.info(f"  Fan speed range: {FAN_SPEED_MIN} - {FAN_SPEED_MAX}")
    logger.info(f"  Step size: {FAN_STEP_SIZE}, Update interval: {UPDATE_INTERVAL}s")
    
    while True:
        # Get CPU temperature
        cpu_temp = get_cpu_temp()
        logger.debug(f"Current CPU temperature: {cpu_temp}°C")
        
        # Get max HDD temperature
        max_hdd_temp = 0
        for device in drives:
            hdd_temp = get_hdd_temp(device)
            if hdd_temp is not None and hdd_temp > max_hdd_temp:
                max_hdd_temp = hdd_temp

        logger.debug(f"Max HDD temperature: {max_hdd_temp}°C")
        
        # Use the highest temperature to decide fan speed
        current_temp = max(cpu_temp if cpu_temp is not None else 0, max_hdd_temp)
        logger.debug(f"Overall max temperature: {current_temp}°C")

        if current_temp == 0:
            logger.debug("No valid temperature readings, using minimum fan speed")
            logger.warning("Failed to read any temperatures. Using minimum fan speed.")
            new_speed, speed_desc = FAN_SPEED_MIN, f"MIN ({FAN_SPEED_MIN})"
        else:
            logger.info(f"Current temp: {current_temp}°C")
            # Calculate new fan speed based on temperature and previous speed
            new_speed, speed_desc = calculate_fan_speed(current_temp, current_fan_speed)
        
        # Only change fan speed if it's different from current
        if current_fan_speed is None or new_speed != current_fan_speed:
            logger.info(f"Adjusting fan speed to {speed_desc} (temp: {current_temp}°C)")
            if set_fan_speed(new_speed, pwm_path_override):
                current_fan_speed = new_speed
        else:
            logger.debug(f"Fan speed unchanged: {speed_desc} (temp: {current_temp}°C)")

        logger.debug(f"Waiting {UPDATE_INTERVAL} seconds before next check...")
        # Wait for configured interval before checking again
        time.sleep(UPDATE_INTERVAL)

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='CPU and HDD fan control script for Odroid H4 and similar systems',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sudo python3 fan-control.py                    # Run with auto-detection
  sudo python3 fan-control.py --debug            # Run with debug output
  sudo python3 fan-control.py --pwm-path /sys/class/hwmon/hwmon3/pwm2  # Force specific PWM
  sudo python3 fan-control.py --test-fan         # Test fan control and exit
  
Temperature thresholds can be adjusted by editing the script configuration section.
        """
    )
    parser.add_argument('--debug', '-d', action='store_true', 
                       help='Enable debug output')
    parser.add_argument('--pwm-path', type=str,
                       help='Force specific PWM control path (e.g., /sys/class/hwmon/hwmon3/pwm2)')
    parser.add_argument('--test-fan', action='store_true',
                       help='Test fan control by cycling through speeds and exit')
    parser.add_argument('--info', action='store_true',
                       help='Show system information (temperatures, fans, drives) and exit')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(debug=args.debug)
    
    if args.debug:
        logger.info("Debug mode enabled")
        logger.debug("Starting in debug mode...")
    
    # Ensure the script is run with root privileges for fan control
    if not args.info and os.geteuid() != 0:
        logger.error("This script must be run as root for fan control. Please use 'sudo python3 fan-control.py'.")
        logger.error("Use --info flag to run without root privileges for system information only.")
        sys.exit(1)
    
    logger.debug("Script starting with appropriate privileges")
    
    # Handle info mode
    if args.info:
        show_system_info(args.pwm_path)
        sys.exit(0)
    
    # Handle test fan mode
    if args.test_fan:
        test_fan_control(args.pwm_path)
        sys.exit(0)
    
    logger.info("Starting fan control script...")
    main(args.pwm_path)

