import time
import threading
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

# --- Constants ---
# Modbus parameters for input registers
SLAVE_ID_INPUT = 1
COIL_ADDRESS_INPUT = 0x0081
INPUT_COUNT = 8
LOOP_ONE = 0
LOOP_TWO = 1
BUTTON_TICKET = 2

# Modbus parameters for output coils
SLAVE_ID_OUTPUT = 2
COIL_ADDRESS_OUTPUT = 0
OUTPUT_COUNT = 4
COIL_BARRIER_GATE = 0


class ParkingController:
    """
    A class-based controller for the parking system to encapsulate state and logic,
    improving robustness and maintainability.
    """

    def __init__(self):
        # --- System State ---
        self.running = True
        self.is_busy = False
        self.vehicle_detected = False
        self.type_vehicle = None
        self.ip_address = '127.0.0.1'

        # --- Threading & Concurrency ---
#         self.lock = threading.Lock()
        self.lock = threading.RLock()
        self.read_interval = 0.5  # Modbus read interval
        self.prev_button_value = None

        # --- Hardware Clients & Config ---
        self.client_modbus = None
        self.serial_emoney = None
        self.serial_rfid = None
        self.serial_lpr = None

        self.HOST = os.getenv('ETH_HOST')
        self.PORT = int(os.getenv('ETH_PORT', '502'))
        self.TIMEOUT = 3

        # --- Printer Configuration ---
        self.PRINTER_VENDOR = None
        self.PRINTER_PRODUCT = None

        # --- UI ---
        self.main_widget = None
        self.welcome_text = os.getenv(
            "WELCOME_TEXT")

    def _setup_logging(self):
        """Initializes file-based rotating logging."""
        log_file = "parking_system.log"
        max_bytes = 10 * 1024 * 1024  # 10 MB
        backup_count = 5

        handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s')
        handler.setFormatter(formatter)

        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)
        logging.info("Logging configured.")
        print("✅ Logging configured.")

    def _get_local_ip(self):
        """Fetches and stores the local IP address."""
        try:
            proc = subprocess.Popen(
                ["hostname", "-I"], stdout=subprocess.PIPE, universal_newlines=True)
            out, _ = proc.communicate()
            self.ip_address = out.split(' ')[0]
            logging.info(f"System IP Address: {self.ip_address}")
            print(f"✅ System IP: {self.ip_address}")
        except Exception as e:
            self.ip_address = "Unknown"
            logging.error(f"Failed to get IP address: {e}")
            print(f"❌ Failed to get IP: {e}")

    def _print_to_oled(self, row_one='', row_two='', row_three=''):
        """Helper method to print to the OLED display."""
        logging.info(f"OLED: {row_one}, {row_two}, {row_three}")
        oled_handler.print_oled(self.ip_address, row_one, row_two, row_three)

    def _connect_modbus(self):
        """Initializes and connects the Modbus client."""
        self.client_modbus = ModbusTcpClient(
            host=self.HOST,
            port=self.PORT,
            framer=FramerType.RTU,
            timeout=self.TIMEOUT,
            retries=1
        )
        with self.lock:
            if self.client_modbus.connect():
                logging.info("Modbus client connected.")
                print("✅ Modbus client connected.")
                return True
            else:
                logging.error(
                    f"Failed to connect to Modbus server at {self.HOST}:{self.PORT}")
                print(
                    f"❌ Failed to connect to Modbus server at {self.HOST}:{self.PORT}")
                return False

    def _disconnect(self):
        """Disconnects clients and gracefully shuts down."""
        self.running = False
        with self.lock:
            if self.client_modbus:
                self.client_modbus.close()
                logging.info("Modbus connection closed.")
                print("\n🔌 Modbus connection closed.")

        # Close serial ports if they are open
        if self.serial_emoney and self.serial_emoney.is_open:
            self.serial_emoney.close()
        if self.serial_rfid and self.serial_rfid.is_open:
            self.serial_rfid.close()
        if self.serial_lpr and self.serial_lpr.is_open:
            self.serial_lpr.close()
        print("Program finished.")
        logging.info("Application shut down.")

    def _write_coil(self, address, state):
        """Writes a value to a Modbus coil with thread-safety."""
        try:
            with self.lock:
                result = self.client_modbus.write_coil(
                    address=COIL_ADDRESS_OUTPUT + address,
                    value=bool(state),
                    slave=SLAVE_ID_OUTPUT
                )
            if not result.isError():
                logging.info(
                    f"Coil {address} set to {'ON' if state else 'OFF'}")
                return True
            else:
                logging.error(f"Modbus write error: {result}")
                return False
        except Exception as e:
            logging.error(f"Modbus write exception: {e}")
            return False

    def _reset_system_state(self, message="System ready"):
        """Resets the system to its initial state after a transaction or vehicle departure."""
        with self.lock:
            self.is_busy = False
            self.vehicle_detected = False
            self.type_vehicle = None

        if os.path.exists("ticket_data.json"):
            os.remove("ticket_data.json")

        self.main_widget.mode = "welcome"
        self.main_widget.set_welcome_text(self.welcome_text.upper())
        self.main_widget.update()
        
        ui.cleanup_vehicle_images()
        
        self._print_to_oled(message)
        self._write_coil(COIL_BARRIER_GATE, False)
        logging.info(f"System state has been reset. Reason: {message}")

    def _process_inputs_loop(self):
        """Main loop for reading Modbus inputs for vehicle detection and ticket button."""
        while self.running:
            try:
                if not self.client_modbus.is_socket_open():
                    logging.warning("Modbus connection lost. Reconnecting...")
                    self._connect_modbus()
                    time.sleep(2)
                    continue

                response = None
                with self.lock:
                    response = self.client_modbus.read_holding_registers(
                        address=COIL_ADDRESS_INPUT,
                        count=INPUT_COUNT,
                        slave=SLAVE_ID_INPUT
                    )

                if not response or response.isError():
                    if self.running:
                        logging.warning(f"Modbus read error: {response}")
                    time.sleep(self.read_interval)
                    continue

                current_values = response.registers
                loop_one = current_values[LOOP_ONE]

                # --- Vehicle Detection Logic ---
                with self.lock:
                    if loop_one == 1 and not self.vehicle_detected:
                        loop_two = current_values[LOOP_TWO]
                        self.vehicle_detected = True
                        self.type_vehicle = os.getenv(
                            "IDLOOP1") if loop_two == 0 else os.getenv("IDLOOP2")
                        logging.info(f"Vehicle detected: {self.type_vehicle}")

                        sound_handler.play_vehicle_detected_sound(
                            "../assets/print_ticket.mp3")
                        self._print_to_oled(
                            "Vehicle detected", f"{self.type_vehicle}")

                        self.main_widget.mode = "welcome"
                        self.main_widget.set_welcome_text(
                            "SILAHKAN TEMPELKAN KARTU ATAU TEKAN TOMBOL TICKET")
                        self.main_widget.update()

                        # Clear serial buffers
                        if self.serial_emoney and self.serial_emoney.is_open:
                            self.serial_emoney.reset_input_buffer()
                        if self.serial_rfid and self.serial_rfid.is_open:
                            self.serial_rfid.reset_input_buffer()

                    elif loop_one == 0 and self.vehicle_detected:
                        logging.info("Vehicle has left the sensor loop.")
                        self._reset_system_state()

                # --- Ticket Button Logic ---
                button_ticket = current_values[BUTTON_TICKET]
                if self.prev_button_value == 0 and button_ticket == 1:
                    should_start_thread = False
                    local_type_vehicle = None

                    with self.lock:
                        if not self.is_busy and self.vehicle_detected:
                            self.is_busy = True  # CRITICAL: Lock the system
                            should_start_thread = True
                            local_type_vehicle = self.type_vehicle

                    if should_start_thread:
                        logging.info(
                            "Ticket button pressed, starting transaction.")
                        threading.Thread(
                            target=self._handle_print_ticket,
                            args=(local_type_vehicle,),
                            daemon=True,
                            name="TicketHandler"
                        ).start()
                    else:
                        logging.warning(
                            "Button pressed, but system is busy or no vehicle detected.")

                self.prev_button_value = button_ticket

            except Exception as e:
                if self.running:
                    logging.error(
                        f"Unexpected error in input loop: {e}", exc_info=True)

            time.sleep(self.read_interval)

    def _get_printer(self):
        """Initializes and returns a printer object, with a fallback."""
        try:
            printer = Usb(self.PRINTER_VENDOR, self.PRINTER_PRODUCT,
                          timeout=5000, profile="TM-T88III")
            printer.open()
            logging.info("Primary printer initialized.")
            return printer
        except Exception as e:
            logging.warning(
                f"Primary printer failed: {str(e)}. Trying fallback.")
            try:
                printer = Usb(0x0483, 0x5743, timeout=5000,
                              profile="TM-T88III")  # Fallback
                printer.open()
                logging.info("Fallback printer initialized.")
                return printer
            except Exception as e2:
                logging.error(f"Fallback printer also failed: {str(e2)}")
                return None

    def _print_ticket_layout(self, printer, data):
        """Prints the standard ticket layout."""
        # This function is mostly IO and formatting, no state change
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

        printer.set(align='center', bold=False)
        printer.text(f"{os.getenv('LABEL_DOWN')}\n")
        printer.text(f"{os.getenv('LABEL_CENTER')}\n\n")
        printer.cut()

    def _handle_print_ticket(self, vehicle_type):
        """Handles the entire ticket printing transaction, both online and offline."""
        transaction_successful = False
        try:
            success, response = validate_ticket(vehicle_type)
            ticket_data = None

            if success:
                logging.info("Online ticket validation successful.")
                self._print_to_oled("Validate ticket")
                ticket_data = response
            else:
                logging.warning(
                    "Online validation failed. Switching to offline mode.")
                self._print_to_oled("Print offline ticket")
                now = datetime.datetime.now()
                plate = ""
                if os.path.exists("lpr.txt"):
                    with open("lpr.txt", "r") as f:
                        plate = f.readline().strip()

                ticket_data = {
                    "ticket_code": f"{vehicle_type}&PRK{int(time.time())}",
                    "device_name": vehicle_type,
                    "start_time": now.strftime("%Y/%m/%d %H:%M:%S"),
                    "plat": plate,
                    "status": "Offline"
                }
                with open("ticket-offline.txt", "a") as f:
                    f.write(ticket_data["ticket_code"] + "\n")

            # --- Save and Print ---
            if self._save_transaction(ticket_data):
                printer = self._get_printer()
                if printer:
                    try:
                        self._print_ticket_layout(printer, ticket_data)
                    except Exception as e_print:
                        logging.error(
                            f"Failed to print ticket: {e_print}", exc_info=True)
                    finally:
                        printer.close()
                else:
                    logging.error(
                        "Printer not available. Transaction continues without ticket.")

                # --- Open Gate ---
                self._write_coil(COIL_BARRIER_GATE, True)
                sound_handler.play_vehicle_detected_sound(
                    "../assets/please_enter.mp3")
                self._print_to_oled("Gate opened")
                self._write_coil(COIL_BARRIER_GATE, False)
                time.sleep(1.5)
                ui.switch_to_payment_mode_with_data()
                if os.path.exists("lpr.txt"):
                    os.remove("lpr.txt")
                
                transaction_successful = True
            else:
                logging.error("Failed to save transaction data.")
                transaction_successful = False

        except Exception as e:
            logging.error(
                f"Error during ticket transaction: {e}", exc_info=True)
            transaction_successful = False
        finally:
            if not transaction_successful:
                logging.warning("Ticket transaction failed. Resetting system.")
                # Reset with error message
                self._reset_system_state("Transaksi Gagal")
            else:
                logging.info(
                    "Ticket transaction successful. Awaiting vehicle to leave.")
                # The system will be fully reset once the vehicle leaves the loop.

    def _emoney_loop(self):
        """Loop to handle e-money card transactions."""
        emoney_port = os.getenv('SERIAL_PORT')
        ALLOWED_CARD_TYPES = ["02", "03", "04", "05"]

        while self.running:
            try:
                if not self.serial_emoney or not self.serial_emoney.is_open:
                    try:
                        self.serial_emoney = serial.Serial(
                            emoney_port, 9600, timeout=1)
                    except serial.SerialException as e:
                        if self.running:
                            logging.debug(
                                f"E-money reader not connected: {e}. Retrying...")
                        time.sleep(3)
                        continue

                # Fast check without lock to reduce contention
                if not self.vehicle_detected:
                    time.sleep(0.1)
                    continue

                if self.serial_emoney.in_waiting > 0:
                    should_process = False
                    local_type_vehicle = None
                    with self.lock:
                        if not self.is_busy and self.vehicle_detected:
                            self.is_busy = True
                            should_process = True
                            local_type_vehicle = self.type_vehicle

                    if should_process:
                        transaction_successful = False
                        try:
                            emoney_data = self.serial_emoney.readline().hex().upper()
                            card_info = self._process_emoney_data(emoney_data)

                            if card_info and card_info["cardType"] in ALLOWED_CARD_TYPES:
                                card_no = card_info["cardNo"]
                                logging.info(
                                    f"E-Money card detected: {card_no}")
                                success, message, response = validate_emoney(
                                    card_no, card_info["cardType"], local_type_vehicle)

                                if success:
                                    self._write_coil(COIL_BARRIER_GATE, True)
                                    self._save_transaction(response)
                                    
                                    sound_handler.play_vehicle_detected_sound(
                                        "../assets/please_enter.mp3")
                                    self._print_to_oled("Gate opened")
                                    self._write_coil(COIL_BARRIER_GATE, False)
                                    time.sleep(1.5)
                                    ui.switch_to_payment_mode_with_data()
                                    transaction_successful = True
                                else:
                                    # Display error on UI
                                    self.main_widget.set_welcome_text(
                                        f"{message} : {card_no}".upper())
                                    self.main_widget.update()
                                    time.sleep(2)
                        except Exception as e:
                            logging.error(
                                f"Error processing e-money: {e}", exc_info=True)
                        finally:
                            if not transaction_successful:
                                self._reset_system_state("E-Money Gagal")
                            else:
                                logging.info(
                                    "E-Money transaction successful. Awaiting vehicle to leave.")

                            if self.serial_emoney and self.serial_emoney.is_open:
                                self.serial_emoney.reset_input_buffer()

                time.sleep(0.05)

            except serial.SerialException as se:
                logging.error(f"E-money reader disconnected: {se}")
                if self.serial_emoney:
                    self.serial_emoney.close()
                self.serial_emoney = None
                time.sleep(1)
            except Exception as e:
                if self.running:
                    logging.error(
                        f"Unexpected error in e-money loop: {e}", exc_info=True)

    def _process_emoney_data(self, data):
        """Parses raw hex data from the e-money reader."""
        try:
            if len(data) != 50:
                return None

            removeHeader = data[2:]
            index = 0
            hexLRC = 0
            for _ in range(23):
                byte_val = int(removeHeader[index:index+2], 16)
                hexLRC ^= byte_val
                index += 2

            calculated_lrc_hex = f'{hexLRC:02X}'
            received_lrc_hex = data[48:50]

            if calculated_lrc_hex == received_lrc_hex:
                balance_bytes = bytes.fromhex(data[40:48])
                return {
                    "cardType": data[6:8],
                    "uidCard": data[8:22],
                    "dataValidity": data[22:24],
                    "cardNo": data[24:40],
                    "balance": int.from_bytes(balance_bytes, byteorder='big', signed=False),
                }
            else:
                logging.warning(
                    f"LRC mismatch in e-money data. Got {received_lrc_hex}, expected {calculated_lrc_hex}")
                return None
        except Exception as e:
            logging.error(f"Error parsing e-money data: {e}", exc_info=True)
            return None

    def _rfid_loop(self):
        """Loop to handle RFID member card transactions."""
        # This structure is very similar to emoney_loop, showing a good pattern
        rfid_port = os.getenv('SERIAL_PORT_RFID')
        while self.running:
            try:
                if not self.serial_rfid or not self.serial_rfid.is_open:
                    try:
                        self.serial_rfid = serial.Serial(
                            rfid_port, 9600, timeout=1)
                    except serial.SerialException:
                        time.sleep(3)
                        continue

                if not self.vehicle_detected:
                    time.sleep(0.1)
                    continue

                if self.serial_rfid.in_waiting > 0:
                    should_process, local_type_vehicle = False, None
                    with self.lock:
                        if not self.is_busy and self.vehicle_detected:
                            self.is_busy = True
                            should_process = True
                            local_type_vehicle = self.type_vehicle

                    if should_process:
                        transaction_successful = False
                        try:
                            raw_data = self.serial_rfid.readline()
                            data_rfid, success_parse = self._parsing_rfid(
                                raw_data)
                            if success_parse:
                                logging.info(
                                    f"RFID card detected: {data_rfid}")
                                success, response = validate_rfid(
                                    data_rfid, local_type_vehicle)
                                if success:
                                    self._write_coil(COIL_BARRIER_GATE, True)
                                    text = f"SILAHKAN MASUK: {response.get('name', '-')}"
                                    self.main_widget.set_welcome_text(
                                        text.upper())
                                    self.main_widget.update()
                                    self._print_to_oled("Gate opened")
                                    self._write_coil(COIL_BARRIER_GATE, False)
                                    transaction_successful = True
                                else:
                                    self.main_widget.set_welcome_text(
                                        f"{response} : {data_rfid}".upper())
                                    self.main_widget.update()
                                    time.sleep(2)
                        except Exception as e:
                            logging.error(
                                f"Error processing rfid: {e}", exc_info=True)
                        finally:
                            if not transaction_successful:
                                self._reset_system_state("RFID Gagal")
                            else:
                                logging.info(
                                    "RFID transaction successful. Awaiting vehicle to leave.")

                            if self.serial_rfid and self.serial_rfid.is_open:
                                self.serial_rfid.reset_input_buffer()
                time.sleep(0.05)
            except serial.SerialException as se:
                logging.error(f"RFID reader disconnected: {se}")
                if self.serial_rfid:
                    self.serial_rfid.close()
                self.serial_rfid = None
                time.sleep(1)
            except Exception as e:
                if self.running:
                    logging.error(
                        f"Unexpected error in rfid loop: {e}", exc_info=True)

    def _parsing_rfid(self, data):
        """Parses raw data from the RFID reader."""
        try:
            data_str = data.decode("utf-8", errors="ignore").strip()
            # Clean STX/ETX control characters
            if data_str.startswith('\x02'):
                data_str = data_str[1:]
            if data_str.endswith('\x03'):
                data_str = data_str[:-1]
            data_str = data_str.strip()

            if len(data_str) <= 1:
                return "", False

            data_integer = int(data_str, 16)
            final_str = str(data_integer).zfill(10)
            return final_str, True
        except (ValueError, TypeError):
            logging.warning(f"Could not parse RFID data as hex: '{data}'")
            return "", False
        except Exception as e:
            logging.error(f"Unexpected RFID parsing error: {e}", exc_info=True)
            return "", False

    def _save_transaction(self, ticket_data):
        """Saves transaction data to a JSON file."""
        try:
            with open("ticket_data.json", "w") as f:
                json.dump(ticket_data, f)
                
            nameCSV = str(ticket_data.get('ticket_code')) + ".tyto"
            with open(nameCSV, 'w') as f:
                f.write(ticket_data.get('ticket_code') + "\n")
                
            logging.info(
                f"Transaction data saved for ticket: {ticket_data.get('ticket_code')}")
            return True
        except Exception as e:
            logging.error(
                f"Failed to save transaction JSON: {e}", exc_info=True)
            return False

    def start(self):
        """Main entry point to set up and start the parking controller."""
        self._setup_logging()
        self._get_local_ip()

        # Clean up any leftover data from a previous run
        if os.path.exists("ticket_data.json"):
            os.remove("ticket_data.json")
        if os.path.exists("lpr.txt"):
            os.remove("lpr.txt")

        # NOTE: Flash drive setup is a one-time operation at startup.
        # It's kept separate as it modifies the environment itself.
        if setup_from_flash_drive():
            print("\n✅ Setup from flash disk completed.")
            # Reload env variables that might have been changed
            self.HOST = os.getenv('ETH_HOST')
            self.PORT = int(os.getenv('ETH_PORT', '502'))
        else:
            print("\n⚠️ Setup from flash disk failed or skipped. Using existing .env")

        try:
            vendor_str = os.getenv('PRINTER_VENDOR')
            product_str = os.getenv('PRINTER_PRODUCT')
            if vendor_str:
                self.PRINTER_VENDOR = int(vendor_str, 16)
            if product_str:
                self.PRINTER_PRODUCT = int(product_str, 16)
        except (ValueError, TypeError) as e:
            logging.error(
                f"Invalid printer ID format in .env file. Must be hex (e.g., 0x0483). Error: {e}")
            print("❌ Invalid printer ID format in .env file.")

        # --- Initialize Handlers and UI ---
        sound_handler.setup_sound()
        oled_handler.setup_oled()
        self.main_widget = ui.show_ui()
        self._print_to_oled("System booting...")

        # --- Start Hardware Loops ---
        if self._connect_modbus():
            thread_details = {
                "_emoney_loop": "EMoneyThread",
                "_rfid_loop": "RFIDThread",
                # "_lpr_loop": "LPRThread", # LPR can be added here if needed
                "_process_inputs_loop": "ModbusInputThread"
            }
            for target_method, name in thread_details.items():
                threading.Thread(
                    target=getattr(self, target_method),
                    daemon=True,
                    name=name
                ).start()

            self._print_to_oled("System ready")
            print("🚀 Parking controller running. Press Ctrl+C to stop.")
            ui.app.exec_()  # Start the UI event loop (blocking)

        # --- Shutdown ---
        self._disconnect()

# =================================================================================
# Helper functions for one-time setup (can remain outside the class)
# =================================================================================


def _get_removable_drives():
    """Finds removable drives (USB flash drives) across platforms."""
    found_drives = []
    try:
        partitions = psutil.disk_partitions()
        found_drives.extend(
            [p.mountpoint for p in partitions if 'removable' in p.opts.lower()])
    except Exception as e:
        print(f"Error checking psutil for drives: {e}")

    if platform.system() == "Linux":
        raspi_mount_path = "/media/pi"
        if os.path.exists(raspi_mount_path):
            try:
                linux_drives = [os.path.join(raspi_mount_path, d) for d in os.listdir(
                    raspi_mount_path) if os.path.isdir(os.path.join(raspi_mount_path, d))]
                if linux_drives:
                    found_drives.extend(linux_drives)
            except Exception as e:
                print(f"Error checking /media/pi: {e}")

    final_drives = sorted(list(set(found_drives)))
    if final_drives:
        print(f"Found removable drives: {final_drives}")
    return final_drives


def setup_from_flash_drive(project_directory=".", assets_folder="assets"):
    """
    Looks for a .env file on a removable drive and copies it and associated assets
    to the project directory.
    """
    print("\n🚀 Starting setup from flash drive...")
    found_drives = _get_removable_drives()
    if not found_drives:
        print("No removable drives found.")
        return False

    drive_path = None
    for drive in found_drives:
        if os.path.exists(os.path.join(drive, ".env")):
            print(f"✅ .env file found on drive: {drive}")
            drive_path = drive
            break

    if not drive_path:
        print("❌ No .env file found on any removable drive.")
        return False

    # Copy .env file
    try:
        project_env_path = os.path.join(project_directory, ".env")
        shutil.copy2(os.path.join(drive_path, ".env"), project_env_path)
        print(f"✅ .env file copied to {project_env_path}")
    except Exception as e:
        print(f"❌ Failed to copy .env file: {e}")
        return False

    # Load the new environment variables
    load_dotenv(dotenv_path=project_env_path, override=True)
    print("✅ Environment variables reloaded from new .env file.")

    # Copy background image if specified
    background_filename = os.getenv('BACKGROUND_IMAGE')
    if background_filename:
        drive_asset_path = os.path.join(drive_path, background_filename)
        project_asset_path = os.path.join(
            project_directory, assets_folder, background_filename)
        if os.path.exists(drive_asset_path):
            try:
                os.makedirs(os.path.join(project_directory,
                            assets_folder), exist_ok=True)
                shutil.copy2(drive_asset_path, project_asset_path)
                print(f"✅ Asset '{background_filename}' copied.")
            except Exception as e:
                print(f"❌ Failed to copy asset '{background_filename}': {e}")
        else:
            print(f"⚠️ Asset '{background_filename}' not found on drive.")

    return True


if __name__ == "__main__":
    try:
        ui.cleanup_vehicle_images()
        controller = ParkingController()
        controller.start()
    except KeyboardInterrupt:
        print("\n🛑 Shutdown requested by user.")
    except Exception as e:
        logging.critical(
            f"A critical error occurred in the main thread: {e}", exc_info=True)
        print(f"\n❌ A critical error occurred: {e}")
    finally:
        # The disconnect logic is handled inside the start() method's finally block,
        # but we call it again here in case of an error during initialization.
        if 'controller' in locals() and controller.running:
            controller._disconnect()
