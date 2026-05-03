import json
import os
import logging


def calculate_lrc(data: bytes) -> bytes:
    """Menghitung LRC (XOR dari LEN-H sampai Data[n])."""
    lrc = 0
    for byte in data:
        lrc ^= byte
    return bytes([lrc])


def bcd_to_str(bcd: bytes) -> str:
    """Konversi BCD ke string desimal"""
    return ''.join(f"{byte:02X}" for byte in bcd)


def read_json_session(filename):
    """Membaca file JSON yang berisi transaksi aktif."""
    if os.path.exists(filename):
        try:
            with open(filename, "r") as file:
                return json.load(file)
        except json.JSONDecodeError:
            logging.error("Error membaca file JSON.")
    return None


def delete_json_session(filename):
    """Menghapus file transaksi aktif."""
    if os.path.exists(filename):
        os.remove(filename)
        logging.info(f"Session {filename} berhasil dihapus.")


def card_type(card_type_code):
    """Mengembalikan jenis kartu berdasarkan kode kartu."""
    card_types = {
        0x01: "Luminos Prepaid Card",
        0x02: "MANDIRI eMoney",
        0x03: "BRI BRIZZI",
        0x04: "BNI Tapcash",
        0x05: "BCA Flazz",
        0x06: "DKI JakCard",
        0x07: "NOBU Card",
        0x08: "MEGA MegaCash",
        0x09: "QR Payment"
    }
    return card_types.get(card_type_code, f"Unknown (0x{card_type_code:02X})")

def get_card_type(card_type_code):
    """Mengembalikan jenis kartu berdasarkan kode kartu."""
    card_types = {
        0x01: "Luminos Prepaid Card",
        0x02: "MANDIRI eMoney",
        0x03: "BRI BRIZZI",
        0x04: "BNI Tapcash",
        0x05: "BCA Flazz",
        0x06: "DKI JakCard",
        0x07: "NOBU Card",
        0x08: "MEGA MegaCash",
        0x09: "QR Payment"
    }
    return card_types.get(card_type_code, f"Unknown (0x{card_type_code:02X})")

def format_transaction(
    card_type_code, mid, tid, trans_datetime_bcd, card_number_bcd,
    deduct_amount, balance_remaining, trans_log
):
    transaction_date = (
        f"{bcd_to_str(trans_datetime_bcd[0:1])}"  # Hari (DD)
        f"{bcd_to_str(trans_datetime_bcd[1:2])}"  # Bulan (MM)
        # Tahun (YYYY)
        f"{bcd_to_str(trans_datetime_bcd[2:3])}{bcd_to_str(trans_datetime_bcd[3:4])}"
        f"{bcd_to_str(trans_datetime_bcd[4:5])}"  # Jam (HH)
        f"{bcd_to_str(trans_datetime_bcd[5:6])}"  # Menit (MM)
        f"{bcd_to_str(trans_datetime_bcd[6:7])}"  # Detik (SS)
    )

    mid_str = mid.hex().upper()
    tid_str = tid.hex().upper()
    card_number = bcd_to_str(card_number_bcd)
    deduct_value = deduct_amount.hex().upper()
    balance_value = balance_remaining.hex().upper()
    trans_log_str = trans_log.hex().upper()

    formatted_transaction = (
        f"{card_type_code:02X}"
        f"{mid_str}"
        f"{tid_str}"
        f"{transaction_date}"
        f"{card_number}"
        f"{deduct_value}"
        f"{balance_value}"
        f"{trans_log_str}"
    )
    return formatted_transaction
