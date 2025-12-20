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
        "webhook_url": "",
        "check_interval": 5,
        "debug": False,
        "leaderboard_show_country": False
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
            
        if config.get("socks_port") is None:
            print(f"Error: 'socks_port' is not set or null in {CONFIG_FILE}.")
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

def send_discord_webhook(url, title, description, fields=[], color=0x00ff00):
    embed = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fields": fields
    }
    
    data = {
        "embeds": [embed]
    }
    try:
        response = requests.post(url, json=data)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send webhook: {e}")

STATS_FILE = 'stats.json'

class StatsManager:
    def __init__(self):
        self.stats = self.load_stats()

    def load_stats(self):
        if not os.path.exists(STATS_FILE):
            return {}
        try:
            with open(STATS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def save_stats(self):
        try:
            with open(STATS_FILE, 'w') as f:
                json.dump(self.stats, f, indent=4)
            print(f"[DEBUG] Stats saved to {STATS_FILE}")
        except Exception as e:
            print(f"Error saving stats: {e}")

    def update_client(self, ip, duration_seconds):
        if ip not in self.stats:
            self.stats[ip] = {
                "total_duration": 0,
                "first_seen": datetime.now(timezone.utc).isoformat(),
                "last_seen": None
            }
        
        self.stats[ip]["total_duration"] += duration_seconds
        self.stats[ip]["last_seen"] = datetime.now(timezone.utc).isoformat()
        print(f"[DEBUG] Updated stats for {ip}. Added {duration_seconds}s. Total: {self.stats[ip]['total_duration']}s")
        self.save_stats()

    def get_leaderboard(self, limit=5):
        sorted_clients = sorted(
            self.stats.items(),
            key=lambda item: item[1].get("total_duration", 0),
            reverse=True
        )

        return sorted_clients[:limit]

# Cache for IP to Country mapping
ip_country_cache = {}

def get_country_from_ip(ip):
    if ip in ip_country_cache:
        return ip_country_cache[ip]
    
    # Skip private/local IPs
    if ip.startswith("127.") or ip.startswith("192.168.") or ip.startswith("10.") or ip == "::1":
        return "Localhost/Private"

    try:
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=3)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                country = data.get("country", ip)
                ip_country_cache[ip] = country
                return country
    except Exception as e:
        print(f"[WARN] Failed to resolve IP {ip}: {e}")
    
    return ip

def get_formatted_duration(seconds):
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}h {minutes}m {secs}s"

import subprocess

def get_docker_netstat_output(container_name):
    try:
        cmd = f"docker exec {container_name} netstat -tunap"
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode('utf-8')
        return output.splitlines()
    except Exception:
        return []

def check_docker_connections(container_name, target_ports, socks_port=None, debug=False):
    found_connections = []
    active_clients = []
    
    try:
        lines = get_docker_netstat_output(container_name)
        
        if socks_port:
            for line in lines:
                parts = line.split()
                if len(parts) < 5 or 'ESTABLISHED' not in line:
                    continue
                
                local_addr = parts[3]
                remote_addr = parts[4]
                
                try:
                    l_port = int(local_addr.split(":")[-1])
                    if l_port == int(socks_port):
                        if remote_addr not in active_clients:
                            active_clients.append(remote_addr)
                except: pass

        for line in lines:
            parts = line.split()
            if len(parts) < 5 or 'ESTABLISHED' not in line:
                continue
                
            local_addr = parts[3]
            remote_addr = parts[4]
            
            is_client = False
            if remote_addr in active_clients:
                is_client = True
            
            if socks_port:
                 try:
                    l_port = int(local_addr.split(":")[-1])
                    if l_port == int(socks_port):
                        is_client = True
                 except: pass

            
            if is_client:
                continue

            if debug:
                 print(f"[DEBUG] Checking Candidate: Local={local_addr} Remote={remote_addr}")
            
            try:
                port_str = remote_addr.split(":")[-1]
                current_port = int(port_str)
            except ValueError:
                continue

            is_match = False
            if "*" in target_ports:
                 if not remote_addr.startswith("127.0.0.1") and not remote_addr.startswith("::1"):
                     is_match = True
            else:
                for port in target_ports:
                    if port == "*": continue
                    if int(port) == current_port:
                         is_match = True
                         break
            
            if is_match:
                conn_details = {
                    "remote": remote_addr,
                    "local": local_addr,
                    "port": current_port
                }
                if conn_details not in found_connections:
                    found_connections.append(conn_details)
                    if debug:
                        print(f"[DEBUG] Match! {conn_details}")

    except Exception as e:
        print(f"Docker check failed: {e}")
        return None, None
        
    return found_connections, active_clients

def check_connections(socks_port, target_ports):
    found_connections = []
    active_clients = []
    
    try:
        connections = psutil.net_connections(kind='inet')
        for conn in connections:
            if conn.status == psutil.CONN_ESTABLISHED:
                l_ip, l_port = conn.laddr.ip, conn.laddr.port
                r_ip, r_port = (conn.raddr.ip, conn.raddr.port) if conn.raddr else (None, None)
                
                if l_port == int(socks_port) and r_ip:
                     client = f"{r_ip}:{r_port}"
                     if client not in active_clients:
                         active_clients.append(client)
                
                if r_port:
                    is_match = False
                    if "*" in target_ports:
                         if r_ip != "127.0.0.1" and r_ip != "::1":
                             is_match = True
                    elif r_port in target_ports:
                         is_match = True
                    
                    if is_match:
                        found_connections.append({
                            "remote": f"{r_ip}:{r_port}",
                            "local": f"{l_ip}:{l_port}",
                            "port": r_port
                        })

    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass
        
    return found_connections, active_clients

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
    
    if container_name:
        print(f"\n[INFO] Current connections in container '{container_name}':")
        try:
            cmd = f"docker exec {container_name} netstat -tunap"
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode('utf-8')
            print(output)
            print("-" * 50)
        except Exception as e:
            print(f"Failed to list initial connections: {e}")

    stats_manager = StatsManager()
    client_sessions = {}
    last_status = "disconnected"
    connection_start_time = None

    try:
        while True:
            loop_time = datetime.now()
            
            if container_name:
                result = check_docker_connections(container_name, target_ports, socks_port, debug)
                if result[0] is None:
                    time.sleep(1)
                    continue
                active_connections, active_clients = result
            else:
                active_connections, active_clients = check_connections(socks_port, target_ports)

            current_client_ips = set()
            for client in active_clients:
                ip = client.split(':')[0] if ':' in client else client
                current_client_ips.add(ip)
            
            active_tracked_ips = set(client_sessions.keys())
            
            new_ips = current_client_ips - active_tracked_ips
            for ip in new_ips:
                client_sessions[ip] = loop_time
            
            left_ips = active_tracked_ips - current_client_ips
            for ip in left_ips:
                start_time = client_sessions.pop(ip)
                duration = (loop_time - start_time).total_seconds()
                print(f"[DEBUG] Client disconnected: {ip}. Session duration: {duration}s")
                stats_manager.update_client(ip, duration)
                if debug:
                    print(f"[DEBUG] Client IP {ip} disconnected. Duration: {duration}s")


            target_active = len(active_connections) > 0
            
            current_status = "connected" if target_active else "disconnected"
            
            if current_status != last_status:
                if current_status == "connected":
                    connection_start_time = datetime.now()
                    
                    unique_ports = sorted(list(set([c['port'] for c in active_connections])))
                    ports_str = ", ".join([str(p) for p in unique_ports])
                    
                    fields = []
                    for i, conn in enumerate(active_connections[:5]):
                        fields.append({
                            "name": f"🌍 Target Connection #{i+1}",
                            "value": f"**IP**: `{conn['remote']}`\n**Port**: `{conn['port']}`",
                            "inline": True
                        })
                    
                    client_list = "\n".join([f"`{c}`" for c in active_clients[:5]]) if active_clients else "No direct SOCKS clients found or unknown."
                        
                    fields.append({
                        "name": "👤 Proxy Client",
                        "value": client_list,
                        "inline": False
                    })
                    
                    msg = f"Detected traffic to **{ports_str}**"
                    print(f"🟢 Connected: {ports_str} | Clients: {active_clients}")
                    send_discord_webhook(webhook_url, "🟢 Connection Established", msg, fields, 0x00ff00)
                else:
                    duration_str = "Unknown"
                    if connection_start_time:
                        duration = datetime.now() - connection_start_time
                        hours, remainder = divmod(duration.seconds, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        duration_str = f"{hours}h {minutes}m {seconds}s"
                    
                    print(f"🔴 Disconnected. Duration: {duration_str}")

                    flush_time = datetime.now()
                    for ip, start_time in client_sessions.items():
                        session_dur = (flush_time - start_time).total_seconds()
                        if session_dur > 0:
                            print(f"[DEBUG] Flushing session for {ip}. Duration: {session_dur}s")
                            stats_manager.update_client(ip, session_dur)
                            client_sessions[ip] = flush_time
                    
                    
                    leaderboard = stats_manager.get_leaderboard()
                    print(f"[DEBUG] Leaderboard generated: {leaderboard}")
                    fields = []
                    
                    if leaderboard:
                        lb_text = ""
                        show_country = config.get("leaderboard_show_country", False)
                        
                        for idx, (ip, data) in enumerate(leaderboard):
                            dur = get_formatted_duration(data['total_duration'])
                            
                            display_name = ip
                            if show_country:
                                display_name = get_country_from_ip(ip)
                                
                            lb_text += f"**{idx+1}.** `{display_name}` - ⏳ {dur}\n"
                        
                        fields.append({
                            "name": "🏆 Top Clients (Total Time)",
                            "value": lb_text,
                            "inline": False
                        })

                    send_discord_webhook(webhook_url, "🔴 Disconnected", f"Traffic to target has stopped.\n**Duration**: `{duration_str}`", fields, 0xff0000)
                    connection_start_time = None
                
                last_status = current_status
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\nStopping monitor...")
        print("Saving active sessions...")
        for ip, start_time in client_sessions.items():
            duration = (datetime.now() - start_time).total_seconds()
            stats_manager.update_client(ip, duration)
            print(f"Saved stats for {ip}")

if __name__ == "__main__":
    main()
