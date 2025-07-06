# Garden IoT Monitor

A comprehensive garden management system with IoT sensor integration, AI-powered plant identification, real-time monitoring, and remote database support.

![Python](https://img.shields.io/badge/python-v3.7+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20MacOS-lightgrey.svg)

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [System Architecture](#system-architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Remote Database Setup](#remote-database-setup)
- [Module Documentation](#module-documentation)
- [Getting Started](#getting-started)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## 🌱 Overview

Garden IoT Monitor is a Python-based application suite designed for modern gardeners who want to combine traditional gardening with IoT technology. The system allows you to design garden layouts, monitor plant health through wireless sensors, identify plants using AI, and visualize all data through an intuitive web interface. With support for both local and remote databases, you can manage gardens across multiple locations and devices.

## ✨ Features

- **Visual Garden Designer** - Draw garden boundaries, place plants, add images
- **IoT Sensor Integration** - Connect Tuya-compatible soil sensors for real-time monitoring
- **AI Plant Identification** - Identify plants using photos with multiple AI models
- **Real-time Web Dashboard** - Monitor sensor readings with interactive visualizations
- **Seasonal Threshold Management** - Set temperature/humidity limits per plant type and season
- **Photo Management** - Store and manage multiple photos per plant with compression
- **Database Management** - Complete GUI for managing all garden data
- **Remote Database Support** - Access databases on remote servers via SSH
- **Automated Monitoring** - Continuous sensor polling with configurable intervals
- **Multi-garden Support** - Manage multiple garden layouts
- **Cross-platform Compatibility** - Works on Windows, Linux, macOS, and Raspberry Pi

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Garden IoT Monitor                       │
├─────────────────┬───────────────────┬───────────────────────┤
│  Garden Designer│   Data Collection  │    Web Interface      │
│   (garden.py)   │ (garden_db_logger) │ (garden_api_server)   │
├─────────────────┴───────────────────┴───────────────────────┤
│                Database Layer (Local/Remote)                 │
│              ┌─────────────┬─────────────────┐               │
│              │ Local SQLite│  Remote SQLite  │               │
│              │    (PC)     │ (Raspberry Pi)  │               │
│              └─────────────┴─────────────────┘               │
├─────────────────┬───────────────────┬───────────────────────┤
│ Plant Identifier│  Photo Compressor  │   Database Manager    │
│(plant_identifier)│ (compress_db_photos)│ (garden_db_manager) │
└─────────────────┴───────────────────┴───────────────────────┘
```

## 📦 Requirements

### System Requirements
- Python 3.7 or higher
- Operating System: Windows, Linux, or macOS
- Internet connection (for IoT sensors and AI services)
- GUI support (for Tkinter and Pygame applications)
- SSH client (for remote database access)

### Python Libraries

```bash
# Core libraries
pygame>=2.0.0
tkinter (usually comes with Python)
Pillow>=8.0.0
shapely>=1.8.0

# Web and API
flask>=2.0.0
flask-cors>=3.0.0
requests>=2.25.0

# Database
sqlite3 (usually comes with Python)

# Remote access
paramiko>=2.8.0

# IoT Integration
tinytuya>=1.12.0

# AI Services (optional)
anthropic>=0.3.0
openai>=0.27.0
google-generativeai>=0.1.0

# Utilities
psutil>=5.8.0
configparser (usually comes with Python)
```

## 🔧 Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/yourusername/garden-iot-monitor.git
cd garden-iot-monitor
```

### Step 2: Create Virtual Environment (Recommended)

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/macOS
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

If `requirements.txt` is not provided, install manually:

```bash
pip install pygame Pillow shapely flask flask-cors requests tinytuya psutil anthropic paramiko
```

### Step 4: Download Required Image Files

Create the following image files or download from the repository:
- `tree.png` - Default plant icon (30x30 pixels)
- `sensor.png` - Sensor indicator icon (15x15 pixels)

## ⚙️ Configuration

### 1. Create Configuration File

Create a file named `garden.ini` in the project directory:

```ini
[tuya]
ACCESS_ID = your_tuya_access_id_here
ACCESS_KEY = your_tuya_access_key_here
API_REGION = eu  # or us, cn, in depending on your region

[frequency]
frequency = 2400  # Sensor polling interval in seconds (40 minutes)

[Remote]
# Configuration for remote database access
login = pi@192.168.1.100  # username@hostname or username@ip
dir = /home/pi/garden     # remote directory containing database

[API Keys]
# Optional - only needed for plant identification
Claude = your_claude_api_key_here
OpenAI = your_openai_api_key_here
Gemini = your_gemini_api_key_here
PlantNet = your_plantnet_api_key_here
```

### 2. Obtain API Keys

#### Tuya IoT Platform (Required for sensors)
1. Register at [Tuya IoT Platform](https://iot.tuya.com/)
2. Create a Cloud Project
3. Get your Access ID and Access Key
4. Link your Tuya/Smart Life devices

#### AI Services (Optional)
- **Claude**: Get API key from [Anthropic](https://www.anthropic.com/)
- **OpenAI**: Get API key from [OpenAI Platform](https://platform.openai.com/)
- **Gemini**: Get API key from [Google AI Studio](https://makersuite.google.com/)
- **PlantNet**: Get API key from [PlantNet API](https://my.plantnet.org/developers)

## 🌐 Remote Database Setup

The system supports both local and remote database configurations, allowing you to manage gardens across multiple devices or locations.

### Use Cases
- **Raspberry Pi Garden Hub** - Run database on Pi, access from PC/laptop
- **Multi-location Gardens** - Central database server for multiple garden sites
- **Backup and Sync** - Keep local copy while syncing with remote server
- **Team Collaboration** - Multiple users accessing shared garden database

### Setting Up Remote Database

#### Option 1: Raspberry Pi Setup
```bash
# On Raspberry Pi
mkdir -p /home/pi/garden
cd /home/pi/garden

# Install Python and dependencies
sudo apt update
sudo apt install python3 python3-pip python3-venv
python3 -m venv venv
source venv/bin/activate
pip install sqlite3 tinytuya flask

# Start the garden logger (creates database automatically)
python garden_db_logger.py
```

#### Option 2: Linux Server Setup
```bash
# Create garden user
sudo useradd -m -s /bin/bash garden
sudo mkdir -p /opt/garden
sudo chown garden:garden /opt/garden

# Setup SSH key authentication (recommended)
ssh-copy-id garden@your-server.com
```

### Connection Modes

When starting any application, you'll be prompted to choose:

1. **Local Database** - Uses local `garden_sensors.db` file
2. **Remote Database** - Connects to remote server via SSH

### Remote Connection Features

- **Automatic Download** - Remote database is downloaded and cached locally
- **Progress Indication** - Shows download/upload progress for large databases
- **Automatic Sync** - Changes are automatically uploaded back to remote server
- **Connection Management** - Handles SSH connection errors gracefully
- **Compression** - Uses SSH compression for faster transfers over slow connections

### Security Considerations

- Use SSH key authentication instead of passwords when possible
- Ensure SSH server is properly configured and secured
- Consider using VPN for connections over public networks
- Regular database backups are recommended

## 📚 Module Documentation

### 1. Garden Designer (`garden.py`)

The main application for creating and editing garden layouts with remote database support.

**Features:**
- Draw garden boundaries
- Add plants with photos
- Configure IoT sensors
- Save to local or remote database
- Automatic sync with remote server

**Usage:**
```bash
python garden.py
```

**Database Mode Selection:**
On startup, you'll choose between:
- **Local Database** - Work with local database file
- **Remote Database** - Connect to remote server via SSH

**Controls:**
- **Load Garden**: Load existing garden from database or JSON
- **Create Garden**: Start drawing new garden boundary (right-click to finish)
- **Add Plant**: Click to place plants inside garden
- **Add Image**: Add decorative images to your garden
- **Save & Sync**: Save to database and sync with remote (if applicable)
- **Double-click** on plant: Edit plant details
- **Right-click** on plant: Quick edit menu

### 2. Database Logger (`garden_db_logger.py`)

Continuously polls IoT sensors and logs data to database with remote support.

**Features:**
- Automatic sensor discovery
- Configurable polling interval
- Threshold alerts
- Battery monitoring
- Remote database sync

**Usage:**
```bash
python garden_db_logger.py
```

**Remote Mode Benefits:**
- Can run on Raspberry Pi while accessing data from PC
- Automatic database synchronization
- Centralized sensor data collection

### 3. API Server (`garden_api_server.py`)

RESTful API server for web interface with optimized data loading.

**Features:**
- Garden data endpoints
- Sensor readings API
- Plant photos serving
- Real-time data access
- Optimized dashboard endpoint

**Usage:**
```bash
python garden_api_server.py
```

**Main Endpoints:**
- `GET /` - Web interface
- `GET /api/dashboard-data` - Optimized data for dashboard
- `GET /api/gardens` - List all gardens
- `GET /api/garden/<id>` - Get specific garden
- `GET /api/sensor-data` - Get sensor readings
- `GET /api/plant-photo/<id>` - Get plant photo

### 4. Web Interface (`garden_web_interface.html`)

Interactive web dashboard with enhanced mobile support.

**Features:**
- Real-time sensor data display
- Interactive garden map
- Touch-friendly controls
- Plant information popups
- Responsive design
- Offline indicator
- Auto-refresh functionality

**Access:**
1. Start the API server
2. Open browser to `http://localhost:5000`

**Mobile Features:**
- Touch/swipe navigation
- Pinch to zoom
- Orientation hints
- Optimized layout for small screens

### 5. Plant Identifier (`plant_identifier_db.py`)

AI-powered plant identification from database photos with remote support.

**Features:**
- Multiple AI model support (Claude, OpenAI, Gemini, PlantNet)
- Scientific name identification
- Automatic threshold generation
- Batch processing of database plants
- Remote database sync

**Usage:**
```bash
# Use primary AI model only
python plant_identifier_db.py

# Use all configured AI models
python plant_identifier_db.py --full
```

**Process:**
1. Connects to database (local or remote)
2. Retrieves plant photos from database
3. Uses PlantNet for scientific identification
4. Uses LLMs for soil requirements
5. Updates plant information in database

### 6. Database Manager (`garden_db_manager.py`)

GUI application for database management with remote support.

**Features:**
- Manage plant types
- Edit sensor configurations
- Set seasonal thresholds
- Manage photos
- View sensor readings
- Remote database access
- Export plant/sensor lists

**Usage:**
```bash
python garden_db_manager.py
```

**Remote Features:**
- Connect to remote databases via SSH
- Real-time sync indicators
- Manual sync controls
- Connection status monitoring

### 7. Photo Compressor (`compress_db_photos.py`)

Optimize photo storage with remote database support.

**Features:**
- Batch photo compression
- Configurable quality settings
- Different settings for main/additional photos
- Preview mode (dry run)
- Remote database sync
- Progress tracking

**Usage:**
```bash
# GUI mode with remote support
python compress_db_photos.py

# Analysis only
python compress_db_photos.py --analyze
```

### 8. Service Manager (`garden_service_manager.py`)

Manages API server and logger as services.

**Features:**
- Automatic service startup
- Health monitoring
- Auto-restart on failure
- Consolidated logging

**Usage:**
```bash
python garden_service_manager.py
```

### 9. Database Structure Exporter (`db_structure_export.py`)

Comprehensive database analysis and documentation tool with remote support.

**Features:**
- Complete database structure export
- Schema diagram generation
- Table relationships and constraints analysis
- Sample data preview
- Remote database access via SSH
- Progress tracking for large databases

**Usage:**
```bash
# Interactive mode with database selection
python db_structure_export.py
```

**Export Options:**
- **Full Structure Export** - Complete table definitions, relationships, indexes, and sample data
- **Schema Diagram** - Visual ASCII representation of database structure
- **Both Exports** - Combined comprehensive documentation

### 10. Legacy Plant Identifier (`plant_identifier.py`)

Directory-based plant identification for photo collections.

**Features:**
- Processes plant photos organized in directories
- Multiple AI model support (Claude, OpenAI, Gemini, PlantNet)
- Batch processing with rate limiting
- Force update existing identifications
- Generates text reports per plant directory

**Usage:**
```bash
# Process all plant directories
python plant_identifier.py

# Force update existing files
python plant_identifier.py --update

# Use all available AI models
python plant_identifier.py --full
```

**Directory Structure:**
```
./plant/
├── Melo/
│   ├── photo1.jpg
│   ├── photo2.png
│   └── plant_identification.txt
├── Ulivo/
│   ├── image1.jpeg
│   └── plant_identification.txt
└── ...
```

### 9. Database Structure Exporter (`db_structure_export.py`)

Comprehensive database analysis and documentation tool with remote support.

**Features:**
- Complete database structure export
- Schema diagram generation
- Table relationships and constraints analysis
- Sample data preview
- Remote database access via SSH
- Progress tracking for large databases

**Usage:**
```bash
# Interactive mode with database selection
python db_structure_export.py
```

**Export Options:**
- **Full Structure Export** - Complete table definitions, relationships, indexes, and sample data
- **Schema Diagram** - Visual ASCII representation of database structure
- **Both Exports** - Combined comprehensive documentation

### 10. Legacy Plant Identifier (`plant_identifier.py`)

Directory-based plant identification for photo collections.

**Features:**
- Processes plant photos organized in directories
- Multiple AI model support (Claude, OpenAI, Gemini, PlantNet)
- Batch processing with rate limiting
- Force update existing identifications
- Generates text reports per plant directory

**Usage:**
```bash
# Process all plant directories
python plant_identifier.py

# Force update existing files
python plant_identifier.py --update

# Use all available AI models
python plant_identifier.py --full
```

**Directory Structure:**
```
./plant/
├── Melo/
│   ├── photo1.jpg
│   ├── photo2.png
│   └── plant_identification.txt
├── Ulivo/
│   ├── image1.jpeg
│   └── plant_identification.txt
└── ...
```

## 🚀 Getting Started

### Quick Start Guide

1. **Initial Setup**
   ```bash
   # 1. Configure garden.ini with your API keys and remote settings
   # 2. Run the garden designer
   python garden.py
   ```

2. **Choose Database Mode**
   - Select "Local Database" for standalone operation
   - Select "Remote Database" to connect to SSH server
   - Enter SSH credentials when prompted

3. **Create Your First Garden**
   - Click "Create Garden"
   - Click points to draw garden boundary
   - Right-click to finish drawing
   - Click "Add Plant" to add plants
   - Double-click plants to add details and sensors

4. **Start Monitoring**
   ```bash
   # In separate terminals:
   python garden_db_logger.py  # Start sensor polling
   python garden_api_server.py # Start web server
   ```

5. **View Dashboard**
   - Open browser to `http://localhost:5000`
   - Select your garden
   - Monitor real-time sensor data

### Remote Database Workflow

1. **Setup Remote Server**
   - Install Python and dependencies on remote server
   - Configure SSH access
   - Add remote server details to garden.ini

2. **Design Locally, Deploy Remotely**
   - Create garden layout on local PC
   - Sync to remote database
   - Run data logger on remote server (e.g., Raspberry Pi)

3. **Monitor from Anywhere**
   - Access web interface from any device
   - View real-time sensor data
   - Make adjustments through database manager

### Typical Workflows

#### Single User, Local Setup
1. Design garden in `garden.py` (local mode)
2. Configure sensors and thresholds
3. Run logger and web server locally

#### Multi-device Setup with Raspberry Pi
1. Design garden on PC (remote mode → Pi)
2. Run logger on Raspberry Pi
3. Access web interface from any device on network
4. Make changes from PC, sync to Pi

#### Team/Multi-location Setup
1. Central database server
2. Multiple users connect remotely
3. Each location has local logger
4. Centralized monitoring and management

## 🔍 Troubleshooting

### Common Issues

**1. ImportError: No module named 'xyz'**
```bash
# Install missing module
pip install xyz
```

**2. SSH Connection Failed**
- Verify SSH credentials and server accessibility
- Check firewall settings on remote server
- Ensure SSH service is running on remote server
- Try connecting manually: `ssh username@hostname`

**3. Remote Database Sync Issues**
- Check network connectivity
- Verify remote directory permissions
- Monitor sync progress in status bar
- Check available disk space on both sides

**4. Large Database Downloads**
- Be patient with initial download
- Consider compressing photos first
- Use stable network connection
- Monitor progress indicators

**5. Tuya sensors not connecting**
- Verify API credentials in garden.ini
- Check sensor is online in Smart Life app
- Ensure correct API_REGION setting

**6. Database errors**
```bash
# Database will be created automatically
# To reset database, delete garden_sensors.db (local) or remote file
```

**7. Web interface not loading**
- Ensure API server is running
- Check firewall settings for port 5000
- Try accessing http://127.0.0.1:5000

**9. Plant photos not displaying**
- Check image files exist in specified paths
- Run photo compressor if photos are too large
- Verify database has photo data
- Check network connectivity for remote databases

**10. Plant identification errors**
- Verify API keys are correctly configured in garden.ini
- Check internet connectivity for AI services
- Ensure plant photos are present in database
- Monitor rate limits for AI service usage

### Remote Connection Troubleshooting

**SSH Authentication Issues:**
```bash
# Test SSH connection manually
ssh username@hostname

# For key-based auth
ssh-keygen -t rsa
ssh-copy-id username@hostname
```

**Network Issues:**
```bash
# Test connectivity
ping hostname
telnet hostname 22
```

**Permission Issues:**
```bash
# On remote server, ensure proper permissions
chmod 755 /path/to/garden/directory
chmod 644 /path/to/garden/garden_sensors.db
```

### Debug Mode

For detailed logging, set environment variable:
```bash
# Windows
set FLASK_DEBUG=1

# Linux/macOS
export FLASK_DEBUG=1
```

## 📱 Platform-Specific Notes

### Raspberry Pi
- Optimized for headless operation
- Automatic fallback to pygame dialogs when GUI unavailable
- Efficient photo compression for limited storage
- Power management considerations for 24/7 operation

### Windows
- Full GUI support with Tkinter
- SSH client built-in (Windows 10+)
- Service manager for background operation

### Linux/macOS
- Native SSH support
- Cron job integration possible
- Terminal-friendly operation modes

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Tuya IoT Platform for sensor integration
- Anthropic, OpenAI, Google, and PlantNet for AI services
- The Python community for excellent libraries
- Paramiko developers for SSH functionality

---

**Note**: This is an open-source project for educational and personal use. Ensure you comply with all API terms of service when using third-party services. When using remote databases, follow proper security practices for SSH connections.