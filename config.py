import os
import time
# from handlers import oled_handler

# oled_handler.setup_oled()

# === Retrieve Configurations ===
SERIAL_PORT = ''
BAUDRATE = ''
SERIAL_PORT_RFID = ''
BAUDRATE_RFID = ''
SERVER = ''
IDLOOP1 = ''
IDLOOP2 = ''
PRINTER_VENDOR = ''
PRINTER_PRODUCT = ''
PRINTER_IN_EP = ''
PRINTER_OUT_EP = ''
INIT_FLAG_FILE = ''
MAX_RETRIES = ''
TIMEOUT_DEDUCT = ''
ACTIVE_TRANSACTION_FILE = ''
VALIDATE_TICKET = ''
VALIDATE_RFID = ''
VALIDATE_EMONEY = ''
UNIQ_ID = ''
MQTT_BROKER = ''
MQTT_PORT = ''
MQTT_TOPIC = ''

# Optional
SERIAL_PORT_QR = ''
BAUDRATE_QR = ''
IP_CAM = ''
LABEL_UP = ''
LABEL_CENTER = ''
LABEL_DOWN = ''

# === Printer Object Placeholder ===
printer = None

# === Configuration Initialization Function ===


def load_config():
    global printer
    global SERIAL_PORT, BAUDRATE, SERIAL_PORT_RFID, BAUDRATE_RFID, SERVER, IDLOOP1, IDLOOP2, INIT_FLAG_FILE, MAX_RETRIES, TIMEOUT_DEDUCT, ACTIVE_TRANSACTION_FILE, VALIDATE_TICKET, VALIDATE_RFID, VALIDATE_EMONEY, UNIQ_ID, MQTT_BROKER, MQTT_PORT, MQTT_TOPIC, SERIAL_PORT_QR, BAUDRATE_QR, IP_CAM, LABEL_UP, LABEL_CENTER, LABEL_DOWN, PRINTER_VENDOR, PRINTER_PRODUCT, PRINTER_IN_EP, PRINTER_OUT_EP

    # Serial Env
    SERIAL_PORT = os.getenv("SERIAL_PORT")
    BAUDRATE = os.getenv("BAUDRATE")
    SERIAL_PORT_RFID = os.getenv("SERIAL_PORT_RFID")
    BAUDRATE_RFID = os.getenv("BAUDRATE_RFID")

    # Server env
    SERVER = os.getenv("SERVER")
    IDLOOP1 = os.getenv("IDLOOP1")
    IDLOOP2 = os.getenv("IDLOOP2")
    VALIDATE_TICKET = os.getenv("VALIDATE_TICKET")
    VALIDATE_RFID = os.getenv("VALIDATE_RFID")
    VALIDATE_EMONEY = os.getenv("VALIDATE_EMONEY")

    # Printer Env
    PRINTER_VENDOR = int(os.getenv("PRINTER_VENDOR", "0x0483"), 16)
    PRINTER_PRODUCT = int(os.getenv("PRINTER_PRODUCT", "0x5743"), 16)
    PRINTER_IN_EP = int(os.getenv("PRINTER_IN_EP", "0x82"), 16)
    PRINTER_OUT_EP = int(os.getenv("PRINTER_OUT_EP", "0x01"), 16)
    LABEL_UP = os.getenv("LABEL_UP")
    LABEL_CENTER = os.getenv("LABEL_CENTER")
    LABEL_DOWN = os.getenv("LABEL_DOWN")

    # Deduct
    INIT_FLAG_FILE = os.getenv("INIT_FLAG_FILE")
    MAX_RETRIES = os.getenv("MAX_RETRIES")
    TIMEOUT_DEDUCT = os.getenv("TIMEOUT_DEDUCT")
    ACTIVE_TRANSACTION_FILE = os.getenv("ACTIVE_TRANSACTION_FILE")

    # MQTT env
    UNIQ_ID = os.getenv("UNIQ_ID")
    MQTT_BROKER = os.getenv("MQTT_BROKER")
    MQTT_PORT = os.getenv("MQTT_PORT")
    MQTT_TOPIC = os.getenv("MQTT_TOPIC")

    # Optional
    SERIAL_PORT_QR = os.getenv("SERIAL_PORT_QR")
    BAUDRATE_QR = os.getenv("BAUDRATE_QR")
    IP_CAM = os.getenv("IP_CAM")

    time.sleep(1)
