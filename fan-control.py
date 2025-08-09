#!/usr/bin/env python3
"""
Odroid H4 Fan Control Script v2.0

Monitors CPU and HDD temperatures and automatically adjusts fan speed
using incremental speed control for smooth operation.

Features:
- Automatic PWM path detection with interactive configuration helper
- CPU temperature monitoring via lm-sensors  
- HDD temperature monitoring via smartctl
- Incremental fan speed adjustment with hysteresis
- Comprehensive logging with configurable levels
- Manual PWM path override support

Requirements:
- Python 3.x
- lm-sensors package (sensors command)
- smartmontools package (smartctl command) 
- it87 kernel module (for Odroid H4 and similar systems)
- Root privileges for fan control

Usage:
    sudo python3 fan-control.py              # Normal operation
    python3 fan-control.py --configure       # Interactive setup
    sudo python3 fan-control.py --test-fan   # Test functionality
    python3 fan-control.py --info            # System information
"""

import subprocess
import time
import re
import sys
import os
import glob
import json
import argparse
import logging

__version__ = "2.0"

# Configure logging
logger = logging.getLogger(__name__)

# --- Helper Functions ---

def get_hwmon_device_name(hwmon_dir):
    """Get the name of an hwmon device."""
    name_file = os.path.join(hwmon_dir, 'name')
    try:
        with open(name_file, 'r') as f:
            return f.read().strip()
    except Exception:
        return "unknown"

def read_pwm_value(pwm_path):
    """Safely read a PWM value from a file."""
    try:
        with open(pwm_path, 'r') as f:
            return int(f.read().strip())
    except Exception:
        return None

def write_pwm_value(pwm_path, value):
    """Safely write a PWM value to a file."""
    try:
        with open(pwm_path, 'w') as f:
            f.write(str(value))
        return True
    except Exception as e:
        logger.debug(f"Failed to write PWM value {value} to {pwm_path}: {e}")
        return False

def read_fan_speed(fan_input_path):
    """Safely read fan speed from a fan input file."""
    if not os.path.exists(fan_input_path):
        return None
    try:
        with open(fan_input_path, 'r') as f:
            return int(f.read().strip())
    except Exception:
        return None

def setup_logging(log_level='WARNING'):
    """Setup logging configuration."""
    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # Convert string level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.WARNING)
    
    # Set log level
    logger.setLevel(numeric_level)
    console_handler.setLevel(numeric_level)
    
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

# Manual PWM path override (set to None for auto-detection)
# If auto-detection doesn't work, manually specify your PWM path here
# Examples:
#   MANUAL_PWM_PATH = '/sys/class/hwmon/hwmon3/pwm2'  # For Odroid H4 (typical)
#   MANUAL_PWM_PATH = '/sys/class/hwmon/hwmon3/pwm3'  # Alternative for some systems
MANUAL_PWM_PATH = '/sys/class/hwmon/hwmon3/pwm2'  # Configured for this system

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
    Returns the path if found, None otherwise.
    """
    logger.debug("Searching for fan control PWM paths...")
    
    # Look for PWM controls in all hwmon directories - filter out auto config files
    all_pwm_paths = glob.glob('/sys/class/hwmon/hwmon*/pwm*')
    pwm_paths = [path for path in all_pwm_paths if '/pwm' in path and '_' not in os.path.basename(path)]
    logger.debug(f"Found direct PWM control paths: {pwm_paths}")
    
    if not pwm_paths:
        logger.error("No PWM control paths found")
        return None
    
    # Prioritize based on known working configurations
    preferred_pwm_names = ['pwm2', 'pwm3', 'pwm1', 'pwm4', 'pwm5']
    
    # Test each preferred PWM path
    for pwm_name in preferred_pwm_names:
        for path in pwm_paths:
            if not path.endswith(pwm_name):
                continue
                
            logger.debug(f"Checking preferred PWM path: {path}")
            
            # Check if PWM is writable
            if not os.access(path, os.W_OK):
                logger.debug(f"PWM path {path} is not writable")
                continue
            
            hwmon_dir = os.path.dirname(path)
            hwmon_name = get_hwmon_device_name(hwmon_dir)
            current_pwm = read_pwm_value(path)
            
            if current_pwm is None:
                logger.debug(f"Could not read PWM value from {path}")
                continue
                
            logger.debug(f"Hwmon device: {hwmon_name}, Current PWM: {current_pwm}")
            
            # Check for fan speed sensor (optional)
            fan_input = os.path.join(hwmon_dir, pwm_name.replace('pwm', 'fan') + '_input')
            current_fan_speed = read_fan_speed(fan_input)
            
            if current_fan_speed is not None:
                logger.debug(f"Fan speed sensor: {current_fan_speed} RPM")
            
            # Determine if this PWM is likely functional
            is_functional = False
            
            # Priority 1: PWM has a non-zero value (indicates active use)
            if current_pwm > 0:
                logger.debug(f"PWM is active with value {current_pwm}")
                is_functional = True
            
            # Priority 2: Known good combinations for specific hardware
            elif pwm_name in ['pwm2', 'pwm3'] and hwmon_name in ['it87', 'it8613', 'it8721']:
                logger.debug(f"Known good combination: {pwm_name} on {hwmon_name}")
                is_functional = True
            
            # Priority 3: Fan speed sensor shows activity
            elif current_fan_speed and current_fan_speed > 0:
                logger.debug(f"Fan sensor shows activity: {current_fan_speed} RPM")
                is_functional = True
            
            if is_functional:
                logger.info(f"Selected fan control path: {path} (device: {hwmon_name})")
                if current_fan_speed:
                    logger.info(f"Fan currently at {current_fan_speed} RPM")
                return path
            else:
                logger.debug(f"PWM {path} doesn't appear to be actively used")
    
    # Fallback: try any writable PWM as last resort
    logger.debug("No clearly functional PWM found, trying fallback...")
    for path in pwm_paths:
        if os.access(path, os.W_OK):
            hwmon_name = get_hwmon_device_name(os.path.dirname(path))
            logger.warning(f"Using fallback PWM path: {path} (device: {hwmon_name})")
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
    Requires root privileges.
    
    Args:
        speed: PWM value (0-255)
        pwm_path_override: Optional PWM path override
        
    Returns:
        bool: True if successful, False otherwise
    """
    logger.debug(f"Setting fan speed to: {speed}")
    
    # Determine PWM path priority: CLI override > manual config > auto-detection
    if pwm_path_override:
        fan_control_path = pwm_path_override
        logger.debug(f"Using command-line PWM path: {fan_control_path}")
    elif MANUAL_PWM_PATH:
        fan_control_path = MANUAL_PWM_PATH
        logger.debug(f"Using configured PWM path: {fan_control_path}")
    else:
        fan_control_path = find_fan_control_path()
        if not fan_control_path:
            logger.error("No PWM control path found")
            return False
    
    # Validate speed range
    speed = max(0, min(255, int(speed)))
    
    # Write PWM value
    if write_pwm_value(fan_control_path, speed):
        logger.info(f"Set fan speed to {speed} via {fan_control_path}")
        return True
    else:
        logger.error(f"Failed to set fan speed. Check permissions and PWM path.")
        return False

def show_status():
    """Show current temperature and fan status in a concise format."""
    print("=== Current Status ===")
    
    # CPU temperature
    cpu_temp = get_cpu_temp()
    cpu_status = f"{cpu_temp}°C" if cpu_temp else "Not available"
    print(f"CPU Temperature: {cpu_status}")
    
    # Drive temperatures  
    drives = discover_drives()
    if drives:
        max_drive_temp = 0
        for drive in drives:
            temp = get_hdd_temp(drive)
            if temp and temp > max_drive_temp:
                max_drive_temp = temp
        if max_drive_temp > 0:
            print(f"Max Drive Temperature: {max_drive_temp}°C")
    
    # Current fan speed and PWM
    pwm_path = MANUAL_PWM_PATH or find_fan_control_path()
    if pwm_path:
        current_pwm = read_pwm_value(pwm_path)
        pwm_name = os.path.basename(pwm_path)
        fan_input = os.path.join(os.path.dirname(pwm_path), 
                                pwm_name.replace('pwm', 'fan') + '_input')
        fan_speed = read_fan_speed(fan_input)
        
        print(f"PWM Path: {pwm_path}")
        print(f"Current PWM Value: {current_pwm}")
        if fan_speed is not None:
            print(f"Fan Speed: {fan_speed} RPM")
        else:
            print("Fan Speed: Not available")
    else:
        print("PWM Path: Not found")

def configure_pwm_path():
    """
    Interactive helper to find and configure the correct PWM path.
    """
    print("=== Interactive PWM Configuration Helper ===")
    print("This will help you identify the correct PWM path for your fan control.")
    print("We'll test each PWM path to see which one controls your fan.\n")
    
    # Ensure we're running as root
    if os.geteuid() != 0:
        print("ERROR: This configuration helper requires root privileges.")
        print("Please run: sudo python3 fan-control.py --configure")
        return
    
    # Find all direct PWM control paths
    all_pwm_paths = glob.glob('/sys/class/hwmon/hwmon*/pwm*')
    pwm_paths = [path for path in all_pwm_paths if '/pwm' in path and '_' not in os.path.basename(path)]
    
    if not pwm_paths:
        print("ERROR: No PWM control paths found!")
        return
    
    # Filter to only writable paths
    writable_pwm_paths = [path for path in pwm_paths if os.access(path, os.W_OK)]
    
    if not writable_pwm_paths:
        print("ERROR: No writable PWM control paths found!")
        print("Make sure you're running as root.")
        return
    
    print(f"Found {len(writable_pwm_paths)} writable PWM control path(s):")
    
    # Show available paths with context
    for i, path in enumerate(writable_pwm_paths, 1):
        hwmon_dir = os.path.dirname(path)
        name_file = os.path.join(hwmon_dir, 'name')
        hwmon_name = "unknown"
        try:
            with open(name_file, 'r') as f:
                hwmon_name = f.read().strip()
        except:
            pass
        
        # Get current PWM value
        current_pwm = "?"
        try:
            with open(path, 'r') as f:
                current_pwm = f.read().strip()
        except:
            pass
        
        print(f"  {i}. {path} (Device: {hwmon_name}, Current PWM: {current_pwm})")
    
    print("\n" + "="*60)
    print("INTERACTIVE FAN DETECTION")
    print("="*60)
    
    # Test each PWM path interactively
    working_pwm = None
    for i, path in enumerate(writable_pwm_paths, 1):
        pwm_name = os.path.basename(path)
        hwmon_dir = os.path.dirname(path)
        fan_input = os.path.join(hwmon_dir, pwm_name.replace('pwm', 'fan') + '_input')
        
        print(f"\nTesting PWM {i}/{len(writable_pwm_paths)}: {path}")
        
        # Store original PWM value
        original_pwm = 0
        try:
            with open(path, 'r') as f:
                original_pwm = int(f.read().strip())
            print(f"Original PWM value: {original_pwm}")
        except Exception as e:
            print(f"Could not read original PWM value: {e}")
            continue
        
        # Ask if fan is currently running
        current_status = input("Is your system fan currently running? (y/n): ").lower().strip()
        
        if current_status == 'y':
            # Fan is running, try to stop it
            print("Setting PWM to 0 to stop the fan...")
            try:
                with open(path, 'w') as f:
                    f.write('0')
                
                print("Waiting 3 seconds for fan to stop...")
                time.sleep(3)
                
                stopped = input("Did the fan stop? (y/n): ").lower().strip()
                
                if stopped == 'y':
                    print("✓ This PWM controls your fan!")
                    working_pwm = path
                    
                    # Restore original value and break
                    print("Restoring original fan speed...")
                    with open(path, 'w') as f:
                        f.write(str(original_pwm))
                    break
                else:
                    print("✗ This PWM doesn't control your fan.")
                    
            except Exception as e:
                print(f"Error testing PWM: {e}")
            finally:
                # Always restore original value
                try:
                    with open(path, 'w') as f:
                        f.write(str(original_pwm))
                except:
                    pass
        
        else:
            # Fan is not running, try to start it
            print("Setting PWM to 150 to start the fan...")
            try:
                with open(path, 'w') as f:
                    f.write('150')
                
                print("Waiting 3 seconds for fan to spin up...")
                time.sleep(3)
                
                # Check fan speed sensor if available
                fan_speed = None
                if os.path.exists(fan_input):
                    try:
                        with open(fan_input, 'r') as f:
                            fan_speed = int(f.read().strip())
                        if fan_speed > 0:
                            print(f"Fan speed sensor shows: {fan_speed} RPM")
                    except:
                        pass
                
                started = input("Did the fan start running? (y/n): ").lower().strip()
                
                if started == 'y':
                    print("✓ This PWM controls your fan!")
                    working_pwm = path
                    
                    # Restore original value and break
                    print("Restoring original fan speed...")
                    with open(path, 'w') as f:
                        f.write(str(original_pwm))
                    break
                else:
                    print("✗ This PWM doesn't control your fan.")
                    
            except Exception as e:
                print(f"Error testing PWM: {e}")
            finally:
                # Always restore original value
                try:
                    with open(path, 'w') as f:
                        f.write(str(original_pwm))
                except:
                    pass
        
        # Ask if user wants to continue testing
        if i < len(writable_pwm_paths):
            continue_test = input("\nContinue testing other PWM paths? (y/n): ").lower().strip()
            if continue_test != 'y':
                break
    
    print("\n" + "="*60)
    print("CONFIGURATION RESULTS")
    print("="*60)
    
    if working_pwm:
        print(f"✓ SUCCESS: Found working PWM path: {working_pwm}")
        print("\nTo configure the script permanently:")
        print("1. Edit the fan-control.py file")
        print("2. Find the line: MANUAL_PWM_PATH = ...")
        print(f"3. Change it to: MANUAL_PWM_PATH = '{working_pwm}'")
        print("\nAlternatively, you can use the command line option:")
        print(f"   sudo python3 fan-control.py --pwm-path {working_pwm}")
        print("\nTest your configuration with:")
        print("   sudo python3 fan-control.py --test-fan")
    else:
        print("✗ No working PWM path found.")
        print("This could mean:")
        print("- Your fan is controlled differently")
        print("- The fan control requires additional setup")
        print("- The fan is controlled by BIOS/UEFI")
        print("\nTry checking BIOS settings for fan control options.")

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
        # Priority: command line override, then manual config, then auto-detection
        if pwm_path_override:
            fan_control_path = pwm_path_override
        elif MANUAL_PWM_PATH:
            fan_control_path = MANUAL_PWM_PATH
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
  sudo ./fan-control.py                       # Run with auto-detection
  sudo ./fan-control.py --log-level INFO      # Run with info-level logging
  sudo ./fan-control.py --pwm-path /sys/class/hwmon/hwmon3/pwm2  # Force specific PWM
  sudo ./fan-control.py --test-fan            # Test fan control and exit
  ./fan-control.py --info                     # Show detailed system info
  ./fan-control.py --status                   # Show current temperature/fan status
  sudo ./fan-control.py --configure           # Interactive PWM configuration
  
Configuration:
  1. Use --configure for interactive PWM path discovery (recommended)
  2. Or manually edit MANUAL_PWM_PATH in the script
  3. Or use --pwm-path for one-time override
  
  Example: MANUAL_PWM_PATH = '/sys/class/hwmon/hwmon3/pwm2'
  
Temperature thresholds can be adjusted by editing the script configuration section.
        """
    )
    parser.add_argument('--version', action='version', version=f'Fan Control Script v{__version__}')
    parser.add_argument('--debug', '-d', action='store_true', 
                       help='Enable debug output (equivalent to --log-level DEBUG)')
    parser.add_argument('--log-level', type=str, default='WARNING',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], 
                       help='Set logging level (DEBUG, INFO, WARNING, ERROR)')
    parser.add_argument('--pwm-path', type=str,
                       help='Force specific PWM control path (e.g., /sys/class/hwmon/hwmon3/pwm2)')
    parser.add_argument('--test-fan', action='store_true',
                       help='Test fan control by cycling through speeds and exit')
    parser.add_argument('--info', action='store_true',
                       help='Show system information (temperatures, fans, drives) and exit')
    parser.add_argument('--configure', action='store_true',
                       help='Interactive configuration helper to find the correct PWM path')
    parser.add_argument('--status', action='store_true',
                       help='Show current temperature and fan status')
    
    args = parser.parse_args()
    
    # Handle log level - debug flag overrides log-level
    log_level = 'DEBUG' if args.debug else args.log_level
    
    # Set up logging
    setup_logging(log_level=log_level)
    
    if args.debug or log_level == 'DEBUG':
        logger.info("Debug mode enabled")
        logger.debug("Starting in debug mode...")
    
    # Ensure the script is run with root privileges for fan control
    if not args.info and not args.configure and not args.status and os.geteuid() != 0:
        logger.error("This script must be run as root for fan control. Please use 'sudo python3 fan-control.py'.")
        logger.error("Use --info, --status, or --configure flags to run without root privileges for information only.")
        sys.exit(1)
    
    logger.debug("Script starting with appropriate privileges")
    
    # Handle status mode
    if args.status:
        show_status()
        sys.exit(0)
    
    # Handle info mode
    if args.info:
        show_system_info(args.pwm_path)
        sys.exit(0)
    
    # Handle configure mode
    if args.configure:
        configure_pwm_path()
        sys.exit(0)
    
    # Handle test fan mode
    if args.test_fan:
        test_fan_control(args.pwm_path)
        sys.exit(0)
    
    logger.info("Starting fan control script...")
    main(args.pwm_path)

