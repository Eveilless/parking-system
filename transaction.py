import requests  # type: ignore
import logging
import serial  # type: ignore
import time
import json
import os
import pytz
from datetime import datetime
import config
from handlers import serial_handler
# from handlers import oled_handler
from utils import read_json_session, delete_json_session, get_card_type

# List transaction for settlement
config.load_config()


def validate_ticket(type_vehicle):
    """Memvalidasi tiket ke server."""
    try:
        plate = ""
        if os.path.exists("lpr.txt"):
            with open("lpr.txt", "r") as f:
                lines = f.readlines()
                if len(lines) >= 1:
                    plate = lines[0].strip()
                else:
                    print("File lpr.txt kosong, tidak ada data plat nomor")

        url = os.getenv("SERVER") + os.getenv("VALIDATE_TICKET")
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url,
                                 json={"iddev": type_vehicle, "plate": plate}, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "success":
            print("success request")
            return True, data.get("transaction", {})
    except Exception as e:
        print("error request")
        logging.error(f"Error validating ticket: {e}")
        return False, "Ticket tidak valid"
    return False, "Ticket tidak valid (fallback)"


def validate_rfid(rfid_data, type_vehicle):
    """Memvalidasi RFID ke server."""
    try:
        url = os.getenv("SERVER") + os.getenv("VALIDATE_RFID")
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url,
                                 json={"rfid": rfid_data,
                                       "iddev": type_vehicle},
                                 headers=headers,
                                 timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "open":
            return True, data.get("transaction", {})
        else:
            return False, data.get("message", "Transaction not valid")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error validating RFID: {e}")
        return False, "Transaction tidak valid"


def attempt_deduction():
    """Mencoba proses deduksi saldo."""
    success, message = process_deduction()

    if success:
        try:
            delete_json_session(config.ACTIVE_TRANSACTION_FILE)
            # oled_handler.print_oled("Deduction", "Success", "Gate Opened")
            print("Deduction success")
            return True, message
        except Exception as e:
            logging.error(f"Gagal hapus session: {e}")
            return False, "Error"
    else:
        print("Deduction failed")
        # oled_handler.print_oled("Deduction", "Failed", message)
        time.sleep(1)
        # oled_handler.print_oled("Please use", "Ticket Button", "to continue")
        return False, message


def process_deduction():
    """Proses pengurangan saldo e-money."""
    ticket_data = read_json_session(config.ACTIVE_TRANSACTION_FILE)
    if not ticket_data:
        logging.warning("No active transaction found.")
        return False, "Tidak ada transaksi berjalan"

    amount = int(float(ticket_data.get("total_price", 0)))
    if amount <= 0:
        logging.warning("Invalid ticket amount.")
        return False, "Ticket tidak valid"

    try:
        with serial.Serial(config.SERIAL_PORT, config.BAUDRATE, timeout=10) as ser:
            for _ in range(config.MAX_RETRIES):
                result, message = deduct(ser, amount)
                if result:
                    return True, message
                time.sleep(1)
    except serial.SerialException as e:
        logging.error(f"Error processing deduction: {e}")
        return False, f"Error komunikasi dengan perangkat\n\nSilahkan coba lagi"

    return False, "Gagal melakukan transaksi \nSilahkan coba lagi"


def load_json():
    try:
        with open(config.ACTIVE_TRANSACTION_FILE, 'r', encoding='utf-8') as file:
            data = json.load(file)
            return data
    except FileNotFoundError:
        return None


def calculate_lrc(data: bytes) -> bytes:
    """Menghitung LRC (XOR dari LEN-H sampai Data[n])"""
    lrc = 0
    for byte in data:
        lrc ^= byte
    return bytes([lrc])


def validate_emoney(card_number, card_type, type_vehicle):
    """Memeriksa transaksi e-money ke server."""

    try:
        plate = ""
        if os.path.exists("lpr.txt"):
            with open("lpr.txt", "r") as f:
                lines = f.readlines()
                if len(lines) >= 1:
                    plate = lines[0].strip()
                else:
                    print("File lpr.txt kosong, tidak ada data plat nomor")

        url = os.getenv("SERVER") + os.getenv("VALIDATE_EMONEY")
        print(f"Url emoney: {url}")
        card_name = get_card_type(int(card_type, 16))

        headers = {'Content-Type': 'application/json'}
        response = requests.post(url,
                                 json={"iddev": type_vehicle,
                                       "card_number": card_number,
                                       "card_type": card_name,
                                       "plate": plate},
                                 headers=headers,
                                 timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "success":
            print("Validate success")
            # oled_handler.print_oled("Validate emoney success")
            return True, data.get("message"), data.get("transaction")
        else:
            print("Validate failed")
            # oled_handler.print_oled("Validate emoney failed")
            return False, "Transaksi tidak valid", None
    except requests.exceptions.RequestException as e:
        logging.error(f"Error checking e-money transaction: {e}")
        return False, "Error komunikasi dengan server", None


def deduct(ser, amount):
    """Mengurangi saldo kartu e-money"""
    tz = pytz.timezone("Asia/Jakarta")
    now = datetime.now(tz)

    date_bcd = bytes.fromhex(now.strftime('%d%m%Y'))
    time_bcd = bytes.fromhex(now.strftime('%H%M%S'))
    deduct_amount = amount.to_bytes(4, "big")
    timeout_bcd = bytes.fromhex(config.TIMEOUT_DEDUCT)

    command_body = bytes.fromhex(
        "EF0103") + date_bcd + time_bcd + deduct_amount + timeout_bcd
    data_length = len(command_body)
    length_bytes = bytes([data_length >> 8, data_length & 0xFF])
    lrc_value = calculate_lrc(length_bytes + command_body)

    deduct_command = b"\x02" + length_bytes + command_body + lrc_value

    logging.info(f"📤 Sending command: {deduct_command.hex().upper()}")
    ser.write(deduct_command)
    ser.flush()

    time.sleep(2)
    response = ser.read(128)

    if response:
        response_hex = response.hex().upper()
        logging.info(f"📥 Response: {response_hex}")
        print(f"Response deduct: {response_hex}")

        if len(response) < 47:
            if (response_hex == "0200040001100217"):
                return False, "Timeout: Silahkan scan ulang tiket!"

            if (response_hex == "0200040201100314"):
                if ser and ser.is_open:
                    ser.close()
                    time.sleep(1)

                serial_handler.initialize_device()
                return False, "Perangkat di-reset karena error!"

            return False, "Error: Respon terlalu pendek!"
        else:
            card_type_code = response[7]
            mid = response[8:16]
            tid = response[16:20]
            trans_datetime_bcd = response[20:27]
            card_number_bcd = response[27:35]
            deduct_amount = response[35:39]
            balance_remaining = response[39:43]
            trans_log = response[47:]

            balance_value = int.from_bytes(balance_remaining, "big")

            logging.info(f"Saldo setelah transaksi: Rp {balance_value}")
            return True, "Transaksi berhasil!"
    else:
        logging.warning("No response received from device!")
        return False, "Error: Tidak ada respon dari perangkat!"


def save_settlement(transactions):
    """Membuat file settlement batch berdasarkan format yang sesuai"""
    if not transactions:
        print("⚠️ Tidak ada transaksi untuk disimpan dalam settlement.")
        return

    # Hitung total transaksi & total nominal
    num_transactions = len(transactions)
    total_amount = sum(t["amount"] for t in transactions)

    # Buat nama file settlement
    settlement_time = datetime.now().strftime("%Y%m%d%H%M%S")
    batch_no = "001"  # Bisa diubah jika ingin batch meningkat

    mid = transactions[0]["mid"]  # Ambil MID dari transaksi pertama
    tid = transactions[0]["tid"]  # Ambil TID dari transaksi pertama

    file_name = f"{settlement_time}{mid}{tid}01{batch_no}.txt"
    file_path = os.path.join("./", file_name)

    with open(file_path, "w") as file:
        # Tulis header: "002" + jumlah transaksi (3 digit) + total nominal (10 digit)
        file.write(f"002{num_transactions:03}{total_amount:010}\n")

        # Tulis detail transaksi
        for t in transactions:
            file.write(
                f"0502{t['mid']}{t['tid']}{t['rrn']:06}{t['amount']:010}\n")

    print(f"✅ Settlement file {file_name} berhasil dibuat!")
