"""DeskMate Zero entry point."""

import logging
import os

import os

os.environ.setdefault("SDL_VIDEODRIVER", "KMSDRM")

from kivy.config import Config

Config.set("kivy", "keyboard_mode", "dock")
Config.set("kivy", "exit_on_escape", "0")

from kivy.core.window import Window

Window.show_cursor = False

from ui import WeatherDisplayApp


def setup_logging():
    log_dir = os.path.expanduser("~/.local/share/deskmate")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "deskmate.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(),
        ],
    )


if __name__ == "__main__":
    setup_logging()
    WeatherDisplayApp().run()
