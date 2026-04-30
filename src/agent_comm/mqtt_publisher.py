import json
from typing import Dict, Any

import paho.mqtt.publish as publish
from src.core.config import get_settings

class MQTTPublisher:
    """Sends wake-up signals and commands to Go agents via MQTT."""
    
    def __init__(self):
        settings = get_settings()
        self.hostname = settings.mqtt_host
        self.port = settings.mqtt_port
        
    def wake_device(self, mqtt_topic: str) -> None:
        """
        Send a wake-up push to a specific device.
        The Go agent is subscribed to this topic and will POST back to us.
        """
        publish.single(
            topic=mqtt_topic,
            payload=json.dumps({"action": "wake"}),
            qos=1,
            hostname=self.hostname,
            port=self.port,
        )
