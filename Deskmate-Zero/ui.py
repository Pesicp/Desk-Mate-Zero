"""All Kivy UI widgets for DeskMate Zero."""

import json
import logging
import os
import random
import socket
import time
from datetime import datetime, timezone
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
    def __init__(self, carousel, **kw):
        super().__init__(orientation="vertical", **kw)
        self.carousel = carousel
        self.padding = 50
        self.spacing = 20

        self.clock_label = Label(
            font_size=240, color=(1, 1, 1, 1), halign="center",
            size_hint=(1, None), height=240,
        )
        self.date_label = Label(
            font_size=30, color=(1, 1, 1, 1), halign="center",
            size_hint=(1, None), height=30,
        )

        self.add_widget(BoxLayout(size_hint_y=1))
        self.add_widget(self.clock_label)
        self.add_widget(BoxLayout(size_hint_y=None, height=10))
        self.add_widget(self.date_label)
        self.add_widget(BoxLayout(size_hint_y=1))

        KivyClock.schedule_interval(self.update_clock, 2)

    def update_clock(self, dt):
        wifi = self._check_wifi()
        cards = [s for s in self.carousel.slides if isinstance(s, WeatherCard)]
        if wifi and cards:
            now = datetime.now(cards[0].timezone)
        else:
            now = datetime.now()
        self.clock_label.text = now.strftime("%H:%M")
        self.date_label.text = now.strftime("%A, %d.%m")

    @staticmethod
    def _check_wifi():
        try:
            socket.create_connection(("1.1.1.1", 53), timeout=1)
            return True
        except OSError:
            return False


class WeatherCard(BoxLayout):
    def __init__(self, city, cfg, **kw):
        super().__init__(orientation="vertical", **kw)
        self.city = city
        self.cfg = cfg
        self.timezone = ZoneInfo(city.get("timezone", "UTC"))
        self.time_offset = datetime.now(self.timezone).utcoffset()
        self._last_wifi_on = True
        self._last_weather_code = 0
        self.padding = [0, 0, 0, 0]
        self.spacing = 0

        # Background images (day / night)
        try:
            self.day_tex = CoreImage("weathercard_day.jpg").texture
            self.night_tex = CoreImage("weathercard_night.jpg").texture
        except Exception:
            self.day_tex = None
            self.night_tex = None
        with self.canvas.before:
            Color(1, 1, 1, 1)
            self.bg_rect = Rectangle(texture=self.day_tex, size=self.size, pos=self.pos)
        self.bind(pos=lambda *a: setattr(self.bg_rect, 'pos', self.pos), size=lambda *a: setattr(self.bg_rect, 'size', self.size))

        # ── Top half: 3 equal columns ──
        top_half = BoxLayout(orientation="horizontal", size_hint_y=0.5)

        # Col 1: city above icon
        col1 = RelativeLayout(size_hint_x=1/3)

        self.today_icon = Image(
            size_hint=(None, None), size=(220, 220),
            allow_stretch=True, keep_ratio=True,
            pos_hint={'center_x': 0.5, 'center_y': 0.4},
        )
        col1.add_widget(self.today_icon)


        self.city_label = Label(
            text=city["name"], font_size=40,
            halign="center", valign="top", color=(0.75, 0.80, 0.90, 1),
            size_hint=(1, None),
            bold=True,
            pos_hint={'center_x': 0.5, 'center_y': 0.82},
        )

        def _set_city_layout(inst, ts):
            inst.height = ts[1]
            # Multi-line: pin to top so all text is visible
            # Single-line: center vertically like code/date labels
            inst.pos_hint = (
                {'center_x': 0.5, 'top': 0.95}
                if ts[1] > 55
                else {'center_x': 0.5, 'center_y': 0.82}
            )

        self.city_label.bind(
            width=lambda inst, w: setattr(inst, "text_size", (w, None))
        )
        self.city_label.bind(texture_size=_set_city_layout)
        col1.add_widget(self.city_label)
        top_half.add_widget(col1)

        # Col 2: code above temp
        col2 = RelativeLayout(size_hint_x=1/3)

        self.code_label = Label(
            font_size=40, halign="center", valign="middle",
            color=(0.75, 0.80, 0.90, 1), size_hint=(1, None), height=50,
            bold=True,
            pos_hint={'center_x': 0.5, 'center_y': 0.82},
        )
        self.code_label.bind(size=self.code_label.setter("text_size"))
        col2.add_widget(self.code_label)

        self.temp_label = Label(
            font_size=90, halign="center", valign="middle",
            color=(1, 1, 1, 1), size_hint=(1, None), height=102,
            bold=True,
            pos_hint={'center_x': 0.5, 'center_y': 0.4},
        )
        self.temp_label.bind(size=self.temp_label.setter("text_size"))
        col2.add_widget(self.temp_label)
        top_half.add_widget(col2)

        # Col 3: date above clock
        col3 = RelativeLayout(size_hint_x=1/3)

        self.date_label = Label(
            font_size=40, halign="center", valign="middle",
            color=(0.70, 0.75, 0.85, 1), size_hint=(1, None), height=50,
            bold=True,
            pos_hint={'center_x': 0.5, 'center_y': 0.82},
        )
        self.date_label.bind(size=self.date_label.setter("text_size"))
        col3.add_widget(self.date_label)

        self.clock_label = Label(
            font_size=90, halign="center", valign="middle",
            color=(1, 1, 1, 1), size_hint=(1, None), height=102,
            bold=True,
            pos_hint={'center_x': 0.5, 'center_y': 0.4},
        )
        self.clock_label.bind(size=self.clock_label.setter("text_size"))
        col3.add_widget(self.clock_label)
        top_half.add_widget(col3)


        self.add_widget(top_half)

        # ── Bottom half: hourly + daily ──
        bottom_half = BoxLayout(orientation="vertical", size_hint_y=0.5, spacing=0)

        self.hourly_layout = GridLayout(cols=8, size_hint_y=0.5, spacing=0, padding=0)

        bottom_half.add_widget(self.hourly_layout)

        self.forecast_box = GridLayout(cols=5, size_hint_y=0.5, spacing=0, padding=0)

        bottom_half.add_widget(self.forecast_box)

        with top_half.canvas.before:
            Color(0, 0, 0, 0.3)
            top_ov = Rectangle(size=top_half.size, pos=top_half.pos)
        top_half.bind(pos=lambda *a: setattr(top_ov, 'pos', top_half.pos), size=lambda *a: setattr(top_ov, 'size', top_half.size))

        with self.hourly_layout.canvas.before:
            Color(0, 0, 0, 0.4)
            hr_ov = Rectangle(size=self.hourly_layout.size, pos=self.hourly_layout.pos)
        self.hourly_layout.bind(pos=lambda *a: setattr(hr_ov, 'pos', self.hourly_layout.pos), size=lambda *a: setattr(hr_ov, 'size', self.hourly_layout.size))

        with self.forecast_box.canvas.before:
            Color(0, 0, 0, 0.5)
            day_ov = Rectangle(size=self.forecast_box.size, pos=self.forecast_box.pos)
        self.forecast_box.bind(pos=lambda *a: setattr(day_ov, 'pos', self.forecast_box.pos), size=lambda *a: setattr(day_ov, 'size', self.forecast_box.size))
        self.add_widget(bottom_half)

        self.update_weather_async()
        self._clock_event = KivyClock.schedule_interval(lambda dt: self.update_clock(), 2)
        self._weather_event = KivyClock.schedule_interval(
            lambda dt: self._safe_update_weather(),
            cfg.get("refresh_interval", 1800),
        )


    def update_clock(self):
        try:
            try:
                socket.create_connection(("1.1.1.1", 53), timeout=1)
                wifi_on = True
                now = datetime.now(self.timezone)
                self.time_offset = now.utcoffset()
            except OSError:
                wifi_on = False
                utc_now = datetime.now(timezone.utc)
                now = utc_now + self.time_offset

            if wifi_on and not getattr(self, "_last_wifi_on", True):
                self.update_weather_async()
            self._last_wifi_on = wifi_on

            self.clock_label.text = now.strftime("%H:%M")
            self.date_label.text = now.strftime("%a, %d.%m")

            # Switch background day/night based on local hour
            if hasattr(self, 'bg_rect') and self.day_tex and self.night_tex:
                self.bg_rect.texture = self.day_tex if 6 <= now.hour < 18 else self.night_tex

            if hasattr(self, 'today_icon') and self._last_weather_code:
                dn = "d" if 6 <= now.hour < 18 else "n"
                self.today_icon.source = _icon_file(self._last_weather_code, dn)
        except Exception as exc:
            logger.error("Clock update error for %s: %s", self.city.get("name"), exc)
            try:
                utc_now = datetime.now(timezone.utc)
                now = utc_now + self.time_offset
                self.clock_label.text = now.strftime("%H:%M")
                self.date_label.text = now.strftime("%a, %d.%m")
            except Exception as exc2:
                logger.error("Fallback clock update error: %s", exc2)

    def _safe_update_weather(self):
        try:
            socket.create_connection(("1.1.1.1", 53), timeout=1)
            wifi_on = True
        except OSError:
            wifi_on = False

        if wifi_on:
            self.update_weather_async()
            self.temp_label.opacity = 1
            self.code_label.opacity = 1
            self.clock_label.opacity = 1
            self.date_label.opacity = 1
            self.hourly_layout.opacity = 1
            self.forecast_box.opacity = 1
        else:
            self.temp_label.opacity = 0
            self.code_label.opacity = 0
            self.clock_label.opacity = 1
            self.date_label.opacity = 1
            self.hourly_layout.opacity = 0
            self.forecast_box.opacity = 0

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

        current_time = datetime.now(self.timezone).hour
        dn = "d" if 6 <= current_time < 18 else "n"
        self.today_icon.source = _icon_file(cur_code, dn)

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
            b = RelativeLayout(size_hint_x=1/8)

            hh_hour = dt.hour
            ip = _icon_file(hh["weathercode"], "d" if 6 <= hh_hour < 18 else "n")

            t = Label(text=f"{int(hh['temp'])}°C", font_size=16, halign="center", valign="bottom", size_hint=(1, None), height=28, pos_hint={'x': 0, 'y': 0.08}, color=(1, 1, 1, 1), bold=True)
            t.bind(size=t.setter("text_size"))
            b.add_widget(t)

            b.add_widget(Image(source=ip, size_hint=(None, None), size=(86, 86), allow_stretch=True, keep_ratio=False, pos_hint={"center_x": 0.5, "center_y": 0.5}))

            tm = Label(text=dt.strftime("%H:%M"), font_size=17, halign="center", valign="top", size_hint=(1, None), height=18, pos_hint={'x': 0, 'y': 0.71}, color=(0.65, 0.70, 0.80, 1), bold=True)
            tm.bind(size=tm.setter("text_size"))
            b.add_widget(tm)
            self.hourly_layout.add_widget(b)

        # 5-day forecast — centered in each cell with background
        self.forecast_box.clear_widgets()
        for d in daily:
            dt = datetime.strptime(d["date"], "%Y-%m-%d")
            b = RelativeLayout(size_hint_x=1/5)

            # Explicit pixel positions in a ~150 px tall cell
            # temp(15) + gap(3) + icon(90) + gap(3) + day(16) = 127 px
            # centered vertically with ~11 px margin top & bottom
            temp_lbl = Label(text=f"{int(d['temp_max'])}° / {int(d['temp_min'])}°", font_size=15, halign="center", valign="bottom", size_hint=(1, None), height=15, pos_hint={'x': 0, 'y': 0.077}, color=(1, 1, 1, 1), bold=True)
            temp_lbl.bind(size=temp_lbl.setter("text_size"))
            b.add_widget(temp_lbl)

            ip = _icon_file(d["weathercode"], "d")
            b.add_widget(Image(source=ip, size_hint=(None, None), size=(135, 135), allow_stretch=True, keep_ratio=False, pos_hint={'center_x': 0.5, 'center_y': 0.5}))

            day_lbl = Label(text=dt.strftime("%A"), font_size=16, halign="center", valign="top", size_hint=(1, None), height=16, pos_hint={'x': 0, 'y': 0.817}, color=(0.75, 0.80, 0.90, 1), bold=True)
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

        self.image_widget = Image(allow_stretch=True, keep_ratio=True)
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

        l = BoxLayout(orientation="vertical", size_hint=(0.5, 1))
        add_btn = Button(text="+", font_size=120, size_hint=(1, 0.5))
        add_btn.bind(on_press=self.show_add_city_popup)
        l.add_widget(add_btn)
        l.add_widget(Label(text="Add City", font_size=40, size_hint_y=None, height=60))
        self.add_widget(l)

        r = BoxLayout(orientation="vertical", size_hint=(0.5, 1))
        r.add_widget(Label(text="Remove Cities", font_size=40, size_hint_y=None, height=60))
        self.scroll = ScrollView()
        self.grid = GridLayout(cols=1, spacing=5, size_hint_y=None)
        self.grid.bind(minimum_height=self.grid.setter("height"))
        self.scroll.add_widget(self.grid)
        r.add_widget(self.scroll)
        self.add_widget(r)

        self.refresh_city_list()

    @property
    def cities(self):
        return self.cfg.setdefault("cities", [])

    def refresh_city_list(self):
        self.grid.clear_widgets()
        for c in self.cities:
            b = BoxLayout(orientation="horizontal", size_hint_y=None, height=60)
            lbl = Label(text=c["name"], font_size=32)
            btn = Button(text="X", size_hint_x=None, width=60, font_size=32)
            btn.bind(on_press=lambda i, cc=c: self.remove_city(cc))
            b.add_widget(lbl)
            b.add_widget(btn)
            self.grid.add_widget(b)

    def remove_city(self, c):
        if c in self.cities:
            self.cities.remove(c)
            config.save_config(self.cfg)

        for slide in list(self.carousel.slides):
            if isinstance(slide, WeatherCard) and slide.city == c:
                slide.cleanup()
                self.carousel.remove_widget(slide)
                break

        self.refresh_city_list()

    def show_add_city_popup(self, instance):
        limit = self.cfg.get("city_limit", 10)
        if len(self.cities) >= limit:
            self.show_warning_popup("City list is full. Cannot add more cities.")
            return

        layout = BoxLayout(orientation="vertical", spacing=10, padding=10)
        ti = TextInput(hint_text="Type city name", multiline=False, font_size=32, size_hint_y=None, height=50)
        btn = Button(text="Search", size_hint_y=None, height=50)
        layout.add_widget(ti)
        layout.add_widget(btn)
        popup = Popup(title="Add New City", content=layout, size_hint=(0.8, 0.5))
        popup.open()
        btn.bind(on_press=lambda i: self._search_city(ti, popup))

    def _search_city(self, ti, popup):
        api.search_city_async(
            ti.text.strip(),
            callback=lambda results: KivyClock.schedule_once(
                lambda dt: self._handle_search_results(results, ti, popup), 0
            ),
            error_callback=lambda exc: logger.error("Search error: %s", exc),
        )

    def _handle_search_results(self, results, ti, popup):
        if not popup.parent:
            return
        if results:
            popup.dismiss()
            self.show_city_choices(results)
        else:
            ti.text = ""
            ti.hint_text = "No matches found"

    def show_city_choices(self, results):
        layout = GridLayout(cols=1, spacing=5, size_hint_y=None)
        layout.bind(minimum_height=layout.setter("height"))
        for res in results:
            btn = Button(
                text=f"{res.get('name', '')}, {res.get('country', '')}",
                size_hint_y=None, height=60,
            )
            btn.bind(on_press=lambda i, r=res, b=btn: self._add_city(r, b))
            layout.add_widget(btn)
        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(layout)
        Popup(title="Select City", content=scroll, size_hint=(0.8, 0.6)).open()

    def _add_city(self, r, btn):
        try:
            limit = self.cfg.get("city_limit", 10)
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
            self.refresh_city_list()

        except Exception as exc:
            logger.error("Error in _add_city: %s", exc)
            self.show_warning_popup(f"Could not add city: {exc}")

    def show_warning_popup(self, message):
        layout = BoxLayout(orientation="vertical", spacing=10, padding=10)
        lbl = Label(text=message, font_size=32, size_hint_y=None, height=50)
        btn = Button(text="OK", size_hint_y=None, height=50)
        layout.add_widget(lbl)
        layout.add_widget(btn)
        popup = Popup(title="Warning", content=layout, size_hint=(0.8, 0.5))
        popup.open()
        btn.bind(on_press=popup.dismiss)


class ShutdownRebootTab(BoxLayout):
    def __init__(self, carousel=None, **kwargs):
        super().__init__(**kwargs)
        self.carousel = carousel
        self.orientation = "vertical"
        self.padding = 90
        self.spacing = 50

        self.current_network = None

        top_row = BoxLayout(size_hint_y=None, height=100)
        self.shutdown_button = Button(
            text="Shutdown", font_size=40, background_color=(1, 0, 0, 1),
            size_hint=(0.5, 1), pos_hint={"top": 1, "right": 1},
        )
        self.reboot_button = Button(
            text="Reboot", font_size=40, background_color=(0, 1, 0, 1),
            size_hint=(0.5, 1), pos_hint={"top": 1, "left": 0},
        )
        self.shutdown_button.bind(on_press=self.shutdown_device)
        self.reboot_button.bind(on_press=self.reboot_device)
        top_row.add_widget(self.reboot_button)
        top_row.add_widget(self.shutdown_button)
        self.add_widget(top_row)

        self.add_widget(BoxLayout())

        refresh_row = BoxLayout(size_hint_y=None, height=100)
        self.refresh_btn = Button(
            text="Refresh\n--:--",
            halign="center", valign="middle",
            size_hint=(0.3, 1),
        )
        self.refresh_btn.bind(size=self.refresh_btn.setter("text_size"))
        self.refresh_btn.bind(on_press=self.refresh_weather)
        refresh_row.add_widget(self.refresh_btn)
        refresh_row.add_widget(BoxLayout(size_hint=(0.7, 1)))
        self.add_widget(refresh_row)

        bottom_row = BoxLayout(size_hint_y=None, height=100)
        self.wifi_on = Button(text="Wi-Fi ON", size_hint=(0.3, 1), pos_hint={"bottom": 1, "left": 0})
        self.scan_btn = Button(text="Scan Networks", size_hint=(0.4, 1), pos_hint={"bottom": 1, "center_x": 0.5})
        self.wifi_off = Button(text="Wi-Fi OFF", size_hint=(0.3, 1), pos_hint={"bottom": 1, "right": 1})

        self.wifi_on.bind(on_press=lambda x: self.toggle_wifi(True))
        self.wifi_off.bind(on_press=lambda x: self.toggle_wifi(False))
        self.scan_btn.bind(on_press=self.show_networks_popup)

        bottom_row.add_widget(self.wifi_on)
        bottom_row.add_widget(self.scan_btn)
        bottom_row.add_widget(self.wifi_off)
        self.add_widget(bottom_row)

    def refresh_weather(self, instance):
        now = datetime.now().strftime("%H:%M")
        self.refresh_btn.text = f"Refresh\n{now}"
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

        system.scan_networks_async(
            callback=lambda nets: KivyClock.schedule_once(lambda dt: self._fill_networks(nets), 0)
        )
        system.get_current_network_async(
            callback=lambda net: KivyClock.schedule_once(lambda dt: self._set_current_net(net), 0)
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
            self._net_grid.add_widget(Label(text="No networks found"))

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

        popup = Popup(title="Network Options", content=content, size_hint=(0.8, 0.4))
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

    def show_popup(self, message):
        popup = Popup(title="Info", content=Label(text=message), size_hint=(0.6, 0.4))
        popup.open()
        KivyClock.schedule_once(lambda dt: popup.dismiss(), 2)


class BarWidget(Widget):
    """Single animated bar for the fake visualizer."""

    def __init__(self, **kw):
        super().__init__(**kw)
        with self.canvas:
            Color(0.15, 0.7, 0.35, 1)
            self.rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update, size=self._update)

    def _update(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


class FakeVisualizer(BoxLayout):
    """Procedural animated bar visualizer."""

    def __init__(self, player, **kw):
        super().__init__(**kw)
        self.player = player
        self.bars = []
        self.targets = []
        for _ in range(16):
            w = BarWidget()
            w.size_hint_y = 0.05
            self.add_widget(w)
            self.bars.append(w)
            self.targets.append(0.05)

        with self.canvas.before:
            Color(0.04, 0.04, 0.08, 1)
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        self._anim_event = KivyClock.schedule_interval(self._animate, 0.08)

    def _update_bg(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size

    def _animate(self, dt):
        if self.player.is_playing():
            for i, bar in enumerate(self.bars):
                target = random.uniform(0.08, 1.0)
                self.targets[i] = 0.78 * bar.size_hint_y + 0.22 * target
                bar.size_hint_y = self.targets[i]
        else:
            for bar in self.bars:
                bar.size_hint_y = 0.05

    def cleanup(self):
        if hasattr(self, "_anim_event") and self._anim_event:
            self._anim_event.cancel()
            self._anim_event = None


class RadioCard(BoxLayout):
    def __init__(self, carousel, player, cfg, **kw):
        super().__init__(orientation="horizontal", **kw)
        self.carousel = carousel
        self.player = player
        self.cfg = cfg
        self.padding = 15
        self.spacing = 10

        self._current_stations = []
        self._current_title = ""

        # ── Left Sidebar ──
        sidebar = BoxLayout(orientation="vertical", size_hint_x=0.22, spacing=8)

        # Search
        search_input_box = BoxLayout(orientation="horizontal", size_hint_y=None, height=50, spacing=5)
        self.search_input = TextInput(
            hint_text="Search stations...", multiline=False, font_size=18,
            size_hint=(0.75, 1),
        )
        self.search_btn = Button(text="Go", font_size=20, size_hint=(0.25, 1))
        self.search_btn.bind(on_press=self._do_search)
        search_input_box.add_widget(self.search_input)
        search_input_box.add_widget(self.search_btn)
        sidebar.add_widget(search_input_box)

        sidebar.add_widget(BoxLayout(size_hint_y=0.05))

        # Volume
        self.vol_up_btn = Button(text="Vol +", font_size=24, size_hint_y=None, height=55)
        self.vol_up_btn.bind(on_press=self._vol_up)
        sidebar.add_widget(self.vol_up_btn)

        self.vol_down_btn = Button(text="Vol -", font_size=24, size_hint_y=None, height=55)
        self.vol_down_btn.bind(on_press=self._vol_down)
        sidebar.add_widget(self.vol_down_btn)

        self.vol_label = Label(
            text="Vol: 80%", font_size=18, halign="center", valign="middle",
            color=(1, 1, 1, 1), size_hint_y=None, height=28,
        )
        self.vol_label.bind(size=self.vol_label.setter("text_size"))
        sidebar.add_widget(self.vol_label)

        sidebar.add_widget(BoxLayout(size_hint_y=0.05))

        # Stop
        self.stop_btn = Button(
            text="Stop", font_size=24, size_hint_y=None, height=55,
            background_color=(0.75, 0.15, 0.15, 1),
        )
        self.stop_btn.bind(on_press=self._stop)
        sidebar.add_widget(self.stop_btn)

        sidebar.add_widget(BoxLayout(size_hint_y=0.1))

        # Countries
        self.countries_btn = Button(text="Countries", font_size=20, size_hint_y=None, height=50)
        self.countries_btn.bind(on_press=self._show_continents)
        sidebar.add_widget(self.countries_btn)

        # Favorites
        self.fav_btn = Button(text="Favorites", font_size=20, size_hint_y=None, height=50)
        self.fav_btn.bind(on_press=self._show_favorites)
        sidebar.add_widget(self.fav_btn)

        sidebar.add_widget(BoxLayout())
        self.add_widget(sidebar)

        # ── Main Area ──
        main = BoxLayout(orientation="vertical", size_hint_x=0.78, spacing=6)

        # Station info
        info_box = RelativeLayout(size_hint_y=None, height=75)
        self.station_name_label = Label(
            text="Radio", font_size=30, halign="center", valign="bottom",
            color=(1, 1, 1, 1), bold=True,
            pos_hint={"center_x": 0.5, "center_y": 0.62},
        )
        self.station_name_label.bind(size=self.station_name_label.setter("text_size"))
        self.state_label = Label(
            text="Stopped", font_size=16, halign="center", valign="top",
            color=(0.6, 0.7, 0.8, 1),
            pos_hint={"center_x": 0.5, "center_y": 0.18},
        )
        self.state_label.bind(size=self.state_label.setter("text_size"))
        info_box.add_widget(self.station_name_label)
        info_box.add_widget(self.state_label)
        main.add_widget(info_box)

        # Visualizer
        self.visualizer = FakeVisualizer(player, size_hint_y=0.22)
        main.add_widget(self.visualizer)

        main.add_widget(BoxLayout(size_hint_y=0.02))

        # Section title
        self.section_title = Label(
            text="Favorites", font_size=20, halign="left", valign="middle",
            color=(0.75, 0.8, 0.9, 1), size_hint_y=None, height=28, bold=True,
        )
        self.section_title.bind(size=self.section_title.setter("text_size"))
        main.add_widget(self.section_title)

        # Station list
        self.results_scroll = ScrollView()
        self.results_grid = GridLayout(cols=1, spacing=3, size_hint_y=None)
        self.results_grid.bind(minimum_height=self.results_grid.setter("height"))
        self.results_scroll.add_widget(self.results_grid)
        main.add_widget(self.results_scroll)

        self.add_widget(main)

        # Poll state
        self._poll_event = KivyClock.schedule_interval(self._poll_state, 1)

        # Show favorites by default
        self._show_favorites()

    # ── Search ──
    def _do_search(self, instance):
        name = self.search_input.text.strip()
        if not name:
            return
        self._set_loading(True)

        def _worker():
            try:
                results = radio_api.search_stations(name, limit=30)
                KivyClock.schedule_once(
                    lambda dt: self._show_stations(results, f"Search: {name}"), 0
                )
            except Exception as exc:
                logger.error("Search error: %s", exc)
                KivyClock.schedule_once(
                    lambda dt: self._show_stations([], f"Search: {name}"), 0
                )
        import threading
        threading.Thread(target=_worker, daemon=True).start()

    # ── Volume ──
    def _vol_up(self, instance):
        v = self.player.get_volume() + 10
        self.player.set_volume(v)
        self.vol_label.text = f"Vol: {self.player.get_volume()}%"

    def _vol_down(self, instance):
        v = self.player.get_volume() - 10
        self.player.set_volume(v)
        self.vol_label.text = f"Vol: {self.player.get_volume()}%"

    def _stop(self, instance):
        self.player.stop()
        self._update_info()
        app = App.get_running_app()
        if app and hasattr(app, "_update_radio_indicator"):
            app._update_radio_indicator()

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
                btn.bind(on_press=lambda inst, cc=c["code"]: self._on_country(cc))
                layout.add_widget(btn)
        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(layout)
        popup = Popup(
            title=f"{continent} — Select Country", content=scroll, size_hint=(0.7, 0.75)
        )
        popup.open()

    def _on_country(self, country_code):
        self._set_loading(True)

        def _worker():
            try:
                results = radio_api.get_stations_by_country(country_code, limit=30)
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
            self._show_stations(list(self._current_stations), self._current_title)

    # ── Station list builder ──
    def _show_stations(self, stations, title=""):
        self._current_stations = list(stations)
        self._current_title = title
        self._set_loading(False)
        self.section_title.text = title if title else "Stations"
        self.results_grid.clear_widgets()
        if not stations:
            self.results_grid.add_widget(
                Label(text="No stations", font_size=20, size_hint_y=None, height=50)
            )
            return
        for s in stations:
            row = BoxLayout(
                orientation="horizontal", size_hint_y=None, height=50, spacing=4
            )

            play_btn = Button(text="▶", font_size=20, size_hint_x=None, width=45)
            play_btn.bind(on_press=lambda inst, st=s: self._play_station(st))

            name = s.get("name", "Unknown")
            if len(name) > 34:
                name = name[:31] + "..."
            info = (
                f"{name}  |  {s.get('country', '')}  |  "
                f"{s.get('bitrate', 0)}k {s.get('codec', '')}"
            )
            name_lbl = Label(
                text=info,
                font_size=15,
                halign="left",
                valign="middle",
                color=(1, 1, 1, 1),
                size_hint_x=0.8,
            )
            name_lbl.bind(size=name_lbl.setter("text_size"))

            heart = "♥" if self._is_favorite(s.get("stationuuid")) else "♡"
            fav_btn = Button(
                text=heart,
                font_size=22,
                size_hint_x=None,
                width=45,
                color=(1, 0.3, 0.3, 1) if heart == "♥" else (0.7, 0.7, 0.7, 1),
            )
            fav_btn.bind(on_press=lambda inst, st=s: self._toggle_favorite_and_refresh(st))

            row.add_widget(play_btn)
            row.add_widget(name_lbl)
            row.add_widget(fav_btn)
            self.results_grid.add_widget(row)

    def _play_station(self, station):
        self.player.play(station["url"], station["name"])
        self._update_info()
        app = App.get_running_app()
        if app and hasattr(app, "_update_radio_indicator"):
            app._update_radio_indicator()

    def _update_info(self):
        if self.player.current_name:
            self.station_name_label.text = (
                self.player.current_name[:30]
                if len(self.player.current_name) > 30
                else self.player.current_name
            )
            if self.player.is_playing():
                self.state_label.text = "Playing"
            else:
                self.state_label.text = "Buffering..."
        else:
            self.station_name_label.text = "Radio"
            self.state_label.text = "Stopped"

    def _set_loading(self, loading):
        if loading:
            self.section_title.text = "Loading..."

    def _poll_state(self, dt):
        self._update_info()

    def cleanup(self):
        if hasattr(self, "_poll_event") and self._poll_event:
            self._poll_event.cancel()
            self._poll_event = None
        if hasattr(self, "visualizer") and self.visualizer:
            self.visualizer.cleanup()


class WeatherDisplayApp(App):
    def build(self):
        Window.clearcolor = (0.05, 0.05, 0.2, 1)
        self.cfg = config.load_config()
        self.root_layout = FloatLayout()
        self.carousel = Carousel(direction="right", size_hint=(1, 1), pos_hint={"x": 0, "y": 0})
        self.root_layout.add_widget(self.carousel)

        self.locked = False
        self.lock_label = None
        self.last_touch_time = 0

        # Radio player (singleton, shared across cards)
        self.radio_player = RadioPlayer()

        self.carousel.add_widget(PhotoSlide(self.cfg))
        self.carousel.add_widget(ClockSlide(self.carousel))
        self.carousel.add_widget(RadioCard(self.carousel, self.radio_player, self.cfg))

        for cit in self.cfg.get("cities", []):
            self.carousel.add_widget(WeatherCard(cit, self.cfg))

        self.carousel.add_widget(ManageCitiesCard(self.carousel, self.cfg))
        self.carousel.add_widget(ShutdownRebootTab(self.carousel))

        # Background radio indicator (visible when playing on other slides)
        self.radio_indicator = Button(
            text="",
            font_size=18,
            size_hint=(None, None),
            size=(260, 38),
            pos_hint={"right": 0.99, "top": 0.98},
            background_color=(0.1, 0.35, 0.1, 0.75),
            color=(1, 1, 1, 1),
            opacity=0,
        )
        self.radio_indicator.bind(on_press=self._goto_radio_card)
        self.root_layout.add_widget(self.radio_indicator)

        # Auto-switch to first weather card after startup
        def _goto_weather(dt):
            for i, slide in enumerate(self.carousel.slides):
                if isinstance(slide, WeatherCard):
                    self.carousel.load_slide(self.carousel.slides[i])
                    break
        KivyClock.schedule_once(_goto_weather, 1.5)

        # Poll radio state for background indicator
        KivyClock.schedule_interval(self._update_radio_indicator, 2)

        Window.bind(on_touch_down=self.on_touch_down)

        return self.root_layout

    def on_stop(self):
        """Clean up VLC on app exit."""
        if hasattr(self, "radio_player") and self.radio_player:
            self.radio_player.stop()
            self.radio_player.cleanup()

    def _goto_radio_card(self, instance=None):
        for i, slide in enumerate(self.carousel.slides):
            if isinstance(slide, RadioCard):
                self.carousel.load_slide(self.carousel.slides[i])
                break

    def _update_radio_indicator(self, dt=None):
        if self.radio_player.is_playing() and self.radio_player.current_name:
            name = self.radio_player.current_name
            if len(name) > 22:
                name = name[:19] + "..."
            self.radio_indicator.text = f"▶ {name}"
            self.radio_indicator.opacity = 1
        else:
            self.radio_indicator.opacity = 0

    def on_touch_down(self, window, touch):
        if isinstance(self.carousel.slides[self.carousel.index], ManageCitiesCard):
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
