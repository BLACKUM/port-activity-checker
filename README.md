# Port Activity Checker (SOCKS5 Monitor)

A Python script to monitor network connections on a VPS. It detects when a client connects to a specific target server through a SOCKS5 proxy and sends status updates to a Discord Webhook.

## Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/BLACKUM/port-activity-checker
    cd port-activity-checker
    ```

2.  **Create and activate a virtual environment**:
    *(Required on newer Linux systems to avoid "externally-managed-environment" errors)*
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

1.  **Run the script once** to generate the configuration file:
    ```bash
    python monitor.py
    ```
    This will create a `config.json` file and then exit.

2.  **Edit `config.json`**:
    Open the file and fill in your details:
    ```json
    {
        "socks_port": 1234,          // The port your SOCKS5 proxy listens on
        "container_name": "CONTAINER_NAME", // OPTIONAL: Docker container name if proxy is running in Docker
        "target_ports": [1234],      // The target server port
        "webhook_url": "YOUR_WEBHOOK_URL", // Your Discord Webhook URL
        "check_interval": 5           // How often to check (in seconds)
    }
    ```

## Usage

Start the monitor:

```bash
python monitor.py
```

To keep it running in the background after you disconnect from SSH, use `tmux`:

1.  **Start a new tmux session**:
    ```bash
    tmux new -s monitor
    ```

2.  **Run the script inside the session**:
    ```bash
    python monitor.py
    ```

3.  **Detach from the session** (leave it running in background):
    Press `Ctrl+B`, then release and press `D`.

4.  **Reattach later** (to check logs):
    ```bash
    tmux attach -t monitor
    ```

5.  **All in one command**:
    ```bash
    tmux new -s monitor "cd /root/port-activity-checker && source venv/bin/activate && python monitor.py"
    ```