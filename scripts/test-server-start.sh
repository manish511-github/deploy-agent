#!/bin/bash
set -e

# Start SSH daemon in background
/usr/sbin/sshd -D -e &

# Wait for config to be available (mounted or baked in)
CONFIG=/etc/zdeploy-agent/config.yaml
if [ ! -f "$CONFIG" ]; then
    echo "[start.sh] WARNING: $CONFIG not found — Go agent will not start."
    echo "[start.sh] Mount a config file or the agent will be idle."
    # Keep SSH alive so the container stays up
    wait
fi

echo "[start.sh] Starting Go agent..."
exec /usr/local/bin/zdeploy-agent -config "$CONFIG"
