import pygame
import os


def setup_sound():
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        print_ticket_sound = os.path.join(
            script_dir, "../assets/print_ticket.mp3")
        please_enter_sound = os.path.join(
            script_dir, "../assets/please_enter.mp3")

        if not init_sound(print_ticket_sound):
            print(
                f"Warning: Sound system initialization failed for {print_ticket_sound}")
        if not init_sound(please_enter_sound):
            print(
                f"Warning: Sound system initialization failed for {please_enter_sound}")

        print("Setup sound success")
    except Exception as e:
        print(f"Error setup sound: {e}")
        # print_oled("Hardware", "Setup", "Failed")


def init_sound(sound_file):
    """
    Initialize the sound system and verify sound file exists.
    Returns True if initialization is successful, False otherwise.
    """
    try:
        pygame.mixer.init()
        # Get the absolute path of the script directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        sound_path = os.path.join(script_dir, sound_file)

        # Check if sound file exists
        if not os.path.exists(sound_path):
            print(f"Warning: Sound file {sound_path} not found")
            return False
        return True
    except Exception as e:
        print(f"Error initializing sound: {e}")
        return False


def play_vehicle_detected_sound(sound_file):
    try:
        if pygame.mixer.music.get_busy():
            # Jangan putar ulang jika masih bermain
            print("Sound is already playing, skipping.")
            return

        script_dir = os.path.dirname(os.path.abspath(__file__))
        sound_path = os.path.join(script_dir, sound_file)

        if os.path.exists(sound_path):
            pygame.mixer.music.load(sound_path)
            pygame.mixer.music.play()
            print(f"Playing sound: {sound_path}")
        else:
            print(f"Sound file {sound_path} not found")
    except Exception as e:
        print(f"Error playing sound: {e}")


def stop_sound():
    """
    Stop any currently playing sound.
    Used when canceling or completing an operation.
    """
    try:
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
            print("Stopped playing sound")
    except Exception as e:
        print(f"Error stopping sound: {e}")
