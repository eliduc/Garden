#!/usr/bin/env python3
"""
Plant Database Identifier using Multiple AI Models
Processes plant photos from database and updates plant information
Now supports both local and remote database connections via SSH
"""

import os
import base64
import configparser
import sqlite3
import anthropic
from typing import List, Dict, Optional, OrderedDict
import json
import time
from collections import OrderedDict
import statistics
import io
from PIL import Image
import paramiko
import tempfile
import threading

# Configuration
CONFIG_FILE = 'garden.ini'
DB_FILE = 'garden_sensors.db'
MAX_IMAGES_PER_REQUEST = 5  # AI models have limits on number of images

# Remote connection variables
ssh_client = None
sftp_client = None
remote_mode = False
remote_db_path = None
local_temp_db = None
db_file_path = DB_FILE
has_db_changes = False

# Model configurations
MODEL_CONFIGS = {
    'Claude': {'model': 'claude-3-5-sonnet-20241022', 'name': 'Claude Sonnet 3.5'},
    'OpenAI': {'model': 'gpt-4o', 'name': 'OpenAI GPT-4o'},
    'Gemini': {'model': 'gemini-1.5-pro', 'name': 'Google Gemini 1.5 Pro'},
    'PlantNet': {'model': 'plantnet-api', 'name': 'PlantNet API'}
}

def show_progress(message, progress=0):
    """Show progress message (console-based for CLI tool)"""
    bar_length = 50
    filled_length = int(bar_length * progress / 100)
    bar = '█' * filled_length + '-' * (bar_length - filled_length)
    print(f'\r{message} |{bar}| {progress:.1f}%', end='', flush=True)
    if progress >= 100:
        print()  # New line when complete

def choose_database_mode():
    """Choose between local and remote database"""
    global remote_mode, ssh_client, sftp_client, remote_db_path, local_temp_db, db_file_path
    
    print("Plant Database Identifier")
    print("=" * 25)
    print("\nSelect database connection mode:")
    print("1. Local Database")
    print("2. Remote Database (SSH)")
    
    while True:
        try:
            choice = input("\nEnter choice (1-2): ").strip()
            if choice in ['1', '2']:
                break
            print("Invalid choice. Please enter 1 or 2.")
        except KeyboardInterrupt:
            print("\nExiting...")
            return False
    
    if choice == '1':
        # Local mode
        remote_mode = False
        db_file_path = DB_FILE
        if not os.path.exists(DB_FILE):
            print(f"Warning: Local database '{DB_FILE}' not found!")
            return False
        print(f"Using local database: {DB_FILE}")
        return True
    
    else:
        # Remote mode
        return setup_remote_connection()

def setup_remote_connection():
    """Setup remote SSH connection and database"""
    global ssh_client, sftp_client, remote_db_path, local_temp_db, db_file_path, remote_mode
    
    # Read config for default values
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    
    default_login = ""
    default_dir = ""
    try:
        default_login = config.get('Remote', 'login')
        default_dir = config.get('Remote', 'dir')
    except (configparser.NoSectionError, configparser.NoOptionError):
        pass
    
    print("\nRemote Database Connection Setup")
    print("-" * 35)
    
    # Get connection details
    login = input(f"Login (user@host) [{default_login}]: ").strip() or default_login
    if not login:
        print("Error: Login is required")
        return False
    
    if '@' not in login:
        print("Error: Login format should be username@hostname")
        return False
    
    username, hostname = login.split('@', 1)
    
    remote_dir = input(f"Remote directory [{default_dir}]: ").strip() or default_dir
    if not remote_dir:
        print("Error: Remote directory is required")
        return False
    
    # Get password
    import getpass
    password = getpass.getpass("Password: ")
    if not password:
        print("Error: Password is required")
        return False
    
    max_attempts = 3
    for attempt in range(max_attempts):
        print(f"\nConnecting to {hostname}... (Attempt {attempt + 1}/{max_attempts})")
        
        try:
            # Create SSH client
            ssh_client = paramiko.SSHClient()
            ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect
            ssh_client.connect(hostname, username=username, password=password, compress=True)
            print("✓ SSH connection established")
            
            # Open SFTP
            sftp_client = ssh_client.open_sftp()
            print("✓ SFTP connection established")
            
            # Check remote database
            remote_db_path = os.path.join(remote_dir, DB_FILE).replace('\\', '/')
            
            try:
                file_stat = sftp_client.stat(remote_db_path)
                file_size = file_stat.st_size
                file_size_mb = file_size / (1024 * 1024)
                print(f"✓ Found remote database ({file_size_mb:.1f} MB)")
                
            except FileNotFoundError:
                print("! Remote database not found - this may be a new setup")
                file_size = 0
            
            # Download database
            print("Downloading database...")
            local_temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
            local_temp_db.close()
            
            if file_size > 0:
                def download_callback(transferred, total):
                    progress = (transferred * 100 / total)
                    show_progress("Downloading", progress)
                
                sftp_client.get(remote_db_path, local_temp_db.name, callback=download_callback)
            else:
                # Create empty database file
                temp_conn = sqlite3.connect(local_temp_db.name)
                temp_conn.close()
                print("Created new local temporary database")
            
            db_file_path = local_temp_db.name
            
            # Save settings to config
            if not config.has_section('Remote'):
                config.add_section('Remote')
            config.set('Remote', 'login', login)
            config.set('Remote', 'dir', remote_dir)
            
            with open(CONFIG_FILE, 'w') as f:
                config.write(f)
            
            print("✓ Remote database setup complete!")
            remote_mode = True
            return True
            
        except paramiko.AuthenticationException:
            print(f"✗ Authentication failed")
            if ssh_client:
                ssh_client.close()
                ssh_client = None
            
            if attempt < max_attempts - 1:
                print(f"Retrying... ({max_attempts - attempt - 1} attempts remaining)")
                password = getpass.getpass("Password: ")
                if not password:
                    break
            else:
                print("Maximum authentication attempts reached")
                return False
                
        except Exception as e:
            print(f"✗ Connection error: {str(e)}")
            if ssh_client:
                ssh_client.close()
                ssh_client = None
            return False
    
    return False

def sync_remote_database():
    """Sync local temp database with remote"""
    global sftp_client, local_temp_db, remote_db_path, has_db_changes
    
    if not remote_mode or not sftp_client or not has_db_changes:
        if remote_mode and not has_db_changes:
            print("No database changes to sync")
        return True
    
    try:
        print("\nSyncing database with remote server...")
        
        # Ensure all database connections are closed before sync
        import gc
        gc.collect()
        
        # Get file size for progress
        if not os.path.exists(local_temp_db.name):
            print("✗ Local temporary database file not found!")
            return False
            
        file_size = os.path.getsize(local_temp_db.name)
        file_size_mb = file_size / (1024 * 1024)
        print(f"Syncing database file ({file_size_mb:.2f} MB)...")
        
        # Create backup of remote database first
        backup_path = remote_db_path + '.backup'
        try:
            sftp_client.rename(remote_db_path, backup_path)
            print("✓ Created backup of remote database")
        except FileNotFoundError:
            print("! No existing remote database to backup")
        except Exception as e:
            print(f"! Warning: Could not create backup: {e}")
        
        # Upload with progress callback
        uploaded_bytes = [0]
        def upload_callback(transferred, total):
            uploaded_bytes[0] = transferred
            progress = (transferred * 100 / total)
            show_progress(f"Uploading ({file_size_mb:.1f} MB)", progress)
        
        # Upload temp file to remote
        sftp_client.put(local_temp_db.name, remote_db_path, callback=upload_callback)
        
        # Verify upload
        try:
            remote_stat = sftp_client.stat(remote_db_path)
            if remote_stat.st_size == file_size:
                print("\n✓ Database sync complete and verified!")
                has_db_changes = False
                
                # Remove backup if upload successful
                try:
                    sftp_client.remove(backup_path)
                    print("✓ Backup cleanup complete")
                except:
                    pass  # Backup cleanup is not critical
                    
                return True
            else:
                print(f"\n✗ Sync verification failed! Local: {file_size}, Remote: {remote_stat.st_size}")
                return False
        except Exception as e:
            print(f"\n✗ Sync verification failed: {e}")
            return False
        
    except Exception as e:
        print(f"\n✗ Sync failed: {str(e)}")
        
        # Try to restore backup if sync failed
        try:
            backup_path = remote_db_path + '.backup'
            sftp_client.rename(backup_path, remote_db_path)
            print("✓ Restored backup due to sync failure")
        except:
            print("! Could not restore backup - manual intervention may be needed")
        
        return False

def cleanup_ssh():
    """Clean up SSH connection and temp files"""
    global ssh_client, sftp_client, local_temp_db
    
    if sftp_client:
        try:
            sftp_client.close()
        except:
            pass
    
    if ssh_client:
        try:
            ssh_client.close()
        except:
            pass
    
    if local_temp_db and os.path.exists(local_temp_db.name):
        try:
            os.unlink(local_temp_db.name)
        except:
            pass

def get_db_connection():
    """Create a database connection with timeout"""
    conn = sqlite3.connect(db_file_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrency
    conn.execute('PRAGMA journal_mode=WAL')
    return conn

def mark_db_changed():
    """Mark that database has been changed"""
    global has_db_changes
    has_db_changes = True
    if remote_mode:
        print(f"    Database marked as changed (will sync at end)")

def load_api_keys() -> OrderedDict:
    """Load API keys from garden.ini preserving order"""
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    
    api_keys = OrderedDict()
    
    if not config.has_section('API Keys'):
        print("Error: No [API Keys] section found in garden.ini")
        return api_keys
    
    # Get items in order they appear in the file
    for key, value in config.items('API Keys'):
        # Handle case conversion properly
        key_lower = key.lower()
        if key_lower == 'claude':
            api_keys['Claude'] = value.strip()
        elif key_lower == 'openai':
            api_keys['OpenAI'] = value.strip()
        elif key_lower == 'gemini':
            api_keys['Gemini'] = value.strip()
        elif key_lower == 'plantnet':
            api_keys['PlantNet'] = value.strip()
    
    if not api_keys:
        print("Error: No valid API keys found in garden.ini")
        print("Supported keys: Claude, OpenAI, Gemini, PlantNet")
    else:
        print(f"Found API keys for: {', '.join(api_keys.keys())}")
        print(f"Primary model: {list(api_keys.keys())[0]}")
    
    return api_keys

def get_plants_from_db():
    """Get all plant types from database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT DISTINCT pt.id, pt.name, pt.latin_name
        FROM plant_types pt
        ORDER BY pt.name
    ''')
    
    plants = []
    for row in cursor.fetchall():
        plants.append({
            'id': row['id'],
            'name': row['name'],
            'latin_name': row['latin_name']
        })
    
    conn.close()
    return plants

def get_plant_photos(plant_type_id: int) -> List[bytes]:
    """Get all photos for a plant type from database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get photos from garden_plants that have this plant_type_id
    cursor.execute('''
        SELECT pp.photo_data
        FROM plant_photos pp
        JOIN garden_plants gp ON pp.garden_plant_id = gp.id
        WHERE gp.plant_type_id = ?
        ORDER BY pp.photo_type ASC, pp.id DESC
        LIMIT ?
    ''', (plant_type_id, MAX_IMAGES_PER_REQUEST))
    
    photos = []
    for row in cursor.fetchall():
        if row['photo_data']:
            photos.append(row['photo_data'])
    
    conn.close()
    return photos

def prepare_image_for_ai(photo_data: bytes) -> tuple:
    """Prepare image data for AI models (resize if needed and convert to base64)"""
    try:
        # Open image from bytes
        img = Image.open(io.BytesIO(photo_data))
        
        # Convert RGBA to RGB if necessary
        if img.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        
        # Resize if too large
        max_size = (1024, 1024)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Save to bytes
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=85)
        jpeg_data = output.getvalue()
        
        # Convert to base64
        base64_image = base64.b64encode(jpeg_data).decode('utf-8')
        
        return base64_image, 'image/jpeg'
    except Exception as e:
        print(f"    Error processing image: {e}")
        return None, None

def get_identification_prompt(plant_name: str) -> str:
    """Get the prompt for plant identification"""
    return f"""Please identify this plant/tree from the images provided. The plant is currently named '{plant_name}' in our database.

Please provide:
1. Latin name (scientific name)
2. Italian name (nome italiano)
3. English name
4. Brief description
5. Soil temperature and humidity requirements for Rome, Italy climate

For the soil requirements, provide the acceptable ranges of:
- Soil temperature (Tmin and Tmax in °C)
- Soil humidity/moisture (Hmin and Hmax in %)

These should be specific for the Rome, Italy location (Mediterranean climate, USDA zone 9b-10a) for each season.

Format your response as JSON:
{{
    "latin_name": "...",
    "italian_name": "...",
    "english_name": "...",
    "description": "...",
    "soil_requirements": {{
        "Summer": {{
            "Tmin": 15,
            "Tmax": 30,
            "Hmin": 20,
            "Hmax": 60
        }},
        "Autumn": {{
            "Tmin": 10,
            "Tmax": 25,
            "Hmin": 30,
            "Hmax": 70
        }},
        "Winter": {{
            "Tmin": 5,
            "Tmax": 15,
            "Hmin": 40,
            "Hmax": 80
        }},
        "Spring": {{
            "Tmin": 10,
            "Tmax": 25,
            "Hmin": 30,
            "Hmax": 70
        }}
    }}
}}

Please provide realistic values based on the plant's actual needs in Rome's Mediterranean climate."""

def get_soil_requirements_prompt(plant_info: Dict[str, str]) -> str:
    """Get the prompt for soil requirements when plant is already identified"""
    return f"""I need soil temperature and humidity requirements for the following plant in Rome, Italy climate:

Scientific name: {plant_info['scientific_name']}
Family: {plant_info['family']}
Genus: {plant_info['genus']}

Please provide the acceptable ranges of:
- Soil temperature (Tmin and Tmax in °C)
- Soil humidity/moisture (Hmin and Hmax in %)

These should be specific for the Rome, Italy location (Mediterranean climate, USDA zone 9b-10a) for each season.

Format your response as JSON:
{{
    "latin_name": "{plant_info['scientific_name']}",
    "italian_name": "...",
    "english_name": "...",
    "description": "...",
    "soil_requirements": {{
        "Summer": {{
            "Tmin": 15,
            "Tmax": 30,
            "Hmin": 20,
            "Hmax": 60
        }},
        "Autumn": {{
            "Tmin": 10,
            "Tmax": 25,
            "Hmin": 30,
            "Hmax": 70
        }},
        "Winter": {{
            "Tmin": 5,
            "Tmax": 15,
            "Hmin": 40,
            "Hmax": 80
        }},
        "Spring": {{
            "Tmin": 10,
            "Tmax": 25,
            "Hmin": 30,
            "Hmax": 70
        }}
    }}
}}

Please provide realistic values based on this plant's actual needs in Rome's Mediterranean climate."""

def identify_plant_claude(api_key: str, photos: List[bytes], plant_name: str, plant_info: Dict[str, str] = None) -> Dict[str, any]:
    """Send photos or plant info to Claude and get plant identification"""
    client = anthropic.Anthropic(api_key=api_key)
    
    if plant_info:
        # Use plant info instead of images
        prompt = get_soil_requirements_prompt(plant_info)
        try:
            message = client.messages.create(
                model=MODEL_CONFIGS['Claude']['model'],
                max_tokens=1500,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
        except Exception as e:
            print(f"    Error calling Claude API: {e}")
            return None
    else:
        # Original image-based identification
        image_content = []
        
        for photo_data in photos[:MAX_IMAGES_PER_REQUEST]:
            base64_image, media_type = prepare_image_for_ai(photo_data)
            if base64_image:
                image_content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64_image
                    }
                })
        
        if not image_content:
            return None
        
        prompt = get_identification_prompt(plant_name)
        
        try:
            message = client.messages.create(
                model=MODEL_CONFIGS['Claude']['model'],
                max_tokens=1500,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        *image_content
                    ]
                }]
            )
        except Exception as e:
            print(f"    Error calling Claude API: {e}")
            return None
    
    # Extract JSON from response
    response_text = message.content[0].text
    
    # Try to parse JSON from the response
    try:
        start = response_text.find('{')
        end = response_text.rfind('}') + 1
        if start != -1 and end > start:
            json_str = response_text[start:end]
            return json.loads(json_str)
    except json.JSONDecodeError:
        pass
        
    return None

def identify_plant_openai(api_key: str, photos: List[bytes], plant_name: str, plant_info: Dict[str, str] = None) -> Dict[str, any]:
    """Send photos or plant info to OpenAI and get plant identification"""
    try:
        import openai
    except ImportError:
        print("    OpenAI library not installed. Run: pip install openai")
        return None
    
    client = openai.OpenAI(api_key=api_key)
    
    if plant_info:
        # Use plant info instead of images
        prompt = get_soil_requirements_prompt(plant_info)
        try:
            response = client.chat.completions.create(
                model=MODEL_CONFIGS['OpenAI']['model'],
                messages=[{
                    "role": "user",
                    "content": prompt
                }],
                max_tokens=1500
            )
        except Exception as e:
            print(f"    Error calling OpenAI API: {e}")
            return None
    else:
        # Original image-based identification
        image_content = []
        
        for photo_data in photos[:MAX_IMAGES_PER_REQUEST]:
            base64_image, media_type = prepare_image_for_ai(photo_data)
            if base64_image:
                image_content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{base64_image}"
                    }
                })
        
        if not image_content:
            return None
        
        prompt = get_identification_prompt(plant_name)
        
        try:
            response = client.chat.completions.create(
                model=MODEL_CONFIGS['OpenAI']['model'],
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        *image_content
                    ]
                }],
                max_tokens=1500
            )
        except Exception as e:
            print(f"    Error calling OpenAI API: {e}")
            return None
    
    response_text = response.choices[0].message.content
    
    # Try to parse JSON from the response
    try:
        start = response_text.find('{')
        end = response_text.rfind('}') + 1
        if start != -1 and end > start:
            json_str = response_text[start:end]
            return json.loads(json_str)
    except json.JSONDecodeError:
        pass
        
    return None

def identify_plant_gemini(api_key: str, photos: List[bytes], plant_name: str, plant_info: Dict[str, str] = None) -> Dict[str, any]:
    """Send photos or plant info to Gemini and get plant identification"""
    try:
        import google.generativeai as genai
    except ImportError:
        print("    Google Generative AI library not installed. Run: pip install google-generativeai")
        return None
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODEL_CONFIGS['Gemini']['model'])
    
    if plant_info:
        # Use plant info instead of images
        prompt = get_soil_requirements_prompt(plant_info)
        try:
            response = model.generate_content(prompt)
            response_text = response.text
        except Exception as e:
            print(f"    Error calling Gemini API: {e}")
            return None
    else:
        # Original image-based identification
        image_parts = []
        
        for photo_data in photos[:MAX_IMAGES_PER_REQUEST]:
            try:
                # Prepare image for Gemini
                img = Image.open(io.BytesIO(photo_data))
                # Gemini expects PIL images
                image_parts.append(img)
            except Exception as e:
                print(f"    Error preparing image: {e}")
        
        if not image_parts:
            return None
        
        prompt = get_identification_prompt(plant_name)
        
        try:
            # Prepare content for Gemini
            content = [prompt] + image_parts
            
            response = model.generate_content(content)
            response_text = response.text
        except Exception as e:
            print(f"    Error calling Gemini API: {e}")
            return None
    
    # Try to parse JSON from the response
    try:
        start = response_text.find('{')
        end = response_text.rfind('}') + 1
        if start != -1 and end > start:
            json_str = response_text[start:end]
            return json.loads(json_str)
    except json.JSONDecodeError:
        pass
        
    return None

def identify_plant_plantnet(api_key: str, photos: List[bytes], plant_name: str) -> Dict[str, any]:
    """Send photos to PlantNet and get plant identification"""
    try:
        import requests
    except ImportError:
        print("    Requests library not installed. Run: pip install requests")
        return None
    
    PROJECT = "all"  # Use all flora databases
    api_endpoint = f"https://my-api.plantnet.org/v2/identify/{PROJECT}?api-key={api_key}"
    
    # Prepare image files
    files = []
    organs = []
    
    for idx, photo_data in enumerate(photos[:MAX_IMAGES_PER_REQUEST]):
        try:
            # Convert photo data to file-like object
            files.append(('images', (f'photo_{idx}.jpg', io.BytesIO(photo_data), 'image/jpeg')))
            organs.append('auto')
        except Exception as e:
            print(f"    Error preparing image: {e}")
    
    if not files:
        return None
    
    # PlantNet data
    data = {'organs': organs}
    
    try:
        print(f"    Sending {len(files)} images to PlantNet...")
        response = requests.post(api_endpoint, files=files, data=data, timeout=30)
        
        if response.status_code == 200:
            json_result = response.json()
            print(f"    Got response from PlantNet")
            
            # Extract all results
            all_species = []
            if 'results' in json_result:
                for idx, result in enumerate(json_result['results']):
                    score = result.get('score', 0)
                    species = result.get('species', {})
                    
                    species_info = {
                        'scientific_name': species.get('scientificNameWithoutAuthor', 'Unknown'),
                        'author': species.get('scientificNameAuthorship', ''),
                        'family': species.get('family', {}).get('scientificNameWithoutAuthor', 'Unknown'),
                        'genus': species.get('genus', {}).get('scientificNameWithoutAuthor', 'Unknown'),
                        'common_names': species.get('commonNames', []),
                        'score': score
                    }
                    all_species.append(species_info)
                    
                    if idx == 0:
                        print(f"    Top result: {species_info['scientific_name']} (score: {score:.3f})")
            
            if all_species:
                # Format response to match our standard format
                top_species = all_species[0]
                result = {
                    "latin_name": top_species['scientific_name'],
                    "italian_name": "Non disponibile da PlantNet",
                    "english_name": top_species['common_names'][0] if top_species['common_names'] else 'Unknown',
                    "description": f"Identified by PlantNet with {top_species['score']:.1%} confidence. Family: {top_species['family']}",
                    "plantnet_score": top_species['score'],
                    "plantnet_all_species": all_species,
                    "plantnet_full_result": json_result
                }
                
                return result
            else:
                print(f"    No results from PlantNet")
                return None
        else:
            print(f"    PlantNet API error: {response.status_code}")
            print(f"    Response: {response.text[:200]}...")
            return None
            
    except requests.exceptions.Timeout:
        print(f"    PlantNet API timeout")
        return None
    except Exception as e:
        print(f"    Error calling PlantNet API: {e}")
        return None

def identify_plant(model_name: str, api_key: str, photos: List[bytes], plant_name: str, plant_info: Dict[str, str] = None) -> Dict[str, any]:
    """Route to appropriate model function"""
    if model_name == 'Claude':
        return identify_plant_claude(api_key, photos, plant_name, plant_info)
    elif model_name == 'OpenAI':
        return identify_plant_openai(api_key, photos, plant_name, plant_info)
    elif model_name == 'Gemini':
        return identify_plant_gemini(api_key, photos, plant_name, plant_info)
    elif model_name == 'PlantNet':
        return identify_plant_plantnet(api_key, photos, plant_name)
    else:
        print(f"    Unknown model: {model_name}")
        return None

def calculate_averages(all_results: Dict[str, Dict]) -> Dict:
    """Calculate average values from all model results"""
    if not all_results:
        return {}
    
    averaged = {}
    seasons = ["Summer", "Autumn", "Winter", "Spring"]
    params = ["Tmin", "Tmax", "Hmin", "Hmax"]
    
    for season in seasons:
        averaged[season] = {}
        for param in params:
            values = []
            for model_name, result in all_results.items():
                if result and 'soil_requirements' in result:
                    if season in result['soil_requirements']:
                        value = result['soil_requirements'][season].get(param)
                        if value is not None and isinstance(value, (int, float)):
                            values.append(value)
            
            if values:
                avg = statistics.mean(values)
                averaged[season][param] = int(round(avg))
            else:
                # Default values
                defaults = {
                    "Summer": {"Tmin": 15, "Tmax": 35, "Hmin": 20, "Hmax": 60},
                    "Autumn": {"Tmin": 10, "Tmax": 25, "Hmin": 30, "Hmax": 70},
                    "Winter": {"Tmin": 5, "Tmax": 20, "Hmin": 40, "Hmax": 80},
                    "Spring": {"Tmin": 10, "Tmax": 25, "Hmin": 30, "Hmax": 70}
                }
                averaged[season][param] = defaults[season][param]
    
    return averaged

def update_plant_in_db(plant_type_id: int, latin_name: str, thresholds: Dict):
    """Update plant information in database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Start transaction
        cursor.execute('BEGIN IMMEDIATE')
        
        # Update latin name if provided
        if latin_name and latin_name != 'Unknown':
            cursor.execute('''
                UPDATE plant_types 
                SET latin_name = ?
                WHERE id = ?
            ''', (latin_name, plant_type_id))
            print(f"    Updated latin name: {latin_name}")
        
        # Update thresholds for each season
        for season, values in thresholds.items():
            cursor.execute('''
                INSERT OR REPLACE INTO plant_thresholds 
                (plant_type_id, season, humidity_low, humidity_high, 
                 temperature_low, temperature_high, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                plant_type_id,
                season,
                values.get('Hmin', 30),
                values.get('Hmax', 70),
                values.get('Tmin', 15),
                values.get('Tmax', 25)
            ))
            print(f"    Updated {season} thresholds: T({values.get('Tmin', 15)}-{values.get('Tmax', 25)}°C), H({values.get('Hmin', 30)}-{values.get('Hmax', 70)}%)")
        
        # Commit transaction
        cursor.execute('COMMIT')
        print(f"  ✓ Updated database successfully")
        mark_db_changed()
        
    except Exception as e:
        cursor.execute('ROLLBACK')
        print(f"  ✗ Error updating database: {e}")
        raise e  # Re-raise to handle in calling function
    finally:
        conn.close()

def process_plants(full_mode=False):
    """Main function to process all plants in database"""
    # Load API keys
    api_keys = load_api_keys()
    if not api_keys:
        return
    
    # Check if PlantNet is available
    has_plantnet = 'PlantNet' in api_keys
    plantnet_key = api_keys.pop('PlantNet', None) if has_plantnet else None
    
    # Determine which models to use
    if full_mode:
        models_to_use = list(api_keys.keys())
        print(f"\nFull mode: will query all {len(models_to_use)} models ({', '.join(models_to_use)})")
        if has_plantnet:
            print("PlantNet will be used for plant identification")
    else:
        models_to_use = [list(api_keys.keys())[0]] if api_keys else []
        print(f"\nPrimary mode: will query {models_to_use[0] if models_to_use else 'no models'} only")
        if has_plantnet:
            print("PlantNet will be used for plant identification")
    
    if not models_to_use and not has_plantnet:
        print("Error: No models available for processing")
        return
    
    # Get all plant types from database
    plants = get_plants_from_db()
    
    if not plants:
        print(f"No plant types found in database")
        return
    
    print(f"Found {len(plants)} plant types to process")
    print("=" * 50)
    
    # Process each plant
    processed_count = 0
    skipped_count = 0
    
    for i, plant in enumerate(plants, 1):
        print(f"\n[{i}/{len(plants)}] Processing: {plant['name']}")
        
        # Get photos for this plant type
        photos = get_plant_photos(plant['id'])
        
        if not photos:
            print(f"  No photos found, skipping...")
            skipped_count += 1
            continue
        
        print(f"  Found {len(photos)} photos")
        
        # Step 1: Plant identification
        plant_info = None
        plantnet_result = None
        
        if has_plantnet:
            # Use PlantNet for identification
            print(f"  Identifying plant with PlantNet...")
            plantnet_result = identify_plant('PlantNet', plantnet_key, photos, plant['name'])
            
            if plantnet_result and 'plantnet_all_species' in plantnet_result:
                # Extract plant info for LLMs
                top_species = plantnet_result['plantnet_all_species'][0]
                plant_info = {
                    'scientific_name': top_species['scientific_name'],
                    'family': top_species['family'],
                    'genus': top_species['genus']
                }
                print(f"    ✓ PlantNet identified as: {plant_info['scientific_name']}")
            else:
                print(f"    ⚠ PlantNet identification failed")
        
        # Step 2: Get soil requirements from LLMs
        all_results = {}
        success = False
        
        if models_to_use:
            print(f"  Getting soil requirements from LLMs...")
            
            for model_idx, model_name in enumerate(models_to_use):
                print(f"  Querying {MODEL_CONFIGS[model_name]['name']}... (model {model_idx + 1} of {len(models_to_use)})")
                
                if plant_info:
                    # Use plant info from PlantNet
                    result = identify_plant(model_name, api_keys[model_name], [], plant['name'], plant_info)
                else:
                    # Use images for full identification
                    result = identify_plant(model_name, api_keys[model_name], photos, plant['name'])
                
                if result:
                    all_results[model_name] = result
                    success = True
                    print(f"    ✓ Got response from {model_name}")
                else:
                    print(f"    ⚠ Failed to get response from {model_name}")
                
                # Add delay between model queries to avoid rate limits
                if model_idx < len(models_to_use) - 1:
                    print(f"    Waiting 1 second before next model...")
                    time.sleep(1)
        
        if not success and not plantnet_result:
            print(f"  ✗ Failed to get any results")
            continue
        
        # Determine latin name and thresholds
        latin_name = None
        thresholds = {}
        
        if plantnet_result:
            # Use PlantNet's scientific name if available
            latin_name = plantnet_result.get('latin_name', None)
        
        if all_results:
            # Get latin name from first model if not from PlantNet
            if not latin_name:
                primary_result = all_results.get(models_to_use[0], {})
                latin_name = primary_result.get('latin_name', None)
            
            # Calculate averaged thresholds
            if full_mode and len(all_results) > 1:
                thresholds = calculate_averages(all_results)
            else:
                # Use single model results
                primary_result = all_results.get(models_to_use[0], {})
                thresholds = primary_result.get('soil_requirements', {})
        
        # Update database
        if latin_name or thresholds:
            print(f"  Updating database...")
            if latin_name:
                print(f"    Latin name: {latin_name}")
            try:
                update_plant_in_db(plant['id'], latin_name, thresholds)
                processed_count += 1
            except Exception as e:
                print(f"  ✗ Failed to update database: {e}")
                continue
        else:
            print(f"  ✗ No data to update")
        
        # Rate limiting - wait between requests
        if i < len(plants) and processed_count > 0:
            wait_time = 3 if full_mode else 2
            print(f"  Waiting {wait_time} seconds before next request...")
            time.sleep(wait_time)
    
    print("\n" + "=" * 50)
    print(f"Processing complete!")
    print(f"Processed: {processed_count} plants")
    print(f"Skipped: {skipped_count} plants")
    
    # Sync with remote if needed
    if remote_mode:
        if has_db_changes:
            print(f"\nSyncing {processed_count} plant updates with remote database...")
            sync_success = sync_remote_database()
            if sync_success:
                print("✓ All changes successfully synced to remote database")
            else:
                print("✗ Warning: Some changes may not have been synced to remote database")
                print("  Please check the remote database manually")
        else:
            print("\nNo database changes to sync with remote server")
    
    return processed_count, skipped_count

def main():
    """Main entry point"""
    import sys
    
    print("Plant Database Identifier using Multiple AI Models")
    print("=================================================\n")
    
    # Check for flags
    full_mode = '--full' in sys.argv or '-f' in sys.argv
    
    # Check if config file exists
    if not os.path.exists(CONFIG_FILE):
        print(f"Error: Configuration file '{CONFIG_FILE}' not found!")
        print("\nPlease create garden.ini with the following content:")
        print("[API Keys]")
        print("Claude = your_claude_api_key_here")
        print("OpenAI = your_openai_api_key_here  # Optional")
        print("Gemini = your_gemini_api_key_here  # Optional")
        print("PlantNet = your_plantnet_api_key_here  # Optional")
        print("\nFor remote database access, also add:")
        print("[Remote]")
        print("login = username@hostname")
        print("dir = /path/to/remote/directory")
        print("\nThe first key listed will be the primary model.")
        print("PlantNet will be used for scientific name verification.")
        return
    
    # Show usage if needed
    if '--help' in sys.argv or '-h' in sys.argv:
        print("Usage: python plant_identifier_db.py [options]")
        print("\nOptions:")
        print("  -f, --full      Query all available models (not just primary)")
        print("  -h, --help      Show this help message")
        print("\nThis script will:")
        print("  1. Choose database connection mode (local or remote)")
        print("  2. Scan all plants in the database")
        print("  3. Use their photos for identification")
        print("  4. Update latin names and thresholds")
        print("  5. Sync changes to remote database (if in remote mode)")
        return
    
    try:
        # Install required libraries hint
        missing_libs = []
        try:
            import openai
        except ImportError:
            missing_libs.append("openai")
        try:
            import google.generativeai
        except ImportError:
            missing_libs.append("google-generativeai")
        try:
            import requests
        except ImportError:
            missing_libs.append("requests")
        try:
            import paramiko
        except ImportError:
            missing_libs.append("paramiko")
        
        if missing_libs:
            print(f"Note: Some libraries are not installed: {', '.join(missing_libs)}")
            print("Install them if you plan to use those features.")
            print("For remote database: pip install paramiko")
            print()
        
        try:
            # Setup database connection
            if not choose_database_mode():
                print("Database setup failed. Exiting...")
                return
            
            # Process plants and get results
            processed, skipped = process_plants(full_mode)
            
            # Final summary
            print(f"\n{'='*60}")
            print(f"FINAL SUMMARY:")
            print(f"{'='*60}")
            print(f"Total plants processed: {processed}")
            print(f"Total plants skipped: {skipped}")
            
            if remote_mode:
                if has_db_changes:
                    print(f"Remote database: ✗ SYNC INCOMPLETE")
                    print(f"Please run the script again or check the remote connection")
                else:
                    print(f"Remote database: ✓ All changes synced")
            else:
                print(f"Local database: ✓ All changes saved")
            
        except Exception as db_error:
            print(f"\nDatabase error: {db_error}")
            if remote_mode and has_db_changes:
                print("Warning: There may be unsaved changes!")
                print("Attempting emergency sync...")
                try:
                    if sync_remote_database():
                        print("✓ Emergency sync successful")
                    else:
                        print("✗ Emergency sync failed")
                except:
                    print("✗ Emergency sync failed")
            raise db_error
        finally:
            # Always cleanup SSH connection
            cleanup_ssh()
            
    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user")
        cleanup_ssh()
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        cleanup_ssh()

if __name__ == "__main__":
    main()