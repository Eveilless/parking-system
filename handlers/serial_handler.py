import re
import serial  # type: ignore
import time
from datetime import datetime
import logging
from config import SERIAL_PORT, BAUDRATE, SERIAL_PORT_QR, SERIAL_PORT_RFID
from utils import calculate_lrc
# from oled_handler import print_oled


def init_serial(port, baudrate=9600, timeout=0.1, name=""):
    try:
        serial_port = serial.Serial(
            port=port,
            baudrate=baudrate,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=timeout
        )
        print(f"Serial {name} connected")
        return serial_port, False
    except Exception as e:
        print(f"Error opening serial port {port}: {e}")
        # print_oled(f"Error serial {name}", "Not connected")
        return None, True


def initialize_device():
    """Menginisialisasi perangkat e-money reader."""
    try:
        with serial.Serial(SERIAL_PORT, BAUDRATE, timeout=2) as ser:
            logging.info("Initializing device...")
            init_command = bytes.fromhex(
                "020013EF0101758F40D46D95D1641448AA19B9282C0588")
            ser.write(init_command)
            ser.flush()
            time.sleep(1)
            response = ser.read_all()
            if response:
                logging.info(f"Device initialized: {response.hex().upper()}")
            else:
                logging.error("No response received during initialization.")
    except serial.SerialException as e:
        logging.error(f"Error opening serial port: {e}")


def read_rfid(serial_rfid):
    try:
        if serial_rfid is None or not serial_rfid.is_open:
            raise serial.SerialException("RFID Serial not open")

        data = serial_rfid.readline()

        if len(data) < 3:
            serial_rfid.flushInput()
            serial_rfid.flushOutput()
            return "", False, serial_rfid

        data = data.decode("utf-8", errors="ignore").strip()
        data = data[1:]

        if len(data) <= 1:
            return "", False, serial_rfid

        try:
            data_integer = int(data, 16)
        except ValueError:
            return "", False, serial_rfid

        data_str = str(data_integer)[0:10]
        if len(data_str) < 10:
            data_str = data_str.zfill(10)

        serial_rfid.flushInput()
        serial_rfid.flushOutput()

        print(f"RFID Data (parsed): {data_str}")
        return data_str, True, serial_rfid
    except (serial.SerialException, OSError) as e:
        print(f"RFID Serial disconnected: {e}, attempting reconnect...")
        try:
            serial_rfid.close()
        except:
            pass
        try:
            serial_rfid = serial.Serial(
                SERIAL_PORT_RFID, 9600, timeout=0.1)
            print("RFID Serial reconnected.")
        except Exception as e:
            print(f"Reconnect RFID failed: {e}")
            serial_rfid = None
        return "", False, serial_rfid


def parse_lpr_data(data: bytes):
    try:
        hex_string = data.hex().upper()
        # print(hex_string)
        # print(hex_string[0:10])
        # BB88AA03FF42453236313644414B00000000000000000000000000006402001C
        if hex_string[0:10] == "BB88AA02FF" or hex_string[0:10] == "BB88AA03FF":
            raw_plate_data = hex_string[10:]
            # print(raw_plate_data)
            raw_plate_data = raw_plate_data[:-34]
            # print(raw_plate_data)
            plate_ascii_string = bytes.fromhex(raw_plate_data).decode('ascii')
            # print(plate_ascii_string)
            clean_plate = plate_ascii_string
            return clean_plate, True
        else:
            return "", False

    except Exception as e:
        print(f"LPR parsing error: {e}")
        return "", False


def read_lpr(serial_lpr):
    try:
        if serial_lpr is None or not serial_lpr.is_open:
            raise serial.SerialException("LPR Serial not open")

        data = serial_lpr.read(64)
        # print(data.hex())
        if len(data) < 5:
            serial_lpr.flushInput()
            serial_lpr.flushOutput()
            return "", False, serial_lpr

        plate, valid = parse_lpr_data(data)
        if not valid:
            print("Invalid LPR data received")
            return "", False, serial_lpr

        print(f"LPR Data (parsed): {plate}")
        return plate, True, serial_lpr
    except (serial.SerialException, OSError) as e:
        print(f"LPR Serial disconnected: {e}, attempting reconnect...")
        try:
            serial_lpr.close()
        except:
            pass
        try:
            serial_lpr = serial.Serial('/dev/ttyACM0', 9600, timeout=0.1)
            print("LPR Serial reconnected.")
        except Exception as e:
            print(f"Reconnect LPR failed: {e}")
            serial_lpr = None
        return "", False, serial_lpr


def parse_emoney_simple(response_hex: str):
    """
    Menghapus header lalu memisahkan cardType, cardNumber, dan balance.

    Args:
        response_hex (str): String hex seperti '02001100000000015715048100000205000EFBDCF9'

    Returns:
        dict: cardType, cardNo, balance (int)
    """
    try:
        response_hex = response_hex.upper().strip()

        if len(response_hex) < 41:
            print("❌ Invalid response length")
            return None

        # Step 1: Hapus header (02 00 11 00 00 00)
        payload = response_hex[14:-2]  # -2 untuk menghilangkan LRC di akhir

        # Step 2: Pisahkan field
        card_type = payload[0:2]
        card_number = payload[2:18]
        balance_hex = payload[18:26]

        balance = int(balance_hex, 16)

        return {
            "cardType": card_type,
            "cardNo": card_number,
            "balance": balance
        }

    except Exception as e:
        print(f"❌ Error parsing EMoney: {e}")
        return None


def check_balance(serial_emoney):
    try:
        if serial_emoney is None or not serial_emoney.is_open:
            raise serial.SerialException("EMoney Serial not open")

        logging.info("Checking balance...")

        current_time = time.strftime("%d%m%Y%H%M%S")
        timeout_bcd = "0002"
        command_body = bytes.fromhex("EF0102" + current_time + timeout_bcd)

        data_length = len(command_body)
        len_h = (data_length >> 8) & 0xFF
        len_l = data_length & 0xFF
        length_bytes = bytes([len_h, len_l])

        lrc_value = calculate_lrc(length_bytes + command_body)
        check_balance_command = b"\x02" + length_bytes + command_body + lrc_value

        logging.info(
            f"📤 Sending command: {check_balance_command.hex().upper()}")

        serial_emoney.write(check_balance_command)
        serial_emoney.flush()

        time.sleep(2)
        response = serial_emoney.read(64)

        if not response:
            print("No response received!")
            return False, "No response received"

        response_hex = response.hex().upper()
        print("Response:", response_hex)

        card_data = parse_emoney_simple(response_hex)
        if card_data is None:
            print("❌ Gagal memproses data EMoney (format atau LRC tidak valid)")
            return False, "Invalid EMoney data", serial_emoney

        print(f"Card Type: {card_data['cardType']}")
        print(f"Card No: {card_data['cardNo']}")
        print(f"Balance: {card_data['balance']}")

        return True, card_data, serial_emoney
    except (serial.SerialException, OSError) as e:
        logging.error(
            f"EMoney Serial disconnected: {e}, attempting reconnect...")
        try:
            serial_emoney.close()
        except:
            pass
        try:
            serial_emoney = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=2)
            initialize_device()
            logging.info("EMoney Serial reconnected.")
        except Exception as e:
            logging.error(f"Reconnect EMoney failed: {e}")
            serial_emoney = None
        return False, "Serial reconnect failed", serial_emoney
