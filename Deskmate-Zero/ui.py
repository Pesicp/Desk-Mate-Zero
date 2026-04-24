"""All Kivy UI widgets for DeskMate Zero."""

import json
import logging
import os
import random
import socket
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from kivy.app import App
from kivy.clock import Clock as KivyClock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, Line
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.carousel import Carousel
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.core.image import Image as CoreImage
from kivy.uix.relativelayout import RelativeLayout
from kivy.animation import Animation
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

import api
import config
import system
import radio_api
from radio_player import RadioPlayer

logger = logging.getLogger(__name__)

# ── Cached WiFi state (non-blocking background check) ──
_wifi_state = True
_wifi_lock = threading.Lock()
_wifi_worker_started = False


def _wifi_check_worker():
    """Background daemon that checks internet reachability every 10 s."""
    global _wifi_state
    while True:
        try:
            socket.create_connection(("1.1.1.1", 53), timeout=1)
            new_state = True
        except OSError:
            new_state = False
        with _wifi_lock:
            _wifi_state = new_state
        time.sleep(10)


def _ensure_wifi_worker():
    """Start the WiFi check worker once."""
    global _wifi_worker_started
    with _wifi_lock:
        if not _wifi_worker_started:
            _wifi_worker_started = True
            threading.Thread(target=_wifi_check_worker, daemon=True).start()


def _wifi_available():
    """Return cached WiFi state (never blocks)."""
    _ensure_wifi_worker()
    with _wifi_lock:
        return _wifi_state


_CFG = config.load_config()
_ICON_PATH = config.get_icon_path(_CFG)

def _load_weather_descriptions() -> dict:
    """Load WMO code descriptions from JSON."""
    desc_path = _ICON_PATH.parent / "weather_descriptions.json"
    if desc_path.exists():
        try:
            with open(desc_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return {int(k): v for k, v in data.items()}
        except Exception as exc:
            logger.warning("Failed to load weather_descriptions.json: %s", exc)
    # Fallback hardcoded descriptions
    return {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
        55: "Dense drizzle", 56: "Light freezing drizzle", 57: "Dense freezing drizzle",
        61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
        66: "Light freezing rain", 67: "Heavy freezing rain",
        71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
        77: "Snow grains", 80: "Slight rain showers", 81: "Moderate rain showers",
        82: "Violent rain showers", 85: "Slight snow showers", 86: "Heavy snow showers",
        95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
    }


WEATHER_DESC = _load_weather_descriptions()

# Scan available icon files once at module load
_AVAILABLE_ICONS = set()


def _scan_available_icons():
    """Build set of available PNG filenames in the icon folder."""
    global _AVAILABLE_ICONS
    if _ICON_PATH.exists():
        _AVAILABLE_ICONS = {
            f.name for f in _ICON_PATH.iterdir()
            if f.suffix.lower() == ".png"
        }
    else:
        _AVAILABLE_ICONS = set()


_scan_available_icons()

# WMO code -> background condition name
_BG_MAP = {
    0: "clear", 1: "clear", 2: "partly_cloudy",
    3: "overcast",
    45: "fog", 48: "fog",
    51: "rain", 53: "rain", 55: "rain",
    56: "rain", 57: "rain",
    61: "rain", 63: "rain", 65: "rain",
    66: "rain", 67: "rain",
    71: "snow", 73: "snow", 75: "snow", 77: "snow",
    80: "rain", 81: "rain", 82: "rain",
    85: "snow", 86: "snow",
    95: "storm", 96: "storm", 99: "storm",
}

# Cache for loaded background textures
_bg_textures = {}


def _get_bg_texture(code: int, is_day: bool):
    """Load background texture for a WMO code + day/night. Cached on demand."""
    condition = _BG_MAP.get(int(code), "clear")
    period = "day" if is_day else "night"
    key = f"{condition}_{period}"

    if key in _bg_textures:
        return _bg_textures[key]

    # Try condition-specific background
    path = Path(f"bg_{condition}_{period}.jpg")
    if path.exists():
        try:
            tex = CoreImage(str(path)).texture
            _bg_textures[key] = tex
            return tex
        except Exception:
            pass

    # Fallback to clear sky background
    fallback_key = f"clear_{period}"
    if fallback_key in _bg_textures:
        return _bg_textures[fallback_key]

    fallback_path = Path(f"bg_clear_{period}.jpg")
    if fallback_path.exists():
        try:
            tex = CoreImage(str(fallback_path)).texture
            _bg_textures[fallback_key] = tex
            return tex
        except Exception:
            pass

    return None


def _icon_file(code: int, daynight: str = "d") -> str:
    """Return path to weather icon by WMO code with day/night support.

    Lookup chain:
        1. {code}{d|n}.png  (e.g. 0d.png, 0n.png)
        2. {code}.png       (generic, e.g. 0.png)
        3. 0d.png / 0.png   (clear sky fallback)
    """
    code_str = str(int(code))

    # 1. Day/night specific
    name_dn = f"{code_str}{daynight}.png"
    if name_dn in _AVAILABLE_ICONS:
        return str(_ICON_PATH / name_dn)

    # 2. Generic (no day/night suffix)
    name_generic = f"{code_str}.png"
    if name_generic in _AVAILABLE_ICONS:
        return str(_ICON_PATH / name_generic)

    # 3. Fallback to clear sky
    for fallback in (f"0{daynight}.png", "0.png", "0d.png"):
        if fallback in _AVAILABLE_ICONS:
            return str(_ICON_PATH / fallback)

    return str(_ICON_PATH / "0d.png")


class ClockSlide(BoxLayout):
    def __init__(self, carousel, player, **kw):
        super().__init__(**kw)
        self.carousel = carousel
        self.player = player
        self.orientation = "vertical"

        # Background (mirrors first weather card; black when no wifi)
        self._current_bg_key = None
        with self.canvas.before:
            Color(0, 0, 0, 1)
            self.bg_rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(
            pos=lambda *a: setattr(self.bg_rect, "pos", self.pos),
            size=lambda *a: setattr(self.bg_rect, "size", self.size),
        )

        # Time offset from first weather card (used when wifi is down)
        self.time_offset = timedelta(0)

        # Centered content column (icon + clock share left edge)
        wrapper = BoxLayout(orientation="horizontal", size_hint=(1, 1))
        wrapper.add_widget(BoxLayout(size_hint_x=1))  # left spacer
        content = BoxLayout(
            orientation="vertical", size_hint=(None, 1), width=720,
            padding=[0, 10, 0, 40], spacing=8,
        )

        # ── Top weather info (icon aligns with clock text left edge) ──
        self.top_info = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=100, spacing=15,
        )
        self.icon_spacer = Widget(size_hint=(None, 1), width=0)
        self.top_info.add_widget(self.icon_spacer)
        self.weather_icon = Image(
            size_hint=(None, 1), width=100,
            source=_icon_file(0, "d"),
            fit_mode="contain",
        )
        text_box = BoxLayout(orientation="vertical", size_hint_x=1)
        self.condition_label = Label(
            font_size=30, halign="center", valign="middle",
            color=(1, 1, 1, 1), bold=True,
            outline_color=(0, 0, 0, 1), outline_width=2,
        )
        self.condition_label.bind(size=self.condition_label.setter("text_size"))
        self.info_label = Label(
            font_size=26, halign="center", valign="middle",
            color=(1, 1, 1, 1), bold=True,
            outline_color=(0, 0, 0, 1), outline_width=2,
        )
        self.info_label.bind(size=self.info_label.setter("text_size"))
        text_box.add_widget(self.condition_label)
        text_box.add_widget(self.info_label)
        self.top_info.add_widget(self.weather_icon)
        self.top_info.add_widget(text_box)
        self.right_spacer = Widget(size_hint=(None, 1), width=0)
        self.top_info.add_widget(self.right_spacer)
        content.add_widget(self.top_info)

        # ── Clock + date (centered vertically in content) ──
        content.add_widget(BoxLayout(size_hint_y=1))  # top spacer
        self.clock_label = Label(
            font_size=220, halign="center", valign="middle",
            color=(1, 1, 1, 1), bold=True,
            outline_color=(0, 0, 0, 1), outline_width=3,
            size_hint=(1, None), height=240,
        )
        self.clock_label.bind(size=self.clock_label.setter("text_size"))
        content.add_widget(self.clock_label)

        self.date_label = Label(
            font_size=45, halign="center", valign="middle",
            color=(1, 1, 1, 1), bold=True,
            outline_color=(0, 0, 0, 1), outline_width=2,
            size_hint=(1, None), height=55,
        )
        self.date_label.bind(size=self.date_label.setter("text_size"))
        content.add_widget(self.date_label)

        # Radio station name (bottom, only when playing)
        self.radio_label = Label(
            font_size=28, halign="center", valign="middle",
            color=(0.6, 0.8, 1, 1), bold=True,
            outline_color=(0, 0, 0, 1), outline_width=2,
            size_hint=(1, None), height=40, opacity=0,
        )
        self.radio_label.bind(size=self.radio_label.setter("text_size"))
        content.add_widget(self.radio_label)

        content.add_widget(BoxLayout(size_hint_y=1))  # bottom spacer

        wrapper.add_widget(content)
        wrapper.add_widget(BoxLayout(size_hint_x=1))  # right spacer
        self.add_widget(wrapper)

        def _align_icon(*args):
            if not self.clock_label.text:
                return
            old_ts = self.clock_label.text_size
            self.clock_label.text_size = (None, None)
            self.clock_label.texture_update()
            tw = self.clock_label.texture_size[0]
            self.clock_label.text_size = old_ts
            self.clock_label.texture_update()
            offset = max(0, int((self.clock_label.width - tw) / 2))
            self.icon_spacer.width = max(0, offset - 15)
            self.right_spacer.width = max(0, 85 + offset)
        self.clock_label.bind(text=_align_icon, size=_align_icon)
        KivyClock.schedule_once(_align_icon, 0.5)

        KivyClock.schedule_interval(self.update_clock, 2)

    def update_clock(self, dt):
        wifi = _wifi_available()
        cards = [s for s in self.carousel.slides if isinstance(s, WeatherCard)]
        first_card = cards[0] if cards else None

        # Radio station display
        if self.player and self.player.get_state() == "playing":
            name = self.player.current_name
            if name:
                self.radio_label.text = name[:40] if len(name) > 40 else name
                self.radio_label.opacity = 1
            else:
                self.radio_label.opacity = 0
        else:
            self.radio_label.opacity = 0

        if wifi and first_card and getattr(first_card, "_has_weather_data", False):
            now = datetime.now(first_card.timezone)
            self.time_offset = now.utcoffset() or timedelta(0)
            is_day = 6 <= now.hour < 18
            self._set_background(first_card._last_weather_code, is_day)
            self.top_info.opacity = 1
            self.weather_icon.source = first_card.today_icon.source or ""
            self.condition_label.text = first_card.code_label.text or ""
            city = first_card.city_label.text or ""
            temp = first_card.temp_label.text or ""
            self.info_label.text = f"{city}  {temp}"
        else:
            utc_now = datetime.now(timezone.utc)
            now = utc_now + self.time_offset
            self._set_black_background()
            self.top_info.opacity = 0

        self.clock_label.text = now.strftime("%H:%M")
        self.date_label.text = now.strftime("%A, %d.%m")

    def _set_background(self, code, is_day):
        if not hasattr(self, "bg_rect"):
            return
        key = f"{code}_{'day' if is_day else 'night'}"
        if key == self._current_bg_key:
            return
        tex = _get_bg_texture(code, is_day)
        if tex:
            self.canvas.before.clear()
            with self.canvas.before:
                Color(1, 1, 1, 1)
                self.bg_rect = Rectangle(
                    size=self.size, pos=self.pos, texture=tex
                )
            self._current_bg_key = key
        else:
            self._set_black_background()

    def _set_black_background(self):
        if self._current_bg_key == "black":
            return
        self.canvas.before.clear()
        with self.canvas.before:
            Color(0, 0, 0, 1)
            self.bg_rect = Rectangle(size=self.size, pos=self.pos)
        self._current_bg_key = "black"

    @staticmethod
    def _check_wifi():
        return _wifi_available()


class WeatherCard(BoxLayout):
    def __init__(self, city, cfg, auto_fetch=True, **kw):
        super().__init__(orientation="vertical", **kw)
        self.city = city
        self.cfg = cfg
        self.timezone = ZoneInfo(city.get("timezone", "UTC"))
        self.time_offset = datetime.now(self.timezone).utcoffset()
        self._last_wifi_on = True
        self._last_weather_code = 0
        self._has_weather_data = False
        self.padding = [0, 0, 0, 0]
        self.spacing = 0

        # Background texture (set dynamically by condition + day/night)
        self._current_bg_key = None
        with self.canvas.before:
            Color(1, 1, 1, 1)
            self.bg_rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(pos=lambda *a: setattr(self.bg_rect, 'pos', self.pos), size=lambda *a: setattr(self.bg_rect, 'size', self.size))

        # ── Top half: 3 equal columns ──
        top_half = BoxLayout(orientation="horizontal", size_hint_y=0.4)

        # Col 1: condition above icon
        col1 = RelativeLayout(size_hint_x=1/3)

        self.today_icon = Image(
            size_hint=(None, None), size=(220, 220),
            source=_icon_file(0, "d"),
            fit_mode="contain",
            pos_hint={'center_x': 0.5, 'center_y': 0.4},
            opacity=0,
        )
        col1.add_widget(self.today_icon)

        self.code_label = Label(
            font_size=30, halign="center", valign="top",
            color=(1, 1, 1, 1), size_hint=(1, None),
            outline_color=(0, 0, 0, 1), outline_width=2,
            bold=True,
            pos_hint={'center_x': 0.5, 'top': 0.95},
        )

        def _set_code_layout(inst, ts):
            inst.height = ts[1]
            inst.pos_hint = {'center_x': 0.5, 'top': 0.95}

        self.code_label.bind(
            width=lambda inst, w: setattr(inst, "text_size", (w, None))
        )
        self.code_label.bind(texture_size=_set_code_layout)
        col1.add_widget(self.code_label)
        top_half.add_widget(col1)

        # Col 2: city above temp
        col2 = RelativeLayout(size_hint_x=1/3)

        self.city_label = Label(
            text=city["name"], font_size=40,
            halign="center", valign="top", color=(1, 1, 1, 1),
            outline_color=(0, 0, 0, 1), outline_width=2,
            size_hint=(1, None),
            bold=True,
            pos_hint={'center_x': 0.5, 'top': 0.99},
        )

        def _set_city_layout(inst, ts):
            inst.height = ts[1]
            inst.pos_hint = {'center_x': 0.5, 'top': 0.99}

        self.city_label.bind(
            width=lambda inst, w: setattr(inst, "text_size", (w, None))
        )
        self.city_label.bind(texture_size=_set_city_layout)
        col2.add_widget(self.city_label)

        self.temp_label = Label(
            font_size=90, halign="center", valign="middle",
            color=(1, 1, 1, 1), size_hint=(1, None), height=102,
            outline_color=(0, 0, 0, 1), outline_width=2,
            bold=True,
            pos_hint={'center_x': 0.5, 'center_y': 0.4},
        )
        self.temp_label.bind(size=self.temp_label.setter("text_size"))
        col2.add_widget(self.temp_label)
        top_half.add_widget(col2)

        # Col 3: date above clock
        col3 = RelativeLayout(size_hint_x=1/3)

        self.date_label = Label(
            font_size=30, halign="center", valign="top",
            color=(1, 1, 1, 1), size_hint=(1, None),
            outline_color=(0, 0, 0, 1), outline_width=2,
            bold=True,
            pos_hint={'center_x': 0.5, 'top': 0.95},
        )

        def _set_date_layout(inst, ts):
            inst.height = ts[1]
            inst.pos_hint = {'center_x': 0.5, 'top': 0.95}

        self.date_label.bind(
            width=lambda inst, w: setattr(inst, "text_size", (w, None))
        )
        self.date_label.bind(texture_size=_set_date_layout)
        col3.add_widget(self.date_label)

        self.clock_label = Label(
            font_size=90, halign="center", valign="middle",
            color=(1, 1, 1, 1), size_hint=(1, None), height=102,
            outline_color=(0, 0, 0, 1), outline_width=2,
            bold=True,
            pos_hint={'center_x': 0.5, 'center_y': 0.4},
        )
        self.clock_label.bind(size=self.clock_label.setter("text_size"))
        col3.add_widget(self.clock_label)
        top_half.add_widget(col3)


        self.add_widget(top_half)

        # ── Hourly forecast row ──
        self.hourly_layout = GridLayout(cols=8, size_hint_y=0.25, spacing=0, padding=0)

        # ── Daily forecast row ──
        self.forecast_box = GridLayout(cols=5, size_hint_y=0.35, spacing=0, padding=0)

        with top_half.canvas.before:
            Color(0, 0, 0, 0.0)
            top_ov = Rectangle(size=top_half.size, pos=top_half.pos)
        top_half.bind(pos=lambda *a: setattr(top_ov, 'pos', top_half.pos), size=lambda *a: setattr(top_ov, 'size', top_half.size))

        with self.hourly_layout.canvas.before:
            Color(0, 0, 0, 0.3)
            hr_ov = Rectangle(size=self.hourly_layout.size, pos=self.hourly_layout.pos)
        self.hourly_layout.bind(pos=lambda *a: setattr(hr_ov, 'pos', self.hourly_layout.pos), size=lambda *a: setattr(hr_ov, 'size', self.hourly_layout.size))

        with self.forecast_box.canvas.before:
            Color(0, 0, 0, 0.2)
            day_ov = Rectangle(size=self.forecast_box.size, pos=self.forecast_box.pos)
        self.forecast_box.bind(pos=lambda *a: setattr(day_ov, 'pos', self.forecast_box.pos), size=lambda *a: setattr(day_ov, 'size', self.forecast_box.size))

        self.add_widget(self.hourly_layout)
        self.add_widget(self.forecast_box)

        if auto_fetch:
            self.update_weather_async()
        self._clock_event = KivyClock.schedule_interval(lambda dt: self.update_clock(), 2)
        self._weather_event = KivyClock.schedule_interval(
            lambda dt: self._safe_update_weather(),
            cfg.get("refresh_interval", 1800),
        )


    def update_clock(self):
        try:
            wifi_on = _wifi_available()
            if wifi_on:
                now = datetime.now(self.timezone)
                self.time_offset = now.utcoffset()
            else:
                utc_now = datetime.now(timezone.utc)
                now = utc_now + self.time_offset

            if wifi_on and not getattr(self, "_last_wifi_on", True):
                api.clear_cache()
                self.update_weather_async()
            self._last_wifi_on = wifi_on

            self.clock_label.text = now.strftime("%H:%M")
            self.date_label.text = now.strftime("%a, %d.%m")

            # Switch background by condition + day/night
            is_day = 6 <= now.hour < 18
            if self._has_weather_data:
                self._set_background(self._last_weather_code, is_day)
                dn = "d" if 6 <= now.hour < 18 else "n"
                self.today_icon.source = _icon_file(self._last_weather_code, dn)
                self.today_icon.opacity = 1
                self.temp_label.opacity = 1
                self.code_label.opacity = 1
                self.hourly_layout.opacity = 1
                self.forecast_box.opacity = 1
            else:
                self._set_black_background()
                self.today_icon.opacity = 0
                self.temp_label.opacity = 0
                self.code_label.opacity = 0
                self.hourly_layout.opacity = 0
                self.forecast_box.opacity = 0
        except Exception as exc:
            logger.error("Clock update error for %s: %s", self.city.get("name"), exc)
            try:
                utc_now = datetime.now(timezone.utc)
                now = utc_now + self.time_offset
                self.clock_label.text = now.strftime("%H:%M")
                self.date_label.text = now.strftime("%a, %d.%m")
            except Exception as exc2:
                logger.error("Fallback clock update error: %s", exc2)

    def _set_background(self, code, is_day):
        """Update the card background texture based on weather code and time."""
        if not hasattr(self, 'bg_rect'):
            return
        if code is None:
            self._set_black_background()
            return
        key = f"{code}_{'day' if is_day else 'night'}"
        if key == self._current_bg_key:
            return
        tex = _get_bg_texture(code, is_day)
        if tex:
            self.canvas.before.clear()
            with self.canvas.before:
                Color(1, 1, 1, 1)
                self.bg_rect = Rectangle(
                    size=self.size, pos=self.pos, texture=tex
                )
            self._current_bg_key = key
        else:
            self._set_black_background()

    def _set_black_background(self):
        if getattr(self, '_current_bg_key', None) == "black":
            return
        if not hasattr(self, 'bg_rect'):
            return
        self.canvas.before.clear()
        with self.canvas.before:
            Color(0, 0, 0, 1)
            self.bg_rect = Rectangle(size=self.size, pos=self.pos)
        self._current_bg_key = "black"

    def _safe_update_weather(self):
        wifi_on = _wifi_available()

        if wifi_on:
            self.update_weather_async()

        has_data = getattr(self, "_has_weather_data", False)
        if wifi_on and has_data:
            self.temp_label.opacity = 1
            self.code_label.opacity = 1
            self.clock_label.opacity = 1
            self.date_label.opacity = 1
            self.hourly_layout.opacity = 1
            self.forecast_box.opacity = 1
            self.today_icon.opacity = 1
        else:
            self.temp_label.opacity = 0
            self.code_label.opacity = 0
            self.hourly_layout.opacity = 0
            self.forecast_box.opacity = 0
            self.today_icon.opacity = 0
            # Always keep clock and date visible
            self.clock_label.opacity = 1
            self.date_label.opacity = 1

    def update_weather_async(self):
        api.fetch_forecast_async(
            self.city["lat"],
            self.city["lon"],
            callback=self._on_forecast_ready,
            error_callback=self._on_forecast_error,
        )

    def _on_forecast_ready(self, result):
        KivyClock.schedule_once(lambda dt: self._apply_forecast(result), 0)

    def _on_forecast_error(self, exc):
        logger.error("Forecast error for %s: %s", self.city.get("name"), exc)

    def cleanup(self):
        if hasattr(self, "_clock_event") and self._clock_event:
            self._clock_event.cancel()
            self._clock_event = None
        if hasattr(self, "_weather_event") and self._weather_event:
            self._weather_event.cancel()
            self._weather_event = None

    def _apply_forecast(self, result):
        daily, current, hourly, tz = result
        self.timezone = ZoneInfo(tz)

        if not daily:
            self.temp_label.opacity = 0
            self.code_label.opacity = 0
            self.hourly_layout.opacity = 0
            self.forecast_box.opacity = 0
            return

        # Show weather widgets (in case they were hidden)
        self.temp_label.opacity = 1
        self.code_label.opacity = 1
        self.hourly_layout.opacity = 1
        self.forecast_box.opacity = 1

        today = daily[0]
        cur_code = current.get("weathercode", today.get("weathercode", 0))
        cur_temp = current.get("temperature", today.get("temp_max", ""))
        self._last_weather_code = cur_code
        self._has_weather_data = True

        current_time = datetime.now(self.timezone).hour
        is_day = 6 <= current_time < 18
        dn = "d" if is_day else "n"
        self.today_icon.source = _icon_file(cur_code, dn)
        self.today_icon.opacity = 1

        self.current_weather = {
            "temp": cur_temp,
            "code": cur_code,
            "desc": WEATHER_DESC.get(cur_code, f"Code {cur_code}"),
            "icon": _icon_file(cur_code, dn),
        }
        self._set_background(cur_code, is_day)

        self.temp_label.text = f"{int(cur_temp)}°C" if isinstance(cur_temp, (int, float)) else str(cur_temp)
        self.code_label.text = WEATHER_DESC.get(cur_code, f"Code {cur_code}")


        # Hourly forecast (next 9 hours) — centered in each cell with background
        self.hourly_layout.clear_widgets()
        now = datetime.now(self.timezone)
        start_index = 0
        for i, hh in enumerate(hourly):
            if "time" in hh:
                dt = datetime.fromisoformat(hh["time"]).replace(tzinfo=self.timezone)
                if dt > now:
                    start_index = i
                    break

        for hh in hourly[start_index:start_index + 8]:
            if "time" not in hh:
                continue
            dt = datetime.fromisoformat(hh["time"]).replace(tzinfo=self.timezone)
            b = RelativeLayout(size_hint=(1, 1))

            hh_hour = dt.hour
            ip = _icon_file(hh["weathercode"], "d" if 6 <= hh_hour < 18 else "n")

            b.add_widget(Image(source=ip, size_hint=(None, None), size=(75, 75), fit_mode="fill", pos_hint={"center_x": 0.5, "center_y": 0.5}))

            t = Label(text=f"{int(hh['temp'])}°C", font_size=18, halign="center", valign="bottom", size_hint=(1, None), height=30, pos_hint={'center_x': 0.5, 'y': 0.05}, color=(1, 1, 1, 1), outline_color=(0, 0, 0, 1), outline_width=2, bold=True)
            t.bind(size=t.setter("text_size"))
            b.add_widget(t)

            tm = Label(text=dt.strftime("%H:%M"), font_size=18, halign="center", valign="top", size_hint=(1, None), height=24, pos_hint={'center_x': 0.5, 'top': 0.95}, color=(1, 1, 1, 1), outline_color=(0, 0, 0, 1), outline_width=2, bold=True)
            tm.bind(size=tm.setter("text_size"))
            b.add_widget(tm)
            self.hourly_layout.add_widget(b)

        # 5-day forecast — centered in each cell with background
        self.forecast_box.clear_widgets()
        for d in daily:
            dt = datetime.strptime(d["date"], "%Y-%m-%d")
            b = RelativeLayout(size_hint=(1, 1))

            # Daily forecast cell (~210 px tall at 35% of 600px screen)
            ip = _icon_file(d["weathercode"], "d")
            b.add_widget(Image(source=ip, size_hint=(None, None), size=(110, 110), fit_mode="fill", pos_hint={"center_x": 0.5, "center_y": 0.55}))

            temp_lbl = Label(text=f"{int(d['temp_max'])}° / {int(d['temp_min'])}°", font_size=18, halign="center", valign="bottom", size_hint=(1, None), height=24, pos_hint={'center_x': 0.5, 'y': 0.09}, color=(1, 1, 1, 1), outline_color=(0, 0, 0, 1), outline_width=2, bold=True)
            temp_lbl.bind(size=temp_lbl.setter("text_size"))
            b.add_widget(temp_lbl)


            day_lbl = Label(text=dt.strftime("%A"), font_size=18, halign="center", valign="top", size_hint=(1, None), height=24, pos_hint={'center_x': 0.5, 'top': 0.95}, color=(1, 1, 1, 1), outline_color=(0, 0, 0, 1), outline_width=2, bold=True)
            day_lbl.bind(size=day_lbl.setter("text_size"))
            b.add_widget(day_lbl)
            self.forecast_box.add_widget(b)



class PhotoSlide(BoxLayout):
    def __init__(self, cfg, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.padding = 0
        self.spacing = 0

        with self.canvas.before:
            Color(0, 0, 0, 1)
            self.bg_rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(size=self._update_bg, pos=self._update_bg)

        self.pics_folder = Path(cfg.get("pictures_dir", "/home/rpi/pictures"))
        try:
            self.images = [
                str(self.pics_folder / f)
                for f in os.listdir(self.pics_folder)
                if f.lower().endswith((".png", ".jpg", ".jpeg"))
            ]
        except Exception as exc:
            logger.warning("Could not list pictures folder: %s", exc)
            self.images = []

        self.image_widget = Image(fit_mode="contain")
        self.add_widget(self.image_widget)

        self._last_image = None
        self.show_random_image(initial=True)

        minutes = cfg.get("slideshow_minutes", 60)
        KivyClock.schedule_interval(lambda dt: self.show_random_image(), minutes * 60)

    def _update_bg(self, *args):
        self.bg_rect.size = self.size
        self.bg_rect.pos = self.pos

    def show_random_image(self, initial=False):
        if not self.images:
            return
        new_source = random.choice(self.images)
        if not initial and len(self.images) > 1:
            while new_source == self._last_image:
                new_source = random.choice(self.images)
        self._last_image = new_source
        self.image_widget.source = new_source
        self.image_widget.opacity = 1

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            self.show_random_image()
            return True
        return super().on_touch_down(touch)


class ManageCitiesCard(BoxLayout):
    def __init__(self, carousel, cfg, **kw):
        super().__init__(orientation="horizontal", **kw)
        self.carousel = carousel
        self.cfg = cfg

        # ── Single panel with header row + city list ──
        main = BoxLayout(orientation="vertical", size_hint=(1, 1), padding=15, spacing=10)

        # Header row: Search | Search Button | City Count
        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=50, spacing=10)
        self.city_input = TextInput(
            hint_text="Type city name…", multiline=False,
            font_size=24, size_hint_x=0.5, size_hint_y=None, height=50,
        )
        search_btn = Button(
            text="Search", font_size=24, size_hint_x=0.2, size_hint_y=None, height=50,
            background_color=(0.2, 0.4, 1, 1), color=(1, 1, 1, 1), bold=True,
        )
        search_btn.bind(on_press=self._on_search_pressed)
        self.count_label = Label(
            text="", font_size=24, color=(1, 1, 1, 0.7),
            size_hint_x=0.3, halign="right", valign="center",
        )
        self.count_label.bind(size=self.count_label.setter("text_size"))
        header.add_widget(self.city_input)
        header.add_widget(search_btn)
        header.add_widget(self.count_label)
        main.add_widget(header)

        self.scroll = ScrollView()
        self.grid = GridLayout(cols=1, spacing=8, size_hint_y=None)
        self.grid.bind(minimum_height=self.grid.setter("height"))
        self.scroll.add_widget(self.grid)
        main.add_widget(self.scroll)
        self.add_widget(main)

        self.refresh_city_list()
        # Auto-refresh every 10 s so mini weather icons stay in sync
        self._refresh_event = KivyClock.schedule_interval(lambda dt: self.refresh_city_list(), 10)

    @property
    def cities(self):
        return self.cfg.setdefault("cities", [])

    def _get_city_weather(self, city):
        for slide in self.carousel.slides:
            if isinstance(slide, WeatherCard) and slide.city == city:
                if hasattr(slide, "current_weather") and slide.current_weather:
                    cw = slide.current_weather
                    temp = cw.get("temp")
                    temp_str = f"{int(temp)}°C" if isinstance(temp, (int, float)) else str(temp)
                    return {
                        "temp": temp,
                        "temp_str": temp_str,
                        "code": cw.get("code", 0),
                        "desc": cw.get("desc", ""),
                        "icon": cw.get("icon", ""),
                    }
        return {}

    def refresh_city_list(self):
        limit = self.cfg.get("city_limit", 5)
        self.count_label.text = f"{len(self.cities)} / {limit}"

        if not hasattr(self, "_city_widgets"):
            self._city_widgets = {}

        current_ids = [id(c) for c in self.cities]
        stored_ids = list(self._city_widgets.keys())
        need_rebuild = len(current_ids) != len(stored_ids) or current_ids != stored_ids

        if need_rebuild:
            self._build_city_list()
        else:
            self._update_city_list()

    def _build_city_list(self):
        """Create city cards from scratch (called when structure changes)."""
        self.grid.clear_widgets()
        self._city_widgets = {}

        for idx, c in enumerate(self.cities):
            card = RelativeLayout(size_hint_y=None, height=90)
            bg = Button(
                background_normal="", background_color=(0, 0, 0, 0.75),
                size_hint=(1, 1), pos_hint={"center_x": 0.5, "center_y": 0.5},
            )
            card.add_widget(bg)

            content = BoxLayout(orientation="horizontal", size_hint=(1, 1), padding=10, spacing=8)
            # Left: icon + temp
            left_box = BoxLayout(orientation="vertical", size_hint=(0.2, 1), spacing=2)
            weather_data = self._get_city_weather(c)
            icon_source = weather_data.get("icon", "")
            if not icon_source:
                icon_source = _icon_file(0, "d")
            icon = Image(
                source=icon_source,
                size_hint=(1, 0.6), fit_mode="contain",
            )
            temp_lbl = Label(
                text=weather_data.get("temp_str", "--°C"), font_size=22,
                color=(1, 1, 1, 1), bold=True, size_hint=(1, 0.4),
                outline_color=(0, 0, 0, 1), outline_width=1,
            )
            left_box.add_widget(icon)
            left_box.add_widget(temp_lbl)

            # Center: name, country, local time
            center_box = BoxLayout(orientation="vertical", size_hint=(0.50, 1), padding=(5, 0), spacing=2)
            name_lbl = Label(
                text=c.get("name", "Unknown"), font_size=26,
                color=(1, 1, 1, 1), bold=True, halign="left", valign="center",
                outline_color=(0, 0, 0, 1), outline_width=2,
            )
            name_lbl.bind(size=name_lbl.setter("text_size"))
            country_lbl = Label(
                text=c.get("country", ""), font_size=18,
                color=(1, 1, 1, 0.7), halign="left", valign="center",
                outline_color=(0, 0, 0, 1), outline_width=1,
            )
            country_lbl.bind(size=country_lbl.setter("text_size"))
            tz = c.get("timezone", "UTC")
            try:
                local_time = datetime.now(ZoneInfo(tz)).strftime("%H:%M")
            except Exception:
                local_time = "--:--"
            time_lbl = Label(
                text=local_time, font_size=20,
                color=(1, 1, 1, 0.9), halign="left", valign="center",
                outline_color=(0, 0, 0, 1), outline_width=1,
            )
            time_lbl.bind(size=time_lbl.setter("text_size"))
            center_box.add_widget(name_lbl)
            center_box.add_widget(country_lbl)
            center_box.add_widget(time_lbl)

            # Right: up, down, remove
            right_box = BoxLayout(orientation="horizontal", size_hint=(0.30, 1), spacing=5)
            up_btn = Button(
                text="UP", font_size=18,
                background_color=(0.3, 0.3, 0.3, 1), color=(1, 1, 1, 1),
            )
            down_btn = Button(
                text="DOWN", font_size=18,
                background_color=(0.3, 0.3, 0.3, 1), color=(1, 1, 1, 1),
            )
            rm_btn = Button(
                text="DEL", font_size=18,
                background_color=(1, 0, 0, 0.8), color=(1, 1, 1, 1),
            )
            up_btn.disabled = (idx == 0)
            down_btn.disabled = (idx == len(self.cities) - 1)
            up_btn.bind(on_press=lambda i, cc=c: self._move_city(cc, -1))
            down_btn.bind(on_press=lambda i, cc=c: self._move_city(cc, 1))
            rm_btn.bind(on_press=lambda i, cc=c: self._confirm_remove_city(cc))
            right_box.add_widget(up_btn)
            right_box.add_widget(down_btn)
            right_box.add_widget(rm_btn)

            content.add_widget(left_box)
            content.add_widget(center_box)
            content.add_widget(right_box)
            card.add_widget(content)
            self.grid.add_widget(card)

            self._city_widgets[id(c)] = {
                "icon": icon,
                "temp": temp_lbl,
                "time": time_lbl,
            }

    def _update_city_list(self):
        """Update only dynamic values on existing cards (called every 10 s)."""
        for c in self.cities:
            wid = self._city_widgets.get(id(c))
            if not wid:
                continue
            weather_data = self._get_city_weather(c)
            icon_source = weather_data.get("icon", "")
            if not icon_source:
                icon_source = _icon_file(0, "d")
            wid["icon"].source = icon_source
            wid["temp"].text = weather_data.get("temp_str", "--°C")
            tz = c.get("timezone", "UTC")
            try:
                local_time = datetime.now(ZoneInfo(tz)).strftime("%H:%M")
            except Exception:
                local_time = "--:--"
            wid["time"].text = local_time

    def _rebuild_weather_slides(self):
        # Remove all WeatherCards
        for slide in list(self.carousel.slides):
            if isinstance(slide, WeatherCard):
                slide.cleanup()
                self.carousel.remove_widget(slide)
        # Re-add in config order (reversed because insert pushes existing widgets)
        manage_index = next(
            (i for i, s in enumerate(self.carousel.slides) if isinstance(s, ManageCitiesCard)),
            len(self.carousel.slides),
        )
        for cit in reversed(self.cities):
            wc = WeatherCard(cit, self.cfg)
            self.carousel.add_widget(wc, index=manage_index)

    def _move_city(self, city, direction):
        cities = self.cities
        idx = next((i for i, c in enumerate(cities) if c is city), -1)
        if idx == -1:
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(cities):
            return
        cities[idx], cities[new_idx] = cities[new_idx], cities[idx]
        config.save_config(self.cfg)
        self._rebuild_weather_slides()
        self.refresh_city_list()

    def _confirm_remove_city(self, city):
        name = city.get("name", "this city")
        content = BoxLayout(orientation="vertical", spacing=10, padding=10)
        content.add_widget(Label(
            text=f"Remove {name}?", font_size=28,
            outline_color=(0, 0, 0, 1), outline_width=1,
        ))
        btn_box = BoxLayout(size_hint_y=None, height=60, spacing=10)
        popup = Popup(title="Remove City?", content=content, size_hint=(0.6, 0.35))

        cancel_btn = Button(text="Cancel", font_size=24)
        cancel_btn.bind(on_press=popup.dismiss)
        rm_btn = Button(
            text="Remove", font_size=24,
            background_color=(1, 0, 0, 0.8), color=(1, 1, 1, 1),
        )
        rm_btn.bind(on_press=lambda i: (self._do_remove_city(city), popup.dismiss()))
        btn_box.add_widget(cancel_btn)
        btn_box.add_widget(rm_btn)
        content.add_widget(btn_box)
        popup.open()

    def _do_remove_city(self, city):
        if city in self.cities:
            self.cities.remove(city)
            config.save_config(self.cfg)
        for slide in list(self.carousel.slides):
            if isinstance(slide, WeatherCard) and slide.city == city:
                slide.cleanup()
                self.carousel.remove_widget(slide)
                break
        self.refresh_city_list()

    def _on_search_pressed(self, instance):
        limit = self.cfg.get("city_limit", 5)
        if len(self.cities) >= limit:
            self.show_warning_popup("City list is full. Cannot add more cities.")
            return
        query = self.city_input.text.strip()
        if not query:
            return
        api.search_city_async(
            query,
            callback=lambda results: KivyClock.schedule_once(
                lambda dt: self._handle_search_results(results), 0
            ),
            error_callback=lambda exc: logger.error("Search error: %s", exc),
        )

    def _handle_search_results(self, results):
        if results:
            self.show_city_choices(results)
        else:
            self.city_input.text = ""
            self.city_input.hint_text = "No matches found"

    def show_city_choices(self, results):
        layout = GridLayout(cols=1, spacing=5, size_hint_y=None)
        layout.bind(minimum_height=layout.setter("height"))
        for res in results:
            name = res.get("name", "")
            country = res.get("country", "")
            admin1 = res.get("admin1", "")
            region = res.get("region", "")
            extra = admin1 or region
            text = f"{name}, {extra}, {country}" if extra else f"{name}, {country}"
            btn = Button(
                text=text, size_hint_y=None, height=60, font_size=22,
                halign="center", valign="middle",
            )
            btn.bind(size=btn.setter("text_size"))
            btn.bind(on_press=lambda i, r=res, b=btn: self._add_city(r, b))
            layout.add_widget(btn)
        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(layout)
        Popup(title="Select City", content=scroll, size_hint=(0.8, 0.6)).open()

    def _add_city(self, r, btn):
        try:
            limit = self.cfg.get("city_limit", 5)
            if len(self.cities) >= limit:
                self.show_warning_popup("City list is full. Cannot add more cities.")
                return

            city_name = r.get("name", "Unknown")
            city_country = r.get("country", "")
            exists = any(
                city["name"] == city_name and city.get("country", "") == city_country
                for city in self.cities
            )
            if exists:
                self.show_warning_popup(f"{city_name}, {city_country} is already added.")
                return

            tz = r.get("timezone") or "UTC"
            new_city = {
                "name": city_name,
                "lat": r.get("latitude", 0),
                "lon": r.get("longitude", 0),
                "timezone": tz,
                "country": city_country,
            }
            self.cities.append(new_city)
            config.save_config(self.cfg)

            manage_index = next(
                (i for i, s in enumerate(self.carousel.slides) if isinstance(s, ManageCitiesCard)),
                len(self.carousel.slides),
            )
            wc = WeatherCard(new_city, self.cfg)
            self.carousel.add_widget(wc, index=manage_index)

            btn.background_color = (0, 1, 0, 1)
            if hasattr(self, "city_input"):
                self.city_input.text = ""
            self.refresh_city_list()

        except Exception as exc:
            logger.error("Error in _add_city: %s", exc)
            self.show_warning_popup(f"Could not add city: {exc}")

    def show_warning_popup(self, message):
        layout = BoxLayout(orientation="vertical", spacing=10, padding=10)
        lbl = Label(
            text=message, font_size=32, size_hint_y=None, height=50,
            outline_color=(0, 0, 0, 1), outline_width=1,
        )
        btn = Button(text="OK", size_hint_y=None, height=50)
        layout.add_widget(lbl)
        layout.add_widget(btn)
        popup = Popup(title="Warning", content=layout, size_hint=(0.8, 0.5))
        popup.open()
        btn.bind(on_press=popup.dismiss)

    def cleanup(self):
        if hasattr(self, "_refresh_event") and self._refresh_event:
            self._refresh_event.cancel()
            self._refresh_event = None


class ShutdownRebootTab(GridLayout):
    def __init__(self, carousel=None, cfg=None, **kwargs):
        super().__init__(**kwargs)
        self.carousel = carousel
        self.cfg = cfg or {}
        self.cols = 3
        self.rows = 3
        self.padding = 30
        self.spacing = 30

        self.current_network = None

        # Row 1: Reboot | Refresh App | Shutdown
        self.reboot_button = Button(
            text="Reboot", font_size=40, background_color=(0, 1, 0, 1),
            size_hint=(1, 1),
        )
        self.reboot_button.bind(on_press=self._confirm_reboot)
        self.add_widget(self.reboot_button)

        self.refresh_app_btn = Button(
            text="Refresh App", font_size=40, background_color=(1, 0.65, 0, 1),
            size_hint=(1, 1),
        )
        self.refresh_app_btn.bind(on_press=self._confirm_restart_app)
        self.add_widget(self.refresh_app_btn)

        self.shutdown_button = Button(
            text="Shutdown", font_size=40, background_color=(1, 0, 0, 1),
            size_hint=(1, 1),
        )
        self.shutdown_button.bind(on_press=self._confirm_shutdown)
        self.add_widget(self.shutdown_button)

        # Row 2: Refresh Weather | Startup | (blank)
        self.refresh_btn = Button(
            text="Refresh Weather\n--:--",
            font_size=20, halign="center", valign="middle",
            size_hint=(1, 1),
        )
        self.refresh_btn.bind(size=self.refresh_btn.setter("text_size"))
        self.refresh_btn.bind(on_press=self.refresh_weather)
        self.add_widget(self.refresh_btn)

        # Startup slide selector (single button + popup)
        self._startup_options = {
            "clock": "Clock",
            "radio": "Radio",
            "weather": "Weather",
            "slideshow": "Slideshow",
        }
        startup = self.cfg.get("startup_slide", "clock")
        self.startup_btn = Button(
            text=f"Startup: {self._startup_options.get(startup, 'Clock')}",
            font_size=20, halign="center", valign="middle",
            background_color=(0.2, 0.4, 1, 1),
            color=(1, 1, 1, 1), bold=True,
            size_hint=(1, 1),
        )
        self.startup_btn.bind(size=self.startup_btn.setter("text_size"))
        self.startup_btn.bind(on_press=self._show_startup_popup)
        self.add_widget(self.startup_btn)

        # SSH toggle
        self.ssh_btn = Button(
            text="SSH: ...", font_size=28,
            size_hint=(1, 1),
        )
        self.ssh_btn.bind(on_press=self._toggle_ssh)
        self.add_widget(self.ssh_btn)
        system.get_ssh_status_async(
            callback=lambda result: KivyClock.schedule_once(lambda dt: self._on_ssh_status(result), 0)
        )

        # Row 3: Wi-Fi ON | Scan Networks | Wi-Fi OFF
        self.wifi_on = Button(
            text="Wi-Fi ON", font_size=28,
            size_hint=(1, 1),
        )
        self.scan_btn = Button(
            text="Scan Networks", font_size=28,
            size_hint=(1, 1),
        )
        self.wifi_off = Button(
            text="Wi-Fi OFF", font_size=28,
            size_hint=(1, 1),
        )

        self.wifi_on.bind(on_press=self._confirm_wifi_on)
        self.wifi_off.bind(on_press=self._confirm_wifi_off)
        self.scan_btn.bind(on_press=self.show_networks_popup)

        self.add_widget(self.wifi_on)
        self.add_widget(self.scan_btn)
        self.add_widget(self.wifi_off)

    def _show_startup_popup(self, instance):
        layout = GridLayout(cols=1, spacing=5, size_hint_y=None)
        layout.bind(minimum_height=layout.setter("height"))
        current = self.cfg.get("startup_slide", "clock")
        for key, label in self._startup_options.items():
            btn = Button(
                text=label, font_size=22, size_hint_y=None, height=55,
                background_color=(0.2, 0.4, 1, 1) if key == current else (0.3, 0.3, 0.3, 1),
                color=(1, 1, 1, 1), bold=True,
            )
            btn.bind(on_press=lambda inst, k=key: (self._set_startup(k), popup.dismiss()))
            layout.add_widget(btn)
        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(layout)
        popup = Popup(title="Startup Slide", content=scroll, size_hint=(0.5, 0.55))
        popup.open()

    def _set_startup(self, key):
        self.cfg["startup_slide"] = key
        config.save_config(self.cfg)
        self.startup_btn.text = f"Startup: {self._startup_options.get(key, 'Clock')}"

    def refresh_weather(self, instance):
        now = datetime.now().strftime("%H:%M")
        self.refresh_btn.text = f"Refresh Weather\n{now}"
        if self.carousel:
            for slide in self.carousel.slides:
                if isinstance(slide, WeatherCard):
                    slide.update_weather_async()

    def show_networks_popup(self, instance):
        content = BoxLayout(orientation="vertical", spacing=10, padding=10)
        self._net_status = Label(text="Scanning...", size_hint_y=None, height=40)
        content.add_widget(self._net_status)

        scroll = ScrollView(size_hint=(1, 0.9))
        self._net_grid = GridLayout(cols=1, spacing=5, size_hint_y=None)
        self._net_grid.bind(minimum_height=self._net_grid.setter("height"))
        scroll.add_widget(self._net_grid)
        content.add_widget(scroll)

        rescan_btn = Button(text="Rescan", size_hint_y=None, height=40)
        content.add_widget(rescan_btn)

        self._net_popup = Popup(title="Available Networks", content=content, size_hint=(0.8, 0.8))
        rescan_btn.bind(on_press=lambda x: (self._net_popup.dismiss(), self.show_networks_popup(None)))
        self._net_popup.open()

        # Chain: get current network first, then scan, to avoid race condition
        def _on_current(net):
            self.current_network = net
            if hasattr(self, "_net_status") and self._net_status and self._net_status.parent:
                if net:
                    self._net_status.text = f"Connected to: {net}"
                    self._net_status.color = (0, 1, 0, 1)
                else:
                    self._net_status.text = "Not connected"
            system.scan_networks_async(
                callback=lambda nets: KivyClock.schedule_once(lambda dt: self._fill_networks(nets), 0),
                error_callback=lambda exc: KivyClock.schedule_once(
                    lambda dt: self._on_scan_error(str(exc)), 0
                ),
            )

        system.get_current_network_async(
            callback=lambda net: KivyClock.schedule_once(lambda dt: _on_current(net), 0)
        )

    def _set_current_net(self, net):
        self.current_network = net
        if hasattr(self, "_net_status") and self._net_status and self._net_status.parent:
            if net:
                self._net_status.text = f"Connected to: {net}"
                self._net_status.color = (0, 1, 0, 1)
            else:
                self._net_status.text = "Not connected"

    def _fill_networks(self, networks):
        if not hasattr(self, "_net_grid") or not self._net_grid or not self._net_grid.parent:
            return
        self._net_grid.clear_widgets()
        if networks:
            for net in networks:
                net_box = BoxLayout(size_hint_y=None, height=50, spacing=5)
                btn_text = f"{net['ssid']} ({net['signal']}%) {'Locked' if net['security'] else 'Free'}"
                btn = Button(
                    text=btn_text, size_hint=(0.7, 1),
                    background_color=(0, 1, 0, 0.3) if net["ssid"] == self.current_network else (1, 1, 1, 1),
                )
                btn.bind(on_press=lambda x, s=net["ssid"]: self.show_connection_popup(s))
                net_box.add_widget(btn)
                self._net_grid.add_widget(net_box)
        else:
            self._net_grid.add_widget(Label(text="No networks found", size_hint_y=None, height=50))

    def _on_scan_error(self, message):
        if hasattr(self, "_net_status") and self._net_status and self._net_status.parent:
            self._net_status.text = f"Scan failed: {message}"
            self._net_status.color = (1, 0, 0, 1)
        if hasattr(self, "_net_grid") and self._net_grid:
            self._net_grid.clear_widgets()
            self._net_grid.add_widget(Label(text="No networks found", size_hint_y=None, height=50))

    def show_connection_popup(self, ssid):
        content = BoxLayout(orientation="vertical", spacing=10, padding=10)
        current_net = self.current_network
        is_current = ssid == current_net

        content.add_widget(Label(text=f"{'Currently connected to' if is_current else 'Connect to'} {ssid}"))

        if not is_current:
            password_box = BoxLayout(size_hint_y=None, height=40)
            self.password_input = TextInput(
                password=True, multiline=False, hint_text="Enter Password", size_hint=(0.8, 1),
            )
            show_pass_btn = Button(text="Show", size_hint=(0.2, 1))
            show_pass_btn.bind(on_press=self.toggle_password_visibility)
            password_box.add_widget(self.password_input)
            password_box.add_widget(show_pass_btn)
            content.add_widget(password_box)

        btn_box = BoxLayout(size_hint_y=None, height=40, spacing=5)
        popup = Popup(title="Network Options", content=content, size_hint=(0.8, 0.4))

        if is_current:
            disconnect_btn = Button(text="Disconnect")
            disconnect_btn.bind(on_press=lambda x: self._do_disconnect(ssid, popup))
            btn_box.add_widget(disconnect_btn)
        else:
            connect_btn = Button(text="Connect")
            connect_btn.bind(on_press=lambda x: self._do_connect(ssid, popup))
            btn_box.add_widget(connect_btn)

        forget_btn = Button(text="Forget")
        forget_btn.bind(on_press=lambda x: self._do_forget(ssid, popup))
        cancel_btn = Button(text="Cancel")
        cancel_btn.bind(on_press=popup.dismiss)
        btn_box.add_widget(forget_btn)
        btn_box.add_widget(cancel_btn)
        content.add_widget(btn_box)
        popup.open()

    def toggle_password_visibility(self, instance):
        self.password_input.password = not self.password_input.password
        instance.text = "Hide" if not self.password_input.password else "Show"

    def _do_connect(self, ssid, popup):
        password = self.password_input.text if hasattr(self, "password_input") else ""
        system.connect_to_network_async(
            ssid, password,
            callback=lambda result: KivyClock.schedule_once(lambda dt: self._on_connect_result(result, popup), 0)
        )

    def _on_connect_result(self, result, popup):
        ok, msg = result
        if popup and popup.parent:
            popup.dismiss()
        self.show_popup(msg)
        if ok:
            self.current_network = msg.replace("Connected to ", "")

    def _do_disconnect(self, ssid, popup):
        system.disconnect_network_async(
            callback=lambda result: KivyClock.schedule_once(lambda dt: self._on_disconnect_result(result, popup), 0)
        )

    def _on_disconnect_result(self, result, popup):
        ok, msg = result
        if popup and popup.parent:
            popup.dismiss()
        self.show_popup(msg)
        if ok:
            self.current_network = None

    def _do_forget(self, ssid, popup):
        system.forget_network_async(
            ssid,
            callback=lambda result: KivyClock.schedule_once(lambda dt: self._on_forget_result(result, ssid, popup), 0)
        )

    def _on_forget_result(self, result, ssid, popup):
        ok, msg = result
        if popup and popup.parent:
            popup.dismiss()
        self.show_popup(msg)
        if ok and self.current_network == ssid:
            self.current_network = None

    def toggle_wifi(self, enable=True):
        system.toggle_wifi_async(
            enable,
            callback=lambda result: KivyClock.schedule_once(lambda dt: self._on_toggle_result(result, enable), 0)
        )

    def _on_toggle_result(self, result, enable):
        ok, msg = result
        self.show_popup(msg)
        if ok and not enable:
            self.current_network = None
        if ok and enable:
            KivyClock.schedule_once(lambda dt: self.show_networks_popup(None), 2)

    def shutdown_device(self, instance):
        system.shutdown()

    def reboot_device(self, instance):
        system.reboot()

    def restart_app_service(self, instance):
        os.system('echo p | sudo -S systemctl restart weather_app.service')

    def _show_confirm(self, title, message, on_confirm):
        content = BoxLayout(orientation="vertical", spacing=10, padding=10)
        content.add_widget(Label(text=message, font_size=28))
        btn_box = BoxLayout(size_hint_y=None, height=60, spacing=10)
        popup = Popup(title=title, content=content, size_hint=(0.6, 0.35))

        cancel_btn = Button(text="Cancel", font_size=24)
        cancel_btn.bind(on_press=popup.dismiss)
        ok_btn = Button(
            text="Confirm", font_size=24,
            background_color=(1, 0, 0, 0.8), color=(1, 1, 1, 1),
        )
        ok_btn.bind(on_press=lambda i: (on_confirm(), popup.dismiss()))
        btn_box.add_widget(cancel_btn)
        btn_box.add_widget(ok_btn)
        content.add_widget(btn_box)
        popup.open()

    def _confirm_reboot(self, instance):
        self._show_confirm("Reboot?", "Reboot the device?", lambda: self.reboot_device(None))

    def _confirm_shutdown(self, instance):
        self._show_confirm("Shutdown?", "Shut down the device?", lambda: self.shutdown_device(None))

    def _confirm_restart_app(self, instance):
        self._show_confirm("Restart App?", "Restart weather app service?", lambda: self.restart_app_service(None))

    def _confirm_wifi_on(self, instance):
        self._show_confirm("Wi-Fi ON?", "Turn Wi-Fi ON?", lambda: self.toggle_wifi(True))

    def _confirm_wifi_off(self, instance):
        self._show_confirm("Wi-Fi OFF?", "Turn Wi-Fi OFF?", lambda: self.toggle_wifi(False))

    def show_popup(self, message):
        popup = Popup(title="Info", content=Label(text=message), size_hint=(0.6, 0.4))
        popup.open()
        KivyClock.schedule_once(lambda dt: popup.dismiss(), 2)

    def _on_ssh_status(self, active):
        if active:
            self.ssh_btn.text = "SSH: ON"
            self.ssh_btn.background_color = (0, 0.7, 0, 1)
        else:
            self.ssh_btn.text = "SSH: OFF"
            self.ssh_btn.background_color = (0.7, 0, 0, 1)

    def _toggle_ssh(self, instance):
        current = self.ssh_btn.text == "SSH: ON"
        system.toggle_ssh_async(
            not current,
            callback=lambda result: KivyClock.schedule_once(lambda dt: self._on_ssh_toggle(result), 0),
        )

    def _on_ssh_toggle(self, result):
        ok, msg = result
        self.show_popup(msg)
        if ok:
            system.get_ssh_status_async(
                callback=lambda result: KivyClock.schedule_once(lambda dt: self._on_ssh_status(result), 0)
            )


class RadioCard(RelativeLayout):
    def __init__(self, carousel, player, cfg, **kw):
        super().__init__(**kw)
        self.carousel = carousel
        self.player = player
        self.cfg = cfg

        # Background
        bg_path = Path(__file__).parent / "radio.jpg"
        if bg_path.exists():
            bg_tex = CoreImage(str(bg_path)).texture
            with self.canvas.before:
                Color(1, 1, 1, 1)
                self._bg_rect = Rectangle(pos=self.pos, size=self.size, texture=bg_tex)
            self.bind(pos=self._update_bg, size=self._update_bg)

        self._current_stations = []
        self._current_title = ""
        self._searching = False
        self._play_start_time = 0
        self._VOL_STEPS = [0, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]

        # Inner layout (sidebar + main)
        inner = BoxLayout(orientation="horizontal", padding=15, spacing=10, size_hint=(1, 1))

        # ── Left Sidebar ──
        sidebar = BoxLayout(orientation="vertical", size_hint_x=0.22, spacing=0)
        _BTN = dict(background_normal='', background_color=(0, 0, 0, 0.75), color=(1, 1, 1, 1), bold=True)

        def _sep():
            w = Widget(size_hint_y=None, height=5)
            with w.canvas:
                Color(0, 0, 0, 0.75)
                w.line1 = Rectangle(pos=(w.x, w.y + 1), size=(w.width, 1))
                w.line2 = Rectangle(pos=(w.x, w.y + 3), size=(w.width, 1))
            def _up(inst, val):
                inst.line1.pos = (inst.x, inst.y + 1)
                inst.line1.size = (inst.width, 1)
                inst.line2.pos = (inst.x, inst.y + 3)
                inst.line2.size = (inst.width, 1)
            w.bind(pos=_up, size=_up)
            return w

        # Search
        search_input_box = BoxLayout(orientation="horizontal", size_hint_y=None, height=50, spacing=5)
        self.search_input = TextInput(
            hint_text="Search", multiline=False, font_size=18,
            size_hint=(0.75, 1), background_color=(0, 0, 0, 0.75),
            foreground_color=(1, 1, 1, 1), cursor_color=(1, 1, 1, 1),
            hint_text_color=(0.7, 0.7, 0.7, 1), padding=[8, 14, 8, 14],
        )
        self.search_btn = Button(text="Go", font_size=20, size_hint=(0.25, 1), **_BTN)
        self.search_btn.bind(on_press=self._do_search)
        search_input_box.add_widget(self.search_input)
        search_input_box.add_widget(self.search_btn)
        sidebar.add_widget(search_input_box)
        sidebar.add_widget(_sep())

        # Volume
        self.vol_up_btn = Button(text="Vol +", font_size=24, **_BTN)
        self.vol_up_btn.bind(on_press=self._vol_up)
        sidebar.add_widget(self.vol_up_btn)
        sidebar.add_widget(_sep())

        self.vol_down_btn = Button(text="Vol -", font_size=24, **_BTN)
        self.vol_down_btn.bind(on_press=self._vol_down)
        sidebar.add_widget(self.vol_down_btn)
        sidebar.add_widget(_sep())

        # Countries
        self.countries_btn = Button(text="Countries", font_size=20, **_BTN)
        self.countries_btn.bind(on_press=self._show_continents)
        sidebar.add_widget(self.countries_btn)
        sidebar.add_widget(_sep())

        # Favorites
        self.fav_btn = Button(text="Favorites", font_size=20, **_BTN)
        self.fav_btn.bind(on_press=self._show_favorites)
        sidebar.add_widget(self.fav_btn)
        sidebar.add_widget(_sep())

        # Pause
        self.pause_btn = Button(text="Pause", font_size=24, **dict(_BTN, color=(0.3, 0.5, 1, 1)))
        self.pause_btn.bind(on_press=self._pause_resume)
        sidebar.add_widget(self.pause_btn)
        sidebar.add_widget(_sep())

        # Stop
        self.stop_btn = Button(text="Stop", font_size=24, **dict(_BTN, color=(1, 0.2, 0.2, 1)))
        self.stop_btn.bind(on_press=self._stop)
        sidebar.add_widget(self.stop_btn)

        inner.add_widget(sidebar)

        # ── Main Area ──
        main = BoxLayout(orientation="vertical", size_hint_x=0.78, spacing=6)

        # Combined top box (station name + status only)
        top_box = BoxLayout(orientation="vertical", size_hint_y=None, height=100, padding=6, spacing=4)
        with top_box.canvas.before:
            Color(0, 0, 0, 0.75)
            self._top_box_bg = Rectangle(pos=top_box.pos, size=top_box.size)
        top_box.bind(pos=lambda inst, val: setattr(self._top_box_bg, 'pos', val))
        top_box.bind(size=lambda inst, val: setattr(self._top_box_bg, 'size', val))
        self.station_name_label = Label(
            text="Radio", font_size=48, halign="center", valign="middle",
            color=(1, 1, 1, 1), bold=True, size_hint=(1, None), height=62,
        )
        self.station_name_label.bind(size=self.station_name_label.setter("text_size"))
        self.status_state = Label(
            text="Stopped", font_size=24, halign="center", valign="middle",
            color=(0.6, 0.8, 1, 1), size_hint=(1, None), height=30,
        )
        self.status_state.bind(size=self.status_state.setter("text_size"))
        top_box.add_widget(self.station_name_label)
        top_box.add_widget(self.status_state)
        main.add_widget(top_box)

        main.add_widget(BoxLayout(size_hint_y=0.02))

        # Section title (centered, above station list)
        self.section_title = Label(
            text="Favorites", font_size=24, halign="center", valign="middle",
            color=(1, 1, 1, 1), bold=True, size_hint_y=None, height=30,
        )
        self.section_title.bind(size=self.section_title.setter("text_size"))
        with self.section_title.canvas.before:
            Color(0, 0, 0, 0.75)
            self._title_bg = Rectangle(pos=self.section_title.pos, size=self.section_title.size)
        self.section_title.bind(pos=lambda inst, val: setattr(self._title_bg, 'pos', val))
        self.section_title.bind(size=lambda inst, val: setattr(self._title_bg, 'size', val))
        main.add_widget(self.section_title)

        # Station list (paginated ScrollView + GridLayout)
        self.results_scroll = ScrollView()
        self.results_grid = GridLayout(cols=1, spacing=3, size_hint_y=None)
        self.results_grid.bind(minimum_height=self.results_grid.setter("height"))
        self.results_scroll.add_widget(self.results_grid)
        main.add_widget(self.results_scroll)

        # Page navigation
        self.page_nav = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=50, spacing=6, opacity=0,
        )
        self.page_back = Button(text="Back", font_size=20, size_hint_x=0.3, **_BTN)
        self.page_back.bind(on_press=self._prev_page)
        self.page_info = Label(
            text="", font_size=20, halign="center", valign="middle",
            color=(1, 1, 1, 1), bold=True, size_hint_x=0.4,
        )
        self.page_info.bind(size=self.page_info.setter("text_size"))
        self.page_next = Button(text="Next", font_size=20, size_hint_x=0.3, **_BTN)
        self.page_next.bind(on_press=self._next_page)
        self.page_nav.add_widget(self.page_back)
        self.page_nav.add_widget(self.page_info)
        self.page_nav.add_widget(self.page_next)
        main.add_widget(self.page_nav)

        inner.add_widget(main)
        self.add_widget(inner)

        # Equalizer button (top-right, only if VLC supports it)
        if self.player.has_equalizer():
            eq_btn = Button(
                text="EQ", font_size=20, size_hint=(None, None), size=(60, 60),
                pos_hint={"right": 0.99, "top": 0.99},
                background_color=(0.2, 0.2, 0.2, 0.6), color=(1, 1, 1, 1),
            )
            with eq_btn.canvas.before:
                Color(1, 1, 1, 1)
                eq_btn._outline = Line(
                    rectangle=(eq_btn.x, eq_btn.y, eq_btn.width, eq_btn.height), width=1.5
                )
            def _update_outline(inst, val):
                inst._outline.rectangle = (inst.x, inst.y, inst.width, inst.height)
            eq_btn.bind(pos=_update_outline, size=_update_outline)
            eq_btn.bind(on_press=self._show_eq_popup)
            self.add_widget(eq_btn)

        # Poll state
        self._poll_event = KivyClock.schedule_interval(self._poll_state, 2)

        # Show favorites by default
        self._show_favorites()

    # ── Search ──
    def _update_bg(self, *args):
        if hasattr(self, "_bg_rect"):
            self._bg_rect.pos = self.pos
            self._bg_rect.size = self.size

    def _do_search(self, instance):
        name = self.search_input.text.strip()
        if not name or self._searching:
            return
        self._searching = True
        self._set_loading(True)

        def _worker():
            try:
                results = radio_api.search_stations(name)
                KivyClock.schedule_once(
                    lambda dt: self._show_stations(results, f"Search: {name}"), 0
                )
            except Exception as exc:
                logger.error("Search error: %s", exc)
                KivyClock.schedule_once(
                    lambda dt: self._show_stations([], f"Search: {name}"), 0
                )
            finally:
                self._searching = False
        import threading
        threading.Thread(target=_worker, daemon=True).start()

    # ── Volume ──
    def _vol_up(self, instance):
        v = self.player.get_volume()
        for step in self._VOL_STEPS:
            if step > v:
                self.player.set_volume(step)
                self.cfg["radio_volume"] = step
                config.save_config(self.cfg)
                self._show_volume()
                return

    def _vol_down(self, instance):
        v = self.player.get_volume()
        for step in reversed(self._VOL_STEPS):
            if step < v:
                self.player.set_volume(step)
                self.cfg["radio_volume"] = step
                config.save_config(self.cfg)
                self._show_volume()
                return

    def _show_volume(self):
        self._volume_show_until = time.time() + 1.2
        self._update_info()

    def _stop(self, instance):
        self.player.stop()
        self._current_playing_uuid = None
        self.pause_btn.text = "Pause"
        self._update_info()
        if self._current_stations:
            self._render_page()

    def _pause_resume(self, instance):
        state = self.player.get_state()
        if state == "playing":
            self.player.pause()
            self.pause_btn.text = "Resume"
        elif state == "paused":
            self.player.resume()
            self.pause_btn.text = "Pause"
        self._update_info()

    # ── Continent / Country flow ──
    def _show_continents(self, instance):
        layout = GridLayout(cols=1, spacing=5, size_hint_y=None)
        layout.bind(minimum_height=layout.setter("height"))
        for cont in radio_api.CONTINENTS:
            btn = Button(text=cont, font_size=22, size_hint_y=None, height=55)
            btn.bind(on_press=lambda inst, c=cont: self._on_continent(c))
            layout.add_widget(btn)
        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(layout)
        self._continent_popup = Popup(
            title="Select Continent", content=scroll, size_hint=(0.55, 0.7)
        )
        self._continent_popup.open()

    def _on_continent(self, continent):
        if hasattr(self, "_continent_popup") and self._continent_popup:
            self._continent_popup.dismiss()
        self._set_loading(True)

        def _worker():
            try:
                countries = radio_api.get_countries()
                filtered = [c for c in countries if c["continent"] == continent]
                KivyClock.schedule_once(
                    lambda dt: self._show_countries(filtered, continent), 0
                )
            except Exception as exc:
                logger.error("Countries fetch error: %s", exc)
                KivyClock.schedule_once(
                    lambda dt: self._show_countries([], continent), 0
                )
        import threading
        threading.Thread(target=_worker, daemon=True).start()

    def _show_countries(self, countries, continent):
        self._set_loading(False)
        layout = GridLayout(cols=1, spacing=4, size_hint_y=None)
        layout.bind(minimum_height=layout.setter("height"))
        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(layout)
        popup = Popup(
            title=f"{continent} — Select Country", content=scroll, size_hint=(0.7, 0.75)
        )
        if not countries:
            layout.add_widget(
                Label(text="No countries found", font_size=20, size_hint_y=None, height=50)
            )
        else:
            for c in countries:
                btn = Button(
                    text=f"{c['name']}  ({c['stationcount']} stations)",
                    font_size=18, size_hint_y=None, height=46,
                    halign="left", valign="middle",
                )
                btn.bind(size=btn.setter("text_size"))
                btn.bind(on_press=lambda inst, cc=c["code"], pop=popup: (pop.dismiss(), self._on_country(cc)))
                layout.add_widget(btn)
        popup.open()

    def _on_country(self, country_code):
        self._set_loading(True)

        def _worker():
            try:
                results = radio_api.get_stations_by_country(country_code)
                KivyClock.schedule_once(
                    lambda dt: self._show_stations(results, country_code), 0
                )
            except Exception as exc:
                logger.error("Station fetch error: %s", exc)
                KivyClock.schedule_once(
                    lambda dt: self._show_stations([], country_code), 0
                )
        import threading
        threading.Thread(target=_worker, daemon=True).start()

    # ── Favorites ──
    def _show_favorites(self, instance=None):
        favs = list(self.cfg.get("radio_favorites", []))
        self._show_stations(favs, "Favorites")

    def _is_favorite(self, station_uuid):
        favs = self.cfg.get("radio_favorites", [])
        return any(f.get("stationuuid") == station_uuid for f in favs)

    def _toggle_favorite(self, station):
        favs = self.cfg.setdefault("radio_favorites", [])
        idx = next(
            (
                i
                for i, f in enumerate(favs)
                if f.get("stationuuid") == station.get("stationuuid")
            ),
            -1,
        )
        if idx >= 0:
            favs.pop(idx)
        else:
            favs.append(
                {
                    "name": station.get("name", ""),
                    "url": station.get("url", ""),
                    "codec": station.get("codec", ""),
                    "bitrate": station.get("bitrate", 0),
                    "country": station.get("country", ""),
                    "stationuuid": station.get("stationuuid", ""),
                }
            )
        config.save_config(self.cfg)

    def _toggle_favorite_and_refresh(self, station):
        self._toggle_favorite(station)
        if self._current_title == "Favorites":
            self._show_favorites()
        elif self._current_stations:
            self._render_page()

    # ── Station list builder (paginated) ──
    PAGE_SIZE = 25

    def _show_stations(self, stations, title=""):
        self._current_stations = list(stations)
        self._current_title = title
        self._current_page = 0
        self._set_loading(False)
        self.section_title.text = title if title else "Stations"
        self._render_page()

    def _render_page(self):
        stations = self._current_stations
        self.results_grid.clear_widgets()

        if not stations:
            self.results_grid.add_widget(
                Label(text="No stations", font_size=20, size_hint_y=None, height=50,
                      color=(0.7, 0.7, 0.7, 1))
            )
            self.page_nav.opacity = 0
            return
        total_pages = max(1, (len(stations) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        page = max(0, min(self._current_page, total_pages - 1))
        self._current_page = page

        start = page * self.PAGE_SIZE
        end = start + self.PAGE_SIZE
        page_stations = stations[start:end]

        for s in page_stations:
            row = BoxLayout(
                orientation="horizontal", size_hint_y=None, height=48, spacing=4
            )
            name = s.get("name", "Unknown")
            info = (
                f"{name}  |  {s.get('country', '')}  |  "
                f"{s.get('bitrate', 0)}k {s.get('codec', '')}"
            )
            if len(info) > 50:
                info = info[:47] + "..."
            is_playing = s.get("stationuuid") == getattr(self, "_current_playing_uuid", None)
            name_btn = Button(
                text=info,
                font_size=18,
                halign="left",
                valign="middle",
                color=(1, 1, 1, 1),
                bold=True,
                background_normal='',
                background_color=(0.1, 0.3, 0.8, 0.75) if is_playing else (0, 0, 0, 0.75),
                size_hint_x=0.8,
                padding=[12, 0],
            )
            name_btn.bind(size=name_btn.setter("text_size"))
            name_btn.bind(on_press=lambda inst, st=s: self._play_station(st))

            is_fav = self._is_favorite(s.get("stationuuid"))
            fav_btn = Button(
                text="Fav-" if is_fav else "Fav+",
                font_size=18,
                size_hint_x=None,
                width=80,
                background_normal='',
                background_color=(0, 0, 0, 0.75),
                color=(1, 0.2, 0.2, 1) if is_fav else (0.2, 0.4, 1, 1),
                bold=True,
            )
            fav_btn.bind(on_press=lambda inst, st=s: self._toggle_favorite_and_refresh(st))

            row.add_widget(name_btn)
            row.add_widget(fav_btn)
            self.results_grid.add_widget(row)

        # Update nav
        if total_pages > 1:
            self.page_nav.opacity = 1
            self.page_info.text = f"{page + 1} / {total_pages}"
            self.page_back.opacity = 0.5 if page == 0 else 1
            self.page_next.opacity = 0.5 if page >= total_pages - 1 else 1
        else:
            self.page_nav.opacity = 0

    def _next_page(self, instance=None):
        total_pages = max(1, (len(self._current_stations) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        if self._current_page < total_pages - 1:
            self._current_page += 1
            self._render_page()

    def _prev_page(self, instance=None):
        if self._current_page > 0:
            self._current_page -= 1
            self._render_page()

    def _play_station(self, station):
        self._play_start_time = time.time()
        self._current_playing_uuid = station.get("stationuuid")
        self.player.play(station["url"], station["name"])
        self.pause_btn.text = "Pause"
        self._update_info()
        if self._current_stations:
            self._render_page()

    def _update_info(self):
        name = self.player.current_name
        if name:
            display = name[:18] if len(name) > 18 else name
        else:
            display = "Radio"
        self.station_name_label.text = display

        # Show volume temporarily after vol change
        if getattr(self, "_volume_show_until", 0) > time.time():
            self.status_state.text = f"Volume: {self.player.get_volume()}%"
            return

        state = self.player.get_state()
        if not name:
            text = "Stopped"
        elif state == "paused":
            text = "Paused"
        elif state == "playing":
            text = "Muted" if self.player.get_volume() == 0 else "Playing"
        else:
            elapsed = time.time() - self._play_start_time
            text = "Buffering..." if elapsed < 8 else "Stopped"
        self.status_state.text = text

    def _set_loading(self, loading):
        if loading:
            self.section_title.text = "Loading..."

    def _poll_state(self, dt):
        self._update_info()

    def _show_eq_popup(self, instance):
        content = GridLayout(cols=4, spacing=5, padding=10)
        presets = [
            ("Off", -1), ("Flat", 0), ("Classical", 1), ("Club", 2),
            ("Dance", 3), ("Full Bass", 4), ("Rock", 13), ("Pop", 11),
        ]
        popup = Popup(title="Equalizer", content=content, size_hint=(0.8, 0.5))
        for name, preset_id in presets:
            btn = Button(text=name, font_size=18)
            if preset_id == -1:
                btn.bind(on_press=lambda i, p=preset_id: (self.player.disable_equalizer(), popup.dismiss()))
            else:
                btn.bind(on_press=lambda i, p=preset_id: (self.player.set_equalizer_preset(p), popup.dismiss()))
            content.add_widget(btn)
        popup.open()

    def cleanup(self):
        if hasattr(self, "_poll_event") and self._poll_event:
            self._poll_event.cancel()
            self._poll_event = None


class WeatherDisplayApp(App):
    def build(self):
        Window.clearcolor = (0.05, 0.05, 0.2, 1)
        self.cfg = config.load_config()
        self.root_layout = FloatLayout()
        self.carousel = Carousel(direction="right", size_hint=(1, 1), pos_hint={"x": 0, "y": 0})
        self.root_layout.add_widget(self.carousel)

        self.radio_player = RadioPlayer(volume=self.cfg.get("radio_volume", 20))

        self.locked = False
        self.lock_label = None
        self.last_touch_time = 0

        self.carousel.add_widget(PhotoSlide(self.cfg))
        self.carousel.add_widget(ClockSlide(self.carousel, self.radio_player))
        self.carousel.add_widget(RadioCard(self.carousel, self.radio_player, self.cfg))

        api.clear_cache()
        cities = self.cfg.get("cities", [])
        for i, cit in enumerate(cities):
            wc = WeatherCard(cit, self.cfg, auto_fetch=False)
            self.carousel.add_widget(wc)
            if i == 0:
                wc.update_weather_async()
            else:
                KivyClock.schedule_once(lambda dt, w=wc: w.update_weather_async(), i * 1.5)

        self.carousel.add_widget(ManageCitiesCard(self.carousel, self.cfg))
        self.carousel.add_widget(ShutdownRebootTab(self.carousel, self.cfg))

        # Auto-switch to configured startup slide
        startup = self.cfg.get("startup_slide", "clock")
        def _goto_startup(dt):
            target = {
                "clock": ClockSlide,
                "radio": RadioCard,
                "weather": WeatherCard,
                "slideshow": PhotoSlide,
            }.get(startup, ClockSlide)
            for i, slide in enumerate(self.carousel.slides):
                if isinstance(slide, target):
                    self.carousel.load_slide(self.carousel.slides[i])
                    break
        KivyClock.schedule_once(_goto_startup, 1.5)

        Window.bind(on_touch_down=self.on_touch_down)

        return self.root_layout

    def on_stop(self):
        """Clean up VLC and all slides on app exit."""
        if hasattr(self, "carousel") and self.carousel:
            for slide in self.carousel.slides:
                if hasattr(slide, "cleanup") and callable(slide.cleanup):
                    slide.cleanup()
        if hasattr(self, "radio_player") and self.radio_player:
            self.radio_player.stop()
            self.radio_player.cleanup()

    def on_touch_down(self, window, touch):
        if isinstance(self.carousel.slides[self.carousel.index], (ManageCitiesCard, ShutdownRebootTab)):
            return False

        now = time.time()
        threshold = self.cfg.get("lock_double_tap_seconds", 0.2)
        if now - getattr(self, "last_touch_time", 0) < threshold:
            if self.locked:
                self.unlock_screen()
            else:
                self.lock_screen()
        self.last_touch_time = now
        if self.locked and self.lock_label:
            self.lock_label.opacity = 1
            KivyClock.schedule_once(self.hide_lock_label, 10)
        return self.locked

    def lock_screen(self):
        if not self.locked:
            self.locked = True
            if not self.lock_label:
                self.lock_label = Label(
                    text="Double tap to unlock",
                    font_size=24, size_hint=(1, None), height=50,
                    pos_hint={"top": 1}, color=(1, 1, 1, 0.8),
                )
                self.root_layout.add_widget(self.lock_label)
            else:
                self.lock_label.opacity = 1
            KivyClock.schedule_once(self.hide_lock_label, 10)

    def hide_lock_label(self, dt=None):
        if self.lock_label:
            self.lock_label.opacity = 0

    def unlock_screen(self):
        if self.locked:
            self.locked = False
            if self.lock_label:
                self.root_layout.remove_widget(self.lock_label)
                self.lock_label = None
