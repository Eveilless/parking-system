import time
import threading
import config
import json
import serial
import os
import ui
import psutil
import shutil
import datetime
import logging
import platform
import subprocess
from logging.handlers import RotatingFileHandler
from pymodbus.client import ModbusTcpClient
from pymodbus import FramerType
from pymodbus.exceptions import ModbusIOException
from escpos.printer import Usb
from dotenv import load_dotenv
from transaction import validate_ticket, validate_emoney, validate_rfid
from handlers import sound_handler, oled_handler

# Modbus server configuration
HOST = None
PORT = None
TIMEOUT = 3

# Modbus parameters for input registers
SLAVE_ID_INPUT = 1
COIL_ADDRESS_INPUT = 0x0081
INPUT_COUNT = 8

# --- Konstanta Register (Perbaikan) ---
LOOP_ONE = 0
LOOP_TWO = 1
BUTTON_TICKET = 2

# Modbus parameters for output coils
SLAVE_ID_OUTPUT = 2
COIL_ADDRESS_OUTPUT = 0
OUTPUT_COUNT = 4
COIL_BARRIER_GATE = 0

# --- Global State Variables (Pengganti 'self') ---
# Variabel-variabel ini sekarang 'global'
# client = ModbusTcpClient(
#     host=HOST,
#     port=PORT,
#     framer=FramerType.RTU,
#     timeout=TIMEOUT,
#     retries=1
# )
client = None
prev_values = [None] * INPUT_COUNT
running = True
read_interval = 0.5  # 1 detik untuk RTU over TCP
lock = threading.Lock()
prev_button_value = None

# Global variable
serial_emoney = None
serial_rfid = None
serial_lpr = None

PRINTER_VENDOR = None
PRINTER_PRODUCT = None
PRINTER_IN_EP = None
PRINTER_OUT_EP = None

vehicle_detected = False
type_vehicle = None
ip_address = '127.0.0.1'

is_busy = False
main_widget = None
welcome_text = os.getenv(
    "WELCOME_TEXT", "SELAMAT DATANG DI BHC PARKING SYSTEM")
# --- Akhir Global State Variables ---


def connect():
    global HOST, PORT
    """Fungsi untuk koneksi (pengganti method connect)"""
    # Mengunci koneksi untuk thread-safety
    with lock:
        if client.connect():
            print(f"✅ Connected")
            return True
        else:
            print(f"❌ Failed to connect to {HOST}:{PORT}")
            return False


def disconnect():
    """Fungsi untuk diskoneksi (pengganti method disconnect)"""
    global running  # Kita perlu 'global' untuk mengubah nilainya
    running = False

    # Mengunci diskoneksi untuk thread-safety
    with lock:
        if client:
            client.close()
            # Pindah baris baru untuk kejelasan
            print("\n🔌 Connection closed")


def write_coil(address, state):
    """Fungsi untuk menulis coil (pengganti method write_coil)"""
    try:
        # --- Gunakan Lock untuk mengamankan penulisan ---
        with lock:
            result = client.write_coil(
                address=COIL_ADDRESS_OUTPUT + address,
                value=bool(state),
                slave=SLAVE_ID_OUTPUT
            )

        if not result.isError():
            print(f"✅ Coil {address} set to {'ON' if state else 'OFF'}")
            return True
        else:
            print(f"❌ Write error: {result}")
            return False

    except Exception as e:
        print(f"❌ Write exception: {e}")
        return False


def process_inputs_loop():
    """
    Loop tunggal untuk membaca SEMUA input (loop sensor DAN tombol)
    dari SLAVE_ID_INPUT.
    """
    global vehicle_detected, type_vehicle, prev_button_value, is_busy, main_widget, serial_emoney, serial_rfid

    while running:
        try:
            response = None
            # Lock ini HANYA untuk I/O Modbus, dan itu sudah benar.
            with lock:
                response = client.read_holding_registers(
                    address=COIL_ADDRESS_INPUT,
                    count=INPUT_COUNT,
                    slave=SLAVE_ID_INPUT
                )

            if response and not response.isError():
                current_values = response.registers

                # --- Logika 1: Deteksi Kendaraan ---
                loop_one = current_values[LOOP_ONE]
                loop_two = current_values[LOOP_TWO]

                if loop_one == 1:
                    local_type_vehicle = None
                    if loop_two == 0:
                        local_type_vehicle = os.getenv("IDLOOP1")
                    elif loop_two == 1:
                        local_type_vehicle = os.getenv("IDLOOP2")

                    # <-- PERBAIKAN: Gunakan lock untuk mengubah state deteksi
                    with lock:
                        if not vehicle_detected:
                            print(f"Kendaraan terdeteksi: {local_type_vehicle}")
                            sound_handler.play_vehicle_detected_sound(
                                "../assets/print_ticket.mp3")

                            vehicle_detected = True
                            type_vehicle = local_type_vehicle
                            print_to_oled("Vehicle detected", f"{type_vehicle}")
                            try:
                                if serial_emoney and serial_emoney.is_open:
                                    serial_emoney.reset_input_buffer()
                                if serial_rfid and serial_rfid.is_open:
                                    serial_rfid.reset_input_buffer()
                            except Exception as e:
                                print(
                                    f"Error membersihkan buffer serial: {e}")

                            main_widget.mode = "welcome"
                            main_widget.set_welcome_text(
                                "SILAHKAN TEMPELKAN KARTU ATAU TEKAN TOMBOL TICKET")
                            main_widget.update()

                else:  # (loop_one == 0)
                    # <-- PERBAIKAN: Gunakan lock untuk me-reset state
#                     with lock:
                    if vehicle_detected:
                        print("Kendaraan meninggalkan loop sensor")

                        main_widget.mode = "welcome"
                        main_widget.set_welcome_text(welcome_text.upper())
                        main_widget.update()
                        
                        ui.cleanup_vehicle_images()

                        print_to_oled("System ready")
                        write_coil(COIL_BARRIER_GATE, False)
                        print("Gate closed")
                        if is_busy:
                            print("Sistem SIAP kembali (Kendaraan Pergi).")
                            
                            if os.path.exists("ticket_data.json"):
                                os.remove("ticket_data.json")

                            print_to_oled("System ready")
                            write_coil(COIL_BARRIER_GATE, False)
#                             with lock:
                            is_busy = False

                        vehicle_detected = False
                        type_vehicle = None

                # --- Logika 2: Deteksi Tombol Tiket ---
                button_ticket = current_values[BUTTON_TICKET]
                prev = prev_button_value

                # Cek HANYA saat tombol DITEKAN (transisi 0 -> 1)
                if prev is not None and prev == 0 and button_ticket == 1:
                    
                    # <-- PERBAIKAN KRITIS: 'Cek-dan-Set' is_busy HARUS di dalam lock
                    with lock:
                        if is_busy == False and vehicle_detected == True:
                            # 1. Kunci sistem
                            time.sleep(2)
                            is_busy = True
                            
                            local_type_vehicle = type_vehicle
#                             print_to_oled("Button pressed")

                            # 2. Jalankan thread (di luar lock)
                            threading.Thread(
                                target=handle_print_ticket,
                                args=(local_type_vehicle,),
                                daemon=True).start()
                        elif is_busy == True:
                            print(
                                "Tombol ditekan, tapi sistem SIBUK. Abaikan.", "Button pressed only")
                        elif vehicle_detected == False:
                            print(
                                "❌ Tombol ditekan, tapi tidak ada kendaraan. Abaikan.")

                prev_button_value = button_ticket

            elif response and response.isError():
                if running:
                    print(
                        f"❌ Read error (Input Loop): {response}", "Error input loop")

        except ModbusIOException as e:
            if running:
                print(
                    f"❌ Read exception (Input Loop): {e}", "Exception (Input Loop)")
        except Exception as e:
            if running:
                print(
                    f"❌ UNEXPECTED exception (Input Loop): {e}", "UNEXPECTED exception", "Input Loop")

        time.sleep(read_interval)


def _get_printer():
    global PRINTER_VENDOR, PRINTER_PRODUCT, PRINTER_IN_EP, PRINTER_OUT_EP
    """
    Mencoba menginisialisasi dan mengembalikan objek printer.
    Mengembalikan None jika semua upaya gagal.
    """

    try:
        printer = Usb(
            PRINTER_VENDOR,
            PRINTER_PRODUCT,
            timeout=5000,
            profile="TM-T88III"
        )
        printer.open()
        return printer
    except Exception as e:
        print(
            f"Error initializing printer (utama): {str(e)}")
        try:
            # Fallback ke printer lain jika ada
            printer = Usb(0x0483, 0x5743, timeout=5000, profile="TM-T88III")
            printer.open()
            print("Fallback printer initialized.")
            return printer
        except Exception as e2:
            print(f"❌ GAGAL: Fallback printer juga gagal: {str(e2)}")
            return None


def _print_ticket_layout(printer, data):
    """
    Mencetak layout tiket standar menggunakan data (dict) yang diberikan.
    Akan melempar exception jika gagal.
    """
#     print(json.dumps(data, indent=2))
#     time.sleep(0.1)

    printer.set(align='center', bold=True, width=2, height=2)
    printer.text("TIKET MASUK\n\n")

    printer.set(align='left', bold=True, width=1, height=1)
    printer.text(f"{os.getenv('LABEL_UP')}\n\n")

    printer.set(align='left', bold=False, width=1, height=1)
    text = (
        f"{'ID':13}: {data.get('ticket_code', '')}\n"
        f"{'Pintu':13}: {data.get('device_name', '')}\n"
        f"{'Waktu Masuk':13}: {data.get('start_time', '')}\n"
        f"{'Plat Nomor':13}: {data.get('plat', '')}\n"
        f"{'Status':13}: {data.get('status', '')}\n"
    )
    printer.text(text)

    printer.set(align='center')
    printer.qr(str(data.get('ticket_code', '')), size=8)
    printer.text("\n\n")

#     time.sleep(0.2)
    printer.set(align='center', bold=False)
    printer.text(f"{os.getenv('LABEL_CENTER')}\n")
    printer.text(f"{os.getenv('LABEL_DOWN')}\n\n")

#     print("=== SELESAI print, akan cut ===", "Success print ticket")
#     time.sleep(0.1)
    printer.cut()


def handle_print_ticket(type_vehicle):
    global is_busy

#     print(f"🎟️ Tombol tiket ditekan untuk Tipe: {type_vehicle}")
#     print("✅ PROSES TIKET DIMULAI...", "Process print ticket")

    transaction_successful = False
    try:
        # ... (Logika validate_ticket dan print Anda) ...
        success, response = validate_ticket(type_vehicle)
        if success:
            save_transaction(response)
            # ... (Logika print online) ...
#             print("Validasi Online Sukses")
#             print_to_oled("Validate ticket")
            printer = None
            try:
                printer = _get_printer()  # Panggil helper
                if printer:
                    _print_ticket_layout(printer, response)  # Panggil helper
#                     print("Success print ticket (Online)",
#                                "Success print", "Online ticket")
                else:
                    print(
                        "❌❌ GAGAL Inisialisasi Printer (Online). Transaksi tetap lanjut.")

            except Exception as e_print:
                print(
                    f"❌❌ GAGAL PRINT TIKET (Online): {e_print} ❌❌")
                # Transaksi tetap lanjut, palang tetap buka.
            finally:
                if printer:
                    printer.close()

            
            write_coil(COIL_BARRIER_GATE, True)
            sound_handler.play_vehicle_detected_sound(
                "../assets/please_enter.mp3")
            time.sleep(2)
            ui.switch_to_payment_mode_with_data()
            print("Validasi sukses, Buka Palang.")
            print_to_oled("Gate opened")
            transaction_successful = True
        else:
            # ... (Logika print offline) ...
            print("Validasi Online Gagal. Masuk mode Offline...")
            print_to_oled("Print offline ticket")
            now = datetime.now()
            ticket_time = now.strftime("%Y/%m/%d %H:%M:%S")
            ticket_code = f"{type_vehicle}&PRK{int(time.time())}"
            plate = ""
            if os.path.exists("lpr.txt"):
                with open("lpr.txt", "r") as f:
                    lines = f.readlines()
                    if len(lines) >= 1:
                        plate = lines[0].strip()
                    else:
                        print("File lpr not found")
#                         print(
#                             "File lpr.txt kosong, tidak ada data plat nomor", "File lpr not found")

            ticket_data = {
                "ticket_code": ticket_code,
                "device_name": type_vehicle,
                "start_time": ticket_time,
                "plat": plate,
                "status": "Offline"
            }

            with open("ticket-offline.txt", "a") as f:
                f.write(ticket_code)
                f.write("\n")
#                 print(
#                     f"Saved offline ticket: {ticket_code}", "Saved offline ticket")

            success_save = save_transaction(ticket_data)
            if success_save:
                printer = None
                try:
                    printer = _get_printer()  # Panggil helper
                    if printer:
                        _print_ticket_layout(
                            printer, ticket_data)  # Panggil helper
#                         print("Success print ticket (Offline)",
#                                    "Success print", "Offline ticket")
                    else:
                        print(
                            "❌❌ GAGAL Inisialisasi Printer (Offline). Transaksi tetap lanjut.")

                except Exception as e_print_offline:
                    print(
                        f"❌❌ GAGAL PRINT TIKET (Offline): {e_print_offline} ❌❌")
                finally:
                    if printer:
                        printer.close()

                # Jika print offline sukses:
                write_coil(COIL_BARRIER_GATE, True)
                sound_handler.play_vehicle_detected_sound(
                    "../assets/please_enter.mp3")
                time.sleep(2)
                ui.switch_to_payment_mode_with_data()

                if os.path.exists("lpr.txt"):
                    os.remove("lpr.txt")

                print_to_oled("Gate opened")
                transaction_successful = True
            else:
                transaction_successful = False
                print(f"Gagal menyimpan tiket offline")
    except Exception as e:
        print(
            f"❌ Error saat proses tiket: {e}", "Error process", "Print ticket")
        transaction_successful = False  # Pastikan false jika ada exception
    finally:
        if not transaction_successful:
            print(
                "Sistem SIAP kembali (dari Tombol Tiket GAGAL).", "System ready")
            with lock:
                is_busy = False
        else:
            print("Proses Tiket sukses. Sistem menunggu kendaraan pergi.",)
            write_coil(COIL_BARRIER_GATE, False)
            print("Gate closed")


def emoney_loop():
    global is_busy, vehicle_detected, type_vehicle, serial_emoney

    # <-- PERBAIKAN: Inisialisasi 'serial_emoney' di luar try/except
    serial_emoney = None
    emoney_port = os.getenv('SERIAL_PORT')

    ALLOWED_CARD_TYPES = ["02", "03", "04", "05"]

    while running:
        try:
            # --- PERBAIKAN: BLOK KONEKSI ULANG ---
            if not serial_emoney or not serial_emoney.is_open:
                try:
                    serial_emoney = serial.Serial(emoney_port, 9600, timeout=1)
#                     print("✅ Emoney reader connected",
#                                "Emoney connected")
                except serial.SerialException as e:
                    print(
                        f"❌ Emoney reader not connected: {e}. Retrying in 3s...")
                    serial_emoney = None  # Pastikan None jika gagal
                    time.sleep(3)  # Tunggu 3 detik sebelum mencoba lagi
                    continue  # Ulangi loop
            # --- AKHIR BLOK KONEKSI ULANG ---

            # Cek 'vehicle_detected' dulu (ringan, tak perlu lock)
            if not vehicle_detected:
                time.sleep(0.1)
                continue

            # Jika ada data DAN kendaraan terdeteksi
            if serial_emoney.in_waiting > 0:

                should_process = False
                local_type_vehicle = None

                # <-- PERBAIKAN KRITIS: Cek-dan-Set 'is_busy'
                with lock:
                    if is_busy == False and vehicle_detected == True:
                        is_busy = True  # Klaim 'lock'
                        should_process = True
                        local_type_vehicle = type_vehicle

                if should_process:
                    transaction_successful = False
                    try:
                        # ... (Logika baca serial, process_emoney_data, validate_emoney) ...
                        emoney_data = serial_emoney.readline().hex().upper()
                        
                        card_info = process_emoney_data(emoney_data)

                        if card_info and card_info["cardType"] in ALLOWED_CARD_TYPES:
                            card_no = card_info["cardNo"]
                            card_type = card_info["cardType"]

                            print(f"EMoney Detected: {card_type} - {card_no}")
                            main_widget.set_welcome_text(
                                f"VALIDATE EMONEY: {card_no}".upper())
                            main_widget.update()

                            success, message, response = validate_emoney(
                                card_no, card_type, local_type_vehicle)
                            print_to_oled("Validate emoney", f"{card_no}")

                            if success:
                                write_coil(COIL_BARRIER_GATE, True)
                                save_transaction(response)
                                sound_handler.play_vehicle_detected_sound(
                                    "../assets/please_enter.mp3")
                                time.sleep(2)
                                ui.switch_to_payment_mode_with_data()
                                print_to_oled("Gate opened")
                                transaction_successful = True  # <-- TANDAI SUKSES
                            else:
                                # ... (tampilkan pesan error di UI) ...
                                text = f"{message} : {card_no}"
                                main_widget.set_welcome_text(text.upper())
                                main_widget.update()
                                time.sleep(1)
                        else:
                            print("Invalid EMoney data or CardType not allowed. Skipping.")

                    except Exception as e:
                        print(
                            f"Error memproses emoney: {e}")
                    finally:
                        if not transaction_successful:
                            # <-- PERBAIKAN: Jika GAGAL, bebaskan 'is_busy'
                            print("Sistem SIAP kembali (dari E-Money GAGAL).")
                            with lock:
                                is_busy = False
                        else:
                            print(
                                "Proses E-Money sukses. Sistem menunggu kendaraan pergi.")
                            write_coil(COIL_BARRIER_GATE, False)
                            print("Gate closed")

                        if serial_emoney and serial_emoney.is_open:
                            serial_emoney.reset_input_buffer()

            time.sleep(0.05)  # Poll cepat

        except serial.SerialException as se:
            # Tangani jika USB dicabut saat sedang running
            print(
                f"❌ Emoney reader disconnect error: {se}", "Emoney disconnected")
            if serial_emoney:
                serial_emoney.close()
            serial_emoney = None
            time.sleep(1)
        except Exception as e:
            if running:
                print(f"Error in emoney_loop: {e}", "Error emoney loop")
                time.sleep(0.5)

    if serial_emoney and serial_emoney.is_open:
        serial_emoney.close()
        print("Emoney reader connection closed.")


def process_emoney_data(data):
    try:
        if len(data) != 50:
            return None

        print("Processs emoney")
#         oled_handler.print_oled("Process emoney data")

        removeHeader = data[2:]
        index = 0
        hexLRC = "00"
        hexLRC = bytes.fromhex(hexLRC)

        # Calculate LRC
        for x in range(23):
            zz = removeHeader[index:index+2]
            zz = bytes.fromhex(zz)
            zz = int.from_bytes(zz, byteorder='big', signed=False)
            hexLRC = int.from_bytes(hexLRC, byteorder='big', signed=False)

            hexLRC = hexLRC ^ zz

            hexLRC = hex(hexLRC)
            hexLRC = str(hexLRC)
            hexLRC = hexLRC[2:]
            if len(hexLRC) == 1:
                hexLRC = "0"+hexLRC
            hexLRC = bytes.fromhex(hexLRC)
            index = index+2

        hexLRC = hexLRC.hex().upper()

#         print(hexLRC)

        if hexLRC == data[48:50]:
            print("LRC True")
            typeCard = data[6:8]
#             if typeCard == "01":
#                 print("STI Luminos Card")
#             elif typeCard == "02":
#                 print("eMoney Mandiri Card")
#             elif typeCard == "03":
#                 print("Brizzi BRI Card")
#             elif typeCard == "04":
#                 print("Tapcash BNI Card ")
#             elif typeCard == "05":
#                 print("Flazz BCA Card")
#             elif typeCard == "06":
#                 print("Jakcard DKI Card")
#             elif typeCard == "07":
#                 print("Bank Nobu Card ")
#             elif typeCard == "08":
#                 print("Bank Mega Card")
#             elif typeCard == "FF":
#                 print("Type A or Mifare Card")
#             else:
#                 print("unknown type card")

            uidCard = data[8:22]
#             print("UID card")
#             print(uidCard)

            dataValidity = data[22:24]
#             if dataValidity == "00":
#                 print("Card number and card balance is invalid")
#             elif dataValidity == "01":
#                 print("Card number is valid, but card balance is invalid")
#             elif dataValidity == "02":
#                 print("Card balance is valid, but card number is Invalid")
#             elif dataValidity == "03":
#                 print("Card balance and card number is valid")

            cardNo = data[24:40]
#             print("Card no")
#             print(cardNo)

            balance = data[40:48]
            balance = bytes.fromhex(balance)
            balance = int.from_bytes(balance, byteorder='big', signed=False)
#             print("balance")
#             print(balance)

        return {
            "cardType": typeCard,
            "uidCard": uidCard,
            "dataValidity": dataValidity,
            "cardNo": cardNo,
            "balance": balance,
        }

    except Exception as e:
        print(f"Error processing EMoney data: {e}")
        return None


def rfid_loop():
    global is_busy, vehicle_detected, type_vehicle, serial_rfid

    # <-- PERBAIKAN: Inisialisasi 'serial_rfid' di luar try/except
    serial_rfid = None
    rfid_port = os.getenv('SERIAL_PORT_RFID')

    while running:
        try:
            # --- PERBAIKAN: BLOK KONEKSI ULANG ---
            if not serial_rfid or not serial_rfid.is_open:
                try:
                    serial_rfid = serial.Serial(rfid_port, 9600, timeout=1)
#                     print("✅ RFID reader connected", "RFID Connected")
                except serial.SerialException as e:
                    print(
                        f"❌ RFID reader not connected: {e}. Retrying in 3s...")
                    serial_rfid = None
                    time.sleep(3)
                    continue
            # --- AKHIR BLOK KONEKSI ULANG ---

            if not vehicle_detected:
                time.sleep(0.1)
                continue

            if serial_rfid.in_waiting > 0:

                should_process = False
                local_type_vehicle = None

                # <-- PERBAIKAN KRITIS: Cek-dan-Set 'is_busy'
                with lock:
                    if is_busy == False and vehicle_detected == True:
                        is_busy = True  # Klaim 'lock'
                        should_process = True
                        local_type_vehicle = type_vehicle

                if should_process:
                    transaction_successful = False
                    try:
                        raw_data = serial_rfid.readline()
                        if len(raw_data) < 3:
                            continue  # Data sampah, abaikan
                        
                        data_rfid, success_parse = parsing_rfid(raw_data)
                        if success_parse:
                            main_widget.set_welcome_text(
                                f"VALIDATE RFID: {data_rfid}")
                            main_widget.update()

                            print_to_oled("Validate RFID", f"{data_rfid}")

                            success_validate, response = validate_rfid(
                                data_rfid, local_type_vehicle)

                            if success_validate:
                                write_coil(COIL_BARRIER_GATE, True)
                                text = f"Silahkan masuk: {data_rfid} / {response.get('name', '-')}"
                                main_widget.set_welcome_text(text.upper())
                                main_widget.update()
                                print_to_oled("Gate opened")
                                transaction_successful = True  # <-- TANDAI SUKSES
                            else:
                                text = f"{response} : {data_rfid}"
                                main_widget.set_welcome_text(text.upper())
                                main_widget.update()
                        else:
                            print(
                                "Data RFID tidak valid (parsing_rfid gagal).", "RFID invalid")

                    except Exception as e:
                        print(
                            f"Error process rfid: {e}", "Error process RFID")
                    finally:
                        if not transaction_successful:
                            # <-- PERBAIKAN: Jika GAGAL, bebaskan 'is_busy'
                            print(
                                "Sistem SIAP kembali (dari RFID GAGAL).", "System Ready")
                            
                            is_busy = False
                        else:
                            print(
                                "Proses RFID sukses. Sistem menunggu kendaraan pergi.")
                            write_coil(COIL_BARRIER_GATE, False)
                            print("Gate closed")

                        if serial_rfid and serial_rfid.is_open:
                            serial_rfid.reset_input_buffer()

            time.sleep(0.05)

        except serial.SerialException as se:
            print(f"❌ RFID reader disconnect error: {se}")
            if serial_rfid:
                serial_rfid.close()
            serial_rfid = None
            time.sleep(1)
        except Exception as e:
            if running:
                print(f"[RFID Error] {e}")
                time.sleep(0.5)

    if serial_rfid and serial_rfid.is_open:
        serial_rfid.close()
        print("RFID reader connection closed.")


def parsing_rfid(data):
    try:
        data = data.decode("utf-8", errors="ignore").strip()
        # Buang STX (0x02) jika ada
        if data.startswith('\x02'):
            data = data[1:]
        # Buang ETX (0x03) jika ada
        if data.endswith('\x03'):
            data = data[:-1]

        data = data.strip()  # Bersihkan spasi/karakter tak terlihat

        if len(data) <= 1:
            return "", False
        try:
            data_integer = int(data, 16)
        except ValueError:
            print(
                f"Parsing RFID (ValueError): '{data}' bukan hex. Cek format reader.")
            return "", False

        data_str = str(data_integer)[0:10]
        if len(data_str) < 10:
            data_str = data_str.zfill(10)

        print(f"RFID Data (parsed): {data_str}")
        return data_str, True
    except (serial.SerialException, OSError) as e:
        print(f"Parsing failed: {e}")
        return "", False
    except Exception as e:
        print(f"Unexpected parsing error: {e}")
        return "", False


def save_transaction(ticket_data):
    try:
        filename = "ticket_data.json"
        with open(filename, "w") as f:
            json.dump(ticket_data, f)

        nameCSV = str(ticket_data.get('ticket_code')) + ".tyto"
        with open(nameCSV, 'w') as f:
            f.write(ticket_data.get('ticket_code') + "\n")

        print(f"[Trigger] Ticket data written to {filename}")
        return True
    except Exception as e:
        print(f"[Error] Failed to write JSON: {e}")
        return False


def lpr_loop():
    global serial_lpr

    # <-- PERBAIKAN: Gunakan getenv dan inisialisasi di luar
    serial_lpr = None
    lpr_port = os.getenv('SERIAL_PORT_LPR', '/dev/ttyACM0')  # Ambil dari .env

    while running:  # <-- PERBAIKAN: Gunakan 'running'
        try:
            # --- PERBAIKAN: BLOK KONEKSI ULANG ---
            if not serial_lpr or not serial_lpr.is_open:
                if not os.path.exists(lpr_port):
                    print(
                        f"LPR device not found at {lpr_port}. Skipping 3s...")
                    time.sleep(3)
                    continue

                try:
                    serial_lpr = serial.Serial(lpr_port, 9600, timeout=1)
#                     print("✅ LPR connected")
                except serial.SerialException as e:
                    print(f"❌ LPR not connected: {e}. Retrying in 3s...")
                    serial_lpr = None
                    time.sleep(3)
                    continue
            # --- AKHIR BLOK KONEKSI ULANG ---

            data = serial_lpr.read(64)

            if len(data) < 5:
                serial_lpr.flushInput()
                serial_lpr.flushOutput()
                continue  # <-- PERBAIKAN: Gunakan 'continue', bukan 'return'

            plate, valid = parse_lpr_data(data)
            if valid:
                success, message = handle_lpr(plate)
                if success:
                    print(f"LPR: {message}")
                else:
                    print(f"LPR Error: {message}")

        except serial.SerialException as se:
            # Tangani jika USB dicabut
            print(f"❌ LPR disconnect error: {se}")
            if serial_lpr:
                serial_lpr.close()
            serial_lpr = None
            time.sleep(1)
        except Exception as e:
            if running:
                print(f"LPR Error: {e}")
                time.sleep(0.5)

    # Cleanup saat program berhenti
    if serial_lpr and serial_lpr.is_open:
        serial_lpr.close()
        print("LPR connection closed.")


def parse_lpr_data(data: bytes):
    try:
        hex_string = data.hex().upper()

        if hex_string[0:10] == "BB88AA02FF" or hex_string[0:10] == "BB88AA03FF":
            raw_plate_data = hex_string[10:]
            raw_plate_data = raw_plate_data[:-34]
            plate_ascii_string = bytes.fromhex(raw_plate_data).decode('ascii')
            clean_plate = plate_ascii_string
            return clean_plate, True
        else:
            return "", False

    except Exception as e:
        print(f"LPR parsing error: {e}")
        return "", False


def handle_lpr(dataLpr):
    try:
        cleaned_string = dataLpr.encode('ascii', 'ignore').decode('ascii')

        with open("lpr.txt", "w") as f:
            f.write(cleaned_string + "\n")
        print(f"License Plate Detected: {dataLpr}")

        return True, "File lpr saved successfully"
    except Exception as e:
        print(f"Error saving LPR data: {e}")
        return False, f"Error saving LPR data: {e}"


def print_to_oled(row_one='', row_two='', row_three=''):
    global ip_address
    logging.info(row_one)
    oled_handler.print_oled(ip_address, row_one, row_two, row_three)


def get_local_ip():
    global ip_address
    try:
        proc = subprocess.Popen(
            ["hostname", "-I"], stdout=subprocess.PIPE, universal_newlines=True)
        out, _ = proc.communicate()
        ip_address = out.split(' ')[0]
        print(f"Raspberry Pi IP: {ip_address}")
        logging.info(f"Raspberry PI IP: {ip_address}")
        return ip_address
    except Exception as e:
        print(f"Error getting IP address: {e}")
        logging.info(f"Error getting ip: {e}")
        ip_address = "Unknown"
        return ip_address


def _get_removable_drives():
    """
    Fungsi helper yang lebih tangguh untuk menemukan drive removable
    di Windows dan Linux (Raspberry Pi).
    """
    print("Memindai drive removable (flash disk)...")
    found_drives = []

    # --- Metode 1: psutil (Cross-platform, bagus untuk Windows) ---
    try:
        partitions = psutil.disk_partitions()
        psutil_drives = [
            p.mountpoint for p in partitions if 'removable' in p.opts.lower()]
        if psutil_drives:
            print(f"Drive (psutil) terdeteksi: {psutil_drives}")
            found_drives.extend(psutil_drives)
    except Exception as e:
        print(f"❌ Error saat cek psutil: {e}")

    # --- Metode 2: Fallback khusus untuk Linux/Raspi ---
    # Cek jika kita di Linux dan metode psutil gagal menemukan
    if platform.system() == "Linux":
        # Path umum untuk auto-mount di Raspi OS
        raspi_mount_path = "/media/pi"

        if os.path.exists(raspi_mount_path):
            try:
                # Ambil semua folder di /media/pi
                linux_drives = [
                    os.path.join(raspi_mount_path, d)
                    for d in os.listdir(raspi_mount_path)
                    if os.path.isdir(os.path.join(raspi_mount_path, d))
                ]

                if linux_drives:
                    print(
                        f"Drive (Linux fallback) terdeteksi: {linux_drives}")
                    found_drives.extend(linux_drives)
            except Exception as e:
                print(f"❌ Error saat cek path /media/pi: {e}")

    if not found_drives:
        print("Tidak ada drive removable yang terdeteksi.")
        return []

    # Menghilangkan duplikat jika psutil dan fallback menemukan hal yang sama
    final_drives = list(set(found_drives))
    print(f"Drive final ditemukan: {final_drives}")
    return final_drives


def setup_from_flash_drive(project_directory=".", assets_folder="assets"):
    """
    Menjalankan setup lengkap dari flash disk.
    Telah dimodifikasi untuk mencari .env di SEMUA drive yang ditemukan.
    """
    print(f"\n🚀 Memulai setup dari flash disk...")

    # --- Langkah 1: Temukan flash disk ---
    found_drives = _get_removable_drives()
    if not found_drives:
        return False  # Tidak ada drive terdeteksi

    # --- PERBAIKAN: Loop semua drive, cari .env ---
    drive_path = None
    project_env_path = os.path.join(project_directory, ".env")

    for drive in found_drives:
        drive_env_path = os.path.join(drive, ".env")
        print(f"Mencari file .env di: {drive_env_path}")
        if os.path.exists(drive_env_path):
            print(f"✅ File .env ditemukan di: {drive}")
            drive_path = drive  # Kita temukan drive yang benar
            break  # Hentikan pencarian

    if drive_path is None:
        print(
            "❌ GAGAL: File .env tidak ditemukan di drive removable manapun.")
        return False
    # --- Akhir Perbaikan Loop ---

    # --- Langkah 2: Salin .env dari flash disk ke proyek ---
    try:
        # drive_env_path sudah didefinisikan di loop di atas
        shutil.copy2(drive_env_path, project_env_path)
        print(f"✅ BERHASIL: File .env disalin ke {project_env_path}")
    except Exception as e:
        print(f"❌ GAGAL: Tidak dapat menyalin .env. Error: {e}")
        print(
            "   Pastikan skrip memiliki izin tulis (write permission) di direktori proyek.")
        return False

    # --- Langkah 3: Muat (load) file .env yang BARU disalin ---
    print(f"Memuat variabel dari {project_env_path}...")
    success = load_dotenv(dotenv_path=project_env_path, override=True)
    if not success:
        print(
            f"⚠️ PERINGATAN: Berhasil menyalin .env, tapi gagal memuatnya.")
        return True
    print("✅ Variabel lingkungan (environment) berhasil dimuat.")

    # --- Langkah 4: Salin file BACKGROUND_IMAGE ---
    background_filename = os.getenv('BACKGROUND_IMAGE')
    if not background_filename:
        print(
            f"⚠️ INFO: Variabel 'BACKGROUND_IMAGE' tidak ditemukan di .env.")
        return True

    print(f"Variabel 'BACKGROUND_IMAGE' ditemukan: {background_filename}")
    # Gunakan drive_path yang benar
    drive_asset_path = os.path.join(drive_path, background_filename)
    project_assets_dir = os.path.join(project_directory, assets_folder)
    project_asset_path = os.path.join(project_assets_dir, background_filename)

    try:
        os.makedirs(project_assets_dir, exist_ok=True)
    except Exception as e:
        print(
            f"❌ GAGAL: Tidak dapat membuat folder assets '{project_assets_dir}'. Error: {e}")
        return True

    print(f"Mencari file aset di: {drive_asset_path}")
    if not os.path.exists(drive_asset_path):
        print(
            f"❌ GAGAL: File '{background_filename}' tidak ditemukan di root flash disk.")
        return True

    try:
        shutil.copy2(drive_asset_path, project_asset_path)
        print(
            f"✅ BERHASIL: File '{background_filename}' disalin ke {project_asset_path}")
    except Exception as e:
        print(
            f"❌ GAGAL: Tidak dapat menyalin '{background_filename}'. Error: {e}")

    return True  # Semua proses selesai


def main():
    global main_widget, client
    global PRINTER_PRODUCT, PRINTER_VENDOR, PRINTER_IN_EP, PRINTER_OUT_EP

    # --- KONFIGURASI LOGGING ---
#     log_file = "/home/pi/parking-system/parking_system.log"
#     max_bytes = 10 * 1024 * 1024  # 5 MB
#     backup_count = 3  # Simpan 3 file lama (log.1, log.2, log.3)
# 
#     handler = RotatingFileHandler(
#         log_file,
#         maxBytes=max_bytes,
#         backupCount=backup_count
#     )

    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )

#     handler.setFormatter(formatter)

#     logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)

    get_local_ip()
    if os.path.exists("ticket_data.json"):
        os.remove("ticket_data.json")

    try:
        if setup_from_flash_drive():
            print("\nSetup dari flash disk selesai.")
        else:
            print(
                "\nSetup dari flash disk GAGAL. Program mungkin tidak berjalan normal.")
        
        HOST = os.getenv('ETH_HOST')
        PORT = int(os.getenv('ETH_PORT', '502'))
        
        vendor_str = os.getenv('PRINTER_VENDOR')
        product_str = os.getenv('PRINTER_PRODUCT') # <-- Diperbaiki
        in_ep_str = os.getenv('PRINTER_IN_EP')       # <-- Diperbaiki
        out_ep_str = os.getenv('PRINTER_OUT_EP')     # <-- Diperbaiki
        
        try:
            # Gunakan int(str, 16) untuk konversi hex
            # Cek jika string-nya ada (bukan None) sebelum konversi
            PRINTER_VENDOR = int(vendor_str, 16) if vendor_str else None
            PRINTER_PRODUCT = int(product_str, 16) if product_str else None
            PRINTER_IN_EP = int(in_ep_str, 16) if in_ep_str else None
            PRINTER_OUT_EP = int(out_ep_str, 16) if out_ep_str else None
            
            print(f"Printer Config (Integers): VENDOR={PRINTER_VENDOR}, PRODUCT={PRINTER_PRODUCT}")

        except (ValueError, TypeError) as e:
            print(f"❌❌ ERROR: Gagal konversi ID Printer dari .env. Cek format! Error: {e}")
            print("Pastikan format di .env adalah '0x...' (contoh: PRINTER_VENDOR=0x0483)")
            # Set ke None agar fallback printer bisa dicoba
            PRINTER_VENDOR, PRINTER_PRODUCT, PRINTER_IN_EP, PRINTER_OUT_EP = None, None, None, None

        client = ModbusTcpClient(
            host=HOST,
            port=PORT,
            framer=FramerType.RTU,
            timeout=TIMEOUT,
            retries=1
        )

        sound_handler.setup_sound()
        oled_handler.setup_oled()
        ui.cleanup_vehicle_images()
        main_widget = ui.show_ui()

        if connect(): 
            threading.Thread(target=emoney_loop,
                             daemon=True).start()
            threading.Thread(target=rfid_loop,
                             daemon=True).start()
            threading.Thread(target=lpr_loop,
                             daemon=True).start()
            threading.Thread(target=process_inputs_loop,
                             daemon=True).start()

            ui.app.exec_()
            print(
                "🚀 Modbus controller running. Tekan Ctrl+C untuk berhenti.")
            print_to_oled("System ready")

#             while True:
#                 time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Menjalankan shutdown...")
    except Exception as e:
        print(f"\n❌ Main thread error: {e}")
    finally:
        disconnect()

    print("Program selesai")


if __name__ == "__main__":
    main()
