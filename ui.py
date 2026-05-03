import sys
import sys
import os
import json
import shutil
import glob
from PyQt5.QtWidgets import QApplication, QWidget, QShortcut
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QPolygon, QFontMetrics, QKeySequence
from PyQt5.QtCore import Qt, QTimer, QDateTime, QPoint, pyqtSignal, QObject, QThread

# === Configuration Constants === #
APP_TITLE = "Parking System Uniguard"
LOGO_FILENAME = "assets/uniguard.png"
BACKGROUND_FILENAME = "assets/background.png"  # Default fallback
CONTENT_FILENAME = "assets/content.png"
USB_MOUNT_PATH = "/media/pi"  # USB mount path on Raspberry Pi
HEADER_BG_COLOR = "#ffffff"  # White background for navbar
HEADER_TEXT_COLOR = "#000000"  # Black text for navbar
FOOTER_BG_COLOR = "#ffffff"  # White background for footer
FOOTER_TEXT_COLOR = "#000000"  # Black text for footer
CONTENT_BG_COLOR = "#f0f0f0"
SHADOW_COLOR = "#000000"
TEXT_COLOR = "#FFFFFF"
DEFAULT_FONT = QFont("Arial", 36, QFont.Bold)
HEADER_FONT = QFont("Arial", 20, QFont.Bold)
FOOTER_FONT = QFont("Arial", 28, QFont.Bold)

# Layout proportions
HEADER_HEIGHT_RATIO = 0.05  # 5% of screen height
FOOTER_HEIGHT_RATIO = 0.10  # 10% of screen height
CONTENT_HEIGHT_RATIO = 0.85  # 85% of screen height

# === Signal Handler === #


class SignalHandler(QObject):
    welcome_text_changed = pyqtSignal(str)


# === Global Vars === #
main_widget = None
signal_handler = SignalHandler()
app = None

# === Main Custom UI Widget === #


class CustomWidget(QWidget):
    def __init__(self, mode="welcome"):
        super().__init__()
        print(f"🏗️ Initializing CustomWidget in {mode} mode")
        self.mode = mode
        self.setWindowTitle(APP_TITLE)
        self.resize(1080, 720)
        self.font = DEFAULT_FONT

        # Load assets with error handling
        try:
            self.logo = self.load_logo()
            print("✅ Logo loaded successfully")
        except Exception as e:
            print(f"⚠️ Logo loading failed: {e}")
            self.logo = QPixmap()

        try:
            self.background_image = self.load_background()
            print("✅ Background image loaded successfully")
        except Exception as e:
            print(f"⚠️ Background image loading failed: {e}")
            self.background_image = QPixmap()

        try:
            self.content_image = self.load_content()
            print("✅ Content image loaded successfully")
        except Exception as e:
            print(f"⚠️ Content image loading failed: {e}")
            self.content_image = QPixmap()

        self.welcome_text = os.getenv("WELCOME_TEXT")
        self.payment_instruction_text = "Please tap your eMoney card"

        try:
            self.setup_signals()
            print("✅ Signals setup complete")
        except Exception as e:
            print(f"⚠️ Signals setup failed: {e}")

        try:
            self.setup_timer()
            print("✅ Timer setup complete")
        except Exception as e:
            print(f"⚠️ Timer setup failed: {e}")

        try:
            self.setup_shortcuts()
            print("✅ Shortcuts setup complete")
        except Exception as e:
            print(f"⚠️ Shortcuts setup failed: {e}")

        self.payment_data = {}
        self.vehicle_image = QPixmap()
        self.vehicle_image1 = QPixmap()  # First vehicle image
        self.vehicle_image2 = QPixmap()  # Second vehicle image

        print("🖥️ CustomWidget initialization complete")

    def set_payment_data(self, data_dict):
        self.payment_data = data_dict.copy()
        self.update()

    def set_vehicle_image(self, image_path):
        if os.path.exists(image_path):
            self.vehicle_image = QPixmap(image_path)
        else:
            self.vehicle_image = QPixmap()
        self.update()

    def set_vehicle_image1(self, image_path):
        """Set the first vehicle image for payment display"""
        if image_path and os.path.exists(image_path):
            self.vehicle_image1 = QPixmap(image_path)
            print(f"Vehicle image 1 loaded: {image_path}")
        else:
            self.vehicle_image1 = QPixmap()
            if image_path:
                print(f"Vehicle image 1 not found: {image_path}")
            else:
                print("Vehicle image 1 cleared")
        self.update()

    def set_vehicle_image2(self, image_path):
        """Set the second vehicle image for payment display"""
        if image_path and os.path.exists(image_path):
            self.vehicle_image2 = QPixmap(image_path)
            print(f"Vehicle image 2 loaded: {image_path}")
        else:
            self.vehicle_image2 = QPixmap()
            if image_path:
                print(f"Vehicle image 2 not found: {image_path}")
            else:
                print("Vehicle image 2 cleared")
        self.update()

    def load_logo(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(script_dir, LOGO_FILENAME)

        if os.path.exists(logo_path):
            print(f"Logo loaded from: {logo_path}")
            return QPixmap(logo_path)
        else:
            print(f"Logo not found at: {logo_path}")
            return QPixmap()  # Return empty pixmap as fallback

    def load_background(self):
        """Load background image dynamically from environment variable and USB mount"""
        script_dir = os.path.dirname(os.path.abspath(__file__))

        # Get background image filename from environment variable
        env_bg_filename = os.getenv("BACKGROUND_IMAGE", "background.png")
        print(f"Environment BACKGROUND_IMAGE: {env_bg_filename}")

        # Priority order for loading background image:
        # 1. USB mount path with env filename
        # 2. Local assets with env filename
        # 3. USB mount path with default filename
        # 4. Local assets with default filename

        image_paths = [
            # USB + env filename
            os.path.join("assets/", env_bg_filename),
            # Local + env filename
            os.path.join(script_dir, "assets", env_bg_filename),
            os.path.join("assets/", "background.png"),  # USB + default
            os.path.join("assets/", BACKGROUND_FILENAME)  # Local + default
        ]

        for image_path in image_paths:
            if os.path.exists(image_path):
                print(f"Background image loaded from: {image_path}")
                return QPixmap(image_path)
            else:
                print(f"Background image not found at: {image_path}")

        print("No background image found, using empty pixmap")
        return QPixmap()

    def load_content(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        content_path = os.path.join(script_dir, CONTENT_FILENAME)

        if os.path.exists(content_path):
            print(f"Content image loaded from: {content_path}")
            return QPixmap(content_path)
        else:
            print(f"Content image not found at: {content_path}")
            return QPixmap()  # Return empty pixmap as fallback

    def setup_signals(self):
        signal_handler.welcome_text_changed.connect(self.set_welcome_text)

    def setup_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(30)

    def setup_shortcuts(self):
        QShortcut(QKeySequence("F11"), self).activated.connect(
            self.toggle_fullscreen)

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def set_welcome_text(self, new_text):
        self.welcome_text = new_text
        self.update()

    def set_content_image(self, image_path):
        """Dynamically set content image from file path"""
        if image_path and os.path.exists(image_path):
            self.content_image = QPixmap(image_path)
            print(f"Content image loaded: {image_path}")
        else:
            self.content_image = QPixmap()
            if image_path:
                print(f"Content image not found: {image_path}")
            else:
                print("Content image cleared")
        self.update()

    def set_content_pixmap(self, pixmap):
        """Dynamically set content image from QPixmap object"""
        if isinstance(pixmap, QPixmap) and not pixmap.isNull():
            self.content_image = pixmap
            print("Content image set from pixmap")
        else:
            self.content_image = QPixmap()
            print("Invalid pixmap provided")
        self.update()

    def clear_content(self):
        """Clear the content image"""
        self.content_image = QPixmap()
        print("Content image cleared")
        self.update()

    def reload_background_image(self):
        """Reload background image dynamically"""
        print("Reloading background image...")
        self.background_image = self.load_background()
        self.update()
        print("Background image reloaded")

    def paintEvent(self, event):
        painter = QPainter(self)

        if self.mode == "welcome":
            self.draw_three_section_layout(painter)
        elif self.mode == "payment":
            self.draw_three_section_payment_layout(painter)

    def draw_three_section_layout(self, painter):
        w, h = self.width(), self.height()

        # Calculate section heights
        header_height = int(h * HEADER_HEIGHT_RATIO)
        footer_height = int(h * FOOTER_HEIGHT_RATIO)
        content_height = h - header_height - footer_height

        # Draw header section (top 5%)
        self.draw_header_section(painter, 0, 0, w, header_height)

        # Draw content section (middle 85%)
        self.draw_content_section(painter, 0, header_height, w, content_height)

        # Draw footer section (bottom 10%)
        self.draw_footer_section(
            painter, 0, header_height + content_height, w, footer_height)

    def draw_header_section(self, painter, x, y, width, height):
        # Draw header background
        painter.fillRect(x, y, width, height, QColor(HEADER_BG_COLOR))

        # Get current date and time
        now = QDateTime.currentDateTime()
        painter.setPen(QColor(HEADER_TEXT_COLOR))
        painter.setFont(HEADER_FONT)

        # Format date and time separately
        date_text = now.toString("dddd, dd MMMM yyyy")
        time_text = now.toString("hh:mm:ss")

        # Draw date in the left corner (x=30 as per specifications)
        date_rect = painter.viewport()
        date_rect.setX(x + 30)  # 30px margin from left as per specification
        date_rect.setY(y)
        date_rect.setWidth(width // 2 - 30)  # Left half minus margin
        date_rect.setHeight(height)

        painter.drawText(date_rect, Qt.AlignLeft | Qt.AlignVCenter, date_text)

        # Draw time in the right corner
        time_rect = painter.viewport()
        time_rect.setX(x + width // 2)
        time_rect.setY(y)
        time_rect.setWidth(width // 2 - 30)  # Right half minus margin
        time_rect.setHeight(height)

        painter.drawText(time_rect, Qt.AlignRight | Qt.AlignVCenter, time_text)

    def draw_content_section(self, painter, x, y, width, height):
        # Draw background image if available, otherwise use solid color
        if not self.background_image.isNull():
            # Scale the background image to fit exactly within the content area
            scaled_bg = self.background_image.scaled(
                width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            # Center the background image in the content area
            bg_x = x + (width - scaled_bg.width()) // 2
            bg_y = y + (height - scaled_bg.height()) // 2

            # Ensure background image stays within content section boundaries
            bg_x = max(x, min(bg_x, x + width - scaled_bg.width()))
            bg_y = max(y, min(bg_y, y + height - scaled_bg.height()))

            # Clip the drawing area to prevent overflow into header/footer
            painter.save()
            painter.setClipRect(x, y, width, height)
            painter.drawPixmap(bg_x, bg_y, scaled_bg)
            painter.restore()
        else:
            # Fallback to solid color background
            painter.fillRect(x, y, width, height, QColor(CONTENT_BG_COLOR))

        # Draw content image if available (overlaid on background)
        if not self.content_image.isNull():
            # Scale the content image to fit the area while maintaining aspect ratio
            # Add margins to ensure image doesn't touch boundaries
            margin = 20
            scaled_content = self.content_image.scaled(
                width - (margin * 2), height - (margin * 2), Qt.KeepAspectRatio, Qt.SmoothTransformation)

            # Center the image in the content area with margins
            img_x = x + (width - scaled_content.width()) // 2
            img_y = y + (height - scaled_content.height()) // 2

            # Ensure the image stays within the content section boundaries
            img_x = max(x + margin, min(img_x, x + width -
                        scaled_content.width() - margin))
            img_y = max(y + margin, min(img_y, y + height -
                        scaled_content.height() - margin))

            painter.drawPixmap(img_x, img_y, scaled_content)

    def draw_footer_section(self, painter, x, y, width, height):
        # Draw footer background
        painter.fillRect(x, y, width, height, QColor(FOOTER_BG_COLOR))

        # Draw welcome text
        painter.setPen(QColor(FOOTER_TEXT_COLOR))
        painter.setFont(FOOTER_FONT)

        # Center the welcome text in footer
        painter.drawText(x, y, width, height,
                         Qt.AlignCenter, self.welcome_text)

    def draw_three_section_payment_layout(self, painter):
        w, h = self.width(), self.height()

        # Calculate section heights (same as welcome mode)
        header_height = int(h * HEADER_HEIGHT_RATIO)
        footer_height = int(h * FOOTER_HEIGHT_RATIO)
        content_height = h - header_height - footer_height

        # Draw header section (same as welcome)
        self.draw_header_section(painter, 0, 0, w, header_height)

        # Draw payment content section (white background with payment data)
        self.draw_payment_content_section(
            painter, 0, header_height, w, content_height)

        # Draw footer section (same as welcome)
        self.draw_footer_section(
            painter, 0, header_height + content_height, w, footer_height)

    def draw_payment_content_section(self, painter, x, y, width, height):
        # Draw white background for payment content
        painter.fillRect(x, y, width, height, QColor("#FFFFFF"))

        # Calculate layout areas
        left_width = int(width * 0.6)  # 60% for payment data
        right_width = width - left_width  # 40% for vehicle photo
        margin = 20

        # Draw payment data on the left side
        self.draw_payment_data(painter, x + margin, y + margin,
                               left_width - margin * 2, height - margin * 2)

        # Draw vehicle photos on the right side (2 photos stacked vertically)
        self.draw_vehicle_photos(painter, x + left_width + margin, y + margin,
                                 right_width - margin * 2, height - margin * 2)

    def draw_payment_data(self, painter, x, y, width, height):
        # Set font for payment data
        painter.setFont(QFont("Arial", 20, QFont.Bold))
        painter.setPen(QColor("#333333"))  # Dark gray text

        # Calculate total content height for vertical centering
        title_height = 40
        line_spacing = 50  # Increased spacing for better readability
        data_lines = len(self.payment_data)
        total_content_height = title_height + 40 + (data_lines * line_spacing)

        # Calculate starting Y position for vertical centering
        start_y = y + (height - total_content_height) // 2
        current_y = start_y

        # Draw title
        painter.setFont(QFont("Arial", 28, QFont.Bold))
        painter.setPen(QColor("#000000"))  # Black text for title
        painter.drawText(x, current_y, "DATA TIKET PARKIR")
        current_y += title_height + 40  # Increased spacing after title

        # Draw payment data
        painter.setFont(QFont("Arial", 20, QFont.Normal))
        painter.setPen(QColor("#333333"))  # Dark gray text

        # Define friendly field names
        field_names = {
            'ticket_code': 'Kode Tiket',
            'device_name': 'Pintu Masuk',
            'start_time': 'Waktu Masuk',
            'plat': 'Plat Nomor',
            'status': 'Status',
            'emoney_card_number': 'No Kartu',
            'emoney_card_type': 'Jenis Kartu',
            'emoney_balance': 'Sisa Saldo'
        }

        for key, value in self.payment_data.items():
            display_key = field_names.get(key, key.replace('_', ' ').title())

            # Format balance with currency if it's the balance field
            if key == 'emoney_balance' and value is not None:
                try:
                    balance_value = float(value)
                    formatted_value = f"Rp {balance_value:,.0f}".replace(
                        ",", ".")
                except (ValueError, TypeError):
                    formatted_value = str(value)
            else:
                formatted_value = str(value) if value is not None else 'N/A'

            line = f"{display_key}: {formatted_value}"
            painter.drawText(x, current_y, line)
            current_y += line_spacing

    def draw_vehicle_photos(self, painter, x, y, width, height):
        """Draw 2 vehicle photos stacked vertically on the right side"""
        # Calculate dimensions for 2 photos with spacing
        photo_spacing = 10
        # Split height equally with spacing
        photo_height = (height - photo_spacing) // 2

        # Draw first photo (top)
        photo1_y = y
        self.draw_single_vehicle_photo(painter, x, photo1_y, width, photo_height,
                                       self.vehicle_image1, "FOTO KENDARAAN\n(IPCAM)\nTIDAK TERSEDIA")

        # Draw second photo (bottom)
        photo2_y = y + photo_height + photo_spacing
        self.draw_single_vehicle_photo(painter, x, photo2_y, width, photo_height,
                                       self.vehicle_image2, "FOTO PLAT NOMOR\n(LPR)\nTIDAK TERSEDIA")

    def draw_single_vehicle_photo(self, painter, x, y, width, height, image, placeholder_text):
        """Draw a single vehicle photo with placeholder if image is not available"""
        if not image.isNull():
            # Scale the vehicle image to fit the area
            scaled_vehicle = image.scaled(
                width, height - 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)

            # Center the image in the area
            img_x = x + (width - scaled_vehicle.width()) // 2
            img_y = y + (height - scaled_vehicle.height()) // 2

            # Ensure image stays within bounds
            img_x = max(x, min(img_x, x + width - scaled_vehicle.width()))
            img_y = max(y, min(img_y, y + height - scaled_vehicle.height()))

            painter.drawPixmap(img_x, img_y, scaled_vehicle)
        else:
            # Draw placeholder for vehicle photo
            painter.setPen(QColor("#CCCCCC"))
            painter.drawRect(x, y, width, height - 20)

            painter.setPen(QColor("#666666"))
            painter.setFont(QFont("Arial", 14, QFont.Normal))
            painter.drawText(x, y, width, height - 20,
                             Qt.AlignCenter, placeholder_text)


# === Public API === #
def show_ui():
    global main_widget, app

    print("📱 Starting UI initialization...")

    # Check if QApplication already exists
    if QApplication.instance() is not None:
        app = QApplication.instance()
        print("✅ Using existing QApplication instance")
    else:
        try:
            app = QApplication(sys.argv)
            print("✅ New QApplication created")
        except Exception as e:
            print(f"❌ Failed to create QApplication: {e}")
            raise

    try:
        main_widget = CustomWidget()
        print("✅ CustomWidget created")

        main_widget.setCursor(Qt.BlankCursor)
        print("✅ Cursor set to blank")

        # Show fullscreen
        main_widget.showFullScreen()
        print("✅ Widget shown in fullscreen")

        # Force update to ensure it's visible
        main_widget.update()
        app.processEvents()
        print("✅ UI events processed")

        return main_widget

    except Exception as e:
        print(f"❌ CustomWidget initialization failed: {e}")
        raise


def show_ui_payment(ticket_data):
    global main_widget, app

    print("📳 Starting payment UI initialization...")

    # Check if QApplication already exists
    if QApplication.instance() is not None:
        app = QApplication.instance()
        print("✅ Using existing QApplication instance")
    else:
        try:
            app = QApplication(sys.argv)
            print("✅ New QApplication created")
        except Exception as e:
            print(f"❌ Failed to create QApplication: {e}")
            raise

    try:
        main_widget = CustomWidget(mode="payment")
        print("✅ CustomWidget created in payment mode")

        main_widget.setCursor(Qt.BlankCursor)
        main_widget.set_payment_data(ticket_data)
        print("✅ Payment data set")

        # Show fullscreen
        main_widget.showFullScreen()
        print("✅ Payment widget shown in fullscreen")

        # Force update to ensure it's visible
        main_widget.update()
        app.processEvents()
        print("✅ Payment UI events processed")

        return main_widget

    except Exception as e:
        print(f"❌ Payment UI initialization failed: {e}")
        raise


def set_welcome_text(text):
    if app and app.thread() == QThread.currentThread() and main_widget:
        main_widget.set_welcome_text(text)
    else:
        signal_handler.welcome_text_changed.emit(text)


def set_content_image(image_path):
    """Dynamically set content image from external modules"""
    if app and app.thread() == QThread.currentThread() and main_widget:
        main_widget.set_content_image(image_path)


def set_content_pixmap(pixmap):
    """Dynamically set content image from QPixmap object"""
    if app and app.thread() == QThread.currentThread() and main_widget:
        main_widget.set_content_pixmap(pixmap)


def clear_content():
    """Clear the content image"""
    if app and app.thread() == QThread.currentThread() and main_widget:
        main_widget.clear_content()


def set_vehicle_image1(image_path):
    """Set the first vehicle image for payment display"""
    if app and app.thread() == QThread.currentThread() and main_widget:
        main_widget.set_vehicle_image1(image_path)


def set_vehicle_image2(image_path):
    """Set the second vehicle image for payment display"""
    if app and app.thread() == QThread.currentThread() and main_widget:
        main_widget.set_vehicle_image2(image_path)


def reload_background_image():
    """Reload background image dynamically from environment and USB"""
    if app and app.thread() == QThread.currentThread() and main_widget:
        main_widget.reload_background_image()


def load_ipcam_image():
    """Load the latest image from ipcam folder"""
    ipcam_folder = "ipcam"
    if not os.path.exists(ipcam_folder):
        print(f"ipcam folder not found: {ipcam_folder}")
        return None

    try:
        # Get all image files in ipcam folder
        image_files = [f for f in os.listdir(ipcam_folder)
                       if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp'))]

        if not image_files:
            print("No image files found in ipcam folder")
            return None

        # Sort by modification time and get the latest
        image_files.sort(key=lambda x: os.path.getmtime(
            os.path.join(ipcam_folder, x)), reverse=True)
        latest_image = os.path.join(ipcam_folder, image_files[0])

        print(f"Loading ipcam image: {latest_image}")
        return latest_image
    except Exception as e:
        print(f"Error loading ipcam image: {e}")
        return None


def load_lpr_image():
    """Load the latest image from lpr folder"""
    lpr_folder = "lpr"
    if not os.path.exists(lpr_folder):
        print(f"lpr folder not found: {lpr_folder}")
        return None

    try:
        # Get all image files in lpr folder
        image_files = [f for f in os.listdir(lpr_folder)
                       if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp'))]

        if not image_files:
            print("No image files found in lpr folder")
            return None

        # Sort by modification time and get the latest
        image_files.sort(key=lambda x: os.path.getmtime(
            os.path.join(lpr_folder, x)), reverse=True)
        latest_image = os.path.join(lpr_folder, image_files[0])

        print(f"Loading lpr image: {latest_image}")
        return latest_image
    except Exception as e:
        print(f"Error loading lpr image: {e}")
        return None


def switch_to_payment_mode_with_data():
    """Switch UI to payment mode and load ticket data from JSON"""
    global main_widget

    if not main_widget:
        return False

    try:
        # Load ticket data from JSON
        ticket_data_path = "ticket_data.json"
        if os.path.exists(ticket_data_path):
            with open(ticket_data_path, 'r') as f:
                ticket_data = json.load(f)
        else:
            print(f"ticket_data.json not found")
            ticket_data = {}

        plate = ""
        if os.path.exists("lpr.txt"):
            with open("lpr.txt", "r") as f:
                lines = f.readlines()
                if len(lines) >= 1:
                    plate = lines[0].strip()
                else:
                    print(
                        "File lpr.txt kosong, tidak ada data plat nomor")

        payment_data = {
            "ticket_code": ticket_data.get("ticket_code", ""),
            "device_name": ticket_data.get("device_name", ""),
            "jam_masuk": ticket_data.get("start_time", ""),
            "status": ticket_data.get("status"),
            "plat": plate
        }

        if ticket_data.get("emoney_card_number"):
            emoney_info = {
                "emoney_card_number": ticket_data.get("emoney_card_number", ""),
                "emoney_card_type": ticket_data.get("emoney_card_type", ""),
                "emoney_balance": ticket_data.get("emoney_balance", "")
            }

            payment_data.update(emoney_info)

        # Switch to payment mode with raw ticket data
        main_widget.mode = "payment"
        main_widget.set_payment_data(payment_data)

        # Load images from folders
        ipcam_image = load_ipcam_image()
        lpr_image = load_lpr_image()

        # Set vehicle images
        main_widget.set_vehicle_image1(ipcam_image)
        main_widget.set_vehicle_image2(lpr_image)

        main_widget.set_welcome_text(f"silahkan masuk".upper())

        # Update the display
        main_widget.update()

        print("Successfully switched to payment mode with data")
        return True

    except Exception as e:
        print(f"Error switching to payment mode: {e}")
        return False


def create_image_folders():
    """Create ipcam and lpr folders if they don't exist"""
    folders = ["ipcam", "lpr"]

    for folder in folders:
        if not os.path.exists(folder):
            try:
                os.makedirs(folder)
                print(f"Created folder: {folder}")
            except Exception as e:
                print(f"Error creating folder {folder}: {e}")
        else:
            print(f"Folder already exists: {folder}")


def cleanup_image_folders():
    """Empty the ipcam and lpr folders by deleting all files in them"""
    folders = ["ipcam", "lpr"]

    for folder in folders:
        if os.path.exists(folder):
            try:
                # Get all files in the folder
                files = glob.glob(os.path.join(folder, "*"))

                # Delete each file
                for file_path in files:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        print(f"Deleted file: {file_path}")
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                        print(f"Deleted directory: {file_path}")

                print(f"Cleaned up folder: {folder}")

            except Exception as e:
                print(f"Error cleaning up folder {folder}: {e}")
        else:
            print(f"Folder not found for cleanup: {folder}")


def cleanup_vehicle_images():
    """Clean up vehicle images after transaction is complete"""
    global main_widget

    try:
        # Clear the images from UI
        if main_widget:
            main_widget.set_vehicle_image1(None)
            main_widget.set_vehicle_image2(None)

        # Clean up the folders
        cleanup_image_folders()

        print("Vehicle images cleaned up successfully")

    except Exception as e:
        print(f"Error cleaning up vehicle images: {e}")


# === Main Entry === #
if __name__ == "__main__":
    show_ui()
    app.exec_()
