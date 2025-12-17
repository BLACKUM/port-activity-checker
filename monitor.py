import psutil
import requests
import time
import json
import os
import sys
from datetime import datetime

CONFIG_FILE = 'config.json'

def load_config():
    default_config = {
        "socks_port": None,
        "target_ports": [],
        "webhook_url": "",
        "check_interval": 5
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
                "timestamp": datetime.utcnow().isoformat()
            }
        ]
    }
    try:
        response = requests.post(url, json=data)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send webhook: {e}")

def check_connections(socks_port, target_ports):
    socks_active = False
    target_active = False
    
    try:
        connections = psutil.net_connections(kind='inet')
        for conn in connections:
            if conn.status == psutil.CONN_ESTABLISHED:
                if conn.laddr.port == socks_port:
                    socks_active = True
                
                if conn.raddr and conn.raddr.port in target_ports:
                    target_active = True
                    
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass
        
    return socks_active, target_active

def main():
    print("Starting SOCKS5 Monitor...")
    config = load_config()
    
    socks_port = config["socks_port"]
    target_ports = config["target_ports"]
    webhook_url = config["webhook_url"]
    interval = config.get("check_interval", 5)
    
    print(f"Monitoring SOCKS port: {socks_port}")
    print(f"Target ports: {target_ports}")
    
    last_status = "disconnected"
    
    try:
        while True:
            socks_active, target_active = check_connections(socks_port, target_ports)
            
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
