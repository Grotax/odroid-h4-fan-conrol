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
# You'll need to set these paths and thresholds according to your system.
# Find the correct path for your fan control. It's usually in /sys/class/hwmon.
# Use 'find /sys -name "pwm*"' to find it.

# Define temperature thresholds and corresponding fan speeds (0-255).
# These are just examples. You should adjust them for your specific hardware.
# Be careful not to set the temperature too high or the fan speed too low,
# as this could cause thermal damage to your components.
TEMP_THRESHOLD_LOW = 40  # Temp below this means low speed
TEMP_THRESHOLD_MEDIUM = 55 # Temp between low and medium means medium speed
TEMP_THRESHOLD_HIGH = 70  # Temp above this means high speed

FAN_SPEED_LOW = 100    # Low fan speed value (e.g., quiet operation)
FAN_SPEED_MEDIUM = 180   # Medium fan speed
FAN_SPEED_HIGH = 255   # Full fan speed

# Auto-discover drives - no need to manually specify them
# The script will automatically find all physical drives

def find_fan_control_path():
    """
    Dynamically finds the correct PWM control path for the fan.
    Returns the path if found, None otherwise.
    """
    logger.debug("Searching for fan control PWM paths...")
    # Look for PWM controls in all hwmon directories
    pwm_paths = glob.glob('/sys/class/hwmon/hwmon*/pwm2')
    logger.debug(f"Found PWM paths: {pwm_paths}")
    
    for path in pwm_paths:
        logger.debug(f"Checking PWM path: {path}")
        # Check if this PWM control is writable and likely a fan control
        if os.access(path, os.W_OK):
            logger.debug(f"PWM path {path} is writable")
            # You can add additional checks here if needed
            # For example, check for corresponding fan input or name file
            hwmon_dir = os.path.dirname(path)
            name_file = os.path.join(hwmon_dir, 'name')
            
            # Try to read the hwmon name to identify the right one
            try:
                with open(name_file, 'r') as f:
                    hwmon_name = f.read().strip()
                    logger.debug(f"Hwmon device name: {hwmon_name}")
                    
                # You might want to filter by specific hwmon names if you know them
                # For now, return the first writable PWM path found
                logger.debug(f"Selected fan control path: {path}")
                return path
            except Exception as e:
                # If we can't read the name, still consider this PWM path
                logger.debug(f"Could not read hwmon name: {e}")
                logger.info(f"Found PWM control at {path}")
                return path
        else:
            logger.debug(f"PWM path {path} is not writable")
    
    logger.debug("No writable PWM control path found")
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
        
        # Use a regular expression to find the temperature value
        match = re.search(r'Temperature_Celsius:\s*(\d+)', output.stdout)
        if match:
            temp = int(match.group(1))
            logger.debug(f"Drive {device_path} temperature: {temp}°C")
            return temp
        else:
            logger.debug(f"No temperature data found for drive: {device_path}")
            logger.warning(f"Could not find temperature data for drive {device_path}.")
            return None
            
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.debug(f"smartctl command failed for {device_path}: {e}")
        logger.error(f"Error getting HDD temperature for {device_path}: {e}")
        return None

def set_fan_speed(speed):
    """
    Sets the fan speed by writing a value to the dynamically found control file.
    This usually requires root privileges.
    """
    logger.debug(f"Attempting to set fan speed to: {speed}")
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

def main():
    """
    Main loop to monitor temperatures and adjust fan speed.
    """
    # Discover drives once at startup
    drives = discover_drives()
    if drives:
        logger.info(f"Monitoring {len(drives)} drive(s): {', '.join(drives)}")
    else:
        logger.info("No drives with SMART support found. Only monitoring CPU temperature.")
    
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
            logger.debug("No valid temperature readings, skipping fan control")
            logger.warning("Failed to read any temperatures. Skipping fan control.")
        else:
            logger.info(f"Current temp: {current_temp}°C")

            # Determine fan speed based on thresholds
            if current_temp < TEMP_THRESHOLD_LOW:
                new_speed = FAN_SPEED_LOW
                speed_level = "LOW"
            elif current_temp < TEMP_THRESHOLD_MEDIUM:
                new_speed = FAN_SPEED_MEDIUM
                speed_level = "MEDIUM"
            else:
                new_speed = FAN_SPEED_HIGH
                speed_level = "HIGH"
            
            logger.debug(f"Temperature {current_temp}°C requires {speed_level} fan speed ({new_speed})")
            logger.info(f"Setting fan speed to {new_speed} (based on temp: {current_temp}°C)")
            set_fan_speed(new_speed)

        logger.debug("Waiting 30 seconds before next check...")
        # Wait for a period before checking again
        time.sleep(30) # Check every 30 seconds

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='CPU and HDD fan control script')
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug output')
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(debug=args.debug)
    
    if args.debug:
        logger.info("Debug mode enabled")
        logger.debug("Starting in debug mode...")
    
    # Ensure the script is run with root privileges
    if os.geteuid() != 0:
        logger.error("This script must be run as root. Please use 'sudo python3 fan-control.py'.")
        logger.debug("Script not running as root, exiting")
        sys.exit(1)
    
    logger.debug("Script starting with root privileges")
    logger.info("Starting fan control script...")
    main()

