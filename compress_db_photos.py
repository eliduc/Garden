#!/usr/bin/env python3
"""
Compress Photos in Database
Compresses all plant photos in the database to reduce storage size
"""

import sqlite3
import io
from PIL import Image
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import queue
import sys

# Configuration
DB_FILE = 'garden_sensors.db'

# Default settings (note: corrected as per requirements)
DEFAULT_MAIN_PHOTO_SETTINGS = {
    'MAX_SIZE': (640, 640),          # Maximum dimensions
    'JPEG_QUALITY': 70,              # JPEG quality (1-100)
    'TARGET_MAX_SIZE_KB': 150        # Target maximum file size in KB
}

DEFAULT_ADDITIONAL_PHOTO_SETTINGS = {
    'MAX_SIZE': (960, 960),          # Maximum dimensions
    'JPEG_QUALITY': 75,              # JPEG quality (1-100)
    'TARGET_MAX_SIZE_KB': 250        # Target maximum file size in KB
}

# Global settings (will be updated by GUI)
MAIN_PHOTO_SETTINGS = DEFAULT_MAIN_PHOTO_SETTINGS.copy()
ADDITIONAL_PHOTO_SETTINGS = DEFAULT_ADDITIONAL_PHOTO_SETTINGS.copy()

def get_db_connection():
    """Create a database connection"""
    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrency
    conn.execute('PRAGMA journal_mode=WAL')
    return conn

def format_bytes(size):
    """Format bytes to human readable string"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"

def compress_photo(photo_data, photo_id, photo_type='main'):
    """Compress a single photo"""
    # Select settings based on photo type
    settings = MAIN_PHOTO_SETTINGS if photo_type == 'main' else ADDITIONAL_PHOTO_SETTINGS
    max_size = settings['MAX_SIZE']
    jpeg_quality = settings['JPEG_QUALITY']
    target_max_size_kb = settings['TARGET_MAX_SIZE_KB']
    
    try:
        # Open image from bytes
        img = Image.open(io.BytesIO(photo_data))
        original_size = len(photo_data)
        
        # Get original dimensions
        original_width, original_height = img.size
        
        # Convert RGBA to RGB if necessary
        if img.mode in ('RGBA', 'LA'):
            # Create white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'RGBA':
                background.paste(img, mask=img.split()[3])  # Use alpha channel as mask
            else:
                background.paste(img)
            img = background
        elif img.mode not in ('RGB', 'L'):
            # Convert other modes to RGB
            img = img.convert('RGB')
        
        # Start with specified quality
        quality = jpeg_quality
        
        # Try different compressions to achieve target size
        best_data = None
        best_size = float('inf')
        
        # Adjust quality attempts based on photo type
        quality_attempts = [jpeg_quality, jpeg_quality-5, jpeg_quality-10, jpeg_quality-15, jpeg_quality-20]
        quality_attempts = [q for q in quality_attempts if q >= 40]  # Don't go below 40
        
        for attempt_quality in quality_attempts:
            # Resize if larger than max_size
            temp_img = img.copy()
            if temp_img.width > max_size[0] or temp_img.height > max_size[1]:
                temp_img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Save to bytes
            output = io.BytesIO()
            if temp_img.mode == 'L':  # Grayscale
                temp_img.save(output, format='JPEG', quality=attempt_quality, optimize=True)
            else:
                temp_img.save(output, format='JPEG', quality=attempt_quality, optimize=True, progressive=True)
            
            compressed_data = output.getvalue()
            compressed_size = len(compressed_data)
            
            # Check if this is better than previous attempts
            if compressed_size < best_size and compressed_size < original_size:
                best_data = compressed_data
                best_size = compressed_size
                quality = attempt_quality
            
            # If we're under target size, we're done
            if compressed_size <= target_max_size_kb * 1024:
                break
        
        # If no compression achieved, return None
        if best_data is None or best_size >= original_size:
            return None, original_size, 0, "No compression achieved"
        
        # Calculate compression ratio
        compression_ratio = (1 - best_size / original_size) * 100
        
        result_info = f"Quality: {quality}, Size: {original_width}x{original_height}"
        if temp_img.width != original_width or temp_img.height != original_height:
            result_info += f" → {temp_img.width}x{temp_img.height}"
        
        return best_data, original_size, best_size, result_info
        
    except Exception as e:
        return None, len(photo_data), 0, f"Error: {str(e)}"

def process_photos_thread(dry_run, output_queue, progress_queue):
    """Process photos in a separate thread"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    output_queue.put("Analyzing photos in database...\n")
    output_queue.put("=" * 80 + "\n")
    
    # Get all photos
    cursor.execute('''
        SELECT pp.id, pp.garden_plant_id, pp.photo_type, pp.file_size,
               LENGTH(pp.photo_data) as actual_size, pp.photo_data,
               gp.custom_name, pt.name as plant_type_name
        FROM plant_photos pp
        JOIN garden_plants gp ON pp.garden_plant_id = gp.id
        JOIN plant_types pt ON gp.plant_type_id = pt.id
        ORDER BY LENGTH(pp.photo_data) DESC
    ''')
    
    photos = cursor.fetchall()
    total_photos = len(photos)
    
    if total_photos == 0:
        output_queue.put("No photos found in database\n")
        conn.close()
        progress_queue.put(('done', {}))
        return
    
    output_queue.put(f"Found {total_photos} photos to process\n\n")
    
    # Statistics
    total_original_size = 0
    total_compressed_size = 0
    compressed_count = 0
    failed_count = 0
    skipped_count = 0
    
    # Process each photo
    for idx, photo in enumerate(photos, 1):
        photo_id = photo['id']
        plant_name = photo['custom_name'] or photo['plant_type_name']
        photo_type = photo['photo_type']
        original_size = photo['actual_size']
        
        # Update progress
        progress_queue.put(('progress', idx / total_photos * 100))
        
        output_queue.put(f"[{idx}/{total_photos}] Processing photo ID {photo_id}\n")
        output_queue.put(f"  Plant: {plant_name} ({photo_type})\n")
        output_queue.put(f"  Original size: {format_bytes(original_size)}\n")
        
        total_original_size += original_size
        
        # Skip if already small (different thresholds for main and additional photos)
        skip_threshold = 30 * 1024 if photo_type == 'main' else 20 * 1024  # 30KB for main, 20KB for additional
        if original_size < skip_threshold:
            output_queue.put(f"  → Skipping (already small, < {skip_threshold // 1024}KB)\n")
            skipped_count += 1
            total_compressed_size += original_size
            continue
        
        # Compress photo with appropriate settings
        compressed_data, orig_size, new_size, info = compress_photo(photo['photo_data'], photo_id, photo_type)
        
        if compressed_data is None:
            output_queue.put(f"  → Failed: {info}\n")
            failed_count += 1
            total_compressed_size += original_size
        else:
            compression_ratio = (1 - new_size / orig_size) * 100
            output_queue.put(f"  → Compressed: {format_bytes(new_size)} ({compression_ratio:.1f}% reduction)\n")
            output_queue.put(f"     {info}\n")
            
            total_compressed_size += new_size
            compressed_count += 1
            
            # Update database if not dry run
            if not dry_run:
                try:
                    cursor.execute('''
                        UPDATE plant_photos 
                        SET photo_data = ?, file_size = ?
                        WHERE id = ?
                    ''', (compressed_data, new_size, photo_id))
                    output_queue.put(f"  ✓ Updated in database\n")
                except Exception as e:
                    output_queue.put(f"  ✗ Database update failed: {e}\n")
                    conn.rollback()
                    continue
        
        output_queue.put("\n")
    
    # Summary
    output_queue.put("=" * 80 + "\n")
    output_queue.put("SUMMARY:\n")
    output_queue.put(f"Total photos processed: {total_photos}\n")
    output_queue.put(f"  - Compressed: {compressed_count}\n")
    output_queue.put(f"  - Skipped (already small): {skipped_count}\n")
    output_queue.put(f"  - Failed: {failed_count}\n")
    output_queue.put("\n")
    output_queue.put(f"Total original size: {format_bytes(total_original_size)}\n")
    output_queue.put(f"Total compressed size: {format_bytes(total_compressed_size)}\n")
    
    if total_original_size > 0:
        total_reduction = (1 - total_compressed_size / total_original_size) * 100
        space_saved = total_original_size - total_compressed_size
        output_queue.put(f"Total space saved: {format_bytes(space_saved)} ({total_reduction:.1f}% reduction)\n")
    
    output_queue.put("\nCompression settings used:\n")
    output_queue.put("  Main photos:\n")
    output_queue.put(f"    - Max size: {MAIN_PHOTO_SETTINGS['MAX_SIZE'][0]}x{MAIN_PHOTO_SETTINGS['MAX_SIZE'][1]}\n")
    output_queue.put(f"    - Quality: {MAIN_PHOTO_SETTINGS['JPEG_QUALITY']}\n")
    output_queue.put(f"    - Target: {MAIN_PHOTO_SETTINGS['TARGET_MAX_SIZE_KB']}KB\n")
    output_queue.put("  Additional photos:\n")
    output_queue.put(f"    - Max size: {ADDITIONAL_PHOTO_SETTINGS['MAX_SIZE'][0]}x{ADDITIONAL_PHOTO_SETTINGS['MAX_SIZE'][1]}\n")
    output_queue.put(f"    - Quality: {ADDITIONAL_PHOTO_SETTINGS['JPEG_QUALITY']}\n")
    output_queue.put(f"    - Target: {ADDITIONAL_PHOTO_SETTINGS['TARGET_MAX_SIZE_KB']}KB\n")
    
    if not dry_run and compressed_count > 0:
        # Commit changes
        conn.commit()
        output_queue.put("\n✓ All changes committed to database\n")
        
        # Run VACUUM to reclaim space
        output_queue.put("\nReclaiming database space...\n")
        conn.execute('VACUUM')
        output_queue.put("✓ Database optimized\n")
    elif dry_run:
        output_queue.put("\n(DRY RUN - no changes were made)\n")
    
    conn.close()
    
    # Send completion signal
    progress_queue.put(('done', {
        'total': total_photos,
        'compressed': compressed_count,
        'skipped': skipped_count,
        'failed': failed_count,
        'space_saved': space_saved if total_original_size > 0 else 0
    }))

class CompressionApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Photo Compression Tool")
        self.root.geometry("800x700")
        self.root.minsize(800, 700)
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Settings tab
        self.settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_frame, text="Settings")
        self.create_settings_tab()
        
        # Progress tab
        self.progress_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.progress_frame, text="Progress")
        self.create_progress_tab()
        
        # Initialize queues for thread communication
        self.output_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        
        # Processing thread
        self.processing_thread = None
        
        # Update UI periodically
        self.update_ui()
        
    def create_settings_tab(self):
        # Variables for settings
        self.main_width = tk.IntVar(value=MAIN_PHOTO_SETTINGS['MAX_SIZE'][0])
        self.main_height = tk.IntVar(value=MAIN_PHOTO_SETTINGS['MAX_SIZE'][1])
        self.main_quality = tk.IntVar(value=MAIN_PHOTO_SETTINGS['JPEG_QUALITY'])
        self.main_target_kb = tk.IntVar(value=MAIN_PHOTO_SETTINGS['TARGET_MAX_SIZE_KB'])
        
        self.add_width = tk.IntVar(value=ADDITIONAL_PHOTO_SETTINGS['MAX_SIZE'][0])
        self.add_height = tk.IntVar(value=ADDITIONAL_PHOTO_SETTINGS['MAX_SIZE'][1])
        self.add_quality = tk.IntVar(value=ADDITIONAL_PHOTO_SETTINGS['JPEG_QUALITY'])
        self.add_target_kb = tk.IntVar(value=ADDITIONAL_PHOTO_SETTINGS['TARGET_MAX_SIZE_KB'])
        
        self.dry_run_var = tk.BooleanVar(value=False)
        
        # Main frame
        main_frame = ttk.Frame(self.settings_frame, padding="20")
        main_frame.pack(fill='both', expand=True)
        
        # Title
        title_label = ttk.Label(main_frame, text="Photo Compression Settings", 
                               font=('Arial', 16, 'bold'))
        title_label.pack(pady=(0, 20))
        
        # Main photos section
        main_section = ttk.LabelFrame(main_frame, text="Main Photos (displayed in web interface)", 
                                     padding="10")
        main_section.pack(fill='x', pady=(0, 10))
        
        # Main photo controls
        dims_frame = ttk.Frame(main_section)
        dims_frame.pack(fill='x')
        ttk.Label(dims_frame, text="Max dimensions:").pack(side='left', padx=(0, 10))
        ttk.Spinbox(dims_frame, from_=100, to=2000, textvariable=self.main_width, width=10).pack(side='left')
        ttk.Label(dims_frame, text="x").pack(side='left', padx=5)
        ttk.Spinbox(dims_frame, from_=100, to=2000, textvariable=self.main_height, width=10).pack(side='left')
        ttk.Label(dims_frame, text="pixels").pack(side='left', padx=(5, 0))
        
        quality_frame = ttk.Frame(main_section)
        quality_frame.pack(fill='x', pady=(10, 0))
        ttk.Label(quality_frame, text="JPEG quality:").pack(side='left', padx=(0, 10))
        self.main_quality_scale = ttk.Scale(quality_frame, from_=40, to=95, variable=self.main_quality, 
                                      orient=tk.HORIZONTAL, length=200)
        self.main_quality_scale.pack(side='left')
        self.main_quality_label = ttk.Label(quality_frame, text=f"{self.main_quality.get()}")
        self.main_quality_label.pack(side='left', padx=(10, 0))
        
        target_frame = ttk.Frame(main_section)
        target_frame.pack(fill='x', pady=(10, 0))
        ttk.Label(target_frame, text="Target size:").pack(side='left', padx=(0, 10))
        ttk.Spinbox(target_frame, from_=50, to=1000, textvariable=self.main_target_kb, 
                   width=10, increment=50).pack(side='left')
        ttk.Label(target_frame, text="KB").pack(side='left', padx=(5, 0))
        
        # Additional photos section
        add_section = ttk.LabelFrame(main_frame, text="Additional Photos (stored only)", 
                                    padding="10")
        add_section.pack(fill='x', pady=(0, 10))
        
        # Additional photo controls
        dims_frame2 = ttk.Frame(add_section)
        dims_frame2.pack(fill='x')
        ttk.Label(dims_frame2, text="Max dimensions:").pack(side='left', padx=(0, 10))
        ttk.Spinbox(dims_frame2, from_=100, to=2000, textvariable=self.add_width, width=10).pack(side='left')
        ttk.Label(dims_frame2, text="x").pack(side='left', padx=5)
        ttk.Spinbox(dims_frame2, from_=100, to=2000, textvariable=self.add_height, width=10).pack(side='left')
        ttk.Label(dims_frame2, text="pixels").pack(side='left', padx=(5, 0))
        
        quality_frame2 = ttk.Frame(add_section)
        quality_frame2.pack(fill='x', pady=(10, 0))
        ttk.Label(quality_frame2, text="JPEG quality:").pack(side='left', padx=(0, 10))
        self.add_quality_scale = ttk.Scale(quality_frame2, from_=40, to=95, variable=self.add_quality, 
                                     orient=tk.HORIZONTAL, length=200)
        self.add_quality_scale.pack(side='left')
        self.add_quality_label = ttk.Label(quality_frame2, text=f"{self.add_quality.get()}")
        self.add_quality_label.pack(side='left', padx=(10, 0))
        
        target_frame2 = ttk.Frame(add_section)
        target_frame2.pack(fill='x', pady=(10, 0))
        ttk.Label(target_frame2, text="Target size:").pack(side='left', padx=(0, 10))
        ttk.Spinbox(target_frame2, from_=50, to=1000, textvariable=self.add_target_kb, 
                   width=10, increment=50).pack(side='left')
        ttk.Label(target_frame2, text="KB").pack(side='left', padx=(5, 0))
        
        # Update quality labels
        self.main_quality_scale.config(command=lambda v: self.main_quality_label.config(text=f"{int(float(v))}"))
        self.add_quality_scale.config(command=lambda v: self.add_quality_label.config(text=f"{int(float(v))}"))
        
        # Options
        options_frame = ttk.Frame(main_frame)
        options_frame.pack(pady=(20, 10))
        ttk.Checkbutton(options_frame, text="Dry run (preview only, no changes)", 
                       variable=self.dry_run_var).pack()
        
        # Statistics
        stats_frame = ttk.LabelFrame(main_frame, text="Database Statistics", padding="10")
        stats_frame.pack(fill='x', pady=(0, 20))
        self.stats_label = ttk.Label(stats_frame, text="Loading statistics...")
        self.stats_label.pack()
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack()
        
        self.start_button = ttk.Button(button_frame, text="Start Compression", 
                                      command=self.start_compression)
        self.start_button.pack(side='left', padx=5)
        ttk.Button(button_frame, text="Reset Defaults", 
                  command=self.reset_defaults).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Exit", 
                  command=self.root.quit).pack(side='left', padx=5)
        
        # Load statistics
        self.load_statistics()
        
    def create_progress_tab(self):
        # Progress bar
        progress_frame = ttk.Frame(self.progress_frame, padding="20")
        progress_frame.pack(fill='x')
        
        ttk.Label(progress_frame, text="Compression Progress:", 
                 font=('Arial', 12)).pack(anchor='w')
        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate', length=400)
        self.progress_bar.pack(fill='x', pady=(5, 0))
        
        # Output text
        output_frame = ttk.Frame(self.progress_frame, padding="10")
        output_frame.pack(fill='both', expand=True)
        
        ttk.Label(output_frame, text="Output:", font=('Arial', 12)).pack(anchor='w')
        
        # Text widget with scrollbar
        text_frame = ttk.Frame(output_frame)
        text_frame.pack(fill='both', expand=True)
        
        self.output_text = scrolledtext.ScrolledText(text_frame, wrap='word', height=20)
        self.output_text.pack(fill='both', expand=True)
        
    def load_statistics(self):
        def load():
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total_photos,
                        SUM(LENGTH(photo_data)) as total_size,
                        COUNT(CASE WHEN photo_type = 'main' THEN 1 END) as main_count,
                        COUNT(CASE WHEN photo_type != 'main' THEN 1 END) as additional_count
                    FROM plant_photos
                ''')
                
                stats = cursor.fetchone()
                conn.close()
                
                if stats and stats['total_photos'] > 0:
                    stats_text = (
                        f"Total photos: {stats['total_photos']}\n"
                        f"  Main photos: {stats['main_count']}\n"
                        f"  Additional photos: {stats['additional_count']}\n"
                        f"Total size: {format_bytes(stats['total_size'])}"
                    )
                else:
                    stats_text = "No photos found in database"
                
                self.stats_label.config(text=stats_text)
            except Exception as e:
                self.stats_label.config(text=f"Error loading statistics: {e}")
        
        threading.Thread(target=load, daemon=True).start()
        
    def reset_defaults(self):
        self.main_width.set(DEFAULT_MAIN_PHOTO_SETTINGS['MAX_SIZE'][0])
        self.main_height.set(DEFAULT_MAIN_PHOTO_SETTINGS['MAX_SIZE'][1])
        self.main_quality.set(DEFAULT_MAIN_PHOTO_SETTINGS['JPEG_QUALITY'])
        self.main_target_kb.set(DEFAULT_MAIN_PHOTO_SETTINGS['TARGET_MAX_SIZE_KB'])
        
        self.add_width.set(DEFAULT_ADDITIONAL_PHOTO_SETTINGS['MAX_SIZE'][0])
        self.add_height.set(DEFAULT_ADDITIONAL_PHOTO_SETTINGS['MAX_SIZE'][1])
        self.add_quality.set(DEFAULT_ADDITIONAL_PHOTO_SETTINGS['JPEG_QUALITY'])
        self.add_target_kb.set(DEFAULT_ADDITIONAL_PHOTO_SETTINGS['TARGET_MAX_SIZE_KB'])
        
    def start_compression(self):
        # Check if already processing
        if self.processing_thread and self.processing_thread.is_alive():
            messagebox.showwarning("Warning", "Compression is already in progress!")
            return
        
        # Confirm if not dry run
        if not self.dry_run_var.get():
            answer = messagebox.askyesno(
                "Confirm Compression",
                "WARNING: This will modify photos in your database!\n\n"
                "It's recommended to backup your database first.\n\n"
                "Do you want to continue?",
                icon='warning'
            )
            if not answer:
                return
        
        # Update global settings
        MAIN_PHOTO_SETTINGS['MAX_SIZE'] = (self.main_width.get(), self.main_height.get())
        MAIN_PHOTO_SETTINGS['JPEG_QUALITY'] = self.main_quality.get()
        MAIN_PHOTO_SETTINGS['TARGET_MAX_SIZE_KB'] = self.main_target_kb.get()
        
        ADDITIONAL_PHOTO_SETTINGS['MAX_SIZE'] = (self.add_width.get(), self.add_height.get())
        ADDITIONAL_PHOTO_SETTINGS['JPEG_QUALITY'] = self.add_quality.get()
        ADDITIONAL_PHOTO_SETTINGS['TARGET_MAX_SIZE_KB'] = self.add_target_kb.get()
        
        # Clear output
        self.output_text.delete(1.0, tk.END)
        self.progress_bar['value'] = 0
        
        # Switch to progress tab
        self.notebook.select(self.progress_frame)
        
        # Disable start button
        self.start_button.config(state='disabled')
        
        # Start processing thread
        self.processing_thread = threading.Thread(
            target=process_photos_thread,
            args=(self.dry_run_var.get(), self.output_queue, self.progress_queue),
            daemon=True
        )
        self.processing_thread.start()
        
    def update_ui(self):
        # Check output queue
        try:
            while True:
                text = self.output_queue.get_nowait()
                self.output_text.insert(tk.END, text)
                self.output_text.see(tk.END)
        except queue.Empty:
            pass
        
        # Check progress queue
        try:
            while True:
                msg_type, data = self.progress_queue.get_nowait()
                if msg_type == 'progress':
                    self.progress_bar['value'] = data
                elif msg_type == 'done':
                    self.start_button.config(state='normal')
                    messagebox.showinfo(
                        "Compression Complete",
                        f"Processing completed!\n\n"
                        f"Photos processed: {data['total']}\n"
                        f"Compressed: {data['compressed']}\n"
                        f"Space saved: {format_bytes(data['space_saved'])}"
                    )
        except queue.Empty:
            pass
        
        # Schedule next update
        self.root.after(100, self.update_ui)

def analyze_photos():
    """Analyze photos without making changes"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print("Photo Analysis")
    print("=" * 80)
    
    # Get statistics
    cursor.execute('''
        SELECT 
            COUNT(*) as total_photos,
            SUM(LENGTH(photo_data)) as total_size,
            AVG(LENGTH(photo_data)) as avg_size,
            MAX(LENGTH(photo_data)) as max_size,
            MIN(LENGTH(photo_data)) as min_size
        FROM plant_photos
    ''')
    
    stats = cursor.fetchone()
    
    if stats['total_photos'] == 0:
        print("No photos found in database")
        conn.close()
        return
    
    print(f"Total photos: {stats['total_photos']}")
    print(f"Total size: {format_bytes(stats['total_size'])}")
    print(f"Average size: {format_bytes(stats['avg_size'])}")
    print(f"Largest photo: {format_bytes(stats['max_size'])}")
    print(f"Smallest photo: {format_bytes(stats['min_size'])}")
    print()
    
    # Size distribution
    print("Size distribution:")
    size_ranges = [
        (0, 20*1024, "< 20 KB"),
        (20*1024, 50*1024, "20-50 KB"),
        (50*1024, 100*1024, "50-100 KB"),
        (100*1024, 250*1024, "100-250 KB"),
        (250*1024, 500*1024, "250-500 KB"),
        (500*1024, 1024*1024, "500 KB - 1 MB"),
        (1024*1024, 2*1024*1024, "1-2 MB"),
        (2*1024*1024, 5*1024*1024, "2-5 MB"),
        (5*1024*1024, float('inf'), "> 5 MB")
    ]
    
    for min_size, max_size, label in size_ranges:
        cursor.execute('''
            SELECT COUNT(*) as count, SUM(LENGTH(photo_data)) as total_size,
                   SUM(CASE WHEN photo_type = 'main' THEN 1 ELSE 0 END) as main_count
            FROM plant_photos
            WHERE LENGTH(photo_data) >= ? AND LENGTH(photo_data) < ?
        ''', (min_size, max_size))
        
        result = cursor.fetchone()
        if result['count'] > 0:
            main_info = f" ({result['main_count']} main)" if result['main_count'] > 0 else ""
            print(f"  {label:15} {result['count']:4} photos{main_info} ({format_bytes(result['total_size'])})")
    
    print()
    
    # Top 10 largest photos
    print("Top 10 largest photos:")
    cursor.execute('''
        SELECT pp.id, LENGTH(pp.photo_data) as size, pp.photo_type,
               gp.custom_name, pt.name as plant_type_name
        FROM plant_photos pp
        JOIN garden_plants gp ON pp.garden_plant_id = gp.id
        JOIN plant_types pt ON gp.plant_type_id = pt.id
        ORDER BY LENGTH(pp.photo_data) DESC
        LIMIT 10
    ''')
    
    for idx, row in enumerate(cursor.fetchall(), 1):
        plant_name = row['custom_name'] or row['plant_type_name']
        print(f"  {idx:2}. ID {row['id']:4} - {format_bytes(row['size']):>10} - {plant_name} ({row['photo_type']})")
    
    conn.close()

def main():
    """Main entry point"""
    import os
    
    print("Database Photo Compression Tool")
    print("==============================\n")
    
    # Check if database exists
    if not os.path.exists(DB_FILE):
        print(f"Error: Database '{DB_FILE}' not found!")
        return
    
    # Parse arguments
    if '--analyze' in sys.argv or '-a' in sys.argv:
        analyze_photos()
    elif '--help' in sys.argv or '-h' in sys.argv:
        print("Usage: python compress_db_photos.py [options]")
        print("\nOptions:")
        print("  -a, --analyze   Analyze photos without GUI")
        print("  -h, --help      Show this help message")
        print("\nWithout options, the program will launch the GUI.")
    else:
        # Launch GUI
        root = tk.Tk()
        app = CompressionApp(root)
        root.mainloop()

if __name__ == "__main__":
    main()