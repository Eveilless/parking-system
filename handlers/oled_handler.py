import Adafruit_SSD1306
from PIL import Image, ImageDraw, ImageFont
import logging
import os

# Global variables for OLED elements
disp = None
draw = None
image = None
font = None
widthOled = 128
heightOled = 64
line1 = 0
line2 = 10
line3 = 20
line4 = 30
oled_available = False


def setup_oled():
    global disp, draw, image, font, oled_available

    try:
        # Check if I2C device exists
        if not os.path.exists('/dev/i2c-1'):
            logging.warning("I2C device not found at /dev/i2c-1")
            print("⚠️ I2C device not found - OLED will not be available")
            oled_available = False
            return False

        # Initialize display (I2C)
        disp = Adafruit_SSD1306.SSD1306_128_64(rst=None)
        disp.begin()
        disp.clear()
        disp.display()

        # Create blank image and drawing object
        image = Image.new('1', (disp.width, disp.height))
        draw = ImageDraw.Draw(image)

        # Load default font
        font = ImageFont.load_default()

        oled_available = True
        logging.info("✅ OLED display initialized successfully")
        print("✅ OLED display initialized successfully")
        return True

    except ImportError as e:
        logging.warning(f"OLED libraries not available: {e}")
        print(f"⚠️ OLED libraries not available: {e}")
        oled_available = False
        return False
    except Exception as e:
        logging.error(f"❌ Failed to initialize OLED display: {e}")
        print(f"❌ Failed to initialize OLED display: {e}")
        oled_available = False
        return False


def print_oled(str1="", str2="", str3="", str4=""):
    global disp, draw, image, font, oled_available

    # If OLED is not available, just log the message
    if not oled_available or not all([disp, draw, image, font]):
        logging.info(f"OLED (unavailable): {str1} | {str2} | {str3} | {str4}")
        return False

    try:
        # Clear the image canvas
        draw.rectangle((0, 0, widthOled, heightOled), outline=0, fill=0)

        # Draw text lines
        draw.text((0, line1), str1, font=font, fill=255)
        draw.text((0, line2), str2, font=font, fill=255)
        draw.text((0, line3), str3, font=font, fill=255)
        draw.text((0, line4), str4, font=font, fill=255)

        # Send image to OLED display
        disp.image(image)
        disp.display()

        logging.info(f"OLED: {str1} | {str2} | {str3} | {str4}")
        return True

    except Exception as e:
        logging.error(f"❌ OLED display error: {e}")
        print(f"❌ OLED display error: {e}")
        # Mark OLED as unavailable if we get persistent errors
        oled_available = False
        return False


def is_oled_available():
    """Check if OLED is available and working"""
    return oled_available
