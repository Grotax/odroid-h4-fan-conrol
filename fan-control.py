# fan_control_script.py

import subprocess
import time
import re
import sys
import os
import glob

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

# List your hard drive devices. Use 'lsblk' to find them.
# Example: ['/dev/sda', '/dev/sdb']
HARD_DRIVE_DEVICES = ['/dev/sda', '/dev/sdb']

def find_fan_control_path():
    """
    Dynamically finds the correct PWM control path for the fan.
    Returns the path if found, None otherwise.
    """
    # Look for PWM controls in all hwmon directories
    pwm_paths = glob.glob('/sys/class/hwmon/hwmon*/pwm2')
    
    for path in pwm_paths:
        # Check if this PWM control is writable and likely a fan control
        if os.access(path, os.W_OK):
            # You can add additional checks here if needed
            # For example, check for corresponding fan input or name file
            hwmon_dir = os.path.dirname(path)
            name_file = os.path.join(hwmon_dir, 'name')
            
            # Try to read the hwmon name to identify the right one
            try:
                with open(name_file, 'r') as f:
                    hwmon_name = f.read().strip()
                    print(f"Found hwmon device: {hwmon_name} at {path}")
                    
                # You might want to filter by specific hwmon names if you know them
                # For now, return the first writable PWM path found
                return path
            except:
                # If we can't read the name, still consider this PWM path
                print(f"Found PWM control at {path}")
                return path
    
    return None

# --- Functions to get sensor data ---

def get_cpu_temp():
    """
    Reads and returns the CPU package temperature in Celsius.
    This function requires the 'lm-sensors' package to be installed.
    """
    try:
        # Use subprocess to run the 'sensors' command with JSON output
        output = subprocess.run(['sensors', '-j'], capture_output=True, text=True, check=True)
        # Parse the JSON output
        import json
        data = json.loads(output.stdout)
        
        # Find the coretemp adapter and get the package temperature
        for key, adapter in data.items():
            if 'coretemp' in key:
                package_data = adapter.get('Package id 0')
                if package_data:
                    package_temp = package_data.get('temp1_input')
                    if package_temp:
                        return package_temp
        
        print("Warning: Could not find CPU package temperature data from 'sensors'.")
        return None

    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Error getting CPU temperature: {e}")
        return None

def get_hdd_temp(device_path):
    """
    Reads and returns the temperature of a hard drive device using smartctl.
    This function requires the 'smartmontools' package to be installed.
    """
    try:
        # Use subprocess to run 'smartctl' command and get the output
        output = subprocess.run(['smartctl', '-A', device_path], capture_output=True, text=True, check=True)
        
        # Use a regular expression to find the temperature value
        match = re.search(r'Temperature_Celsius:\s*(\d+)', output.stdout)
        if match:
            return int(match.group(1))
        else:
            print(f"Warning: Could not find temperature for {device_path}.")
            return None
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Error getting HDD temperature for {device_path}: {e}")
        return None

def set_fan_speed(speed):
    """
    Sets the fan speed by writing a value to the dynamically found control file.
    This usually requires root privileges.
    """
    fan_control_path = find_fan_control_path()
    
    if not fan_control_path:
        print("Error: No writable fan control path found")
        return False
        
    try:
        with open(fan_control_path, 'w') as f:
            f.write(str(speed))
        print(f"Set fan speed to {speed} via {fan_control_path}")
        return True
    except IOError as e:
        print(f"Error setting fan speed: {e}. Are you running as root?")
        return False

def main():
    """
    Main loop to monitor temperatures and adjust fan speed.
    """
    while True:
        # Get CPU temperature
        cpu_temp = get_cpu_temp()
        
        # Get max HDD temperature
        max_hdd_temp = 0
        for device in HARD_DRIVE_DEVICES:
            hdd_temp = get_hdd_temp(device)
            if hdd_temp is not None and hdd_temp > max_hdd_temp:
                max_hdd_temp = hdd_temp

        # Use the highest temperature to decide fan speed
        current_temp = max(cpu_temp if cpu_temp is not None else 0, max_hdd_temp)

        if current_temp == 0:
            print("Failed to read any temperatures. Skipping fan control.")
        else:
            print(f"Current temp: {current_temp}°C")

            # Determine fan speed based on thresholds
            if current_temp < TEMP_THRESHOLD_LOW:
                new_speed = FAN_SPEED_LOW
            elif current_temp < TEMP_THRESHOLD_MEDIUM:
                new_speed = FAN_SPEED_MEDIUM
            else:
                new_speed = FAN_SPEED_HIGH
            
            print(f"Setting fan speed to {new_speed} (based on temp: {current_temp}°C)")
            set_fan_speed(new_speed)

        # Wait for a period before checking again
        time.sleep(30) # Check every 30 seconds

if __name__ == "__main__":
    # Ensure the script is run with root privileges
    if os.geteuid() != 0:
        print("This script must be run as root. Please use 'sudo python3 fan_control_script.py'.")
        sys.exit(1)
    
    print("Starting fan control script...")
    main()

