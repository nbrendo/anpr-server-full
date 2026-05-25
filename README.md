
# ANPR Server - Automatic Number Plate Recognition

A complete ANPR (Automatic Number Plate Recognition) system with YOLO models for vehicle and license plate detection.

## Features
- Real-time license plate detection
- Vehicle detection and tracking
- Web dashboard for monitoring
- Mobile server support
- Docker containerization
- SQLite database for storing plate records

## Models Required
- `plate_best.pt` - YOLO model for license plate detection
- `vehicle_best.pt` - YOLO model for vehicle detection

### Download Models
Place the model files (`plate_best.pt` and `vehicle_best.pt`) in the project root directory.

## Database Setup
The system automatically creates `plates.db` on first run. No manual setup required.

## Installation

### Local Setup
1. Clone the repository:
```bash
git clone https://github.com/nbrendo/anpr-server-full.git
cd anpr-server-full

---
title: ANPR Server
emoji: 🚗
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
---

# ANPR - Automatic Number Plate Recognition

Vehicle and license plate detection system using YOLO.


---
title: ANPR Server
emoji: 🚗
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8090
---

# ANPR Server - Automatic Number Plate Recognition

A production-ready ANPR system for Zimbabwean license plates using YOLOv8 and EasyOCR.

## Features

- Real-time vehicle and license plate detection
- Mobile-friendly web interface for photo uploads
- Dashboard for viewing detection history
- SQLite database with CSV export
- Automatic snapshot capture
- Blacklist support for suspicious vehicles
- Demo owner registry lookup

## Quick Start

### Local Installation

```bash
git clone https://github.com/nbrendo/anpr-server-full.git
cd anpr-server-full
pip install -r requirements.txt
python mobile_server.py