import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
from datetime import datetime
import os
import sys
import shutil
from PIL import Image, ImageTk
import json
import io

class GardenDatabaseManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Garden Database Manager")
        self.root.geometry("1200x700")
        
        # Database connection
        self.db_file = 'garden_sensors.db'
        self.conn = None
        self.connect_db()
        
        # Check and update database schema
        self.check_database_schema()
        
        # Create main interface
        self.create_widgets()
        
        # Load initial data
        self.load_plant_types()
        self.load_gardens()
    
    def connect_db(self):
        """Connect to database"""
        try:
            self.conn = sqlite3.connect(self.db_file)
            self.conn.row_factory = sqlite3.Row
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to connect to database: {e}")
            self.root.destroy()
    
    def check_database_schema(self):
        """Check and update database schema if needed"""
        cursor = self.conn.cursor()
        
        # Check if updated_at column exists in plant_types
        cursor.execute("PRAGMA table_info(plant_types)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'updated_at' not in columns:
            print("Adding updated_at column to plant_types table...")
            try:
                cursor.execute('''
                    ALTER TABLE plant_types 
                    ADD COLUMN updated_at DATETIME
                ''')
                self.conn.commit()
            except Exception as e:
                print(f"Warning: Could not add updated_at column: {e}")
        
        # Check if created_at column exists in plant_types
        if 'created_at' not in columns:
            print("Adding created_at column to plant_types table...")
            try:
                cursor.execute('''
                    ALTER TABLE plant_types 
                    ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                ''')
                self.conn.commit()
            except Exception as e:
                print(f"Warning: Could not add created_at column: {e}")
        
        # Ensure plant_thresholds table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='plant_thresholds'
        """)
        
        if not cursor.fetchone():
            print("Creating plant_thresholds table...")
            cursor.execute('''
                CREATE TABLE plant_thresholds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plant_type_id INTEGER NOT NULL,
                    season TEXT NOT NULL,
                    humidity_low INTEGER,
                    humidity_high INTEGER,
                    temperature_low INTEGER,
                    temperature_high INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME,
                    FOREIGN KEY (plant_type_id) REFERENCES plant_types(id),
                    UNIQUE(plant_type_id, season)
                )
            ''')
            self.conn.commit()
        
        # Ensure plant_photos table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='plant_photos'
        """)
        
        if not cursor.fetchone():
            print("Creating plant_photos table...")
            cursor.execute('''
                CREATE TABLE plant_photos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    garden_plant_id INTEGER NOT NULL,
                    photo_path TEXT NOT NULL,
                    photo_type TEXT DEFAULT 'additional',
                    description TEXT,
                    date_taken DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (garden_plant_id) REFERENCES garden_plants(id) ON DELETE CASCADE
                )
            ''')
            
            # Create index
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_plant_photos_garden_plant_id 
                ON plant_photos(garden_plant_id)
            ''')
            
            self.conn.commit()
    
    def create_widgets(self):
        """Create the main interface"""
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Create tabs
        self.create_plant_types_tab()
        self.create_garden_plants_tab()
        self.create_plant_photos_tab()
        self.create_thresholds_tab()
        self.create_sensor_readings_tab()
        
    def create_plant_types_tab(self):
        """Create Plant Types management tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Plant Types")
        
        # Top frame for controls
        control_frame = ttk.Frame(tab)
        control_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Button(control_frame, text="Add Plant Type", 
                  command=self.add_plant_type).pack(side='left', padx=5)
        ttk.Button(control_frame, text="Edit Selected", 
                  command=self.edit_plant_type).pack(side='left', padx=5)
        ttk.Button(control_frame, text="Delete Selected", 
                  command=self.delete_plant_type).pack(side='left', padx=5)
        ttk.Button(control_frame, text="Refresh", 
                  command=self.load_plant_types).pack(side='left', padx=5)
        
        # Treeview for plant types
        tree_frame = ttk.Frame(tab)
        tree_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        
        # Treeview
        self.plant_types_tree = ttk.Treeview(tree_frame, 
                                            columns=('ID', 'Name', 'Latin Name', 'Created', 'Updated'),
                                            show='tree headings',
                                            yscrollcommand=vsb.set,
                                            xscrollcommand=hsb.set)
        
        vsb.config(command=self.plant_types_tree.yview)
        hsb.config(command=self.plant_types_tree.xview)
        
        # Configure columns
        self.plant_types_tree.heading('#0', text='')
        self.plant_types_tree.heading('ID', text='ID')
        self.plant_types_tree.heading('Name', text='Name')
        self.plant_types_tree.heading('Latin Name', text='Latin Name')
        self.plant_types_tree.heading('Created', text='Created')
        self.plant_types_tree.heading('Updated', text='Updated')
        
        self.plant_types_tree.column('#0', width=0, stretch=False)
        self.plant_types_tree.column('ID', width=50)
        self.plant_types_tree.column('Name', width=200)
        self.plant_types_tree.column('Latin Name', width=200)
        self.plant_types_tree.column('Created', width=150)
        self.plant_types_tree.column('Updated', width=150)
        
        # Pack treeview and scrollbars
        self.plant_types_tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
    def create_garden_plants_tab(self):
        """Create Garden Plants management tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Garden Plants")
        
        # Top frame for garden selection and controls
        top_frame = ttk.Frame(tab)
        top_frame.pack(fill='x', padx=10, pady=10)
        
        # Garden selection
        ttk.Label(top_frame, text="Garden:").pack(side='left', padx=5)
        self.garden_var = tk.StringVar()
        self.garden_combo = ttk.Combobox(top_frame, textvariable=self.garden_var, 
                                        state='readonly', width=30)
        self.garden_combo.pack(side='left', padx=5)
        self.garden_combo.bind('<<ComboboxSelected>>', lambda e: self.load_garden_plants())
        
        # Control buttons
        control_frame = ttk.Frame(tab)
        control_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(control_frame, text="Add Plant", 
                  command=self.add_garden_plant).pack(side='left', padx=5)
        ttk.Button(control_frame, text="Edit Selected", 
                  command=self.edit_garden_plant).pack(side='left', padx=5)
        ttk.Button(control_frame, text="Delete Selected", 
                  command=self.delete_garden_plant).pack(side='left', padx=5)
        ttk.Button(control_frame, text="Manage Photo", 
                  command=self.manage_plant_photo).pack(side='left', padx=5)
        ttk.Button(control_frame, text="Configure Sensor", 
                  command=self.configure_sensor).pack(side='left', padx=5)
        ttk.Button(control_frame, text="Refresh", 
                  command=self.load_garden_plants).pack(side='left', padx=5)
        
        # Main content frame
        content_frame = ttk.Frame(tab)
        content_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Treeview frame (left side)
        tree_frame = ttk.Frame(content_frame)
        tree_frame.pack(side='left', fill='both', expand=True)
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        
        # Treeview
        self.garden_plants_tree = ttk.Treeview(tree_frame,
                                              columns=('ID', 'Unique ID', 'Type', 'Custom Name', 
                                                      'Position', 'Has Sensor', 'Sensor Name'),
                                              show='tree headings',
                                              yscrollcommand=vsb.set,
                                              xscrollcommand=hsb.set)
        
        vsb.config(command=self.garden_plants_tree.yview)
        hsb.config(command=self.garden_plants_tree.xview)
        
        # Configure columns
        self.garden_plants_tree.heading('#0', text='')
        self.garden_plants_tree.heading('ID', text='ID')
        self.garden_plants_tree.heading('Unique ID', text='Unique ID')
        self.garden_plants_tree.heading('Type', text='Plant Type')
        self.garden_plants_tree.heading('Custom Name', text='Custom Name')
        self.garden_plants_tree.heading('Position', text='Position')
        self.garden_plants_tree.heading('Has Sensor', text='Has Sensor')
        self.garden_plants_tree.heading('Sensor Name', text='Sensor Name')
        
        self.garden_plants_tree.column('#0', width=0, stretch=False)
        self.garden_plants_tree.column('ID', width=50)
        self.garden_plants_tree.column('Unique ID', width=100)
        self.garden_plants_tree.column('Type', width=150)
        self.garden_plants_tree.column('Custom Name', width=150)
        self.garden_plants_tree.column('Position', width=100)
        self.garden_plants_tree.column('Has Sensor', width=80)
        self.garden_plants_tree.column('Sensor Name', width=150)
        
        # Pack treeview and scrollbars
        self.garden_plants_tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        # Photo preview frame (right side)
        photo_frame = ttk.LabelFrame(content_frame, text="Plant Photo", width=200)
        photo_frame.pack(side='right', fill='y', padx=(10, 0))
        photo_frame.pack_propagate(False)
        
        self.photo_label = ttk.Label(photo_frame, text="No photo")
        self.photo_label.pack(padx=10, pady=10)
        
        # Bind selection event
        self.garden_plants_tree.bind('<<TreeviewSelect>>', self.on_plant_select)
        
    def create_plant_photos_tab(self):
        """Create Plant Photos management tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Plant Photos")
        
        # Top frame with controls
        top_frame = ttk.Frame(tab)
        top_frame.pack(fill='x', padx=10, pady=10)
        
        # Plant selection
        ttk.Label(top_frame, text="Plant:").pack(side='left', padx=5)
        self.photos_plant_var = tk.StringVar()
        self.photos_plant_combo = ttk.Combobox(top_frame, textvariable=self.photos_plant_var,
                                              state='readonly', width=40)
        self.photos_plant_combo.pack(side='left', padx=5)
        self.photos_plant_combo.bind('<<ComboboxSelected>>', lambda e: self.load_plant_photos())
        
        # Control buttons
        control_frame = ttk.Frame(tab)
        control_frame.pack(fill='x', padx=10, pady=5)
        
        ttk.Button(control_frame, text="Add Photos", 
                  command=self.add_plant_photos).pack(side='left', padx=5)
        ttk.Button(control_frame, text="Delete Selected", 
                  command=self.delete_plant_photo).pack(side='left', padx=5)
        ttk.Button(control_frame, text="Set as Primary", 
                  command=self.set_primary_photo).pack(side='left', padx=5)
        ttk.Button(control_frame, text="View Photo", 
                  command=self.view_photo).pack(side='left', padx=5)
        ttk.Button(control_frame, text="Refresh", 
                  command=self.load_plant_photos).pack(side='left', padx=5)
        
        # Main content area
        content_frame = ttk.Frame(tab)
        content_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Photos list (left side)
        list_frame = ttk.Frame(content_frame)
        list_frame.pack(side='left', fill='both', expand=True)
        
        # Scrollbars
        vsb = ttk.Scrollbar(list_frame, orient="vertical")
        hsb = ttk.Scrollbar(list_frame, orient="horizontal")
        
        # Treeview for photos
        self.photos_tree = ttk.Treeview(list_frame,
                                       columns=('ID', 'Type', 'Description', 'Date Taken', 'Created'),
                                       show='tree headings',
                                       yscrollcommand=vsb.set,
                                       xscrollcommand=hsb.set)
        
        vsb.config(command=self.photos_tree.yview)
        hsb.config(command=self.photos_tree.xview)
        
        # Configure columns
        self.photos_tree.heading('#0', text='')
        self.photos_tree.heading('ID', text='ID')
        self.photos_tree.heading('Type', text='Type')
        self.photos_tree.heading('Description', text='Description')
        self.photos_tree.heading('Date Taken', text='Date Taken')
        self.photos_tree.heading('Created', text='Created')
        
        self.photos_tree.column('#0', width=0, stretch=False)
        self.photos_tree.column('ID', width=50)
        self.photos_tree.column('Type', width=80)
        self.photos_tree.column('Description', width=200)
        self.photos_tree.column('Date Taken', width=120)
        self.photos_tree.column('Created', width=120)
        
        # Pack treeview and scrollbars
        self.photos_tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        
        # Photo preview (right side)
        preview_frame = ttk.LabelFrame(content_frame, text="Photo Preview", width=300)
        preview_frame.pack(side='right', fill='y', padx=(10, 0))
        preview_frame.pack_propagate(False)
        
        self.photo_preview_label = ttk.Label(preview_frame, text="No photo selected")
        self.photo_preview_label.pack(padx=10, pady=10)
        
        # Info label
        self.photo_info_label = ttk.Label(preview_frame, text="", wraplength=280)
        self.photo_info_label.pack(padx=10, pady=5)
        
        # Bind selection event
        self.photos_tree.bind('<<TreeviewSelect>>', self.on_photo_select)
        
        # Load plants list
        self.load_plants_for_photos()
        
    def create_thresholds_tab(self):
        """Create Thresholds management tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Thresholds")
        
        # Top frame for plant type selection
        top_frame = ttk.Frame(tab)
        top_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(top_frame, text="Plant Type:").pack(side='left', padx=5)
        self.threshold_plant_var = tk.StringVar()
        self.threshold_plant_combo = ttk.Combobox(top_frame, textvariable=self.threshold_plant_var,
                                                 state='readonly', width=30)
        self.threshold_plant_combo.pack(side='left', padx=5)
        self.threshold_plant_combo.bind('<<ComboboxSelected>>', lambda e: self.load_thresholds())
        
        ttk.Button(top_frame, text="Save All", command=self.save_thresholds).pack(side='left', padx=20)
        
        # Main frame for threshold entries
        main_frame = ttk.Frame(tab)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Create season frames
        self.threshold_vars = {}
        seasons = ['Spring', 'Summer', 'Autumn', 'Winter']
        
        for i, season in enumerate(seasons):
            season_frame = ttk.LabelFrame(main_frame, text=season)
            season_frame.grid(row=i//2, column=i%2, padx=10, pady=10, sticky='ew')
            
            # Create variables
            self.threshold_vars[season] = {
                'humidity_low': tk.IntVar(),
                'humidity_high': tk.IntVar(),
                'temperature_low': tk.IntVar(),
                'temperature_high': tk.IntVar()
            }
            
            # Humidity
            ttk.Label(season_frame, text="Humidity (%)").grid(row=0, column=0, columnspan=2, pady=5)
            ttk.Label(season_frame, text="Low:").grid(row=1, column=0, sticky='e', padx=5)
            ttk.Spinbox(season_frame, from_=0, to=100, 
                       textvariable=self.threshold_vars[season]['humidity_low'],
                       width=10).grid(row=1, column=1, padx=5, pady=2)
            
            ttk.Label(season_frame, text="High:").grid(row=2, column=0, sticky='e', padx=5)
            ttk.Spinbox(season_frame, from_=0, to=100,
                       textvariable=self.threshold_vars[season]['humidity_high'],
                       width=10).grid(row=2, column=1, padx=5, pady=2)
            
            # Temperature
            ttk.Label(season_frame, text="Temperature (°C)").grid(row=3, column=0, columnspan=2, pady=5)
            ttk.Label(season_frame, text="Low:").grid(row=4, column=0, sticky='e', padx=5)
            ttk.Spinbox(season_frame, from_=-10, to=50,
                       textvariable=self.threshold_vars[season]['temperature_low'],
                       width=10).grid(row=4, column=1, padx=5, pady=2)
            
            ttk.Label(season_frame, text="High:").grid(row=5, column=0, sticky='e', padx=5)
            ttk.Spinbox(season_frame, from_=-10, to=50,
                       textvariable=self.threshold_vars[season]['temperature_high'],
                       width=10).grid(row=5, column=1, padx=5, pady=2)
            
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)
        
    def create_sensor_readings_tab(self):
        """Create Sensor Readings viewer tab"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Sensor Readings")
        
        # Filter frame
        filter_frame = ttk.Frame(tab)
        filter_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(filter_frame, text="Plant:").pack(side='left', padx=5)
        self.readings_plant_var = tk.StringVar()
        self.readings_plant_combo = ttk.Combobox(filter_frame, textvariable=self.readings_plant_var,
                                                state='readonly', width=30)
        self.readings_plant_combo.pack(side='left', padx=5)
        
        ttk.Label(filter_frame, text="Date From:").pack(side='left', padx=(20, 5))
        self.date_from_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.date_from_var, width=12).pack(side='left', padx=5)
        
        ttk.Label(filter_frame, text="Date To:").pack(side='left', padx=5)
        self.date_to_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.date_to_var, width=12).pack(side='left', padx=5)
        
        ttk.Button(filter_frame, text="Load Readings", 
                  command=self.load_sensor_readings).pack(side='left', padx=20)
        ttk.Button(filter_frame, text="Delete Selected",
                  command=self.delete_sensor_reading).pack(side='left', padx=5)
        
        # Treeview frame
        tree_frame = ttk.Frame(tab)
        tree_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")
        
        # Treeview
        self.readings_tree = ttk.Treeview(tree_frame,
                                         columns=('ID', 'Plant', 'Sensor', 'Date', 'Time',
                                                 'Temperature', 'Humidity', 'Battery', 'State'),
                                         show='tree headings',
                                         yscrollcommand=vsb.set,
                                         xscrollcommand=hsb.set)
        
        vsb.config(command=self.readings_tree.yview)
        hsb.config(command=self.readings_tree.xview)
        
        # Configure columns
        self.readings_tree.heading('#0', text='')
        self.readings_tree.heading('ID', text='ID')
        self.readings_tree.heading('Plant', text='Plant')
        self.readings_tree.heading('Sensor', text='Sensor')
        self.readings_tree.heading('Date', text='Date')
        self.readings_tree.heading('Time', text='Time')
        self.readings_tree.heading('Temperature', text='Temp (°C)')
        self.readings_tree.heading('Humidity', text='Humidity (%)')
        self.readings_tree.heading('Battery', text='Battery (%)')
        self.readings_tree.heading('State', text='State')
        
        self.readings_tree.column('#0', width=0, stretch=False)
        self.readings_tree.column('ID', width=50)
        self.readings_tree.column('Plant', width=150)
        self.readings_tree.column('Sensor', width=150)
        self.readings_tree.column('Date', width=100)
        self.readings_tree.column('Time', width=100)
        self.readings_tree.column('Temperature', width=80)
        self.readings_tree.column('Humidity', width=80)
        self.readings_tree.column('Battery', width=80)
        self.readings_tree.column('State', width=80)
        
        # Pack treeview and scrollbars
        self.readings_tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        # Load plant list for filter
        self.load_plants_for_readings()
        
    # Plant Types methods
    def load_plant_types(self):
        """Load plant types into treeview"""
        # Clear existing items
        for item in self.plant_types_tree.get_children():
            self.plant_types_tree.delete(item)
        
        cursor = self.conn.cursor()
        
        # Check which columns exist
        cursor.execute("PRAGMA table_info(plant_types)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Build query based on available columns
        select_columns = ['id', 'name']
        if 'latin_name' in columns:
            select_columns.append('latin_name')
        if 'created_at' in columns:
            select_columns.append('created_at')
        if 'updated_at' in columns:
            select_columns.append('updated_at')
        
        query = f"SELECT {', '.join(select_columns)} FROM plant_types ORDER BY name"
        cursor.execute(query)
        
        for row in cursor.fetchall():
            values = [
                row['id'],
                row['name'],
                row['latin_name'] if 'latin_name' in columns and row['latin_name'] else '',
                row['created_at'] if 'created_at' in columns and row['created_at'] else '',
                row['updated_at'] if 'updated_at' in columns and row['updated_at'] else ''
            ]
            self.plant_types_tree.insert('', 'end', values=values)
        
        # Update plant type combos
        self.update_plant_type_combos()
        
    def add_plant_type(self):
        """Add new plant type"""
        dialog = PlantTypeDialog(self.root, "Add Plant Type")
        if dialog.result:
            try:
                cursor = self.conn.cursor()
                
                # Check which columns exist
                cursor.execute("PRAGMA table_info(plant_types)")
                columns = [col[1] for col in cursor.fetchall()]
                
                if 'latin_name' in columns:
                    cursor.execute('''
                        INSERT INTO plant_types (name, latin_name)
                        VALUES (?, ?)
                    ''', (dialog.result['name'], dialog.result['latin_name']))
                else:
                    cursor.execute('''
                        INSERT INTO plant_types (name)
                        VALUES (?)
                    ''', (dialog.result['name'],))
                
                self.conn.commit()
                self.load_plant_types()
                messagebox.showinfo("Success", "Plant type added successfully")
            except sqlite3.IntegrityError:
                messagebox.showerror("Error", "Plant type with this name already exists")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to add plant type: {e}")
                
    def edit_plant_type(self):
        """Edit selected plant type"""
        selection = self.plant_types_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a plant type to edit")
            return
        
        item = self.plant_types_tree.item(selection[0])
        values = item['values']
        
        dialog = PlantTypeDialog(self.root, "Edit Plant Type", 
                               initial_data={'name': values[1], 'latin_name': values[2]})
        if dialog.result:
            try:
                cursor = self.conn.cursor()
                
                # Check which columns exist
                cursor.execute("PRAGMA table_info(plant_types)")
                columns = [col[1] for col in cursor.fetchall()]
                
                if 'latin_name' in columns and 'updated_at' in columns:
                    cursor.execute('''
                        UPDATE plant_types 
                        SET name = ?, latin_name = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    ''', (dialog.result['name'], dialog.result['latin_name'], values[0]))
                elif 'latin_name' in columns:
                    cursor.execute('''
                        UPDATE plant_types 
                        SET name = ?, latin_name = ?
                        WHERE id = ?
                    ''', (dialog.result['name'], dialog.result['latin_name'], values[0]))
                else:
                    cursor.execute('''
                        UPDATE plant_types 
                        SET name = ?
                        WHERE id = ?
                    ''', (dialog.result['name'], values[0]))
                
                self.conn.commit()
                self.load_plant_types()
                messagebox.showinfo("Success", "Plant type updated successfully")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to update plant type: {e}")
                
    def delete_plant_type(self):
        """Delete selected plant type"""
        selection = self.plant_types_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a plant type to delete")
            return
        
        item = self.plant_types_tree.item(selection[0])
        values = item['values']
        
        # Check if plant type is used
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM garden_plants WHERE plant_type_id = ?', (values[0],))
        count = cursor.fetchone()[0]
        
        if count > 0:
            messagebox.showerror("Error", f"Cannot delete plant type. It is used by {count} plants.")
            return
        
        if messagebox.askyesno("Confirm Delete", f"Delete plant type '{values[1]}'?"):
            try:
                cursor.execute('DELETE FROM plant_types WHERE id = ?', (values[0],))
                self.conn.commit()
                self.load_plant_types()
                messagebox.showinfo("Success", "Plant type deleted successfully")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete plant type: {e}")
                
    # Garden Plants methods
    def load_gardens(self):
        """Load garden list"""
        cursor = self.conn.cursor()
        
        # Check if is_active column exists
        cursor.execute("PRAGMA table_info(garden_layouts)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'is_active' in columns:
            cursor.execute('''
                SELECT id, name FROM garden_layouts WHERE is_active = 1
                ORDER BY updated_at DESC, created_at DESC
            ''')
        else:
            cursor.execute('''
                SELECT id, name FROM garden_layouts
                ORDER BY id DESC
            ''')
        
        gardens = cursor.fetchall()
        garden_list = [f"{g['id']}: {g['name']}" for g in gardens]
        self.garden_combo['values'] = garden_list
        
        if garden_list:
            self.garden_combo.current(0)
            self.load_garden_plants()
            
    def load_garden_plants(self):
        """Load plants for selected garden"""
        # Clear existing items
        for item in self.garden_plants_tree.get_children():
            self.garden_plants_tree.delete(item)
        
        if not self.garden_var.get():
            return
        
        garden_id = int(self.garden_var.get().split(':')[0])
        
        cursor = self.conn.cursor()
        
        # Check if latin_name column exists in plant_types
        cursor.execute("PRAGMA table_info(plant_types)")
        columns = [col[1] for col in cursor.fetchall()]
        has_latin_name = 'latin_name' in columns
        
        if has_latin_name:
            cursor.execute('''
                SELECT gp.*, pt.name as plant_type_name
                FROM garden_plants gp
                JOIN plant_types pt ON gp.plant_type_id = pt.id
                WHERE gp.garden_layout_id = ?
                ORDER BY gp.unique_id
            ''', (garden_id,))
        else:
            cursor.execute('''
                SELECT gp.*, pt.name as plant_type_name
                FROM garden_plants gp
                JOIN plant_types pt ON gp.plant_type_id = pt.id
                WHERE gp.garden_layout_id = ?
                ORDER BY gp.unique_id
            ''', (garden_id,))
        
        for row in cursor.fetchall():
            self.garden_plants_tree.insert('', 'end', values=(
                row['id'],
                row['unique_id'],
                row['plant_type_name'],
                row['custom_name'] or '',
                f"({row['position_x']}, {row['position_y']})",
                'Yes' if row['has_sensor'] else 'No',
                row['sensor_name'] or ''
            ))
            
    def add_garden_plant(self):
        """Add new plant to garden"""
        if not self.garden_var.get():
            messagebox.showwarning("Warning", "Please select a garden first")
            return
        
        garden_id = int(self.garden_var.get().split(':')[0])
        
        dialog = GardenPlantDialog(self.root, "Add Garden Plant", self.conn)
        if dialog.result:
            try:
                cursor = self.conn.cursor()
                
                # Generate unique ID
                plant_type_id = dialog.result['plant_type_id']
                cursor.execute('SELECT name FROM plant_types WHERE id = ?', (plant_type_id,))
                plant_name = cursor.fetchone()['name']
                unique_id = f"{plant_name.upper()}-{plant_type_id:03d}"
                
                cursor.execute('''
                    INSERT INTO garden_plants 
                    (unique_id, plant_type_id, position_x, position_y, custom_name,
                     has_sensor, sensor_id, sensor_name, garden_layout_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (unique_id, plant_type_id, dialog.result['position_x'],
                     dialog.result['position_y'], dialog.result['custom_name'],
                     dialog.result['has_sensor'], dialog.result['sensor_id'],
                     dialog.result['sensor_name'], garden_id))
                
                self.conn.commit()
                self.load_garden_plants()
                messagebox.showinfo("Success", "Plant added successfully")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to add plant: {e}")
                
    def edit_garden_plant(self):
        """Edit selected garden plant"""
        selection = self.garden_plants_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a plant to edit")
            return
        
        item = self.garden_plants_tree.item(selection[0])
        values = item['values']
        plant_id = values[0]
        
        # Get full plant data
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM garden_plants WHERE id = ?
        ''', (plant_id,))
        plant_data = cursor.fetchone()
        
        dialog = GardenPlantDialog(self.root, "Edit Garden Plant", self.conn, plant_data)
        if dialog.result:
            try:
                cursor.execute('''
                    UPDATE garden_plants
                    SET plant_type_id = ?, position_x = ?, position_y = ?,
                        custom_name = ?, has_sensor = ?, sensor_id = ?, sensor_name = ?
                    WHERE id = ?
                ''', (dialog.result['plant_type_id'], dialog.result['position_x'],
                     dialog.result['position_y'], dialog.result['custom_name'],
                     dialog.result['has_sensor'], dialog.result['sensor_id'],
                     dialog.result['sensor_name'], plant_id))
                
                self.conn.commit()
                self.load_garden_plants()
                messagebox.showinfo("Success", "Plant updated successfully")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to update plant: {e}")
                
    def delete_garden_plant(self):
        """Delete selected garden plant"""
        selection = self.garden_plants_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a plant to delete")
            return
        
        item = self.garden_plants_tree.item(selection[0])
        values = item['values']
        
        if messagebox.askyesno("Confirm Delete", f"Delete plant '{values[1]}'?"):
            try:
                cursor = self.conn.cursor()
                cursor.execute('DELETE FROM garden_plants WHERE id = ?', (values[0],))
                self.conn.commit()
                self.load_garden_plants()
                messagebox.showinfo("Success", "Plant deleted successfully")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete plant: {e}")
                
    def manage_plant_photo(self):
        """Manage photo for selected plant"""
        selection = self.garden_plants_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a plant")
            return
        
        item = self.garden_plants_tree.item(selection[0])
        plant_id = item['values'][0]
        
        # Redirect to Plant Photos tab
        self.notebook.select(2)  # Switch to Plant Photos tab
        
        # Find and select the plant in the photos combo
        for i, value in enumerate(self.photos_plant_combo['values']):
            if value.startswith(f"{plant_id}:"):
                self.photos_plant_combo.current(i)
                self.load_plant_photos()
                break
        
        messagebox.showinfo("Info", "Use the Plant Photos tab to manage photos for this plant")
                
    def configure_sensor(self):
        """Configure sensor for selected plant"""
        selection = self.garden_plants_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a plant")
            return
        
        item = self.garden_plants_tree.item(selection[0])
        plant_id = item['values'][0]
        
        # Get current sensor data
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT has_sensor, sensor_id, sensor_name 
            FROM garden_plants WHERE id = ?
        ''', (plant_id,))
        sensor_data = cursor.fetchone()
        
        dialog = SensorDialog(self.root, sensor_data)
        if dialog.result is not None:
            try:
                cursor.execute('''
                    UPDATE garden_plants 
                    SET has_sensor = ?, sensor_id = ?, sensor_name = ?
                    WHERE id = ?
                ''', (dialog.result['has_sensor'], dialog.result['sensor_id'],
                     dialog.result['sensor_name'], plant_id))
                self.conn.commit()
                self.load_garden_plants()
                messagebox.showinfo("Success", "Sensor configuration updated")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to update sensor: {e}")
                
    def on_plant_select(self, event):
        """Handle plant selection to show photo"""
        selection = self.garden_plants_tree.selection()
        if not selection:
            self.photo_label.config(image='', text='No photo')
            return
        
        item = self.garden_plants_tree.item(selection[0])
        plant_id = item['values'][0]
        
        # Get main photo from plant_photos table
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT photo_data FROM plant_photos 
            WHERE garden_plant_id = ? AND photo_type = 'main'
            LIMIT 1
        ''', (plant_id,))
        
        result = cursor.fetchone()
        
        if result and result['photo_data']:
            try:
                # Load image from blob data
                import io
                image = Image.open(io.BytesIO(result['photo_data']))
                image.thumbnail((180, 180))
                photo = ImageTk.PhotoImage(image)
                self.photo_label.config(image=photo, text='')
                self.photo_label.image = photo
            except Exception as e:
                self.photo_label.config(image='', text=f'Error loading image:\n{e}')
        else:
            self.photo_label.config(image='', text='No photo')
            
    # Thresholds methods
    def update_plant_type_combos(self):
        """Update plant type combo boxes"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT id, name FROM plant_types ORDER BY name')
        plant_types = cursor.fetchall()
        
        plant_list = [f"{pt['id']}: {pt['name']}" for pt in plant_types]
        self.threshold_plant_combo['values'] = plant_list
        
        if plant_list and not self.threshold_plant_var.get():
            self.threshold_plant_combo.current(0)
            self.load_thresholds()
            
    def load_thresholds(self):
        """Load thresholds for selected plant type"""
        if not self.threshold_plant_var.get():
            return
        
        plant_type_id = int(self.threshold_plant_var.get().split(':')[0])
        
        # Set default values
        defaults = {
            'Spring': {'humidity_low': 40, 'humidity_high': 70, 'temperature_low': 10, 'temperature_high': 25},
            'Summer': {'humidity_low': 50, 'humidity_high': 80, 'temperature_low': 15, 'temperature_high': 35},
            'Autumn': {'humidity_low': 40, 'humidity_high': 70, 'temperature_low': 10, 'temperature_high': 25},
            'Winter': {'humidity_low': 30, 'humidity_high': 60, 'temperature_low': 5, 'temperature_high': 20}
        }
        
        # Apply defaults
        for season, values in defaults.items():
            for key, value in values.items():
                self.threshold_vars[season][key].set(value)
        
        # Load actual values
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT season, humidity_low, humidity_high, temperature_low, temperature_high
            FROM plant_thresholds
            WHERE plant_type_id = ?
        ''', (plant_type_id,))
        
        for row in cursor.fetchall():
            season = row['season']
            if season in self.threshold_vars:
                self.threshold_vars[season]['humidity_low'].set(row['humidity_low'])
                self.threshold_vars[season]['humidity_high'].set(row['humidity_high'])
                self.threshold_vars[season]['temperature_low'].set(row['temperature_low'])
                self.threshold_vars[season]['temperature_high'].set(row['temperature_high'])
                
    def save_thresholds(self):
        """Save all thresholds"""
        if not self.threshold_plant_var.get():
            messagebox.showwarning("Warning", "Please select a plant type")
            return
        
        plant_type_id = int(self.threshold_plant_var.get().split(':')[0])
        
        try:
            cursor = self.conn.cursor()
            
            # Check if updated_at column exists
            cursor.execute("PRAGMA table_info(plant_thresholds)")
            columns = [col[1] for col in cursor.fetchall()]
            has_updated_at = 'updated_at' in columns
            
            for season, vars in self.threshold_vars.items():
                # Validate
                if vars['humidity_low'].get() >= vars['humidity_high'].get():
                    messagebox.showerror("Error", f"{season}: Humidity low must be less than high")
                    return
                
                if vars['temperature_low'].get() >= vars['temperature_high'].get():
                    messagebox.showerror("Error", f"{season}: Temperature low must be less than high")
                    return
                
                if has_updated_at:
                    cursor.execute('''
                        INSERT OR REPLACE INTO plant_thresholds
                        (plant_type_id, season, humidity_low, humidity_high,
                         temperature_low, temperature_high, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (plant_type_id, season, vars['humidity_low'].get(),
                         vars['humidity_high'].get(), vars['temperature_low'].get(),
                         vars['temperature_high'].get()))
                else:
                    cursor.execute('''
                        INSERT OR REPLACE INTO plant_thresholds
                        (plant_type_id, season, humidity_low, humidity_high,
                         temperature_low, temperature_high)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (plant_type_id, season, vars['humidity_low'].get(),
                         vars['humidity_high'].get(), vars['temperature_low'].get(),
                         vars['temperature_high'].get()))
            
            self.conn.commit()
            messagebox.showinfo("Success", "Thresholds saved successfully")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save thresholds: {e}")
            
    # Sensor Readings methods
    def load_plants_for_readings(self):
        """Load plants with sensors for readings filter"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT DISTINCT gp.unique_id, gp.custom_name, pt.name
            FROM garden_plants gp
            JOIN plant_types pt ON gp.plant_type_id = pt.id
            WHERE gp.has_sensor = 1
            ORDER BY gp.unique_id
        ''')
        
        plants = []
        for row in cursor.fetchall():
            name = row['custom_name'] or row['name']
            plants.append(f"{row['unique_id']}: {name}")
        
        self.readings_plant_combo['values'] = ['All'] + plants
        self.readings_plant_combo.set('All')
        
    def load_sensor_readings(self):
        """Load sensor readings based on filters"""
        # Clear existing items
        for item in self.readings_tree.get_children():
            self.readings_tree.delete(item)
        
        # Build query
        query = '''
            SELECT sr.*, gp.custom_name, pt.name as plant_type_name
            FROM sensor_readings sr
            LEFT JOIN garden_plants gp ON sr.garden_plant_id = gp.id
            LEFT JOIN plant_types pt ON gp.plant_type_id = pt.id
            WHERE 1=1
        '''
        params = []
        
        # Apply filters
        if self.readings_plant_var.get() and self.readings_plant_var.get() != 'All':
            unique_id = self.readings_plant_var.get().split(':')[0]
            query += ' AND sr.plant_unique_id = ?'
            params.append(unique_id)
        
        if self.date_from_var.get():
            query += ' AND sr.date >= ?'
            params.append(self.date_from_var.get())
        
        if self.date_to_var.get():
            query += ' AND sr.date <= ?'
            params.append(self.date_to_var.get())
        
        query += ' ORDER BY sr.date DESC, sr.time DESC LIMIT 1000'
        
        # Execute query
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        
        for row in cursor.fetchall():
            plant_name = row['custom_name'] or row['plant_type_name'] or row['plant_unique_id']
            self.readings_tree.insert('', 'end', values=(
                row['id'],
                plant_name,
                row['sensor_name'] or '',
                row['date'],
                row['time'],
                row['temperature'],
                row['humidity'],
                row['battery_charge'],
                'Active' if row['sensor_state'] == 1 else 'Inactive'
            ))
            
    def delete_sensor_reading(self):
        """Delete selected sensor reading"""
        selection = self.readings_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a reading to delete")
            return
        
        if messagebox.askyesno("Confirm Delete", f"Delete {len(selection)} selected reading(s)?"):
            try:
                cursor = self.conn.cursor()
                for item in selection:
                    reading_id = self.readings_tree.item(item)['values'][0]
                    cursor.execute('DELETE FROM sensor_readings WHERE id = ?', (reading_id,))
                
                self.conn.commit()
                self.load_sensor_readings()
                messagebox.showinfo("Success", f"Deleted {len(selection)} reading(s)")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete readings: {e}")
                
    def __del__(self):
        """Clean up database connection"""
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()
    
    # Plant Photos methods
    def load_plants_for_photos(self):
        """Load plants list for photo management"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT gp.id, gp.unique_id, gp.custom_name, pt.name
            FROM garden_plants gp
            JOIN plant_types pt ON gp.plant_type_id = pt.id
            ORDER BY gp.custom_name, pt.name
        ''')
        
        plants = []
        for row in cursor.fetchall():
            name = row['custom_name'] or row['name']
            plants.append(f"{row['id']}: {name} ({row['unique_id']})")
        
        self.photos_plant_combo['values'] = plants
        if plants:
            self.photos_plant_combo.current(0)
            self.load_plant_photos()
    
    def load_plant_photos(self):
        """Load photos for selected plant"""
        # Clear existing items
        for item in self.photos_tree.get_children():
            self.photos_tree.delete(item)
        
        if not self.photos_plant_var.get():
            return
        
        plant_id = int(self.photos_plant_var.get().split(':')[0])
        
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, photo_type, description, date_taken, created_at, file_size
            FROM plant_photos
            WHERE garden_plant_id = ?
            ORDER BY photo_type = 'main' DESC, created_at DESC
        ''', (plant_id,))
        
        for row in cursor.fetchall():
            # Determine display type
            photo_type = row['photo_type']
            if photo_type == 'main':
                type_display = '★ Main'
            else:
                type_display = 'Additional'
            
            self.photos_tree.insert('', 'end', values=(
                row['id'],
                type_display,
                row['description'] or '',
                row['date_taken'] or '',
                row['created_at']
            ), tags=(photo_type,))
        
        # Configure tag colors
        self.photos_tree.tag_configure('main', foreground='darkgreen', font=('Arial', 10, 'bold'))
    
    def add_plant_photos(self):
        """Add photos to selected plant"""
        if not self.photos_plant_var.get():
            messagebox.showwarning("Warning", "Please select a plant first")
            return
        
        plant_id = int(self.photos_plant_var.get().split(':')[0])
        
        # Select multiple files
        file_paths = filedialog.askopenfilenames(
            title="Select Photos",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.gif *.bmp"), ("All files", "*.*")]
        )
        
        if not file_paths:
            return
        
        added_count = 0
        cursor = self.conn.cursor()
        
        # Check if plant has main photo
        cursor.execute('''
            SELECT COUNT(*) FROM plant_photos 
            WHERE garden_plant_id = ? AND photo_type = 'main'
        ''', (plant_id,))
        has_main = cursor.fetchone()[0] > 0
        
        for i, file_path in enumerate(file_paths):
            try:
                # Read file data
                with open(file_path, 'rb') as f:
                    photo_data = f.read()
                
                # Get file date
                file_mtime = os.path.getmtime(file_path)
                date_taken = datetime.fromtimestamp(file_mtime).strftime('%Y-%m-%d %H:%M:%S')
                
                # Determine photo type - first photo becomes main if no main exists
                photo_type = 'main' if (i == 0 and not has_main) else 'additional'
                if photo_type == 'main':
                    has_main = True
                
                # Insert into database with blob data
                cursor.execute('''
                    INSERT INTO plant_photos 
                    (garden_plant_id, photo_data, photo_type, description, date_taken, file_size)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (plant_id, photo_data, photo_type, 
                     f"Photo {added_count + 1}", date_taken, len(photo_data)))
                
                added_count += 1
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to add photo {os.path.basename(file_path)}: {e}")
        
        if added_count > 0:
            self.conn.commit()
            self.load_plant_photos()
            messagebox.showinfo("Success", f"Added {added_count} photo(s)")
            
            # Update photo display if we're on Garden Plants tab
            if self.notebook.index('current') == 1:
                self.on_plant_select(None)
    
    def delete_plant_photo(self):
        """Delete selected photo"""
        selection = self.photos_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a photo to delete")
            return
        
        if messagebox.askyesno("Confirm Delete", "Delete selected photo?"):
            try:
                cursor = self.conn.cursor()
                
                for item in selection:
                    photo_id = self.photos_tree.item(item)['values'][0]
                    
                    # Delete from database
                    cursor.execute('DELETE FROM plant_photos WHERE id = ?', (photo_id,))
                
                self.conn.commit()
                self.load_plant_photos()
                messagebox.showinfo("Success", "Photo(s) deleted successfully")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete photo: {e}")
    
    def set_primary_photo(self):
        """Set selected photo as primary"""
        selection = self.photos_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a photo")
            return
        
        item = self.photos_tree.item(selection[0])
        photo_id = item['values'][0]
        
        if not self.photos_plant_var.get():
            return
        
        plant_id = int(self.photos_plant_var.get().split(':')[0])
        
        try:
            cursor = self.conn.cursor()
            
            # Reset all photos for this plant to additional
            cursor.execute('''
                UPDATE plant_photos 
                SET photo_type = 'additional'
                WHERE garden_plant_id = ?
            ''', (plant_id,))
            
            # Set selected photo as main
            cursor.execute('''
                UPDATE plant_photos 
                SET photo_type = 'main'
                WHERE id = ?
            ''', (photo_id,))
            
            self.conn.commit()
            self.load_plant_photos()
            messagebox.showinfo("Success", "Photo set as main")
            
            # Update display if on Garden Plants tab
            if self.notebook.index('current') == 1:
                self.on_plant_select(None)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update photo: {e}")
    
    def view_photo(self):
        """View selected photo in window"""
        selection = self.photos_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a photo to view")
            return
        
        item = self.photos_tree.item(selection[0])
        photo_id = item['values'][0]
        
        cursor = self.conn.cursor()
        cursor.execute('SELECT photo_data FROM plant_photos WHERE id = ?', (photo_id,))
        result = cursor.fetchone()
        
        if result and result['photo_data']:
            try:
                # Create a new window to display the photo
                photo_window = tk.Toplevel(self.root)
                photo_window.title("Photo Viewer")
                
                # Load image from blob
                image = Image.open(io.BytesIO(result['photo_data']))
                
                # Calculate size for display (max 800x600)
                display_size = list(image.size)
                max_width, max_height = 800, 600
                
                if display_size[0] > max_width:
                    ratio = max_width / display_size[0]
                    display_size[0] = max_width
                    display_size[1] = int(display_size[1] * ratio)
                
                if display_size[1] > max_height:
                    ratio = max_height / display_size[1]
                    display_size[1] = max_height
                    display_size[0] = int(display_size[0] * ratio)
                
                image = image.resize(display_size, Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                
                label = tk.Label(photo_window, image=photo)
                label.image = photo  # Keep a reference
                label.pack()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to display photo: {e}")
        else:
            messagebox.showerror("Error", "Photo data not found")
    
    def on_photo_select(self, event):
        """Handle photo selection to show preview"""
        selection = self.photos_tree.selection()
        if not selection:
            self.photo_preview_label.config(image='', text='No photo selected')
            self.photo_info_label.config(text='')
            return
        
        item = self.photos_tree.item(selection[0])
        photo_id = item['values'][0]
        
        # Get photo info
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT photo_data, photo_type, description, date_taken, file_size 
            FROM plant_photos WHERE id = ?
        ''', (photo_id,))
        
        row = cursor.fetchone()
        if not row:
            return
        
        # Update info label
        info_text = f"Type: {row['photo_type']}\n"
        if row['description']:
            info_text += f"Description: {row['description']}\n"
        if row['date_taken']:
            info_text += f"Date taken: {row['date_taken']}\n"
        if row['file_size']:
            info_text += f"Size: {row['file_size']:,} bytes"
        self.photo_info_label.config(text=info_text)
        
        # Show preview
        if row['photo_data']:
            try:
                # Load image from blob
                image = Image.open(io.BytesIO(row['photo_data']))
                
                # Calculate thumbnail size maintaining aspect ratio
                max_size = (280, 280)
                image.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                photo = ImageTk.PhotoImage(image)
                self.photo_preview_label.config(image=photo, text='')
                self.photo_preview_label.image = photo
            except Exception as e:
                self.photo_preview_label.config(image='', text=f'Error loading image:\n{e}')
        else:
            self.photo_preview_label.config(image='', text='No photo data')


# Dialog classes
class PlantTypeDialog:
    def __init__(self, parent, title, initial_data=None):
        self.result = None
        
        # Create dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("400x200")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Center dialog
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (self.dialog.winfo_width() // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (self.dialog.winfo_height() // 2)
        self.dialog.geometry(f"+{x}+{y}")
        
        # Create form
        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill='both', expand=True)
        
        ttk.Label(main_frame, text="Name:").grid(row=0, column=0, sticky='e', padx=5, pady=5)
        self.name_var = tk.StringVar(value=initial_data['name'] if initial_data else '')
        ttk.Entry(main_frame, textvariable=self.name_var, width=30).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(main_frame, text="Latin Name:").grid(row=1, column=0, sticky='e', padx=5, pady=5)
        self.latin_var = tk.StringVar(value=initial_data['latin_name'] if initial_data else '')
        ttk.Entry(main_frame, textvariable=self.latin_var, width=30).grid(row=1, column=1, padx=5, pady=5)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=20)
        
        ttk.Button(button_frame, text="Save", command=self.save).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.cancel).pack(side='left', padx=5)
        
        # Focus on name field
        self.dialog.after(100, lambda: self.name_var.set(self.name_var.get()))
        
    def save(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Name is required", parent=self.dialog)
            return
        
        self.result = {
            'name': name,
            'latin_name': self.latin_var.get().strip()
        }
        self.dialog.destroy()
        
    def cancel(self):
        self.dialog.destroy()


class GardenPlantDialog:
    def __init__(self, parent, title, conn, plant_data=None):
        self.result = None
        self.conn = conn
        
        # Create dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("500x400")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Center dialog
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (self.dialog.winfo_width() // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (self.dialog.winfo_height() // 2)
        self.dialog.geometry(f"+{x}+{y}")
        
        # Create form
        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill='both', expand=True)
        
        # Plant Type
        ttk.Label(main_frame, text="Plant Type:").grid(row=0, column=0, sticky='e', padx=5, pady=5)
        self.plant_type_var = tk.StringVar()
        self.plant_type_combo = ttk.Combobox(main_frame, textvariable=self.plant_type_var,
                                            state='readonly', width=30)
        self.plant_type_combo.grid(row=0, column=1, padx=5, pady=5)
        
        # Load plant types
        cursor = conn.cursor()
        cursor.execute('SELECT id, name FROM plant_types ORDER BY name')
        plant_types = cursor.fetchall()
        self.plant_type_combo['values'] = [f"{pt['id']}: {pt['name']}" for pt in plant_types]
        
        # Position
        ttk.Label(main_frame, text="Position X:").grid(row=1, column=0, sticky='e', padx=5, pady=5)
        self.pos_x_var = tk.IntVar(value=plant_data['position_x'] if plant_data else 100)
        ttk.Spinbox(main_frame, from_=0, to=5000, textvariable=self.pos_x_var,
                   width=10).grid(row=1, column=1, sticky='w', padx=5, pady=5)
        
        ttk.Label(main_frame, text="Position Y:").grid(row=2, column=0, sticky='e', padx=5, pady=5)
        self.pos_y_var = tk.IntVar(value=plant_data['position_y'] if plant_data else 100)
        ttk.Spinbox(main_frame, from_=0, to=5000, textvariable=self.pos_y_var,
                   width=10).grid(row=2, column=1, sticky='w', padx=5, pady=5)
        
        # Custom Name
        ttk.Label(main_frame, text="Custom Name:").grid(row=3, column=0, sticky='e', padx=5, pady=5)
        self.custom_name_var = tk.StringVar(value=plant_data['custom_name'] if plant_data else '')
        ttk.Entry(main_frame, textvariable=self.custom_name_var, width=30).grid(row=3, column=1, padx=5, pady=5)
        
        # Sensor
        self.has_sensor_var = tk.BooleanVar(value=plant_data['has_sensor'] if plant_data else False)
        ttk.Checkbutton(main_frame, text="Has Sensor", variable=self.has_sensor_var,
                       command=self.toggle_sensor_fields).grid(row=4, column=0, columnspan=2, pady=10)
        
        ttk.Label(main_frame, text="Sensor ID:").grid(row=5, column=0, sticky='e', padx=5, pady=5)
        self.sensor_id_var = tk.StringVar(value=plant_data['sensor_id'] if plant_data else '')
        self.sensor_id_entry = ttk.Entry(main_frame, textvariable=self.sensor_id_var, width=30)
        self.sensor_id_entry.grid(row=5, column=1, padx=5, pady=5)
        
        ttk.Label(main_frame, text="Sensor Name:").grid(row=6, column=0, sticky='e', padx=5, pady=5)
        self.sensor_name_var = tk.StringVar(value=plant_data['sensor_name'] if plant_data else '')
        self.sensor_name_entry = ttk.Entry(main_frame, textvariable=self.sensor_name_var, width=30)
        self.sensor_name_entry.grid(row=6, column=1, padx=5, pady=5)
        
        # Set initial plant type
        if plant_data:
            for i, value in enumerate(self.plant_type_combo['values']):
                if value.startswith(f"{plant_data['plant_type_id']}:"):
                    self.plant_type_combo.current(i)
                    break
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=7, column=0, columnspan=2, pady=20)
        
        ttk.Button(button_frame, text="Save", command=self.save).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.cancel).pack(side='left', padx=5)
        
        # Initialize sensor fields state
        self.toggle_sensor_fields()
        
    def toggle_sensor_fields(self):
        state = 'normal' if self.has_sensor_var.get() else 'disabled'
        self.sensor_id_entry.config(state=state)
        self.sensor_name_entry.config(state=state)
        
    def save(self):
        if not self.plant_type_var.get():
            messagebox.showerror("Error", "Please select a plant type", parent=self.dialog)
            return
        
        if self.has_sensor_var.get():
            if not self.sensor_id_var.get() or len(self.sensor_id_var.get()) != 22:
                messagebox.showerror("Error", "Sensor ID must be exactly 22 characters", parent=self.dialog)
                return
            
            if not self.sensor_name_var.get():
                messagebox.showerror("Error", "Sensor name is required", parent=self.dialog)
                return
        
        self.result = {
            'plant_type_id': int(self.plant_type_var.get().split(':')[0]),
            'position_x': self.pos_x_var.get(),
            'position_y': self.pos_y_var.get(),
            'custom_name': self.custom_name_var.get().strip(),
            'has_sensor': self.has_sensor_var.get(),
            'sensor_id': self.sensor_id_var.get().strip() if self.has_sensor_var.get() else None,
            'sensor_name': self.sensor_name_var.get().strip() if self.has_sensor_var.get() else None
        }
        self.dialog.destroy()
        
    def cancel(self):
        self.dialog.destroy()


class SensorDialog:
    def __init__(self, parent, sensor_data):
        self.result = None
        
        # Create dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Configure Sensor")
        self.dialog.geometry("400x250")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Center dialog
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (self.dialog.winfo_width() // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (self.dialog.winfo_height() // 2)
        self.dialog.geometry(f"+{x}+{y}")
        
        # Create form
        main_frame = ttk.Frame(self.dialog, padding=20)
        main_frame.pack(fill='both', expand=True)
        
        self.has_sensor_var = tk.BooleanVar(value=sensor_data['has_sensor'])
        ttk.Checkbutton(main_frame, text="Has Sensor", variable=self.has_sensor_var,
                       command=self.toggle_fields).pack(pady=10)
        
        # Sensor fields
        fields_frame = ttk.Frame(main_frame)
        fields_frame.pack(fill='x', pady=10)
        
        ttk.Label(fields_frame, text="Sensor ID (22 chars):").grid(row=0, column=0, sticky='e', padx=5, pady=5)
        self.sensor_id_var = tk.StringVar(value=sensor_data['sensor_id'] or '')
        self.sensor_id_entry = ttk.Entry(fields_frame, textvariable=self.sensor_id_var, width=30)
        self.sensor_id_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(fields_frame, text="Sensor Name:").grid(row=1, column=0, sticky='e', padx=5, pady=5)
        self.sensor_name_var = tk.StringVar(value=sensor_data['sensor_name'] or '')
        self.sensor_name_entry = ttk.Entry(fields_frame, textvariable=self.sensor_name_var, width=30)
        self.sensor_name_entry.grid(row=1, column=1, padx=5, pady=5)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=20)
        
        ttk.Button(button_frame, text="Save", command=self.save).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.cancel).pack(side='left', padx=5)
        
        # Initialize fields state
        self.toggle_fields()
        
    def toggle_fields(self):
        state = 'normal' if self.has_sensor_var.get() else 'disabled'
        self.sensor_id_entry.config(state=state)
        self.sensor_name_entry.config(state=state)
        
    def save(self):
        if self.has_sensor_var.get():
            if not self.sensor_id_var.get() or len(self.sensor_id_var.get()) != 22:
                messagebox.showerror("Error", "Sensor ID must be exactly 22 characters", parent=self.dialog)
                return
            
            if not self.sensor_name_var.get():
                messagebox.showerror("Error", "Sensor name is required", parent=self.dialog)
                return
        
        self.result = {
            'has_sensor': self.has_sensor_var.get(),
            'sensor_id': self.sensor_id_var.get() if self.has_sensor_var.get() else None,
            'sensor_name': self.sensor_name_var.get() if self.has_sensor_var.get() else None
        }
        self.dialog.destroy()
        
    def cancel(self):
        self.dialog.destroy()


# Main execution
if __name__ == "__main__":
    root = tk.Tk()
    app = GardenDatabaseManager(root)
    root.mainloop()