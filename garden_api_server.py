from flask import Flask, jsonify, request, send_file, Response, send_from_directory, make_response
from flask_cors import CORS
import sqlite3
import json
from datetime import datetime, timedelta
import csv
import io
import os
import threading
import subprocess

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

DB_FILE = 'garden_sensors.db'

def get_db_connection():
    """Create a database connection"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # This enables column access by name
    return conn

@app.route('/')
def index():
    """Serve the main HTML page"""
    return send_file('garden_web_interface.html')

@app.route('/garden_data.json')
def get_garden_data():
    """Serve garden layout data"""
    if os.path.exists('garden_data.json'):
        return send_file('garden_data.json')
    else:
        return jsonify({'error': 'Garden data file not found'}), 404

@app.route('/<filename>')
def serve_static(filename):
    """Serve static files from current directory with caching"""
    if (filename.endswith(('.png', '.jpg', '.jpeg', '.gif', '.json')) and 
        os.path.exists(filename) and 
        not filename.startswith('api')):
        
        # Get file modification time for ETag
        file_stat = os.stat(filename)
        file_mtime = file_stat.st_mtime
        etag = f'"{filename}-{file_mtime}"'
        
        # Handle conditional requests
        if_none_match = request.headers.get('If-None-Match')
        if if_none_match == etag:
            return Response(status=304)  # Not Modified
        
        response = make_response(send_from_directory('.', filename))
        
        # Set caching headers based on file type
        if filename.endswith(('.png', '.jpg', '.jpeg', '.gif')):
            # Cache images for 24 hours
            response.headers['Cache-Control'] = 'public, max-age=86400'
            response.headers['Expires'] = (datetime.now() + timedelta(days=1)).strftime('%a, %d %b %Y %H:%M:%S GMT')
        elif filename.endswith('.json'):
            # Cache JSON for 1 hour (sensor data changes)
            response.headers['Cache-Control'] = 'public, max-age=3600'
            response.headers['Expires'] = (datetime.now() + timedelta(hours=1)).strftime('%a, %d %b %Y %H:%M:%S GMT')
        
        # Set ETag and Last-Modified
        response.headers['ETag'] = etag
        response.headers['Last-Modified'] = datetime.fromtimestamp(file_mtime).strftime('%a, %d %b %Y %H:%M:%S GMT')
        
        return response
    else:
        return jsonify({'error': 'File not found'}), 404

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Check database connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()}), 200
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

@app.route('/api/trigger-sensor-poll', methods=['POST'])
def trigger_sensor_poll():
    """Trigger immediate sensor polling"""
    try:
        # Try to create a trigger file that the logger can detect
        trigger_file = 'poll_trigger.txt'
        with open(trigger_file, 'w') as f:
            f.write(str(datetime.now().timestamp()))
        
        # Also try to run a single poll if logger is not running
        # Check if we can run it without interfering with existing process
        import psutil
        import sys
        
        # Check if garden_db_logger.py is already running
        logger_running = False
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline', [])
                if cmdline and 'garden_db_logger.py' in ' '.join(cmdline):
                    logger_running = True
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        if not logger_running:
            # Logger not running, we can run single poll
            python_exe = sys.executable
            result = subprocess.run(
                [python_exe, 'garden_db_logger.py', '--single-poll'],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                return jsonify({
                    'status': 'success',
                    'message': 'Sensor polling completed (single poll)',
                    'timestamp': datetime.now().isoformat()
                }), 200
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'Sensor polling failed',
                    'error': result.stderr,
                    'timestamp': datetime.now().isoformat()
                }), 500
        else:
            # Logger is running, trigger file created
            return jsonify({
                'status': 'success',
                'message': 'Sensor poll triggered',
                'timestamp': datetime.now().isoformat()
            }), 200
            
    except subprocess.TimeoutExpired:
        return jsonify({
            'status': 'error',
            'message': 'Sensor polling timeout',
            'timestamp': datetime.now().isoformat()
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/sensor-data', methods=['GET'])
def get_sensor_data():
    """API endpoint to retrieve sensor data"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get query parameters
    plant_id = request.args.get('plant')
    device_id = request.args.get('device_id')
    date_from = request.args.get('dateFrom')
    date_to = request.args.get('dateTo')
    limit = request.args.get('limit', 1000, type=int)
    
    # Build query
    query = "SELECT * FROM sensor_readings WHERE 1=1"
    params = []
    
    if plant_id:
        query += " AND plant_unique_id = ?"
        params.append(plant_id)
    
    if device_id:
        query += " AND device_id = ?"
        params.append(device_id)
    
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)
    
    query += " ORDER BY date DESC, time DESC LIMIT ?"
    params.append(limit)
    
    # Execute query
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    # Convert to list of dictionaries
    data = []
    for row in rows:
        data.append({
            'id': row['id'],
            'plant_unique_id': row['plant_unique_id'],
            'sensor_name': row['sensor_name'],
            'device_id': row['device_id'],
            'date': row['date'],
            'time': row['time'],
            'temperature': row['temperature'],
            'humidity': row['humidity'],
            'battery_charge': row['battery_charge'],
            'sensor_state': row['sensor_state'],
            'timestamp': row['timestamp']
        })
    
    conn.close()
    return jsonify(data)

@app.route('/api/sensor-stats', methods=['GET'])
def get_sensor_stats():
    """API endpoint to get sensor statistics"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get total readings
    cursor.execute("SELECT COUNT(*) as total FROM sensor_readings")
    total_readings = cursor.fetchone()['total']
    
    # Get active sensors count
    cursor.execute("""
        SELECT COUNT(DISTINCT sensor_name) as active_sensors 
        FROM sensor_readings 
        WHERE sensor_state = 1 
        AND date = date('now')
    """)
    active_sensors = cursor.fetchone()['active_sensors']
    
    # Get average temperature and humidity for today
    cursor.execute("""
        SELECT 
            AVG(temperature) as avg_temp,
            AVG(humidity) as avg_humidity
        FROM sensor_readings 
        WHERE sensor_state = 1 
        AND date = date('now')
    """)
    row = cursor.fetchone()
    avg_temp = row['avg_temp']
    avg_humidity = row['avg_humidity']
    
    # Get sensors with low battery
    cursor.execute("""
        SELECT DISTINCT sensor_name, battery_charge
        FROM sensor_readings 
        WHERE battery_charge < 20
        AND date = date('now')
        ORDER BY battery_charge ASC
    """)
    low_battery_sensors = []
    for row in cursor.fetchall():
        low_battery_sensors.append({
            'sensor_name': row['sensor_name'],
            'battery': row['battery_charge']
        })
    
    conn.close()
    
    return jsonify({
        'total_readings': total_readings,
        'active_sensors': active_sensors,
        'avg_temperature': round(avg_temp, 1) if avg_temp else None,
        'avg_humidity': round(avg_humidity, 1) if avg_humidity else None,
        'low_battery_sensors': low_battery_sensors
    })

@app.route('/api/export-csv', methods=['GET'])
def export_csv():
    """Export sensor data as CSV"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get query parameters (same as sensor-data endpoint)
    plant_id = request.args.get('plant')
    date_from = request.args.get('dateFrom')
    date_to = request.args.get('dateTo')
    
    # Build query
    query = "SELECT * FROM sensor_readings WHERE 1=1"
    params = []
    
    if plant_id:
        query += " AND plant_unique_id = ?"
        params.append(plant_id)
    
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)
    
    query += " ORDER BY date DESC, time DESC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Plant ID', 'Sensor Name', 'Device ID', 'Date', 'Time',
        'Temperature (°C)', 'Humidity (%)', 'Battery (%)', 
        'Sensor State', 'Timestamp'
    ])
    
    # Write data
    for row in rows:
        writer.writerow([
            row['plant_unique_id'],
            row['sensor_name'],
            row['device_id'],
            row['date'],
            row['time'],
            row['temperature'],
            row['humidity'],
            row['battery_charge'],
            'Active' if row['sensor_state'] == 1 else 'Inactive',
            row['timestamp']
        ])
    
    # Create response
    output.seek(0)
    response = app.response_class(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename=sensor_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        }
    )
    
    conn.close()
    return response

@app.route('/api/gardens', methods=['GET'])
def get_gardens():
    """Get list of all garden layouts"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, name, created_at, updated_at 
        FROM garden_layouts 
        WHERE is_active = 1 
        ORDER BY updated_at DESC, created_at DESC
    ''')
    
    gardens = []
    for row in cursor.fetchall():
        gardens.append({
            'id': row['id'],
            'name': row['name'],
            'created_at': row['created_at'],
            'updated_at': row['updated_at']
        })
    
    conn.close()
    return jsonify(gardens)

@app.route('/api/garden/<int:layout_id>', methods=['GET'])
def get_garden(layout_id):
    """Get specific garden layout with plants and images"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get garden layout
    cursor.execute('SELECT * FROM garden_layouts WHERE id = ?', (layout_id,))
    layout = cursor.fetchone()
    
    if not layout:
        conn.close()
        return jsonify({'error': 'Garden not found'}), 404
    
    # Get plants
    cursor.execute('''
        SELECT gp.*, pt.name as plant_type_name, pt.latin_name
        FROM garden_plants gp
        JOIN plant_types pt ON gp.plant_type_id = pt.id
        WHERE gp.garden_layout_id = ?
    ''', (layout_id,))
    
    plants = []
    for row in cursor.fetchall():
        plants.append({
            'id': row['id'],
            'unique_id': row['unique_id'],
            'plant_type_name': row['plant_type_name'],
            'position_x': row['position_x'],
            'position_y': row['position_y'],
            'custom_name': row['custom_name'],
            'latin_name': row['latin_name'],
            'image_path': row['image_path'],
            'has_sensor': bool(row['has_sensor']),
            'sensor_id': row['sensor_id'],
            'sensor_name': row['sensor_name']
        })
    
    # Get images
    cursor.execute('''
        SELECT * FROM garden_images
        WHERE garden_layout_id = ?
    ''', (layout_id,))
    
    images = []
    for row in cursor.fetchall():
        images.append({
            'id': row['id'],
            'image_path': row['image_path'],
            'position_x': row['position_x'],
            'position_y': row['position_y'],
            'width': row['width'],
            'height': row['height']
        })
    
    conn.close()
    
    return jsonify({
        'id': layout['id'],
        'name': layout['name'],
        'boundary': json.loads(layout['boundary_points']),
        'plants': plants,
        'images': images
    })

@app.route('/api/plant-photo/<int:garden_plant_id>', methods=['GET'])
def get_plant_photo(garden_plant_id):
    """Get main photo for a specific plant with caching headers"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get main photo for the plant
    cursor.execute('''
        SELECT photo_data, photo_type 
        FROM plant_photos 
        WHERE garden_plant_id = ? AND photo_type = 'main'
        LIMIT 1
    ''', (garden_plant_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result and result['photo_data']:
        # Create response with photo data
        response = Response(
            result['photo_data'],
            mimetype='image/jpeg',
            headers={
                'Content-Type': 'image/jpeg',
                'Cache-Control': 'public, max-age=86400',  # Cache for 24 hours
                'Expires': (datetime.now() + timedelta(days=1)).strftime('%a, %d %b %Y %H:%M:%S GMT'),
                'ETag': f'"{garden_plant_id}-photo"',  # ETag for cache validation
                'Last-Modified': datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')
            }
        )
        
        # Handle conditional requests (browser cache validation)
        if_none_match = request.headers.get('If-None-Match')
        if if_none_match == f'"{garden_plant_id}-photo"':
            return Response(status=304)  # Not Modified
        
        return response
    else:
        return jsonify({'error': 'Photo not found'}), 404

@app.route('/api/plants', methods=['GET'])
def get_plants():
    """Get list of all plants with sensors"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT DISTINCT plant_unique_id, sensor_name
        FROM sensor_readings
        ORDER BY plant_unique_id
    """)
    
    plants = []
    for row in cursor.fetchall():
        plants.append({
            'id': row['plant_unique_id'],
            'sensor_name': row['sensor_name']
        })
    
    conn.close()
    return jsonify(plants)

@app.route('/api/plant-info', methods=['GET'])
def get_plant_info():
    """Get plant information with thresholds from database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        current_season = get_current_season()
        
        # Get all plants with their thresholds for current season
        cursor.execute('''
            SELECT 
                gp.unique_id,
                gp.custom_name,
                pt.name as plant_type_name,
                pt.latin_name,
                pth.humidity_low,
                pth.humidity_high,
                pth.temperature_low,
                pth.temperature_high
            FROM garden_plants gp
            JOIN plant_types pt ON gp.plant_type_id = pt.id
            LEFT JOIN plant_thresholds pth ON pt.id = pth.plant_type_id 
                AND pth.season = ?
            WHERE gp.has_sensor = 1
        ''', (current_season,))
        
        plant_info = {}
        for row in cursor.fetchall():
            plant_name = row['custom_name'] or row['plant_type_name']
            plant_info[plant_name] = {
                "unique_id": row['unique_id'],
                "latin_name": row['latin_name'] or '',
                "current_season": current_season,
                "humidity_range": {
                    "low": row['humidity_low'] if row['humidity_low'] is not None else 30,
                    "high": row['humidity_high'] if row['humidity_high'] is not None else 70
                },
                "temperature_range": {
                    "low": row['temperature_low'] if row['temperature_low'] is not None else 10,
                    "high": row['temperature_high'] if row['temperature_high'] is not None else 30
                }
            }
        
        conn.close()
        return jsonify(plant_info)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/plant-thresholds', methods=['GET'])
def get_plant_thresholds():
    """Get all plant thresholds (all seasons)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    plant_type_id = request.args.get('plant_type_id', type=int)
    
    if plant_type_id:
        cursor.execute('''
            SELECT * FROM plant_thresholds 
            WHERE plant_type_id = ?
            ORDER BY 
                CASE season 
                    WHEN 'Spring' THEN 1
                    WHEN 'Summer' THEN 2
                    WHEN 'Autumn' THEN 3
                    WHEN 'Winter' THEN 4
                END
        ''', (plant_type_id,))
    else:
        cursor.execute('''
            SELECT pt.name, pth.*
            FROM plant_thresholds pth
            JOIN plant_types pt ON pth.plant_type_id = pt.id
            ORDER BY pt.name, 
                CASE pth.season 
                    WHEN 'Spring' THEN 1
                    WHEN 'Summer' THEN 2
                    WHEN 'Autumn' THEN 3
                    WHEN 'Winter' THEN 4
                END
        ''')
    
    thresholds = []
    for row in cursor.fetchall():
        threshold = {
            'id': row['id'],
            'plant_type_id': row['plant_type_id'],
            'season': row['season'],
            'humidity_low': row['humidity_low'],
            'humidity_high': row['humidity_high'],
            'temperature_low': row['temperature_low'],
            'temperature_high': row['temperature_high']
        }
        if 'name' in row.keys():
            threshold['plant_name'] = row['name']
        thresholds.append(threshold)
    
    conn.close()
    return jsonify(thresholds)

@app.route('/api/plant-thresholds', methods=['POST'])
def update_plant_thresholds():
    """Update plant thresholds"""
    data = request.json
    
    required_fields = ['plant_type_id', 'season', 'humidity_low', 'humidity_high', 
                      'temperature_low', 'temperature_high']
    
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO plant_thresholds 
            (plant_type_id, season, humidity_low, humidity_high, 
             temperature_low, temperature_high, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            data['plant_type_id'],
            data['season'],
            data['humidity_low'],
            data['humidity_high'],
            data['temperature_low'],
            data['temperature_high']
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Thresholds updated successfully'}), 200
        
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500

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

@app.route('/api/garden-config', methods=['GET'])
def get_garden_config():
    """Get garden configuration from ini file"""
    try:
        import configparser
        config = configparser.ConfigParser()
        config.read('garden.ini')
        
        frequency = int(config.get('frequency', 'frequency'))
        
        return jsonify({
            'frequency': frequency
        })
    except Exception as e:
        # Return default if config not found
        return jsonify({
            'frequency': 2400  # Default 40 minutes
        })

@app.route('/api/dashboard-data', methods=['GET'])
def get_dashboard_data():
    """Get all dashboard data in one request - optimized for fast loading"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get garden layout (latest active)
        cursor.execute('''
            SELECT id, name, boundary_points 
            FROM garden_layouts 
            WHERE is_active = 1 
            ORDER BY updated_at DESC, created_at DESC 
            LIMIT 1
        ''')
        layout = cursor.fetchone()
        
        if not layout:
            conn.close()
            return jsonify({'error': 'No garden found'}), 404
            
        layout_id = layout['id']
        
        # Get plants
        cursor.execute('''
            SELECT gp.*, pt.name as plant_type_name, pt.latin_name
            FROM garden_plants gp
            JOIN plant_types pt ON gp.plant_type_id = pt.id
            WHERE gp.garden_layout_id = ?
        ''', (layout_id,))
        
        plants = []
        sensor_ids = []
        for row in cursor.fetchall():
            plant = {
                'id': row['id'],
                'unique_id': row['unique_id'],
                'plant_type_name': row['plant_type_name'],
                'position_x': row['position_x'],
                'position_y': row['position_y'],
                'custom_name': row['custom_name'],
                'latin_name': row['latin_name'],
                'image_path': row['image_path'],
                'has_sensor': bool(row['has_sensor']),
                'sensor_id': row['sensor_id'],
                'sensor_name': row['sensor_name']
            }
            plants.append(plant)
            if row['sensor_id']:
                sensor_ids.append(row['sensor_id'])
        
        # Get images
        cursor.execute('''
            SELECT * FROM garden_images WHERE garden_layout_id = ?
        ''', (layout_id,))
        
        images = []
        for row in cursor.fetchall():
            images.append({
                'id': row['id'],
                'image_path': row['image_path'],
                'position_x': row['position_x'],
                'position_y': row['position_y'],
                'width': row['width'],
                'height': row['height']
            })
        
        # Get latest sensor data for all sensors - optimized query
        sensor_data = {}
        if sensor_ids:
            # Create a subquery to get the latest reading for each sensor
            placeholders = ','.join(['?' for _ in sensor_ids])
            cursor.execute(f'''
                SELECT sr1.*
                FROM sensor_readings sr1
                INNER JOIN (
                    SELECT device_id, MAX(date || ' ' || time) as max_datetime
                    FROM sensor_readings 
                    WHERE device_id IN ({placeholders})
                    GROUP BY device_id
                ) sr2 ON sr1.device_id = sr2.device_id 
                AND (sr1.date || ' ' || sr1.time) = sr2.max_datetime
            ''', sensor_ids)
            
            for row in cursor.fetchall():
                sensor_data[row['device_id']] = {
                    'temperature': row['temperature'],
                    'humidity': row['humidity'],
                    'battery_charge': row['battery_charge'],
                    'sensor_state': row['sensor_state'],
                    'date': row['date'],
                    'time': row['time'],
                    'timestamp': row['timestamp']
                }
        
        # Get plant info (thresholds) for current season
        current_season = get_current_season()
        cursor.execute('''
            SELECT 
                gp.unique_id,
                gp.custom_name,
                pt.name as plant_type_name,
                pt.latin_name,
                pth.humidity_low,
                pth.humidity_high,
                pth.temperature_low,
                pth.temperature_high
            FROM garden_plants gp
            JOIN plant_types pt ON gp.plant_type_id = pt.id
            LEFT JOIN plant_thresholds pth ON pt.id = pth.plant_type_id 
                AND pth.season = ?
            WHERE gp.has_sensor = 1 AND gp.garden_layout_id = ?
        ''', (current_season, layout_id))
        
        plant_info = {}
        for row in cursor.fetchall():
            plant_name = row['custom_name'] or row['plant_type_name']
            plant_info[plant_name] = {
                "unique_id": row['unique_id'],
                "latin_name": row['latin_name'] or '',
                "current_season": current_season,
                "humidity_range": {
                    "low": row['humidity_low'] if row['humidity_low'] is not None else 30,
                    "high": row['humidity_high'] if row['humidity_high'] is not None else 70
                },
                "temperature_range": {
                    "low": row['temperature_low'] if row['temperature_low'] is not None else 10,
                    "high": row['temperature_high'] if row['temperature_high'] is not None else 30
                }
            }
        
        conn.close()
        
        return jsonify({
            'garden': {
                'id': layout['id'],
                'name': layout['name'],
                'boundary': json.loads(layout['boundary_points']),
                'plants': plants,
                'images': images
            },
            'sensor_data': sensor_data,
            'plant_info': plant_info,
            'loaded_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Run the server
    # For production, use a proper WSGI server like gunicorn
    app.run(host='0.0.0.0', port=5000, debug=True)