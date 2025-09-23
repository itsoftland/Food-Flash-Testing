import re
from django.conf import settings
from azure.iot.hub import IoTHubRegistryManager
import logging

logger = logging.getLogger(__name__)

IOT_HUB_NAME = getattr(settings, "IOTHUB_NAME", "FoodFlashTestHub")
HOSTNAME = getattr(settings, "IOTHUB_HOSTNAME", f"{IOT_HUB_NAME}.azure-devices.net")
POLICY_NAME = getattr(settings, "IOTHUB_POLICY_NAME", "iothubowner") 
POLICY_KEY = getattr(settings, "IOTHUB_POLICY_KEY", "zMSR3g9qDoBZsOljGR2Ub2CHYlhbmJOyNAIoTF7f42A=")
API_VERSION = getattr(settings, "IOTHUB_API_VERSION", "2020-03-13")
SERVICE_CONNECTION_STRING = f"HostName={HOSTNAME};SharedAccessKeyName={POLICY_NAME};SharedAccessKey={POLICY_KEY}"
registry_manager = IoTHubRegistryManager(SERVICE_CONNECTION_STRING)

def generate_device_id(alias_name, vendor_id, mac_address) :
    """
    Generate a unique and human-readable device_id for TV APK devices.
    Format: aliasName-vendorId-last4Mac
    Example: devoutlet-472435-fa5f
    """
    # Clean alias name (alphanumeric only, lowercased)
    clean_alias = re.sub(r'[^a-zA-Z0-9-]', '', alias_name or "device").lower()

    # Ensure mac is lowercase and extract last 4 chars
    mac_suffix = (mac_address.lower()[-4:] if mac_address else "0000")

    # Final ID
    device_id = f"{clean_alias}-{vendor_id}-{mac_suffix}"
    return device_id

def get_or_create_device(device_id):
    try:
        # Try to get the device
        device = registry_manager.get_device(device_id)
        
    except Exception:
        # If not found, create it
        device = registry_manager.create_device_with_sas(
            device_id,
            primary_key="",
            secondary_key="",
            status="enabled"
        )
    # Extract keys
    primary_key = device.authentication.symmetric_key.primary_key
    secondary_key = device.authentication.symmetric_key.secondary_key
    # Build connection strings
    primary_cs = f"HostName={HOSTNAME};DeviceId={device_id};SharedAccessKey={primary_key}"
    secondary_cs = f"HostName={HOSTNAME};DeviceId={device_id};SharedAccessKey={secondary_key}"
    return {
        "deviceId": device.device_id,
        "primaryKey": primary_key,
        "secondaryKey": secondary_key,
        "primaryConnectionString": primary_cs,
        "secondaryConnectionString": secondary_cs,
    }

import base64
import hmac
import hashlib
import time
import urllib.parse
from vendors.models import IoTDeviceCredential

# In-memory cache: { device_id: { "token": str, "expiry": int } }
_sas_token_cache = {}


def generate_sas_token(hostname, device_id, key, expiry=30*24*3600):
    """
    Generate a SAS token for Azure IoT Hub device connection.
    Default expiry is 30 days for long-lived connections.
    """
    ttl = int(time.time()) + expiry
    uri = f"{hostname}/devices/{device_id}"
    encoded_uri = urllib.parse.quote(uri, safe="")

    key_bytes = base64.b64decode(key)
    msg = f"{encoded_uri}\n{ttl}".encode("utf-8")

    signature = base64.b64encode(
        hmac.new(key_bytes, msg, hashlib.sha256).digest()
    ).decode("utf-8")

    encoded_signature = urllib.parse.quote(signature, safe="")

    return f"SharedAccessSignature sr={encoded_uri}&sig={encoded_signature}&se={ttl}"


def parse_connection_string(connection_string):
    """
    Parse Azure IoT Hub device connection string into components.
    Format: HostName=...;DeviceId=...;SharedAccessKey=...
    """
    parts = dict(item.split("=", 1) for item in connection_string.split(";") if "=" in item)
    return parts["HostName"], parts["DeviceId"], parts["SharedAccessKey"]


def get_device_sas_token(device_id, expiry =30*24*3600):
    """
    Fetch IoT device credentials from DB and generate SAS token.
    Uses cached token if valid, otherwise regenerates.
    Tries primary first, falls back to secondary.

    :param device_id: Device ID stored in IoTDeviceCredential
    :param expiry: Expiry in seconds (default 30 days)
    :return: SAS token string
    """
    now = int(time.time())
    cached = _sas_token_cache.get(device_id)
    # --- Use cached token if still valid ---
    if cached and cached["expiry"] > now:
        return cached["token"]

    try:
        cred = IoTDeviceCredential.objects.get(device_id=device_id)

        # --- Try primary connection string ---
        for conn_name in ["primary_connection_string", "secondary_connection_string"]:
            try:
                connection_string = getattr(cred, conn_name)
                hostname, _, key = parse_connection_string(connection_string)
                token = generate_sas_token(hostname, device_id, key, expiry)
                # Subtract 30 seconds buffer
                _sas_token_cache[device_id] = {"token": token, "expiry": now + expiry - 30}
                return token
            except Exception as e:
                print(f"[WARN] {conn_name} failed for {device_id}: {e}")

        # If both fail
        raise ValueError(f"No valid SAS token could be generated for {device_id}")

    except IoTDeviceCredential.DoesNotExist:
        raise ValueError(f"No IoT credentials found for device_id: {device_id}")


def create_iot_credentials(device):
    # create a deterministic, human-friendly device id
    device_id = generate_device_id(
        device.vendor.alias_name,
        device.vendor.vendor_id,
        device.mac_address
    )
    

    # register with IoT Hub (create if necessary)
    iot_credentials = get_or_create_device(device_id)
    
    # Build connection strings to store in DB
    primary_cs = iot_credentials.get("primaryConnectionString")
    secondary_cs = iot_credentials.get("secondaryConnectionString")

    # Save or update credentials in DB
    # Use update_or_create so existing rows get updated if connection strings changed
    cred_obj, created_flag = IoTDeviceCredential.objects.update_or_create(
        android_device=device,
        vendor=device.vendor,
        defaults={
            "device_id": iot_credentials.get("deviceId"),
            "primary_connection_string": primary_cs,
            "secondary_connection_string": secondary_cs,
        }
    )

    if created_flag:
        logger.info(f"Created IoTDeviceCredential for device {device_id}")
    else:
        logger.info(f"Updated IoTDeviceCredential for device {device_id}")

    # Generate SAS token from stored connection string (tries primary then secondary internally)
    try:
        token = get_device_sas_token(iot_credentials.get("deviceId"))
    except Exception as e:
        # If something goes wrong, log and re-raise or handle according to your app flow
        logger.exception(f"Failed to generate SAS token for device {device_id}: {e}")
        raise

    # Build MQTT connection details (Azure IoT Hub MQTT over TLS)
    # Hostname should be your IoT Hub host (same as in SERVICE_CONNECTION_STRING)
    mqtt_host = getattr(settings,"IOTHUB_HOSTNAME")  # e.g. "<your-iothub>.azure-devices.net"
    api_version = getattr(settings,"IOTHUB_DEVICE_API_VERSION")
    mqtt_port = 8883      # TLS port for MQTT
    # username format = "{iothubhostname}/{device_id}/?api-version={api_version}"
    mqtt_username = f"{mqtt_host}/{device_id}/?api-version={api_version}"
    mqtt_password = token  # the SAS token acts as the MQTT password
    mqtt_client_id = device_id
    topic = f"devices/{device_id}/messages/devicebound/#"

    mqtt_config = {
        "client_id":iot_credentials.get("deviceId"),
        "host": mqtt_host,
        "port": mqtt_port,
        "username": mqtt_username,
        "password": mqtt_password,
        "client_id": mqtt_client_id,
        "topic":topic,
        "qos":0,
        "tls":True
    }
    return mqtt_config
    

