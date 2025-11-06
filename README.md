# Network Backup GUI

**One-click backup for Cisco 9800 WLC, ISE, and Catalyst 9000**  
*Created in Herlev, DK*

![Dashboard](screenshots/dashboard.png)

## Features
- Web GUI (no CLI)
- Manual & scheduled backups
- Local + Azure offsite
- Restore-ready configs
- Runs on Ubuntu (AWS/Azure)

## Quick Start
```bash
git clone https://github.com/jddnd/network-backup-gui.git
cd network-backup-gui
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app.py
Open: http://localhost:5000
Screenshots
<img src="screenshots/add-device.png" alt="Add Device">
Contributing
See CONTRIBUTING.md
License
MIT
