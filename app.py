from flask import Flask, render_template, request, redirect, url_for, flash, send_file
import sqlite3
import subprocess
import os
import json
from datetime import datetime
import secrets
import glob

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

DB_PATH = '/home/ubuntu/network-backup-gui/devices.db'
BACKUP_DIR = "/backups/network"
os.makedirs(BACKUP_DIR, exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS devices
                 (id INTEGER PRIMARY KEY, name TEXT, type TEXT, ip TEXT, user TEXT, pass TEXT, last_backup TEXT, status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs
                 (id INTEGER PRIMARY KEY, timestamp TEXT, device TEXT, action TEXT, output TEXT)''')
    conn.commit()
    conn.close()

init_db()

def run_backup(device):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = f"{device['type'].lower()}-{device['name']}-{timestamp}.cfg"
    local_path = f"{BACKUP_DIR}/{backup_file}"

    inventory = f"""[all]
{device['name']} ansible_host={device['ip']} ansible_user={device['user']} ansible_ssh_pass={device['pass']} ansible_connection=network_cli ansible_network_os=cisco.ios.ios ansible_become=yes ansible_become_method=enable ansible_become_password={device['pass']}
"""
    playbook = f"""---
- name: Backup {device['name']}
  hosts: all
  gather_facts: no
  tasks:
    - name: Copy running-config via SCP
      cisco.ios.ios_command:
        commands:
          - "copy running-config scp://{device['user']}@{device['ip']}{BACKUP_DIR}/{backup_file}"
        prompt: "Password"
        answer: "{device['pass']}"
      ignore_errors: yes
"""
    with open('temp_inventory.yml', 'w') as f:
        f.write(inventory)
    with open('temp_playbook.yml', 'w') as f:
        f.write(playbook)

    result = subprocess.run(
        ['ansible-playbook', '-i', 'temp_inventory.yml', 'temp_playbook.yml'],
        capture_output=True, text=True
    )

    # Log
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO logs (timestamp, device, action, output) VALUES (?, ?, ?, ?)",
              (datetime.now().isoformat(), device['name'], 'backup', result.stdout + result.stderr))
    status = 'success' if result.returncode == 0 else 'failed'
    c.execute("UPDATE devices SET last_backup=?, status=? WHERE name=?", (timestamp, status, device['name']))
    conn.commit()
    conn.close()

    # Upload to Azure (if creds set)
    if os.getenv('AZURE_STORAGE_ACCOUNT') and os.path.isfile(local_path):
        subprocess.run([
            'az', 'storage', 'blob', 'upload',
            '--account-name', os.getenv('AZURE_STORAGE_ACCOUNT'),
            '--container-name', os.getenv('AZURE_CONTAINER', 'network-configs'),
            '--file', local_path,
            '--name', backup_file,
            '--auth-mode', 'login'
        ], capture_output=True)

    return result.returncode == 0

@app.route('/')
def dashboard():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM devices")
    devices = [dict(zip(['id','name','type','ip','user','pass','last','status'], row)) for row in c.fetchall()]
    c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 10")
    logs = c.fetchall()
    conn.close()
    return render_template('dashboard.html', devices=devices, logs=logs)

@app.route('/add', methods=['GET', 'POST'])
def add_device():
    if request.method == 'POST':
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO devices (name, type, ip, user, pass, last_backup, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (request.form['name'], request.form['type'], request.form['ip'],
                   request.form['user'], request.form['pass'], '', 'pending'))
        conn.commit()
        conn.close()
        flash('Device added!')
        return redirect('/')
    return render_template('add.html')

@app.route('/backup/<name>')
def backup_device(name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM devices WHERE name=?", (name,))
    dev = c.fetchone()
    conn.close()
    if dev:
        success = run_backup({
            'name': dev[1], 'type': dev[2], 'ip': dev[3],
            'user': dev[4], 'pass': dev[5]
        })
        flash(f"Backup {name}: {'Success' if success else 'Failed'}")
    return redirect('/')

@app.route('/files')
def list_files():
    files = sorted(glob.glob(f"{BACKUP_DIR}/*.cfg"), key=os.path.getmtime, reverse=True)
    return render_template('files.html', files=[os.path.basename(f) for f in files])

@app.route('/download/<filename>')
def download(filename):
    return send_file(f"{BACKUP_DIR}/{filename}", as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
