import psutil
import requests
import time
import json
import os
import sys
from datetime import datetime, timezone

CONFIG_FILE = 'config.json'

def load_config():
    default_config = {
        "socks_port": None,
        "container_name": "",
        "target_ports": [],
        "webhook_url": "",
        "check_interval": 5,
        "debug": False
    }
    
    if not os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(default_config, f, indent=4)
            print(f"Created {CONFIG_FILE}. Please configure it and run the script again.")
            sys.exit(0)
        except Exception as e:
            print(f"Error creating config file: {e}")
            sys.exit(1)
            
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            
        if not config.get("socks_port"):
            print(f"Error: 'socks_port' is not set in {CONFIG_FILE}.")
            sys.exit(1)
        if not config.get("target_ports"):
             print(f"Error: 'target_ports' is empty in {CONFIG_FILE}.")
             sys.exit(1)
        if not config.get("webhook_url"):
            print(f"Error: 'webhook_url' is not set in {CONFIG_FILE}.")
            sys.exit(1)
            
        return config
    except json.JSONDecodeError:
        print(f"Error: Failed to decode {CONFIG_FILE}. Please check if it is valid JSON.")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

def send_discord_webhook(url, message, color=0x00ff00):
    data = {
        "embeds": [
            {
                "description": message,
                "color": color,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ]
    }
    try:
        response = requests.post(url, json=data)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send webhook: {e}")

import subprocess

def check_docker_connections(container_name, target_ports, debug=False):
    target_active = False
    
    try:
        cmd = f"docker exec {container_name} netstat -tunap"
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode('utf-8')
        
        for line in output.splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue
            
            if 'ESTABLISHED' not in line:
                continue
                
            remote_addr = parts[4]
            
            if debug:
                 print(f"[DEBUG] Found ESTABLISHED connection: {remote_addr}")
            
            # Check for wildcard
            if "*" in target_ports:
                 # Filter out local/internal connections if needed, though netstat inside container usually shows relevant traffic
                 # Common internal IPs: 127.0.0.1, ::1
                 # But in simple SOCKS proxy containers, valid traffic is usually external.
                 if not remote_addr.startswith("127.0.0.1") and not remote_addr.startswith("::1"):
                     target_active = True
                     if debug:
                         print(f"[DEBUG] Wildcard Match! Active.")
                     break
            
            for port in target_ports:
                if port == "*": continue
                if f":{port}" in remote_addr:
                    target_active = True
                    break
            
            if target_active:
                if debug:
                    print(f"[DEBUG] MATCHED Target Port! Active.")
                break
                
    except subprocess.CalledProcessError as e:
        print(f"Error running docker command: {e.output.decode('utf-8')}")
    except Exception as e:
        print(f"Docker check failed: {e}")
        
    return target_active

def check_connections(socks_port, target_ports):
    socks_active = False
    target_active = False
    
    try:
        connections = psutil.net_connections(kind='inet')
        for conn in connections:
            if conn.status == psutil.CONN_ESTABLISHED:
                if conn.laddr.port == socks_port:
                    socks_active = True
                if conn.raddr:
                    if "*" in target_ports:
                        # For host mode, filter out localhost
                        if conn.raddr.ip != "127.0.0.1" and conn.raddr.ip != "::1":
                             target_active = True
                    elif conn.raddr.port in target_ports:
                        target_active = True
                    
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass
        
    return socks_active, target_active

def main():
    print("Starting SOCKS5 Monitor...")
    config = load_config()
    
    socks_port = config["socks_port"]
    container_name = config.get("container_name", "")
    target_ports = config["target_ports"]
    webhook_url = config["webhook_url"]
    interval = config.get("check_interval", 5)
    debug = config.get("debug", False)
    
    if container_name:
        print(f"Monitoring Docker Container: {container_name}")
    else:
        print(f"Monitoring SOCKS port: {socks_port} (Host Mode)")
        
    print(f"Target ports: {target_ports}")
    if debug:
        print("Debug mode enabled: Printing all established connections found.")
    
    last_status = "disconnected"
    
    try:
        while True:
            if container_name:
                target_active = check_docker_connections(container_name, target_ports, debug)
            else:
                _, target_active = check_connections(socks_port, target_ports)
            
            current_status = "connected" if target_active else "disconnected"
            
            if current_status != last_status:
                if current_status == "connected":
                    msg = f"🟢 **Connected** to Target Server (Port: {target_ports})"
                    print(msg)
                    send_discord_webhook(webhook_url, msg, 0x00ff00) # Green
                else:
                    msg = "🔴 **Disconnected** from Target Server"
                    print(msg)
                    send_discord_webhook(webhook_url, msg, 0xff0000) # Red
                
                last_status = current_status
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\nStopping monitor...")

if __name__ == "__main__":
    main()
