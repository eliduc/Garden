# Garden IoT Monitor

A comprehensive garden management system with IoT sensor integration, AI-powered plant identification, and real-time monitoring.

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
- [Module Documentation](#module-documentation)
- [Getting Started](#getting-started)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## 🌱 Overview

Garden IoT Monitor is a Python-based application suite designed for modern gardeners who want to combine traditional gardening with IoT technology. The system allows you to design garden layouts, monitor plant health through wireless sensors, identify plants using AI, and visualize all data through an intuitive web interface.

## ✨ Features

- **Visual Garden Designer** - Draw garden boundaries, place plants, add images
- **IoT Sensor Integration** - Connect Tuya-compatible soil sensors for real-time monitoring
- **AI Plant Identification** - Identify plants using photos with multiple AI models
- **Real-time Web Dashboard** - Monitor sensor readings with interactive visualizations
- **Seasonal Threshold Management** - Set temperature/humidity limits per plant type and season
- **Photo Management** - Store and manage multiple photos per plant with compression
- **Database Management** - Complete GUI for managing all garden data
- **Automated Monitoring** - Continuous sensor polling with configurable intervals
- **Multi-garden Support** - Manage multiple garden layouts

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Garden IoT Monitor                       │
├─────────────────┬───────────────────┬───────────────────────┤
│  Garden Designer│   Data Collection  │    Web Interface      │
│   (garden.py)   │ (garden_db_logger) │ (garden_api_server)   │
├─────────────────┴───────────────────┴───────────────────────┤
│                    SQLite Database                           │
│              (garden_sensors.db)                             │
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
pip install pygame Pillow shapely flask flask-cors requests tinytuya psutil anthropic
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

## 📚 Module Documentation

### 1. Garden Designer (`garden.py`)

The main application for creating and editing garden layouts.

**Features:**
- Draw garden boundaries
- Add plants with photos
- Configure IoT sensors
- Save to database or JSON

**Usage:**
```bash
python garden.py
```

**Controls:**
- **Load Garden**: Load existing garden from database or JSON
- **Create Garden**: Start drawing new garden boundary (right-click to finish)
- **Add Plant**: Click to place plants inside garden
- **Add Image**: Add decorative images to your garden
- **Save**: Save to database or export to JSON
- **Double-click** on plant: Edit plant details
- **Right-click** on plant: Quick edit menu

### 2. Database Logger (`garden_db_logger.py`)

Continuously polls IoT sensors and logs data to database.

**Features:**
- Automatic sensor discovery
- Configurable polling interval
- Threshold alerts
- Battery monitoring

**Usage:**
```bash
python garden_db_logger.py
```

The logger will:
1. Read sensor configuration from database
2. Poll each sensor at specified intervals
3. Store readings with timestamps
4. Check against seasonal thresholds
5. Display warnings for out-of-range values

### 3. API Server (`garden_api_server.py`)

RESTful API server for web interface and external integrations.

**Features:**
- Garden data endpoints
- Sensor readings API
- Plant photos serving
- Real-time data access

**Usage:**
```bash
python garden_api_server.py
```

**Main Endpoints:**
- `GET /` - Web interface
- `GET /api/gardens` - List all gardens
- `GET /api/garden/<id>` - Get specific garden
- `GET /api/sensor-data` - Get sensor readings
- `GET /api/plant-photo/<id>` - Get plant photo

### 4. Web Interface (`garden_web_interface.html`)

Interactive web dashboard for visualization.

**Features:**
- Real-time sensor data display
- Interactive garden map
- Zoom and pan controls
- Plant information popups
- Responsive design

**Access:**
1. Start the API server
2. Open browser to `http://localhost:5000`

### 5. Plant Identifier (`plant_identifier_db.py`)

AI-powered plant identification from photos.

**Features:**
- Multiple AI model support
- Scientific name identification
- Automatic threshold generation
- Batch processing

**Usage:**
```bash
# Use primary AI model only
python plant_identifier_db.py

# Use all configured AI models
python plant_identifier_db.py --full
```

### 6. Database Manager (`garden_db_manager.py`)

GUI application for database management.

**Features:**
- Manage plant types
- Edit sensor configurations
- Set seasonal thresholds
- Manage photos
- View sensor readings

**Usage:**
```bash
python garden_db_manager.py
```

**Tabs:**
- **Plant Types**: Add/edit/delete plant species
- **Garden Plants**: Manage plants in gardens
- **Plant Photos**: Manage plant photos
- **Thresholds**: Set seasonal limits
- **Sensor Readings**: View and filter sensor data

### 7. Photo Compressor (`compress_db_photos.py`)

Optimize photo storage in database.

**Features:**
- Batch photo compression
- Configurable quality settings
- Different settings for main/additional photos
- Preview mode (dry run)

**Usage:**
```bash
# GUI mode
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

## 🚀 Getting Started

### Quick Start Guide

1. **Initial Setup**
   ```bash
   # 1. Configure garden.ini with your API keys
   # 2. Run the garden designer
   python garden.py
   ```

2. **Create Your First Garden**
   - Click "Create Garden"
   - Click points to draw garden boundary
   - Right-click to finish drawing
   - Click "Add Plant" to add plants
   - Double-click plants to add details and sensors

3. **Start Monitoring**
   ```bash
   # In separate terminals:
   python garden_db_logger.py  # Start sensor polling
   python garden_api_server.py # Start web server
   ```

4. **View Dashboard**
   - Open browser to `http://localhost:5000`
   - Select your garden
   - Monitor real-time sensor data

### Typical Workflow

1. **Design Phase**
   - Create garden layout in `garden.py`
   - Add plants and configure sensors
   - Set seasonal thresholds in Database Manager

2. **Setup Phase**
   - Configure Tuya sensors in Smart Life app
   - Add sensor IDs to plants in garden designer
   - Test sensor connectivity

3. **Monitoring Phase**
   - Run service manager for continuous monitoring
   - Access web dashboard for visualization
   - Check logs for threshold alerts

4. **Maintenance Phase**
   - Use Database Manager for adjustments
   - Run Plant Identifier for unknown plants
   - Compress photos periodically

## 🔍 Troubleshooting

### Common Issues

**1. ImportError: No module named 'xyz'**
```bash
# Install missing module
pip install xyz
```

**2. Tuya sensors not connecting**
- Verify API credentials in garden.ini
- Check sensor is online in Smart Life app
- Ensure correct API_REGION setting

**3. Database errors**
```bash
# Database will be created automatically
# To reset database, delete garden_sensors.db
```

**4. Web interface not loading**
- Ensure API server is running
- Check firewall settings for port 5000
- Try accessing http://127.0.0.1:5000

**5. Plant photos not displaying**
- Check image files exist in specified paths
- Run photo compressor if photos are too large
- Verify database has photo data

### Debug Mode

For detailed logging, set environment variable:
```bash
# Windows
set FLASK_DEBUG=1

# Linux/macOS
export FLASK_DEBUG=1
```

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

---

**Note**: This is an open-source project for educational and personal use. Ensure you comply with all API terms of service when using third-party services.