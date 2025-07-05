import pygame
import sys
import sqlite3
import tkinter as tk
from tkinter import simpledialog, filedialog, messagebox, ttk
from shapely.geometry import Point, Polygon
from PIL import Image, ImageTk
import os
import json
import io
import time
import threading
import platform

# Initialize pygame
pygame.init()

# Database configuration
DB_FILE = 'garden_sensors.db'

# Set window size to 90% of screen (like in original)
screen_info = pygame.display.Info()
window_width = int(screen_info.current_w * 0.9)
window_height = int(screen_info.current_h * 0.9)
window_size = (window_width, window_height)

# Create resizable window
window = pygame.display.set_mode(window_size, pygame.RESIZABLE)
pygame.display.set_caption("Garden Designer")

# Center window on screen
if platform.system() == 'Windows':
    import ctypes
    from ctypes import wintypes
    
    # Get window handle
    hwnd = pygame.display.get_wm_info()["window"]
    
    # Center window
    user32 = ctypes.WinDLL("user32")
    screensize = (screen_info.current_w, screen_info.current_h)
    x = (screensize[0] - window_width) // 2
    y = (screensize[1] - window_height) // 2
    
    user32.SetWindowPos(hwnd, 0, x, y, window_width, window_height, 0x0040)

# Adjusted button area height
margin_y = 10
button_height = 40
button_spacing_y = 10
num_button_rows = 2
button_area_height = 2 * margin_y + num_button_rows * button_height + button_spacing_y
garden_area_size = (window_width, window_height - button_area_height)
button_area_size = (window_width, button_area_height)

# Colors
background_color = (100, 200, 100)
outside_background_color = (245, 222, 179)
button_area_color = (245, 245, 245)
button_color = (33, 150, 243)
button_hover_color = (25, 118, 210)
dimmed_button_color = (150, 150, 150)
text_color = (255, 255, 255)
garden_border_color = (0, 0, 0)
grid_color = (170, 170, 170)
dot_color = (0, 0, 0)

# State
garden_loaded_or_created = False
is_creating_garden = False
is_adding_plant = False
is_adding_image = False
garden_boundary = []
plants = []
images = []
garden_modified = False
undo_stack = []
redo_stack = []
selected_plant = None
selected_image = None
dragging = False
dragging_image = False
resizing_image = False
resize_anchor = None
right_click_start_pos = None
current_layout_id = None

# Double-click detection variables
last_click_time = 0
last_click_pos = None
double_click_threshold = 500  # milliseconds

# Centering buttons horizontally
button_width = 150
button_spacing_x = 150
buttons_total_width = button_width * 4 + button_spacing_x * 3
button_area_x_start = (window_width - buttons_total_width) // 2
buttons_area_y_start = garden_area_size[1] + margin_y

# Creating buttons
load_garden_button = pygame.Rect(button_area_x_start, buttons_area_y_start, button_width, button_height)
create_garden_button = pygame.Rect(button_area_x_start, buttons_area_y_start + button_height + button_spacing_y, button_width, button_height)
add_plant_button = pygame.Rect(button_area_x_start + button_width + button_spacing_x, buttons_area_y_start, button_width, button_height)
add_image_button = pygame.Rect(button_area_x_start + button_width + button_spacing_x, buttons_area_y_start + button_height + button_spacing_y, button_width, button_height)
undo_button = pygame.Rect(button_area_x_start + (button_width + button_spacing_x) * 2, buttons_area_y_start, button_width, button_height)
redo_button = pygame.Rect(button_area_x_start + (button_width + button_spacing_x) * 2, buttons_area_y_start + button_height + button_spacing_y, button_width, button_height)
save_button = pygame.Rect(button_area_x_start + (button_width + button_spacing_x) * 3, buttons_area_y_start, button_width, button_height)
exit_button = pygame.Rect(button_area_x_start + (button_width + button_spacing_x) * 3, buttons_area_y_start + button_height + button_spacing_y, button_width, button_height)

# Loading default plant image
default_plant_image = pygame.image.load("tree.png")
default_plant_image = pygame.transform.scale(default_plant_image, (30, 30))

# Loading sensor icon image
sensor_icon = pygame.image.load("sensor.png")
sensor_icon = pygame.transform.scale(sensor_icon, (15, 15))

# Database functions
def get_db_connection():
    """Create a database connection with timeout"""
    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrency
    conn.execute('PRAGMA journal_mode=WAL')
    return conn

def get_plant_types():
    """Get all plant types from database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, latin_name FROM plant_types ORDER BY name')
    types = cursor.fetchall()
    conn.close()
    return types

def get_or_create_plant_type(name, species=""):
    """Get existing plant type or create new one"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if plant type exists
    cursor.execute('SELECT id FROM plant_types WHERE name = ?', (name,))
    result = cursor.fetchone()
    
    if result:
        plant_type_id = result[0]
    else:
        # Create new plant type
        cursor.execute('''
            INSERT INTO plant_types (name, latin_name)
            VALUES (?, ?)
        ''', (name, species))
        plant_type_id = cursor.lastrowid
        conn.commit()
    
    conn.close()
    return plant_type_id

def compress_photo(photo_data, max_size=(1200, 1200), quality=85):
    """Compress photo to reduce size and improve performance"""
    try:
        img = Image.open(io.BytesIO(photo_data))
        
        # Convert RGBA to RGB if necessary
        if img.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        
        # Resize if larger than max_size
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Save compressed
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True)
        return output.getvalue()
    except Exception as e:
        print(f"Error compressing photo: {e}")
        return photo_data  # Return original if compression fails

def save_plant_photo(garden_plant_id, photo_data):
    """Save plant photo to database with proper transaction handling"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Start transaction
        cursor.execute('BEGIN IMMEDIATE')
        
        # Check if plant already has a main photo
        cursor.execute('''
            SELECT COUNT(*) FROM plant_photos 
            WHERE garden_plant_id = ? AND photo_type = 'main'
        ''', (garden_plant_id,))
        
        has_main = cursor.fetchone()[0] > 0
        photo_type = 'additional' if has_main else 'main'
        
        # Compress photo
        compressed_data = compress_photo(photo_data)
        
        # Insert photo
        cursor.execute('''
            INSERT INTO plant_photos 
            (garden_plant_id, photo_data, photo_type, description, file_size)
            VALUES (?, ?, ?, ?, ?)
        ''', (garden_plant_id, compressed_data, photo_type, 'Plant photo', len(compressed_data)))
        
        # Commit transaction
        cursor.execute('COMMIT')
        
        return cursor.lastrowid
    except Exception as e:
        cursor.execute('ROLLBACK')
        print(f"Error saving photo: {e}")
        return None
    finally:
        conn.close()

def get_plant_photo(garden_plant_id):
    """Get main photo for a plant from database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT photo_data FROM plant_photos 
        WHERE garden_plant_id = ? AND photo_type = 'main'
        LIMIT 1
    ''', (garden_plant_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result and result['photo_data']:
        return result['photo_data']
    return None

def save_garden_to_db():
    """Save current garden to database with progress indication"""
    global current_layout_id, garden_modified
    
    # Create progress window
    progress_window = tk.Tk()
    progress_window.title("Saving Garden")
    progress_window.geometry("400x150")
    
    # Center the window
    progress_window.update_idletasks()
    width = progress_window.winfo_width()
    height = progress_window.winfo_height()
    x = (progress_window.winfo_screenwidth() // 2) - (width // 2)
    y = (progress_window.winfo_screenheight() // 2) - (height // 2)
    progress_window.geometry(f'+{x}+{y}')
    
    # Progress label
    progress_label = tk.Label(progress_window, text="Preparing to save...", font=("Arial", 12))
    progress_label.pack(pady=20)
    
    # Progress bar
    progress_bar = ttk.Progressbar(progress_window, length=350, mode='determinate')
    progress_bar.pack(pady=10)
    
    # Status label
    status_label = tk.Label(progress_window, text="", font=("Arial", 10))
    status_label.pack(pady=5)
    
    # Update window
    progress_window.update()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Start transaction
        cursor.execute('BEGIN IMMEDIATE')
        
        # Calculate total steps
        total_photo_count = sum(len(plant.get('all_photos', [])) for plant in plants)
        if any(plant.get('photo_data') and not plant.get('all_photos') for plant in plants):
            # Count new photos that aren't in all_photos yet
            total_photo_count += sum(1 for plant in plants if plant.get('photo_data') and not plant.get('all_photos'))
        
        total_steps = len(plants) + total_photo_count + len(images) + 3
        current_step = 0
        
        def update_progress(step, text, status=""):
            progress_bar['value'] = (step / total_steps) * 100
            progress_label['text'] = text
            status_label['text'] = status
            progress_window.update()
        
        # Create or update garden layout
        update_progress(current_step, "Saving garden layout...")
        
        if current_layout_id:
            # Update existing layout
            cursor.execute('''
                UPDATE garden_layouts 
                SET boundary_points = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (json.dumps(garden_boundary), current_layout_id))
            
            # IMPORTANT: Save ALL existing photos before deleting plants
            update_progress(current_step, "Backing up existing photos...")
            
            # Get all existing photos for this garden with full data
            cursor.execute('''
                SELECT pp.*, gp.unique_id, gp.custom_name
                FROM plant_photos pp
                JOIN garden_plants gp ON pp.garden_plant_id = gp.id
                WHERE gp.garden_layout_id = ?
            ''', (current_layout_id,))
            
            existing_photos_by_plant = {}
            for row in cursor.fetchall():
                key = f"{row['unique_id']}_{row['custom_name']}"  # Use composite key
                if key not in existing_photos_by_plant:
                    existing_photos_by_plant[key] = []
                existing_photos_by_plant[key].append({
                    'id': row['id'],
                    'photo_data': row['photo_data'],
                    'photo_type': row['photo_type'],
                    'description': row['description'],
                    'file_size': row['file_size']
                })
            
            # Now safe to delete existing plants
            cursor.execute('DELETE FROM garden_plants WHERE garden_layout_id = ?', (current_layout_id,))
            cursor.execute('DELETE FROM garden_images WHERE garden_layout_id = ?', (current_layout_id,))
        else:
            # Create new layout
            cursor.execute('''
                INSERT INTO garden_layouts (name, boundary_points)
                VALUES (?, ?)
            ''', ('My Garden', json.dumps(garden_boundary)))
            current_layout_id = cursor.lastrowid
            existing_photos_by_plant = {}
        
        current_step += 1
        
        # Save plants
        update_progress(current_step, "Saving plants...", f"0 of {len(plants)}")
        
        for i, plant in enumerate(plants):
            plant_type_id = get_or_create_plant_type(plant['name'], plant.get('species', ''))
            
            # Generate unique ID
            unique_id = f"{plant['name'].upper()}-{plant_type_id:03d}"
            
            cursor.execute('''
                INSERT INTO garden_plants (
                    unique_id, plant_type_id, position_x, position_y,
                    custom_name, has_sensor, sensor_id,
                    sensor_name, garden_layout_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                unique_id,
                plant_type_id,
                plant['position'][0],
                plant['position'][1],
                plant['name'],
                plant.get('has_sensor', False),
                plant.get('sensor_id'),
                plant.get('sensor_name'),
                current_layout_id
            ))
            
            garden_plant_id = cursor.lastrowid
            
            # Collect photos to save
            photos_to_save = []
            
            # First, check if plant has all_photos list (loaded from DB)
            if plant.get('all_photos'):
                for photo_info in plant['all_photos']:
                    photos_to_save.append({
                        'photo_data': photo_info['photo_data'],
                        'photo_type': photo_info['photo_type'],
                        'description': photo_info.get('description', 'Plant photo')
                    })
            
            # Also check for new photo in photo_data that might not be in all_photos
            if plant.get('photo_data'):
                # Check if this photo is already in all_photos
                photo_already_saved = False
                if plant.get('all_photos'):
                    for photo_info in plant['all_photos']:
                        if photo_info['photo_data'] == plant['photo_data']:
                            photo_already_saved = True
                            break
                
                if not photo_already_saved:
                    photos_to_save.append({
                        'photo_data': plant['photo_data'],
                        'photo_type': 'main',
                        'description': 'Plant photo'
                    })
            
            # If no photos in current plant, check existing photos backup
            if not photos_to_save:
                key = f"{unique_id}_{plant['name']}"
                if key in existing_photos_by_plant:
                    for existing_photo in existing_photos_by_plant[key]:
                        photos_to_save.append({
                            'photo_data': existing_photo['photo_data'],
                            'photo_type': existing_photo['photo_type'],
                            'description': existing_photo.get('description', 'Plant photo')
                        })
            
            # Save all photos for this plant
            for j, photo in enumerate(photos_to_save):
                current_step += 1
                update_progress(current_step, f"Saving photos for {plant['name']}...", f"Photo {j+1} of {len(photos_to_save)}")
                
                try:
                    # Compress photo if needed
                    compressed_data = compress_photo(photo['photo_data'])
                    
                    # Insert photo
                    cursor.execute('''
                        INSERT INTO plant_photos 
                        (garden_plant_id, photo_data, photo_type, description, file_size)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        garden_plant_id, 
                        compressed_data, 
                        photo['photo_type'], 
                        photo['description'], 
                        len(compressed_data)
                    ))
                    
                except Exception as e:
                    print(f"Error saving photo for plant {plant['name']}: {e}")
            
            update_progress(current_step, "Saving plants...", f"{i+1} of {len(plants)}")
        
        current_step += 1
        
        # Save images
        update_progress(current_step, "Saving garden images...", f"0 of {len(images)}")
        
        for i, img in enumerate(images):
            cursor.execute('''
                INSERT INTO garden_images (
                    garden_layout_id, image_path, position_x, position_y,
                    width, height
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                current_layout_id,
                img['image_path'],
                img['rect'].x,
                img['rect'].y,
                img['rect'].width,
                img['rect'].height
            ))
            
            update_progress(current_step, "Saving garden images...", f"{i+1} of {len(images)}")
        
        # Commit all changes
        update_progress(total_steps - 1, "Finalizing...")
        cursor.execute('COMMIT')
        garden_modified = False
        
        # Verify photos were saved
        cursor.execute('''
            SELECT COUNT(*) as total_photos, 
                   COUNT(DISTINCT garden_plant_id) as plants_with_photos
            FROM plant_photos pp
            JOIN garden_plants gp ON pp.garden_plant_id = gp.id
            WHERE gp.garden_layout_id = ?
        ''', (current_layout_id,))
        
        result = cursor.fetchone()
        total_photos = result['total_photos']
        plants_with_photos = result['plants_with_photos']
        
        print(f"Verified {total_photos} photos saved for {plants_with_photos} plants")
        
        # Close progress window
        progress_window.destroy()
        
        # Show success message
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("Success", 
            f"Garden saved successfully!\n"
            f"Layout ID: {current_layout_id}\n"
            f"Total photos saved: {total_photos}\n"
            f"Plants with photos: {plants_with_photos}")
        root.destroy()
        
        print(f"Garden saved to database (Layout ID: {current_layout_id})")
        
    except Exception as e:
        cursor.execute('ROLLBACK')
        progress_window.destroy()
        
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Error", f"Failed to save garden:\n{str(e)}")
        root.destroy()
        
        print(f"Error saving garden: {e}")
        raise
    finally:
        conn.close()

def load_garden_from_db(layout_id):
    """Load garden from database"""
    global garden_boundary, plants, images, current_layout_id, garden_loaded_or_created
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Load layout
    cursor.execute('SELECT boundary_points FROM garden_layouts WHERE id = ?', (layout_id,))
    layout = cursor.fetchone()
    if not layout:
        conn.close()
        return False
    
    garden_boundary = json.loads(layout['boundary_points'])
    current_layout_id = layout_id
    
    # Load plants
    cursor.execute('''
        SELECT gp.*, pt.name as plant_type_name, pt.latin_name
        FROM garden_plants gp
        JOIN plant_types pt ON gp.plant_type_id = pt.id
        WHERE gp.garden_layout_id = ?
    ''', (layout_id,))
    
    plants = []
    for row in cursor.fetchall():
        # Get ALL photos for this plant, not just main
        cursor.execute('''
            SELECT photo_data, photo_type, id
            FROM plant_photos
            WHERE garden_plant_id = ?
            ORDER BY 
                CASE photo_type 
                    WHEN 'main' THEN 1 
                    ELSE 2 
                END
        ''', (row['id'],))
        
        all_photos = cursor.fetchall()
        photo_data = None
        plant_image = default_plant_image
        all_photo_data = []  # Store all photos
        
        # Process all photos
        for photo_row in all_photos:
            photo_info = {
                'photo_data': photo_row['photo_data'],
                'photo_type': photo_row['photo_type'],
                'photo_id': photo_row['id']
            }
            all_photo_data.append(photo_info)
            
            # Use main photo for display
            if photo_row['photo_type'] == 'main':
                photo_data = photo_row['photo_data']
                try:
                    # Load image from blob
                    image_stream = io.BytesIO(photo_data)
                    pil_image = Image.open(image_stream)
                    
                    # Convert PIL image to pygame surface
                    image_string = pil_image.convert('RGBA').tobytes()
                    plant_image = pygame.image.fromstring(image_string, pil_image.size, 'RGBA')
                    plant_image = pygame.transform.scale(plant_image, (30, 30))
                except Exception as e:
                    print(f"Error loading plant photo: {e}")
                    plant_image = default_plant_image
        
        plant = {
            'position': snap_to_grid((row['position_x'], row['position_y'])),
            'image': plant_image,
            'photo_data': photo_data,  # Main photo for compatibility
            'all_photos': all_photo_data,  # ALL photos
            'name': row['custom_name'] or row['plant_type_name'],
            'species': row['latin_name'] or '',
            'has_sensor': bool(row['has_sensor']),
            'sensor_id': row['sensor_id'],
            'sensor_name': row['sensor_name'],
            'db_id': row['id']  # Store database ID
        }
        plants.append(plant)
    
    # Load images
    cursor.execute('''
        SELECT * FROM garden_images
        WHERE garden_layout_id = ?
    ''', (layout_id,))
    
    images = []
    for row in cursor.fetchall():
        image_path = row['image_path']
        if image_path and os.path.exists(image_path):
            try:
                original_image = pygame.image.load(image_path).convert_alpha()
                image = pygame.transform.scale(original_image, (row['width'], row['height']))
                image_rect = image.get_rect()
                image_rect.topleft = (row['position_x'], row['position_y'])
                
                image_data = {
                    'image': image,
                    'original_image': original_image,
                    'image_path': image_path,
                    'rect': image_rect
                }
                images.append(image_data)
            except pygame.error:
                print(f"Error loading image: {image_path}")
    
    conn.close()
    garden_loaded_or_created = True
    return True

# Function to manage plant thresholds
def manage_plant_thresholds(plant_type_id, plant_name):
    """Manage threshold values for a plant type"""
    
    def create_threshold_window():
        threshold_window = tk.Toplevel()
        threshold_window.title(f"Thresholds for {plant_name}")
        
        # Get current thresholds from database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT season, humidity_low, humidity_high, temperature_low, temperature_high
            FROM plant_thresholds
            WHERE plant_type_id = ?
            ORDER BY 
                CASE season 
                    WHEN 'Spring' THEN 1
                    WHEN 'Summer' THEN 2
                    WHEN 'Autumn' THEN 3
                    WHEN 'Winter' THEN 4
                END
        ''', (plant_type_id,))
        
        thresholds = {}
        for row in cursor.fetchall():
            thresholds[row['season']] = {
                'humidity_low': row['humidity_low'],
                'humidity_high': row['humidity_high'],
                'temperature_low': row['temperature_low'],
                'temperature_high': row['temperature_high']
            }
        
        conn.close()
        
        # Default values if no thresholds exist
        default_thresholds = {
            'Spring': {'humidity_low': 40, 'humidity_high': 70, 'temperature_low': 10, 'temperature_high': 25},
            'Summer': {'humidity_low': 50, 'humidity_high': 80, 'temperature_low': 15, 'temperature_high': 35},
            'Autumn': {'humidity_low': 40, 'humidity_high': 70, 'temperature_low': 10, 'temperature_high': 25},
            'Winter': {'humidity_low': 30, 'humidity_high': 60, 'temperature_low': 5, 'temperature_high': 20}
        }
        
        # Create variables for each season
        season_vars = {}
        seasons = ['Spring', 'Summer', 'Autumn', 'Winter']
        
        for season in seasons:
            if season in thresholds:
                values = thresholds[season]
            else:
                values = default_thresholds[season]
            
            season_vars[season] = {
                'humidity_low': tk.IntVar(value=values['humidity_low']),
                'humidity_high': tk.IntVar(value=values['humidity_high']),
                'temperature_low': tk.IntVar(value=values['temperature_low']),
                'temperature_high': tk.IntVar(value=values['temperature_high'])
            }
        
        def save_thresholds():
            conn = get_db_connection()
            cursor = conn.cursor()
            
            try:
                for season in seasons:
                    vars = season_vars[season]
                    
                    # Validate values
                    if vars['humidity_low'].get() >= vars['humidity_high'].get():
                        messagebox.showerror("Error", f"{season}: Humidity low must be less than high")
                        return
                    
                    if vars['temperature_low'].get() >= vars['temperature_high'].get():
                        messagebox.showerror("Error", f"{season}: Temperature low must be less than high")
                        return
                    
                    cursor.execute('''
                        INSERT OR REPLACE INTO plant_thresholds 
                        (plant_type_id, season, humidity_low, humidity_high, 
                         temperature_low, temperature_high)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        plant_type_id,
                        season,
                        vars['humidity_low'].get(),
                        vars['humidity_high'].get(),
                        vars['temperature_low'].get(),
                        vars['temperature_high'].get()
                    ))
                
                conn.commit()
                messagebox.showinfo("Success", "Thresholds saved successfully!")
                threshold_window.destroy()
                
            except Exception as e:
                conn.rollback()
                messagebox.showerror("Error", f"Failed to save thresholds: {e}")
            finally:
                conn.close()
        
        # Create the UI
        main_frame = tk.Frame(threshold_window, padx=20, pady=20)
        main_frame.pack()
        
        # Headers
        tk.Label(main_frame, text="Season", font=("Arial", 10, "bold")).grid(row=0, column=0, padx=5)
        tk.Label(main_frame, text="Humidity %", font=("Arial", 10, "bold")).grid(row=0, column=1, columnspan=2, padx=5)
        tk.Label(main_frame, text="Temperature °C", font=("Arial", 10, "bold")).grid(row=0, column=3, columnspan=2, padx=5)
        
        tk.Label(main_frame, text="Low", font=("Arial", 9)).grid(row=1, column=1, padx=5)
        tk.Label(main_frame, text="High", font=("Arial", 9)).grid(row=1, column=2, padx=5)
        tk.Label(main_frame, text="Low", font=("Arial", 9)).grid(row=1, column=3, padx=5)
        tk.Label(main_frame, text="High", font=("Arial", 9)).grid(row=1, column=4, padx=5)
        
        # Season rows
        row = 2
        for season in seasons:
            tk.Label(main_frame, text=season).grid(row=row, column=0, sticky='w', padx=5, pady=5)
            
            vars = season_vars[season]
            
            # Humidity
            tk.Spinbox(main_frame, from_=0, to=100, textvariable=vars['humidity_low'], 
                      width=8).grid(row=row, column=1, padx=5, pady=5)
            tk.Spinbox(main_frame, from_=0, to=100, textvariable=vars['humidity_high'], 
                      width=8).grid(row=row, column=2, padx=5, pady=5)
            
            # Temperature
            tk.Spinbox(main_frame, from_=-10, to=50, textvariable=vars['temperature_low'], 
                      width=8).grid(row=row, column=3, padx=5, pady=5)
            tk.Spinbox(main_frame, from_=-10, to=50, textvariable=vars['temperature_high'], 
                      width=8).grid(row=row, column=4, padx=5, pady=5)
            
            row += 1
        
        # Buttons
        button_frame = tk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=5, pady=(20, 0))
        
        tk.Button(button_frame, text="Save", command=save_thresholds).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Cancel", command=threshold_window.destroy).pack(side=tk.LEFT, padx=5)
        
        # Center the window
        threshold_window.update_idletasks()
        width = threshold_window.winfo_width()
        height = threshold_window.winfo_height()
        x = (threshold_window.winfo_screenwidth() // 2) - (width // 2)
        y = (threshold_window.winfo_screenheight() // 2) - (height // 2)
        threshold_window.geometry(f'+{x}+{y}')
        
        threshold_window.transient()
        threshold_window.grab_set()
        threshold_window.wait_window()
    
    create_threshold_window()

def manage_plant_photos(plant):
    """Manage multiple photos for a plant"""
    
    def create_photo_window():
        photo_window = tk.Toplevel()
        photo_window.title(f"Photos for {plant['name']}")
        photo_window.geometry("600x500")
        
        # Main frame
        main_frame = tk.Frame(photo_window, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Photo list
        tk.Label(main_frame, text="Plant Photos:", font=("Arial", 12, "bold")).pack(pady=(0, 10))
        
        # Listbox with scrollbar
        list_frame = tk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        photo_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
        photo_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=photo_listbox.yview)
        
        # Load current photos
        current_photos = plant.get('all_photos', [])
        if not current_photos and plant.get('photo_data'):
            # Create all_photos list if it doesn't exist
            current_photos = [{
                'photo_data': plant['photo_data'],
                'photo_type': 'main',
                'description': 'Plant photo'
            }]
            plant['all_photos'] = current_photos
        
        # Populate listbox
        for i, photo in enumerate(current_photos):
            photo_listbox.insert(tk.END, f"{i+1}. {photo['photo_type']} - {len(photo['photo_data'])} bytes")
        
        # Buttons
        button_frame = tk.Frame(main_frame)
        button_frame.pack(pady=(10, 0))
        
        def add_photo():
            file_path = filedialog.askopenfilename(
                title="Select photo",
                filetypes=(("Image files", "*.png;*.jpg;*.jpeg"), ("All files", "*.*"))
            )
            if file_path:
                try:
                    with open(file_path, 'rb') as f:
                        photo_data = f.read()
                    
                    # Determine photo type
                    photo_type = 'main' if not current_photos else 'additional'
                    
                    # Add to list
                    current_photos.append({
                        'photo_data': photo_data,
                        'photo_type': photo_type,
                        'description': 'Plant photo'
                    })
                    
                    # Update listbox
                    photo_listbox.insert(tk.END, f"{len(current_photos)}. {photo_type} - {len(photo_data)} bytes")
                    
                    # Update plant's main photo if this is the first/main photo
                    if photo_type == 'main':
                        plant['photo_data'] = photo_data
                        # Update plant image
                        try:
                            image_stream = io.BytesIO(photo_data)
                            pil_image = Image.open(image_stream)
                            image_string = pil_image.convert('RGBA').tobytes()
                            plant_image = pygame.image.fromstring(image_string, pil_image.size, 'RGBA')
                            plant['image'] = pygame.transform.scale(plant_image, (30, 30))
                        except Exception as e:
                            print(f"Error updating plant image: {e}")
                    
                    global garden_modified
                    garden_modified = True
                    
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to add photo: {e}")
        
        def delete_photo():
            selection = photo_listbox.curselection()
            if selection:
                index = selection[0]
                if messagebox.askyesno("Delete Photo", "Are you sure you want to delete this photo?"):
                    removed = current_photos.pop(index)
                    photo_listbox.delete(index)
                    
                    # If deleted main photo, promote next photo
                    if removed['photo_type'] == 'main' and current_photos:
                        current_photos[0]['photo_type'] = 'main'
                        plant['photo_data'] = current_photos[0]['photo_data']
                        # Update display
                        photo_listbox.delete(0)
                        photo_listbox.insert(0, f"1. main - {len(current_photos[0]['photo_data'])} bytes")
                    elif not current_photos:
                        plant['photo_data'] = None
                        plant['image'] = default_plant_image
                    
                    # Re-number items
                    for i in range(photo_listbox.size()):
                        item_text = photo_listbox.get(i)
                        parts = item_text.split('. ', 1)
                        if len(parts) > 1:
                            photo_listbox.delete(i)
                            photo_listbox.insert(i, f"{i+1}. {parts[1]}")
                    
                    global garden_modified
                    garden_modified = True
        
        def set_as_main():
            selection = photo_listbox.curselection()
            if selection:
                index = selection[0]
                # Update all photos
                for i, photo in enumerate(current_photos):
                    photo['photo_type'] = 'main' if i == index else 'additional'
                
                # Update plant's main photo
                plant['photo_data'] = current_photos[index]['photo_data']
                
                # Update plant image
                try:
                    image_stream = io.BytesIO(current_photos[index]['photo_data'])
                    pil_image = Image.open(image_stream)
                    image_string = pil_image.convert('RGBA').tobytes()
                    plant_image = pygame.image.fromstring(image_string, pil_image.size, 'RGBA')
                    plant['image'] = pygame.transform.scale(plant_image, (30, 30))
                except Exception as e:
                    print(f"Error updating plant image: {e}")
                
                # Update listbox
                photo_listbox.delete(0, tk.END)
                for i, photo in enumerate(current_photos):
                    photo_listbox.insert(tk.END, f"{i+1}. {photo['photo_type']} - {len(photo['photo_data'])} bytes")
                
                global garden_modified
                garden_modified = True
        
        tk.Button(button_frame, text="Add Photo", command=add_photo).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Delete Photo", command=delete_photo).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Set as Main", command=set_as_main).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Close", command=photo_window.destroy).pack(side=tk.LEFT, padx=5)
        
        # Center window
        photo_window.update_idletasks()
        width = photo_window.winfo_width()
        height = photo_window.winfo_height()
        x = (photo_window.winfo_screenwidth() // 2) - (width // 2)
        y = (photo_window.winfo_screenheight() // 2) - (height // 2)
        photo_window.geometry(f'+{x}+{y}')
        
        photo_window.transient()
        photo_window.grab_set()
        photo_window.wait_window()
    
    create_photo_window()

# Function to get plant details
def get_plant_details(current_name="", current_species="", current_photo_data=None, current_has_sensor=False, current_sensor_id="", current_sensor_name=""):
    # На Raspberry Pi используем pygame версию
    if platform.system() == 'Linux' and 'arm' in platform.machine():
        return get_plant_details_pygame(current_name, current_species, current_photo_data, 
                                      current_has_sensor, current_sensor_id, current_sensor_name)
    
    # Оригинальная Tkinter версия для других платформ
    result = {}

    def create_window():
        nonlocal result
        root = tk.Tk()
        root.title("Plant Details")

        # Get plant types from database
        plant_types = get_plant_types()
        plant_names = [pt['name'] for pt in plant_types]

        name = tk.StringVar(value=current_name)
        species = tk.StringVar(value=current_species)
        photo_data = [current_photo_data]  # Store photo data instead of path
        has_sensor = tk.BooleanVar(value=current_has_sensor)
        sensor_id = tk.StringVar(value=current_sensor_id)
        sensor_name = tk.StringVar(value=current_sensor_name)

        def on_plant_type_change(event=None):
            selected_name = name_combo.get()
            for pt in plant_types:
                if pt['name'] == selected_name:
                    species.set(pt['latin_name'] or '')
                    break

        def browse_image():
            nonlocal photo_data
            new_image_path = filedialog.askopenfilename(
                title="Upload a plant image (optional)",
                filetypes=(("Image files", "*.png;*.jpg;*.jpeg"), ("All files", "*.*"))
            )
            if new_image_path:
                try:
                    with open(new_image_path, 'rb') as f:
                        photo_data[0] = f.read()
                    update_thumbnail(photo_data[0])
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to load image: {e}")

        def update_thumbnail(data):
            if data:
                try:
                    image = Image.open(io.BytesIO(data))
                    image.thumbnail((150, 150))
                    img = ImageTk.PhotoImage(image)
                    thumbnail_label.config(image=img)
                    thumbnail_label.image = img
                    thumbnail_label.grid(row=4, column=0, columnspan=2, pady=(10, 10))
                except Exception as e:
                    print(f"Error updating thumbnail: {e}")
                    thumbnail_label.grid_remove()
            else:
                thumbnail_label.grid_remove()
            root.update_idletasks()
            adjust_window_size()

        def adjust_window_size():
            root.update_idletasks()
            width = main_frame.winfo_reqwidth() + 40
            height = main_frame.winfo_reqheight() + 40
            root.geometry(f"{width}x{height}")

        def open_thresholds():
            """Open threshold management window"""
            plant_name = name_combo.get()
            if not plant_name:
                messagebox.showwarning("Warning", "Please select a plant type first")
                return
            
            # Get plant type ID
            plant_type_id = None
            for pt in plant_types:
                if pt['name'] == plant_name:
                    plant_type_id = pt['id']
                    break
            
            if plant_type_id:
                manage_plant_thresholds(plant_type_id, plant_name)

        def open_photo_manager():
            """Open photo manager for current plant"""
            # Find current plant in plants list
            for plant in plants:
                if plant['name'] == current_name:
                    manage_plant_photos(plant)
                    break

        def save():
            # Check for duplicate sensor names
            if has_sensor.get() and sensor_name.get():
                for plant in plants:
                    if plant is not current_plant and plant.get('sensor_name') == sensor_name.get():
                        messagebox.showerror("Error", f"Sensor Name '{sensor_name.get()}' is already used by another plant.")
                        return

            if has_sensor.get() and len(sensor_id.get()) != 22:
                messagebox.showerror("Error", "Sensor ID must be exactly 22 characters.")
                return
            
            plant_name = name_combo.get()
            if not plant_name:
                messagebox.showerror("Error", "Please select or enter a plant name.")
                return
            
            result['action'] = 'saved'
            result['name'] = plant_name
            result['species'] = species.get()
            result['photo_data'] = photo_data[0]  # Return photo data instead of path
            result['has_sensor'] = has_sensor.get()
            result['sensor_id'] = sensor_id.get()
            result['sensor_name'] = sensor_name.get()
            root.quit()

        def cancel():
            result['action'] = 'canceled'
            root.quit()

        def delete():
            if messagebox.askyesno("Delete Plant", "Are you sure you want to delete this plant?"):
                result['action'] = 'deleted'
                root.quit()

        def toggle_sensor_fields():
            if has_sensor.get():
                sensor_id_entry.config(state='normal')
                sensor_name_entry.config(state='normal')
            else:
                sensor_id_entry.config(state='disabled')
                sensor_name_entry.config(state='disabled')

        def on_closing():
            result['action'] = 'canceled'
            root.quit()

        root.protocol("WM_DELETE_WINDOW", on_closing)

        main_frame = tk.Frame(root)
        main_frame.pack(padx=20, pady=20, fill=tk.BOTH, expand=True)

        main_frame.grid_columnconfigure(1, weight=1)

        # Plant type selection with combobox
        tk.Label(main_frame, text="Plant Type:").grid(row=0, column=0, sticky='w')
        name_combo = ttk.Combobox(main_frame, textvariable=name, values=plant_names, width=30)
        name_combo.grid(row=0, column=1, sticky='ew')
        name_combo.bind('<<ComboboxSelected>>', on_plant_type_change)
        
        # Add new plant type button
        tk.Button(main_frame, text="+", command=lambda: name_combo.set("New Plant Type"), width=3).grid(row=0, column=2, padx=(5, 0))

        tk.Label(main_frame, text="Species:").grid(row=1, column=0, sticky='w', pady=(10, 0))
        tk.Entry(main_frame, textvariable=species, width=30).grid(row=1, column=1, sticky='ew', pady=(10, 0))

        # Add thresholds button
        tk.Button(main_frame, text="Set Thresholds", command=open_thresholds).grid(row=2, column=0, columnspan=2, pady=(10, 5))

        tk.Button(main_frame, text="Choose Image", command=browse_image).grid(row=3, column=0, columnspan=2, pady=(10, 5))

        # Add manage photos button if editing existing plant
        if current_name:
            tk.Button(main_frame, text="Manage Photos", command=open_photo_manager).grid(row=3, column=2, pady=(10, 5))

        thumbnail_label = tk.Label(main_frame)
        thumbnail_label.grid(row=4, column=0, columnspan=2, pady=(10, 10))
        thumbnail_label.grid_remove()

        sensor_checkbox = tk.Checkbutton(main_frame, text="Add Sensor", variable=has_sensor, command=toggle_sensor_fields)
        sensor_checkbox.grid(row=5, column=0, columnspan=2, sticky='w', pady=(10, 0))

        sensor_name_label = tk.Label(main_frame, text="Sensor Name:")
        sensor_name_label.grid(row=6, column=0, sticky='w', pady=(5, 0))
        sensor_name_entry = tk.Entry(main_frame, textvariable=sensor_name, width=30)
        sensor_name_entry.grid(row=6, column=1, sticky='ew', padx=(5, 0), pady=(5, 0))

        sensor_id_label = tk.Label(main_frame, text="Sensor ID:")
        sensor_id_label.grid(row=7, column=0, sticky='w', pady=(5, 0))
        sensor_id_entry = tk.Entry(main_frame, textvariable=sensor_id, width=22)
        sensor_id_entry.grid(row=7, column=1, sticky='ew', padx=(5, 0), pady=(5, 0))

        if has_sensor.get():
            sensor_id_entry.config(state='normal')
            sensor_name_entry.config(state='normal')
        else:
            sensor_id_entry.config(state='disabled')
            sensor_name_entry.config(state='disabled')

        button_frame = tk.Frame(main_frame)
        button_frame.grid(row=8, column=0, columnspan=2, pady=(15, 0))

        tk.Button(button_frame, text="Save", command=save).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Cancel", command=cancel).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Delete", command=delete).pack(side=tk.LEFT, padx=5)

        if current_photo_data:
            update_thumbnail(current_photo_data)
        else:
            adjust_window_size()

        root.lift()
        root.attributes('-topmost', True)
        root.after_idle(root.attributes, '-topmost', False)

        root.mainloop()
        root.destroy()

    # Run Tkinter window in a separate thread
    current_plant = None
    if current_name or current_species or current_photo_data or current_has_sensor or current_sensor_id or current_sensor_name:
        for plant in plants:
            if plant['name'] == current_name and plant['species'] == current_species:
                current_plant = plant
                break

    thread = threading.Thread(target=create_window)
    thread.start()

    # Keep Pygame responsive while Tkinter window is open
    while thread.is_alive():
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
        pygame.time.wait(100)

    thread.join()

    if result.get('action') == 'saved':
        return result['name'], result['species'], result['photo_data'], result['has_sensor'], result['sensor_id'], result['sensor_name'], 'saved'
    elif result.get('action') == 'deleted':
        return None, None, None, None, None, None, 'deleted'
    else:
        return None, None, None, None, None, None, 'canceled'

# Pygame версия get_plant_details для Raspberry Pi
def get_plant_details_pygame(current_name="", current_species="", current_photo_data=None, 
                            current_has_sensor=False, current_sensor_id="", current_sensor_name=""):
    """Pygame version of plant details dialog for Raspberry Pi"""
    # Save screen
    screen_backup = window.copy()
    
    # Get plant types from database
    plant_types = get_plant_types()
    plant_names = [pt['name'] for pt in plant_types]
    
    # State
    selected_plant_index = 0
    if current_name in plant_names:
        selected_plant_index = plant_names.index(current_name)
    
    name = current_name
    species = current_species
    has_sensor = current_has_sensor
    sensor_id = current_sensor_id
    sensor_name = current_sensor_name
    photo_data = current_photo_data
    
    # UI settings
    bg_color = (240, 240, 240)
    text_color = (0, 0, 0)
    selected_color = (100, 150, 255)
    button_color = (33, 150, 243)
    button_hover_color = (25, 118, 210)
    input_bg_color = (255, 255, 255)
    
    # Window dimensions
    dialog_width = 500
    dialog_height = 600
    dialog_x = (window_width - dialog_width) // 2
    dialog_y = (window_height - dialog_height) // 2
    
    # Fonts
    title_font = pygame.font.Font(None, 36)
    label_font = pygame.font.Font(None, 24)
    input_font = pygame.font.Font(None, 22)
    
    # Input fields
    active_field = None
    cursor_visible = True
    cursor_timer = 0
    
    # Buttons
    button_width = 100
    button_height = 40
    button_y = dialog_y + dialog_height - 60
    
    save_button = pygame.Rect(dialog_x + 50, button_y, button_width, button_height)
    cancel_button = pygame.Rect(dialog_x + dialog_width // 2 - button_width // 2, button_y, button_width, button_height)
    delete_button = pygame.Rect(dialog_x + dialog_width - 150, button_y, button_width, button_height)
    
    # Input rectangles
    species_rect = pygame.Rect(dialog_x + 120, dialog_y + 120, 350, 30)
    sensor_id_rect = pygame.Rect(dialog_x + 120, dialog_y + 220, 350, 30)
    sensor_name_rect = pygame.Rect(dialog_x + 120, dialog_y + 270, 350, 30)
    
    running = True
    result_action = 'canceled'
    
    while running:
        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                    
                elif event.key == pygame.K_TAB:
                    # Cycle through fields
                    if active_field == 'species':
                        active_field = 'sensor_id' if has_sensor else None
                    elif active_field == 'sensor_id':
                        active_field = 'sensor_name'
                    elif active_field == 'sensor_name':
                        active_field = 'species'
                    else:
                        active_field = 'species'
                        
                elif active_field:
                    if event.key == pygame.K_BACKSPACE:
                        if active_field == 'species':
                            species = species[:-1]
                        elif active_field == 'sensor_id':
                            sensor_id = sensor_id[:-1]
                        elif active_field == 'sensor_name':
                            sensor_name = sensor_name[:-1]
                    elif event.unicode:
                        if active_field == 'species':
                            species += event.unicode
                        elif active_field == 'sensor_id' and len(sensor_id) < 22:
                            sensor_id += event.unicode
                        elif active_field == 'sensor_name':
                            sensor_name += event.unicode
                            
            elif event.type == pygame.MOUSEBUTTONDOWN:
                mouse_pos = event.pos
                
                # Check buttons
                if save_button.collidepoint(mouse_pos):
                    if name:  # Must have a plant name
                        result_action = 'saved'
                        running = False
                elif cancel_button.collidepoint(mouse_pos):
                    running = False
                elif delete_button.collidepoint(mouse_pos):
                    result_action = 'deleted'
                    running = False
                    
                # Check input fields
                elif species_rect.collidepoint(mouse_pos):
                    active_field = 'species'
                elif sensor_id_rect.collidepoint(mouse_pos) and has_sensor:
                    active_field = 'sensor_id'
                elif sensor_name_rect.collidepoint(mouse_pos) and has_sensor:
                    active_field = 'sensor_name'
                else:
                    active_field = None
                    
                # Check sensor checkbox area
                sensor_checkbox_rect = pygame.Rect(dialog_x + 20, dialog_y + 180, 200, 30)
                if sensor_checkbox_rect.collidepoint(mouse_pos):
                    has_sensor = not has_sensor
                    if not has_sensor:
                        active_field = None
                        
                # Check plant type dropdown area
                plant_dropdown_rect = pygame.Rect(dialog_x + 120, dialog_y + 70, 350, 30)
                if plant_dropdown_rect.collidepoint(mouse_pos):
                    # Simple cycling through plant types
                    selected_plant_index = (selected_plant_index + 1) % len(plant_names)
                    name = plant_names[selected_plant_index]
                    # Update species
                    for pt in plant_types:
                        if pt['name'] == name:
                            species = pt['latin_name'] or ''
                            break
        
        # Update cursor blink
        cursor_timer += 1
        if cursor_timer >= 30:
            cursor_visible = not cursor_visible
            cursor_timer = 0
        
        # Draw
        window.blit(screen_backup, (0, 0))
        
        # Draw dialog
        pygame.draw.rect(window, bg_color, (dialog_x, dialog_y, dialog_width, dialog_height))
        pygame.draw.rect(window, text_color, (dialog_x, dialog_y, dialog_width, dialog_height), 2)
        
        # Title
        title_text = title_font.render("Plant Details", True, text_color)
        title_rect = title_text.get_rect(centerx=dialog_x + dialog_width // 2, y=dialog_y + 20)
        window.blit(title_text, title_rect)
        
        # Plant type
        label = label_font.render("Plant Type:", True, text_color)
        window.blit(label, (dialog_x + 20, dialog_y + 75))
        pygame.draw.rect(window, input_bg_color, (dialog_x + 120, dialog_y + 70, 350, 30))
        pygame.draw.rect(window, text_color, (dialog_x + 120, dialog_y + 70, 350, 30), 1)
        text = input_font.render(name, True, text_color)
        window.blit(text, (dialog_x + 125, dialog_y + 75))
        
        # Species
        label = label_font.render("Species:", True, text_color)
        window.blit(label, (dialog_x + 20, dialog_y + 125))
        pygame.draw.rect(window, input_bg_color, species_rect)
        pygame.draw.rect(window, selected_color if active_field == 'species' else text_color, species_rect, 2)
        text = input_font.render(species, True, text_color)
        window.blit(text, (species_rect.x + 5, species_rect.y + 5))
        if active_field == 'species' and cursor_visible:
            cursor_x = species_rect.x + 5 + text.get_width()
            pygame.draw.line(window, text_color, (cursor_x, species_rect.y + 5), (cursor_x, species_rect.y + 25), 2)
        
        # Sensor checkbox
        checkbox_rect = pygame.Rect(dialog_x + 20, dialog_y + 180, 20, 20)
        pygame.draw.rect(window, input_bg_color, checkbox_rect)
        pygame.draw.rect(window, text_color, checkbox_rect, 2)
        if has_sensor:
            pygame.draw.line(window, text_color, (checkbox_rect.x + 4, checkbox_rect.y + 10), 
                           (checkbox_rect.x + 8, checkbox_rect.y + 14), 2)
            pygame.draw.line(window, text_color, (checkbox_rect.x + 8, checkbox_rect.y + 14), 
                           (checkbox_rect.x + 16, checkbox_rect.y + 6), 2)
        label = label_font.render("Add Sensor", True, text_color)
        window.blit(label, (dialog_x + 50, dialog_y + 180))
        
        # Sensor fields (if enabled)
        if has_sensor:
            # Sensor ID
            label = label_font.render("Sensor ID:", True, text_color)
            window.blit(label, (dialog_x + 20, dialog_y + 225))
            pygame.draw.rect(window, input_bg_color, sensor_id_rect)
            pygame.draw.rect(window, selected_color if active_field == 'sensor_id' else text_color, sensor_id_rect, 2)
            text = input_font.render(sensor_id, True, text_color)
            window.blit(text, (sensor_id_rect.x + 5, sensor_id_rect.y + 5))
            if active_field == 'sensor_id' and cursor_visible:
                cursor_x = sensor_id_rect.x + 5 + text.get_width()
                pygame.draw.line(window, text_color, (cursor_x, sensor_id_rect.y + 5), (cursor_x, sensor_id_rect.y + 25), 2)
            
            # Sensor Name
            label = label_font.render("Sensor Name:", True, text_color)
            window.blit(label, (dialog_x + 20, dialog_y + 275))
            pygame.draw.rect(window, input_bg_color, sensor_name_rect)
            pygame.draw.rect(window, selected_color if active_field == 'sensor_name' else text_color, sensor_name_rect, 2)
            text = input_font.render(sensor_name, True, text_color)
            window.blit(text, (sensor_name_rect.x + 5, sensor_name_rect.y + 5))
            if active_field == 'sensor_name' and cursor_visible:
                cursor_x = sensor_name_rect.x + 5 + text.get_width()
                pygame.draw.line(window, text_color, (cursor_x, sensor_name_rect.y + 5), (cursor_x, sensor_name_rect.y + 25), 2)
        
        # Buttons
        mouse_pos = pygame.mouse.get_pos()
        
        # Save button
        save_color = button_hover_color if save_button.collidepoint(mouse_pos) else button_color
        pygame.draw.rect(window, save_color, save_button, border_radius=5)
        text = label_font.render("Save", True, (255, 255, 255))
        text_rect = text.get_rect(center=save_button.center)
        window.blit(text, text_rect)
        
        # Cancel button
        cancel_color = button_hover_color if cancel_button.collidepoint(mouse_pos) else button_color
        pygame.draw.rect(window, cancel_color, cancel_button, border_radius=5)
        text = label_font.render("Cancel", True, (255, 255, 255))
        text_rect = text.get_rect(center=cancel_button.center)
        window.blit(text, text_rect)
        
        # Delete button
        delete_color = button_hover_color if delete_button.collidepoint(mouse_pos) else button_color
        pygame.draw.rect(window, delete_color, delete_button, border_radius=5)
        text = label_font.render("Delete", True, (255, 255, 255))
        text_rect = text.get_rect(center=delete_button.center)
        window.blit(text, text_rect)
        
        pygame.display.flip()
        pygame.time.Clock().tick(30)
    
    # Restore screen
    window.blit(screen_backup, (0, 0))
    pygame.display.flip()
    
    if result_action == 'saved':
        return name, species, photo_data, has_sensor, sensor_id, sensor_name, 'saved'
    elif result_action == 'deleted':
        return None, None, None, None, None, None, 'deleted'
    else:
        return None, None, None, None, None, None, 'canceled'

# Function to draw buttons
def draw_button(button_rect, text, enabled):
    mouse_pos = pygame.mouse.get_pos()
    if button_rect.collidepoint(mouse_pos) and enabled:
        color = button_hover_color
    else:
        color = button_color if enabled else dimmed_button_color

    pygame.draw.rect(window, color, button_rect, border_radius=5)
    font = pygame.font.Font(None, 28)
    text_surface = font.render(text, True, text_color if enabled else (255, 255, 255))
    text_rect = text_surface.get_rect(center=button_rect.center)
    window.blit(text_surface, text_rect)

# Function to update buttons
def update_buttons():
    draw_button(load_garden_button, "Load Garden", True)
    draw_button(create_garden_button, "Create Garden", True)
    draw_button(add_plant_button, "Add Plant", garden_loaded_or_created and not is_creating_garden)
    draw_button(add_image_button, "Add Image", garden_loaded_or_created and not is_creating_garden)
    draw_button(undo_button, "Undo", len(undo_stack) > 0)
    draw_button(redo_button, "Redo", len(redo_stack) > 0)
    draw_button(save_button, "Save", garden_loaded_or_created)
    draw_button(exit_button, "Exit", True)

# Function to draw garden boundary
def draw_garden_boundary():
    if len(garden_boundary) > 1:
        pygame.draw.lines(window, garden_border_color, is_creating_garden == False, garden_boundary, 3)

# Function to draw starting point
def draw_start_point():
    if garden_boundary:
        pygame.draw.circle(window, dot_color, garden_boundary[0], 3)

# Function to draw grid
def draw_grid():
    cell_size = 20
    if garden_loaded_or_created and not is_creating_garden and len(garden_boundary) > 2:
        garden_polygon = Polygon(garden_boundary)
        for x in range(0, garden_area_size[0] + cell_size, cell_size):
            for y in range(0, garden_area_size[1] + cell_size, cell_size):
                point = (x, y)
                if garden_polygon.contains(Point(point)):
                    pygame.draw.line(window, grid_color, (x, y), (x, y + cell_size))
                    pygame.draw.line(window, grid_color, (x, y), (x + cell_size, y))
    else:
        for x in range(0, garden_area_size[0], cell_size):
            pygame.draw.line(window, grid_color, (x, 0), (x, garden_area_size[1]))
        for y in range(0, garden_area_size[1], cell_size):
            pygame.draw.line(window, grid_color, (0, y), (garden_area_size[0], y))

# Snap to nearest grid point
def snap_to_grid(pos):
    grid_size = 20
    grid_x = round(pos[0] / grid_size) * grid_size
    grid_y = round(pos[1] / grid_size) * grid_size
    return (grid_x, grid_y)

# Check if point is inside the garden boundary
def point_in_garden(point, boundary):
    if len(boundary) < 3:
        return False
    polygon = Polygon(boundary)
    return polygon.contains(Point(point))

# Function to add a plant
def add_plant(mouse_pos):
    global garden_modified
    if not point_in_garden(mouse_pos, garden_boundary):
        # На Raspberry Pi используем pygame для сообщений
        if platform.system() == 'Linux' and 'arm' in platform.machine():
            show_message_pygame("Warning", "Plants should be inside the garden!")
        else:
            root = tk.Tk()
            root.withdraw()
            messagebox.showwarning("Warning", "Plants should be inside the garden!")
            root.destroy()
        return

    name, species, photo_data, has_sensor, sensor_id, sensor_name, action = get_plant_details()
    if action == 'saved' and name:
        snapped_pos = snap_to_grid(mouse_pos)
        
        # Process photo data
        plant_image = default_plant_image
        if photo_data:
            try:
                # Load image from blob
                image_stream = io.BytesIO(photo_data)
                pil_image = Image.open(image_stream)
                
                # Convert PIL image to pygame surface
                image_string = pil_image.convert('RGBA').tobytes()
                plant_image = pygame.image.fromstring(image_string, pil_image.size, 'RGBA')
                plant_image = pygame.transform.scale(plant_image, (30, 30))
            except Exception as e:
                print(f"Error loading plant photo: {e}")
                plant_image = default_plant_image
        
        plant = {
            'position': snapped_pos,
            'image': plant_image,
            'photo_data': photo_data,  # Store photo data instead of path
            'name': name,
            'species': species,
            'has_sensor': has_sensor,
            'sensor_id': sensor_id if has_sensor else None,
            'sensor_name': sensor_name if has_sensor else None
        }
        plants.append(plant)
        add_undo_action('add_plant', plant)
        garden_modified = True

# Простое сообщение для Raspberry Pi
def show_message_pygame(title, message):
   """Show simple message dialog using pygame"""
   screen_backup = window.copy()
   
   # Dialog settings
   dialog_width = 400
   dialog_height = 200
   dialog_x = (window_width - dialog_width) // 2
   dialog_y = (window_height - dialog_height) // 2
   
   bg_color = (240, 240, 240)
   text_color = (0, 0, 0)
   button_color = (33, 150, 243)
   
   # Fonts
   title_font = pygame.font.Font(None, 28)
   msg_font = pygame.font.Font(None, 22)
   
   running = True
   clock = pygame.time.Clock()
   
   while running:
       for event in pygame.event.get():
           if event.type == pygame.KEYDOWN:
               if event.key == pygame.K_RETURN or event.key == pygame.K_ESCAPE:
                   running = False
           elif event.type == pygame.MOUSEBUTTONDOWN:
               # Check if clicked on OK button
               ok_button = pygame.Rect(dialog_x + dialog_width // 2 - 40, dialog_y + dialog_height - 50, 80, 30)
               if ok_button.collidepoint(event.pos):
                   running = False
       
       # Draw
       window.blit(screen_backup, (0, 0))
       
       # Dialog
       pygame.draw.rect(window, bg_color, (dialog_x, dialog_y, dialog_width, dialog_height))
       pygame.draw.rect(window, text_color, (dialog_x, dialog_y, dialog_width, dialog_height), 2)
       
       # Title
       title_text = title_font.render(title, True, text_color)
       title_rect = title_text.get_rect(centerx=dialog_x + dialog_width // 2, y=dialog_y + 20)
       window.blit(title_text, title_rect)
       
       # Message
       msg_text = msg_font.render(message, True, text_color)
       msg_rect = msg_text.get_rect(centerx=dialog_x + dialog_width // 2, y=dialog_y + 80)
       window.blit(msg_text, msg_rect)
       
       # OK button
       ok_button = pygame.Rect(dialog_x + dialog_width // 2 - 40, dialog_y + dialog_height - 50, 80, 30)
       pygame.draw.rect(window, button_color, ok_button, border_radius=5)
       ok_text = msg_font.render("OK", True, (255, 255, 255))
       ok_rect = ok_text.get_rect(center=ok_button.center)
       window.blit(ok_text, ok_rect)
       
       pygame.display.flip()
       clock.tick(30)
   
   window.blit(screen_backup, (0, 0))
   pygame.display.flip()

# Function to edit a plant
def edit_plant(plant):
   global garden_modified
   old_data = plant.copy()
   index = plants.index(plant)
   name, species, photo_data, has_sensor, sensor_id, sensor_name, action = get_plant_details(
       current_name=plant['name'],
       current_species=plant.get('species', ''),
       current_photo_data=plant.get('photo_data'),
       current_has_sensor=plant['has_sensor'],
       current_sensor_id=plant.get('sensor_id', ""),
       current_sensor_name=plant.get('sensor_name', "")
   )
   if action == 'saved' and name:
       plant['name'] = name
       plant['species'] = species
       if photo_data:
           try:
               # Load image from blob
               image_stream = io.BytesIO(photo_data)
               pil_image = Image.open(image_stream)
               
               # Convert PIL image to pygame surface
               image_string = pil_image.convert('RGBA').tobytes()
               plant_image = pygame.image.fromstring(image_string, pil_image.size, 'RGBA')
               plant_image = pygame.transform.scale(plant_image, (30, 30))
               
               plant['image'] = plant_image
               plant['photo_data'] = photo_data
           except Exception as e:
               print(f"Error loading plant photo: {e}")
       plant['has_sensor'] = has_sensor
       plant['sensor_id'] = sensor_id if has_sensor else None
       plant['sensor_name'] = sensor_name if has_sensor else None
       add_undo_action('edit_plant', {
           'plant': plant,
           'old_data': old_data
       })
       garden_modified = True
   elif action == 'deleted':
       plants.remove(plant)
       add_undo_action('delete_plant', {
           'plant': plant,
           'index': index
       })
       garden_modified = True

# Function to add an image
def add_image(mouse_pos):
   global garden_modified
   if platform.system() == 'Linux' and 'arm' in platform.machine():
       # На Raspberry Pi пока пропускаем добавление изображений
       show_message_pygame("Info", "Image addition not available on Pi")
       return
   
   root = tk.Tk()
   root.withdraw()
   image_file = filedialog.askopenfilename(
       title="Select an image file",
       filetypes=(("Image files", "*.png;*.jpg;*.jpeg"), ("All files", "*.*"))
   )
   root.destroy()
   if image_file:
       try:
           original_image = pygame.image.load(image_file).convert_alpha()
           image = pygame.transform.scale(original_image, (100, 100))
           image_rect = image.get_rect()
           image_rect.topleft = mouse_pos
           image_data = {
               'image': image,
               'original_image': original_image,
               'image_path': image_file,
               'rect': image_rect
           }
           images.append(image_data)
           add_undo_action('add_image', image_data)
           garden_modified = True
       except pygame.error:
           print(f"Error loading image: {image_file}")

# Undo/Redo functions
def add_undo_action(action_type, data):
   undo_stack.append((action_type, data))
   redo_stack.clear()
   global garden_modified
   garden_modified = True

def undo():
   global is_creating_garden, garden_modified
   if len(undo_stack) > 0:
       action_type, data = undo_stack.pop()
       if action_type == 'add_plant':
           plants.remove(data)
       elif action_type == 'add_image':
           images.remove(data)
       elif action_type == 'add_line':
           garden_boundary.pop()
       elif action_type == 'move_plant':
           data['plant']['position'] = data['old_position']
       elif action_type == 'move_image':
           data['image']['rect'].topleft = data['old_position']
       elif action_type == 'resize_image':
           data['image']['image'] = pygame.transform.scale(data['image']['original_image'], data['old_size'])
           data['image']['rect'].size = data['old_size']
       elif action_type == 'edit_plant':
           plant = data['plant']
           plant.update(data['old_data'])
       elif action_type == 'delete_plant':
           plants.insert(data['index'], data['plant'])
       elif action_type == 'delete_image':
           images.insert(data['index'], data['image'])
       redo_stack.append((action_type, data))
       garden_modified = True
       if len(garden_boundary) == 0:
           is_creating_garden = False

def redo():
   global garden_modified
   if len(redo_stack) > 0:
       action_type, data = redo_stack.pop()
       if action_type == 'add_plant':
           plants.append(data)
       elif action_type == 'add_image':
           images.append(data)
       elif action_type == 'add_line':
           garden_boundary.append(data)
       elif action_type == 'move_plant':
           data['plant']['position'] = data['new_position']
       elif action_type == 'move_image':
           data['image']['rect'].topleft = data['new_position']
       elif action_type == 'resize_image':
           data['image']['image'] = pygame.transform.scale(data['image']['original_image'], data['new_size'])
           data['image']['rect'].size = data['new_size']
       elif action_type == 'edit_plant':
           pass
       elif action_type == 'delete_plant':
           plants.remove(data['plant'])
       elif action_type == 'delete_image':
           images.remove(data['image'])
       undo_stack.append((action_type, data))
       garden_modified = True

# Function to save the garden
def save_garden():
   """Save garden to database or export to JSON"""
   if platform.system() == 'Linux' and 'arm' in platform.machine():
       # На Raspberry Pi сохраняем только в базу данных
       try:
           save_garden_to_db()
       except Exception as e:
           print(f"Error during save: {e}")
           show_message_pygame("Error", "Failed to save garden")
       return
   
   # На других платформах используем оригинальную версию
   root = tk.Tk()
   root.withdraw()
   
   choice = messagebox.askyesnocancel(
       "Save Garden",
       "Save to database (Yes) or export to JSON file (No)?",
       icon='question'
   )
   
   if choice is True:
       # Save to database
       try:
           save_garden_to_db()
       except Exception as e:
           print(f"Error during save: {e}")
   elif choice is False:
       # Export to JSON (note: photos won't be included in JSON export)
       save_file = filedialog.asksaveasfilename(
           defaultextension=".json",
           filetypes=(("JSON files", "*.json"),)
       )
       if save_file:
           data = {
               "boundary": garden_boundary,
               "plants": [
                   {
                       "position": plant['position'],
                       "name": plant['name'],
                       "species": plant.get('species', ''),
                       "has_sensor": plant['has_sensor'],
                       "sensor_id": plant['sensor_id'] if plant['has_sensor'] else None,
                       "sensor_name": plant['sensor_name'] if plant['has_sensor'] else None,
                       "has_photo": plant.get('photo_data') is not None  # Just indicate if photo exists
                   } for plant in plants
               ],
               "images": [
                   {
                       "position": [image_data['rect'].x, image_data['rect'].y],
                       "size": [image_data['rect'].width, image_data['rect'].height],
                       "image_path": os.path.relpath(image_data.get('image_path', ''), start=os.getcwd()).replace('\\', '/')
                   } for image_data in images
               ]
           }
           with open(save_file, 'w') as f:
               json.dump(data, f)
           print(f"Garden exported to {save_file}")
           messagebox.showinfo("Note", "Garden exported to JSON. Note that plant photos are stored in the database and not included in the JSON export.")
           global garden_modified
           garden_modified = False
   
   root.destroy()

# Function to create garden boundary
def create_garden(pos):
   global is_creating_garden, garden_loaded_or_created, garden_modified
   snapped_pos = snap_to_grid(pos)

   # If the right mouse button is clicked, exit drawing mode
   if pygame.mouse.get_pressed()[2]:
       if len(garden_boundary) > 1 and garden_boundary[-1] != garden_boundary[0]:
           garden_boundary.append(garden_boundary[0])
       is_creating_garden = False
       garden_loaded_or_created = True
       garden_modified = True
       return

   # Add segment only if the left mouse button is clicked
   if pygame.mouse.get_pressed()[0] and is_creating_garden and (len(garden_boundary) == 0 or garden_boundary[-1] != snapped_pos):
       garden_boundary.append(snapped_pos)
       add_undo_action('add_line', snapped_pos)

# Function to exit the app with save prompt
def exit_app():
   if garden_modified:
       if platform.system() == 'Linux' and 'arm' in platform.machine():
           # На Raspberry Pi используем pygame диалог
           save_before_exit = show_yes_no_pygame("Exit", "Garden has unsaved changes. Save before exiting?")
           if save_before_exit:
               save_garden()
       else:
           root = tk.Tk()
           root.withdraw()
           if messagebox.askyesno("Exit", "Garden has unsaved changes. Save before exiting?"):
               save_garden()
           root.destroy()
   pygame.quit()
   sys.exit()

def show_yes_no_pygame(title, message):
   """Show Yes/No dialog using pygame"""
   screen_backup = window.copy()
   
   # Dialog settings
   dialog_width = 400
   dialog_height = 200
   dialog_x = (window_width - dialog_width) // 2
   dialog_y = (window_height - dialog_height) // 2
   
   bg_color = (240, 240, 240)
   text_color = (0, 0, 0)
   button_color = (33, 150, 243)
   button_hover_color = (25, 118, 210)
   
   # Fonts
   title_font = pygame.font.Font(None, 28)
   msg_font = pygame.font.Font(None, 22)
   
   # Buttons
   button_width = 80
   button_height = 30
   yes_button = pygame.Rect(dialog_x + dialog_width // 2 - button_width - 20, dialog_y + dialog_height - 50, button_width, button_height)
   no_button = pygame.Rect(dialog_x + dialog_width // 2 + 20, dialog_y + dialog_height - 50, button_width, button_height)
   
   running = True
   result = False
   clock = pygame.time.Clock()
   
   while running:
       mouse_pos = pygame.mouse.get_pos()
       
       for event in pygame.event.get():
           if event.type == pygame.KEYDOWN:
               if event.key == pygame.K_y:
                   result = True
                   running = False
               elif event.key == pygame.K_n or event.key == pygame.K_ESCAPE:
                   result = False
                   running = False
           elif event.type == pygame.MOUSEBUTTONDOWN:
               if yes_button.collidepoint(event.pos):
                   result = True
                   running = False
               elif no_button.collidepoint(event.pos):
                   result = False
                   running = False
       
       # Draw
       window.blit(screen_backup, (0, 0))
       
       # Dialog
       pygame.draw.rect(window, bg_color, (dialog_x, dialog_y, dialog_width, dialog_height))
       pygame.draw.rect(window, text_color, (dialog_x, dialog_y, dialog_width, dialog_height), 2)
       
       # Title
       title_text = title_font.render(title, True, text_color)
       title_rect = title_text.get_rect(centerx=dialog_x + dialog_width // 2, y=dialog_y + 20)
       window.blit(title_text, title_rect)
       
       # Message (handle long messages)
       words = message.split()
       lines = []
       current_line = []
       for word in words:
           test_line = ' '.join(current_line + [word])
           if msg_font.size(test_line)[0] < dialog_width - 40:
               current_line.append(word)
           else:
               if current_line:
                   lines.append(' '.join(current_line))
               current_line = [word]
       if current_line:
           lines.append(' '.join(current_line))
       
       y_offset = 60
       for line in lines:
           msg_text = msg_font.render(line, True, text_color)
           msg_rect = msg_text.get_rect(centerx=dialog_x + dialog_width // 2, y=dialog_y + y_offset)
           window.blit(msg_text, msg_rect)
           y_offset += 25
       
       # Yes button
       yes_color = button_hover_color if yes_button.collidepoint(mouse_pos) else button_color
       pygame.draw.rect(window, yes_color, yes_button, border_radius=5)
       yes_text = msg_font.render("Yes", True, (255, 255, 255))
       yes_rect = yes_text.get_rect(center=yes_button.center)
       window.blit(yes_text, yes_rect)
       
       # No button
       no_color = button_hover_color if no_button.collidepoint(mouse_pos) else button_color
       pygame.draw.rect(window, no_color, no_button, border_radius=5)
       no_text = msg_font.render("No", True, (255, 255, 255))
       no_rect = no_text.get_rect(center=no_button.center)
       window.blit(no_text, no_rect)
       
       pygame.display.flip()
       clock.tick(30)
   
   window.blit(screen_backup, (0, 0))
   pygame.display.flip()
   
   return result

def browse_garden_pygame():
   """Alternative garden selection using pygame (for Raspberry Pi compatibility)"""
   # Save current screen state
   screen_backup = window.copy()
   
   # Get gardens from database
   conn = get_db_connection()
   cursor = conn.cursor()
   cursor.execute('''
       SELECT id, name, created_at, updated_at 
       FROM garden_layouts 
       WHERE is_active = 1 
       ORDER BY updated_at DESC
   ''')
   layouts = cursor.fetchall()
   conn.close()
   
   # UI settings
   bg_color = (240, 240, 240)
   text_color = (0, 0, 0)
   selected_color = (100, 150, 255)
   button_color = (33, 150, 243)
   button_hover_color = (25, 118, 210)
   
   # Dimensions
   menu_width = 600
   menu_height = 400
   menu_x = (window_width - menu_width) // 2
   menu_y = (window_height - menu_height) // 2
   
   # Fonts
   title_font = pygame.font.Font(None, 36)
   item_font = pygame.font.Font(None, 24)
   
   # State
   selected_index = 0
   scroll_offset = 0
   items_per_page = 10
   
   running = True
   result = None
   
   # Add "Load from JSON" option at the beginning of the list
   display_items = [("Load from JSON file...", None)] + [(f"{layout['name']} (Updated: {(layout['updated_at'] or layout['created_at'])[:10]})", layout['id']) for layout in layouts]
   
   while running:
       # Draw background
       window.blit(screen_backup, (0, 0))
       
       # Draw selection window
       pygame.draw.rect(window, bg_color, (menu_x, menu_y, menu_width, menu_height))
       pygame.draw.rect(window, text_color, (menu_x, menu_y, menu_width, menu_height), 2)
       
       # Title
       title_text = title_font.render("Select Garden", True, text_color)
       title_rect = title_text.get_rect(centerx=menu_x + menu_width // 2, y=menu_y + 20)
       window.blit(title_text, title_rect)
       
       # Garden list
       list_y = menu_y + 80
       visible_items = display_items[scroll_offset:scroll_offset + items_per_page]
       
       for i, (text, _) in enumerate(visible_items):
           actual_index = scroll_offset + i
           y_pos = list_y + i * 30
           
           # Highlight selected item
           if actual_index == selected_index:
               pygame.draw.rect(window, selected_color, 
                              (menu_x + 20, y_pos - 5, menu_width - 40, 30))
           
           # Item text
           item_text = item_font.render(text, True, text_color)
           window.blit(item_text, (menu_x + 30, y_pos))
       
       # Buttons
       button_y = menu_y + menu_height - 60
       button_width = 120
       button_height = 40
       
       # Load button
       load_button = pygame.Rect(menu_x + 50, button_y, button_width, button_height)
       mouse_pos = pygame.mouse.get_pos()
       load_color = button_hover_color if load_button.collidepoint(mouse_pos) else button_color
       pygame.draw.rect(window, load_color, load_button, border_radius=5)
       load_text = item_font.render("Load", True, (255, 255, 255))
       load_text_rect = load_text.get_rect(center=load_button.center)
       window.blit(load_text, load_text_rect)
       
       # Cancel button
       cancel_button = pygame.Rect(menu_x + menu_width - 170, button_y, button_width, button_height)
       cancel_color = button_hover_color if cancel_button.collidepoint(mouse_pos) else button_color
       pygame.draw.rect(window, cancel_color, cancel_button, border_radius=5)
       cancel_text = item_font.render("Cancel", True, (255, 255, 255))
       cancel_text_rect = cancel_text.get_rect(center=cancel_button.center)
       window.blit(cancel_text, cancel_text_rect)
       
       # Instructions
       help_text = item_font.render("Use ↑↓ arrows to select, Enter to load, Esc to cancel", 
                                  True, (100, 100, 100))
       help_rect = help_text.get_rect(centerx=menu_x + menu_width // 2, 
                                     y=menu_y + menu_height - 100)
       window.blit(help_text, help_rect)
       
       pygame.display.flip()
       
       # Event handling
       for event in pygame.event.get():
           if event.type == pygame.QUIT:
               running = False
               
           elif event.type == pygame.KEYDOWN:
               if event.key == pygame.K_ESCAPE:
                   running = False
                   
               elif event.key == pygame.K_UP:
                   if selected_index > 0:
                       selected_index -= 1
                       if selected_index < scroll_offset:
                           scroll_offset = selected_index
                           
               elif event.key == pygame.K_DOWN:
                   if selected_index < len(display_items) - 1:
                       selected_index += 1
                       if selected_index >= scroll_offset + items_per_page:
                           scroll_offset = selected_index - items_per_page + 1
                           
               elif event.key == pygame.K_RETURN:
                   if selected_index == 0:
                       # Load from JSON - на Raspberry Pi пока пропускаем
                       show_message_pygame("Info", "JSON loading not available on Pi")
                   else:
                       result = display_items[selected_index][1]
                       running = False
                   
           elif event.type == pygame.MOUSEBUTTONDOWN:
               if event.button == 1:  # Left click
                   if load_button.collidepoint(mouse_pos):
                       if selected_index == 0:
                           # Load from JSON
                           show_message_pygame("Info", "JSON loading not available on Pi")
                       else:
                           result = display_items[selected_index][1]
                           running = False
                   elif cancel_button.collidepoint(mouse_pos):
                       running = False
                   else:
                       # Check click on list item
                       list_area = pygame.Rect(menu_x + 20, list_y - 5, 
                                             menu_width - 40, items_per_page * 30)
                       if list_area.collidepoint(mouse_pos):
                           clicked_index = (mouse_pos[1] - list_y + 5) // 30
                           if 0 <= clicked_index < len(visible_items):
                               selected_index = scroll_offset + clicked_index
   
   # Restore screen
   window.blit(screen_backup, (0, 0))
   pygame.display.flip()
   
   return result

def browse_garden():
   """Browse and select garden from database"""
   # For Raspberry Pi always use pygame version
   if platform.system() == 'Linux' and 'arm' in platform.machine():
       return browse_garden_pygame()
   
   # For other platforms use Tkinter
   selected_id = [None]
   
   def run_tkinter():
       root = tk.Tk()
       root.title("Select Garden")
       
       # Get all gardens from database
       conn = get_db_connection()
       cursor = conn.cursor()
       cursor.execute('''
           SELECT id, name, created_at, updated_at 
           FROM garden_layouts 
           WHERE is_active = 1 
           ORDER BY updated_at DESC
       ''')
       layouts = cursor.fetchall()
       conn.close()
       
       window_closed = [False]
       
       def on_select():
           if window_closed[0]:
               return
           selection = listbox.curselection()
           if selection:
               selected_id[0] = layout_ids[selection[0]]
               window_closed[0] = True
               root.quit()
       
       def on_load_json():
           if window_closed[0]:
               return
           file_path = filedialog.askopenfilename(
               title="Select a garden plan file",
               filetypes=(("JSON files", "*.json"), ("All files", "*.*"))
           )
           if file_path:
               selected_id[0] = 'json:' + file_path
               window_closed[0] = True
               root.quit()
       
       def on_cancel():
           if window_closed[0]:
               return
           window_closed[0] = True
           root.quit()
       
       def on_window_close():
           if window_closed[0]:
               return
           window_closed[0] = True
           root.quit()
       
       root.protocol("WM_DELETE_WINDOW", on_window_close)
       
       # Create GUI
       main_frame = tk.Frame(root, padx=20, pady=20)
       main_frame.pack(fill=tk.BOTH, expand=True)
       
       tk.Label(main_frame, text="Select a garden from database:", font=("Arial", 12)).pack(pady=(0, 10))
       
       # Listbox with scrollbar
       list_frame = tk.Frame(main_frame)
       list_frame.pack(fill=tk.BOTH, expand=True)
       
       scrollbar = tk.Scrollbar(list_frame)
       scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
       
       listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, height=10, width=50)
       listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
       scrollbar.config(command=listbox.yview)
       
       # Populate listbox
       layout_ids = []
       for layout in layouts:
           updated = layout['updated_at'] or layout['created_at']
           listbox.insert(tk.END, f"{layout['name']} (Updated: {updated})")
           layout_ids.append(layout['id'])
       
       # Buttons
       button_frame = tk.Frame(main_frame)
       button_frame.pack(pady=(10, 0))
       
       tk.Button(button_frame, text="Load Selected", command=on_select).pack(side=tk.LEFT, padx=5)
       tk.Button(button_frame, text="Load from JSON", command=on_load_json).pack(side=tk.LEFT, padx=5)
       tk.Button(button_frame, text="Cancel", command=on_cancel).pack(side=tk.LEFT, padx=5)
       
       # Double-click to select
       listbox.bind('<Double-Button-1>', lambda e: on_select())
       
       # Center window
       root.update_idletasks()
       width = root.winfo_width()
       height = root.winfo_height()
       x = (root.winfo_screenwidth() // 2) - (width // 2)
       y = (root.winfo_screenheight() // 2) - (height // 2)
       root.geometry(f'{width}x{height}+{x}+{y}')
       
       root.focus_force()
       root.lift()
       root.attributes('-topmost', True)
       root.after_idle(root.attributes, '-topmost', False)
       
       root.mainloop()
       
       try:
           root.destroy()
       except:
           pass
   
   run_tkinter()
   return selected_id[0]

# Function to check for double click
def is_double_click(pos, current_time):
   global last_click_time, last_click_pos
   
   if last_click_pos is None:
       return False
   
   # Check if click is close enough in time and position
   time_diff = current_time - last_click_time
   pos_diff = ((pos[0] - last_click_pos[0]) ** 2 + (pos[1] - last_click_pos[1]) ** 2) ** 0.5
   
   return time_diff < double_click_threshold and pos_diff < 10

# Initialize font for rendering plant names
pygame.font.init()
font = pygame.font.Font(None, 20)

# Main program loop
running = True
while running:
   for event in pygame.event.get():
       if event.type == pygame.QUIT:
           exit_app()
       
       # Handle window resize
       elif event.type == pygame.VIDEORESIZE:
           window_width = event.w
           window_height = event.h
           window_size = (window_width, window_height)
           window = pygame.display.set_mode(window_size, pygame.RESIZABLE)
           
           # Recalculate button area
           garden_area_size = (window_width, window_height - button_area_height)
           button_area_size = (window_width, button_area_height)
           buttons_area_y_start = garden_area_size[1] + margin_y
           
           # Recalculate button positions
           buttons_total_width = button_width * 4 + button_spacing_x * 3
           button_area_x_start = (window_width - buttons_total_width) // 2
           
           # Update button rectangles
           load_garden_button.x = button_area_x_start
           load_garden_button.y = buttons_area_y_start
           
           create_garden_button.x = button_area_x_start
           create_garden_button.y = buttons_area_y_start + button_height + button_spacing_y
           
           add_plant_button.x = button_area_x_start + button_width + button_spacing_x
           add_plant_button.y = buttons_area_y_start
           
           add_image_button.x = button_area_x_start + button_width + button_spacing_x
           add_image_button.y = buttons_area_y_start + button_height + button_spacing_y
           
           undo_button.x = button_area_x_start + (button_width + button_spacing_x) * 2
           undo_button.y = buttons_area_y_start
           
           redo_button.x = button_area_x_start + (button_width + button_spacing_x) * 2
           redo_button.y = buttons_area_y_start + button_height + button_spacing_y
           
           save_button.x = button_area_x_start + (button_width + button_spacing_x) * 3
           save_button.y = buttons_area_y_start
           
           exit_button.x = button_area_x_start + (button_width + button_spacing_x) * 3
           exit_button.y = buttons_area_y_start + button_height + button_spacing_y

       elif event.type == pygame.MOUSEBUTTONDOWN:
           mouse_pos = event.pos
           current_time = pygame.time.get_ticks()

           if event.button == 3:  # Right mouse button
               right_click_start_pos = mouse_pos
               for image_data in reversed(images):
                   if image_data['rect'].collidepoint(mouse_pos):
                       selected_image = image_data
                       break
               else:
                   selected_image = None

               # Check if right-click is on any plant
               for plant in reversed(plants):
                   plant_rect = plant['image'].get_rect(topleft=plant['position'])
                   if plant_rect.collidepoint(mouse_pos):
                       print(f"Editing plant: {plant['name']}")
                       edit_plant(plant)
                       break

           elif event.button == 1:  # Left mouse button
               # Check for double-click on plants
               if is_double_click(mouse_pos, current_time):
                   for plant in reversed(plants):
                       plant_rect = plant['image'].get_rect(topleft=plant['position'])
                       if plant_rect.collidepoint(mouse_pos):
                           print(f"Double-click editing plant: {plant['name']}")
                           edit_plant(plant)
                           break
                   last_click_time = 0
                   last_click_pos = None
               else:
                   # Update last click info
                   last_click_time = current_time
                   last_click_pos = mouse_pos
                   
                   # Logic for Load Garden button
                   if load_garden_button.collidepoint(mouse_pos):
                       # Always use browse_garden(), it will determine which version to use
                       result = browse_garden()
                       
                       if result:
                           if isinstance(result, str) and result.startswith('json:'):
                               # Load from JSON file
                               json_file = result[5:]
                               with open(json_file, 'r') as f:
                                   data = json.load(f)
                                   garden_boundary = data['boundary']
                                   plants = []
                                   for p in data.get('plants', []):
                                       # Note: JSON doesn't contain photo data
                                       plant_image = default_plant_image

                                       plant = {
                                           'position': snap_to_grid(p['position']),
                                           'image': plant_image,
                                           'photo_data': None,  # No photo data in JSON
                                           'name': p.get('name', 'Unnamed Plant'),
                                           'species': p.get('species', ''),
                                           'has_sensor': p.get('has_sensor', False),
                                           'sensor_id': p.get('sensor_id', None),
                                           'sensor_name': p.get('sensor_name', None)
                                       }
                                       plants.append(plant)
                                   
                                   images = []
                                   for img_data in data.get('images', []):
                                       image_path = img_data.get('image_path', '')
                                       image_path = os.path.normpath(os.path.join(os.getcwd(), image_path))
                                       if image_path and os.path.exists(image_path):
                                           try:
                                               original_image = pygame.image.load(image_path).convert_alpha()
                                               size = img_data.get('size', [100, 100])
                                               image = pygame.transform.scale(original_image, size)
                                               image_rect = image.get_rect()
                                               position = img_data.get('position', [0, 0])
                                               image_rect.topleft = position
                                               image_data = {
                                                   'image': image,
                                                   'original_image': original_image,
                                                   'image_path': image_path,
                                                   'rect': image_rect
                                               }
                                               images.append(image_data)
                                           except pygame.error:
                                               print(f"Error loading image: {image_path}")
                                       else:
                                           print(f"Image file not found: {image_path}")
                               garden_loaded_or_created = True
                               is_creating_garden = False
                               garden_modified = False
                               current_layout_id = None
                               print(f"Loaded garden from {json_file}")
                           else:
                               # Load from database
                               if load_garden_from_db(result):
                                   garden_modified = False
                                   print(f"Loaded garden from database (ID: {result})")

                   # Logic for Create Garden button
                   elif create_garden_button.collidepoint(mouse_pos):
                       print("Entering garden creation mode...")
                       is_creating_garden = True
                       garden_boundary = []
                       is_adding_plant = False
                       garden_loaded_or_created = False
                       garden_modified = True

                   # Logic for Add Plant button
                   elif add_plant_button.collidepoint(mouse_pos) and garden_loaded_or_created:
                       print("Entering plant adding mode...")
                       is_adding_plant = True
                       is_creating_garden = False

                   # Logic for Add Image button
                   elif add_image_button.collidepoint(mouse_pos) and garden_loaded_or_created:
                       print("Entering image adding mode...")
                       is_adding_image = True
                       is_creating_garden = False

                   # Logic for Undo button
                   elif undo_button.collidepoint(mouse_pos):
                       undo()

                   # Logic for Redo button
                   elif redo_button.collidepoint(mouse_pos):
                       redo()

                   # Logic for Save button
                   elif save_button.collidepoint(mouse_pos) and garden_loaded_or_created:
                       save_garden()

                   # Logic for Exit button
                   elif exit_button.collidepoint(mouse_pos):
                       exit_app()

                   # Logic for creating garden boundary
                   elif is_creating_garden and mouse_pos[1] < garden_area_size[1]:
                       create_garden(mouse_pos)

                   # Logic for interacting with images and plants
                   elif garden_loaded_or_created and mouse_pos[1] < garden_area_size[1]:
                       # Check images first
                       for image_data in reversed(images):
                           if image_data['rect'].collidepoint(mouse_pos):
                               selected_image = image_data
                               dragging_image = True
                               offset_x = image_data['rect'].x - mouse_pos[0]
                               offset_y = image_data['rect'].y - mouse_pos[1]
                               break
                       else:
                           # Check if any plant is under the mouse
                           for plant in reversed(plants):
                               plant_rect = plant['image'].get_rect(topleft=plant['position'])
                               if plant_rect.collidepoint(mouse_pos):
                                   selected_plant = plant
                                   dragging = True
                                   offset_x = plant['position'][0] - mouse_pos[0]
                                   offset_y = plant['position'][1] - mouse_pos[1]
                                   break
                           else:
                               if is_adding_image:
                                   add_image(mouse_pos)
                                   is_adding_image = False
                               elif is_adding_plant:
                                   add_plant(mouse_pos)
                                   is_adding_plant = False

       elif event.type == pygame.MOUSEBUTTONUP:
           if event.button == 1 and dragging:
               dragging = False
               selected_plant = None
           elif event.button == 1 and dragging_image:
               dragging_image = False
               selected_image = None
           elif event.button == 3:
               if resizing_image:
                   resizing_image = False
                   selected_image = None
               else:
                   if selected_image:
                       mouse_pos = event.pos
                       movement = ((mouse_pos[0] - right_click_start_pos[0]) ** 2 + (mouse_pos[1] - right_click_start_pos[1]) ** 2) ** 0.5
                       if movement < 5:
                           if platform.system() == 'Linux' and 'arm' in platform.machine():
                               response = show_yes_no_pygame("Delete Image", "Do you want to delete this image?")
                           else:
                               root = tk.Tk()
                               root.withdraw()
                               response = messagebox.askyesno(
                                   "Delete Image",
                                   "Do you want to delete this image?"
                               )
                               root.destroy()
                           if response:
                               index = images.index(selected_image)
                               images.remove(selected_image)
                               add_undo_action('delete_image', {'image': selected_image, 'index': index})
                               garden_modified = True
                           selected_image = None

       elif event.type == pygame.MOUSEMOTION:
           mouse_pos = event.pos
           if resizing_image and selected_image:
               mouse_x, mouse_y = event.pos
               dx = mouse_x - resize_anchor[0]
               dy = mouse_y - resize_anchor[1]
               scaling_factor_width = 1 + dx / 200
               scaling_factor_height = 1 + dy / 200
               scaling_factor_width = max(scaling_factor_width, 0.1)
               scaling_factor_height = max(scaling_factor_height, 0.1)
               new_width = max(int(original_size[0] * scaling_factor_width), 10)
               new_height = max(int(original_size[1] * scaling_factor_height), 10)
               selected_image['image'] = pygame.transform.scale(selected_image['original_image'], (new_width, new_height))
               selected_image['rect'].size = (new_width, new_height)
           elif dragging and selected_plant:
               mouse_x, mouse_y = event.pos
               new_x = mouse_x + offset_x
               new_y = mouse_y + offset_y
               new_position = snap_to_grid((new_x, new_y))
               if point_in_garden(new_position, garden_boundary):
                   old_position = selected_plant['position']
                   selected_plant['position'] = new_position
                   add_undo_action('move_plant', {'plant': selected_plant, 'old_position': old_position, 'new_position': new_position})
           elif dragging_image and selected_image:
               mouse_x, mouse_y = event.pos
               new_x = mouse_x + offset_x
               new_y = mouse_y + offset_y
               old_position = selected_image['rect'].topleft
               selected_image['rect'].topleft = (new_x, new_y)
               add_undo_action('move_image', {'image': selected_image, 'old_position': old_position, 'new_position': (new_x, new_y)})
           elif event.buttons[2] and selected_image:
               if not resizing_image:
                   resizing_image = True
                   resize_anchor = (mouse_pos[0], mouse_pos[1])
                   original_size = (selected_image['rect'].width, selected_image['rect'].height)

   # Drawing logic
   if garden_loaded_or_created and not is_creating_garden and len(garden_boundary) > 2:
       window.fill(outside_background_color)
       pygame.draw.polygon(window, background_color, garden_boundary)
       draw_grid()
       draw_garden_boundary()
   else:
       window.fill(background_color)
       draw_grid()
       draw_garden_boundary()

   # Draw images
   for image_data in images:
       window.blit(image_data['image'], image_data['rect'])

   # Draw starting point
   draw_start_point()

   # Draw plants
   for plant in plants:
       window.blit(plant['image'], plant['position'])
       name_surface = font.render(plant['name'], True, (0, 0, 0))
       name_rect = name_surface.get_rect(center=(plant['position'][0] + 15, plant['position'][1] - 10))
       window.blit(name_surface, name_rect)
       if plant['has_sensor']:
           sensor_pos = (plant['position'][0] + 20, plant['position'][1] - 10)
           window.blit(sensor_icon, sensor_pos)

   # Draw button area
   pygame.draw.rect(window, button_area_color, (0, garden_area_size[1], button_area_size[0], button_area_size[1]))

   # Update buttons
   update_buttons()

   # Update display
   pygame.display.flip()

# Quit pygame
pygame.quit()
sys.exit()