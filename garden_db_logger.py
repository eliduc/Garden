import sqlite3
import json
import time
import configparser
from datetime import datetime
import os
import tinytuya
import threading
import signal
import sys
import argparse

# Configure SQLite to work with datetime properly in Python 3.12+
sqlite3.register_adapter(datetime, lambda val: val.isoformat())
sqlite3.register_converter("DATETIME", lambda val: datetime.fromisoformat(val.decode()))

# Configuration
config = configparser.ConfigParser()
config_file = 'garden.ini'
config.read(config_file)

try:
    ACCESS_ID = config.get('tuya', 'ACCESS_ID')
    ACCESS_KEY = config.get('tuya', 'ACCESS_KEY')
    API_REGION = config.get('tuya', 'API_REGION')
    frequency = int(config.get('frequency', 'frequency'))
    print(f'Polling frequency: {frequency} seconds')
    
except (configparser.NoSectionError, configparser.NoOptionError) as e:
    print(f"Configuration Error: {e}")
    sys.exit(1)

# Database configuration
DB_FILE = 'garden_sensors.db'

def check_soil_sensor_parameters(DEVICE_ID, SENSOR_TYPE):
    """Query sensor data from Tuya API"""
    try:
        client = tinytuya.Cloud(
            apiRegion=API_REGION,
            apiKey=ACCESS_ID,
            apiSecret=ACCESS_KEY
        )
        device_data = client.getstatus(DEVICE_ID)
        
        if 'result' in device_data and isinstance(device_data['result'], list):
            data_points = {}
            for dp in device_data['result']:
                code = dp.get('code')
                value = dp.get('value')
                data_points[code] = value
            
            moisture = data_points.get('humidity')
            temp = data_points.get('temp_current')
            battery = data_points.get('battery_percentage')
            
            if moisture is not None and temp is not None:
                battery = battery if battery is not None else -1
                return (moisture, temp, battery, 1)  # 1 = sensor available
            else:
                print(f"Error: Missing data for device {DEVICE_ID}.")
                return (None, None, None, 0)  # 0 = sensor unavailable
        else:
            print(f"Error: Invalid response for device {DEVICE_ID}.")
            return (None, None, None, 0)
    except Exception as e:
        print(f"Error querying device {DEVICE_ID}: {e}")
        return (None, None, None, 0)

def load_garden_data(file_name='garden_data.json'):
    """Load garden configuration from JSON file"""
    try:
        with open(file_name, "r") as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print(f"Error: '{file_name}' not found.")
        return None
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in '{file_name}'.")
        return None

def insert_sensor_reading(conn, plant_unique_id, sensor_name, device_id, 
                         temperature, humidity, battery, sensor_state):
    """Insert a sensor reading into the database"""
    cursor = conn.cursor()
    current_datetime = datetime.now()
    # Convert date and time to strings for SQLite compatibility
    date_str = current_datetime.strftime('%Y-%m-%d')
    time_str = current_datetime.strftime('%H:%M:%S')
    
    cursor.execute('''
        INSERT INTO sensor_readings 
        (plant_unique_id, sensor_name, device_id, date, time, 
         temperature, humidity, battery_charge, sensor_state)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (plant_unique_id, sensor_name, device_id, date_str, time_str,
          temperature, humidity, battery, sensor_state))
    
    conn.commit()

def get_current_season():
    """Get current season based on month"""
    month = datetime.now().month
    if month in [12, 1, 2]:
        return "Winter"
    elif month in [3, 4, 5]:
        return "Spring"
    elif month in [6, 7, 8]:
        return "Summer"
    else:
        return "Autumn"

def poll_sensors(conn):
    """Poll all sensors and save readings to database"""
    cursor = conn.cursor()
    
    # Get current season for threshold comparison
    current_season = get_current_season()
    
    # Get all plants with sensors from database
    cursor.execute('''
        SELECT gp.id, gp.unique_id, gp.sensor_id, gp.sensor_name, gp.custom_name,
               pt.name as plant_type, pt.id as plant_type_id,
               pth.humidity_low, pth.humidity_high, pth.temperature_low, pth.temperature_high
        FROM garden_plants gp
        JOIN plant_types pt ON gp.plant_type_id = pt.id
        LEFT JOIN plant_thresholds pth ON pt.id = pth.plant_type_id AND pth.season = ?
        WHERE gp.has_sensor = 1 AND gp.sensor_id IS NOT NULL
    ''', (current_season,))
    
    plants_with_sensors = cursor.fetchall()
    
    for plant in plants_with_sensors:
        garden_plant_id = plant[0]
        unique_id = plant[1]
        device_id = plant[2]
        sensor_name = plant[3]
        plant_name = plant[4] or plant[5]  # Use custom name or plant type name
        
        # Threshold values (will be None if not set)
        humidity_low = plant[7]
        humidity_high = plant[8]
        temp_low = plant[9]
        temp_high = plant[10]
        
        print(f"Polling sensor {sensor_name} (ID: {device_id}) for plant {plant_name}")
        
        # Check sensor parameters
        result = check_soil_sensor_parameters(device_id, "Soil")
        
        if result:
            moisture, temp, battery, sensor_state = result
            
            # Insert reading into database
            cursor.execute('''
                INSERT INTO sensor_readings 
                (plant_unique_id, sensor_name, device_id, date, time, 
                 temperature, humidity, battery_charge, sensor_state, garden_plant_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                unique_id,
                sensor_name,
                device_id,
                datetime.now().strftime('%Y-%m-%d'),
                datetime.now().strftime('%H:%M:%S'),
                temp,
                moisture,
                battery,
                sensor_state,
                garden_plant_id
            ))
            
            if sensor_state == 1:
                print(f"  ✓ Data recorded: Temp={temp}°C, Humidity={moisture}%, Battery={battery}%")
                
                # Check if values are within thresholds
                if humidity_low is not None and humidity_high is not None:
                    if moisture < humidity_low or moisture > humidity_high:
                        print(f"  ⚠ WARNING: Humidity {moisture}% is outside range ({humidity_low}-{humidity_high}%)")
                
                if temp_low is not None and temp_high is not None:
                    if temp < temp_low or temp > temp_high:
                        print(f"  ⚠ WARNING: Temperature {temp}°C is outside range ({temp_low}-{temp_high}°C)")
            else:
                print(f"  ✗ Sensor unavailable")
        else:
            print(f"  ✗ Failed to read sensor")
    
    conn.commit()

def continuous_polling(frequency):
    """Continuously poll sensors at specified frequency"""
    print(f"\nStarting continuous polling every {frequency} seconds...")
    print("Press Ctrl+C to stop\n")
    
    trigger_file = 'poll_trigger.txt'
    last_trigger_time = 0
    last_poll_time = 0
    
    while True:
        try:
            # Check for trigger file
            trigger_now = False
            if os.path.exists(trigger_file):
                try:
                    with open(trigger_file, 'r') as f:
                        trigger_time = float(f.read().strip())
                        if trigger_time > last_trigger_time:
                            trigger_now = True
                            last_trigger_time = trigger_time
                            print(f"\n--- Triggered poll at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
                    os.remove(trigger_file)
                except:
                    pass
            
            # Check if it's time for regular polling or if triggered
            current_time = time.time()
            time_since_last_poll = current_time - last_poll_time
            
            if trigger_now or time_since_last_poll >= frequency:
                if not trigger_now:
                    print(f"\n--- Polling at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
                
                conn = sqlite3.connect(DB_FILE)
                poll_sensors(conn)
                conn.close()
                
                last_poll_time = current_time
                
            # Sleep for 1 second and check again
            time.sleep(1)
                        
        except KeyboardInterrupt:
            print("\n\nPolling stopped by user")
            break
        except Exception as e:
            print(f"Error during polling: {e}")
            time.sleep(1)

def single_poll():
    """Perform a single poll of all sensors"""
    print(f"\n--- Single poll at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
    conn = sqlite3.connect(DB_FILE)
    poll_sensors(conn)
    conn.close()
    print("Single poll completed.")

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print('\n\nShutting down gracefully...')
    sys.exit(0)

def main():
    """Main function"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Garden Sensors Database Logger')
    parser.add_argument('--single-poll', action='store_true', 
                        help='Perform a single poll and exit')
    args = parser.parse_args()
    
    print("Garden Sensors Database Logger")
    print("==============================\n")
    
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    # Check if database exists and has new schema
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Check if new tables exist
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='garden_plants'
    """)
    
    if not cursor.fetchone():
        print("Error: Database schema not updated. Please run garden_db_migration.py first.")
        conn.close()
        sys.exit(1)
    
    # Check if plant_thresholds table exists
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='plant_thresholds'
    """)
    
    if not cursor.fetchone():
        print("Warning: plant_thresholds table not found. Please run garden_db_migration_thresholds.py")
        print("Continuing without threshold checking...\n")
    
    # Check if there are any plants with sensors
    cursor.execute("""
        SELECT COUNT(*) FROM garden_plants 
        WHERE has_sensor = 1 AND sensor_id IS NOT NULL
    """)
    
    sensor_count = cursor.fetchone()[0]
    conn.close()
    
    if sensor_count == 0:
        print("No plants with sensors found in database.")
        print("Please configure plants with sensors using garden.py")
        sys.exit(0)
    
    print(f"Found {sensor_count} plants with sensors")
    print(f"Current season: {get_current_season()}")
    
    # Check if single poll mode
    if args.single_poll:
        single_poll()
    else:
        # Start continuous polling
        continuous_polling(frequency)

if __name__ == "__main__":
    main()