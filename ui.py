"""All Kivy UI widgets for DeskMate Zero."""

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
from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.carousel import Carousel
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

import api
import config
import system

logger = logging.getLogger(__name__)

_CFG = config.load_config()
_ICON_PATH = config.get_icon_path(_CFG)

WEATHER_ICON = {
    0: "01", 1: "01", 2: "02", 3: "03", 45: "50", 48: "50",
    51: "09", 53: "09", 55: "09", 61: "10", 63: "10", 65: "10",
    71: "13", 73: "13", 75: "13", 95: "11", 96: "11", 99: "11",
    80: "10", 81: "10", 82: "10",
}

WEATHER_DESC = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
    55: "Heavy drizzle", 61: "Light rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Light snow", 73: "Moderate snow", 75: "Heavy snow",
    95: "Thunderstorm", 96: "Thunderstorm + hail", 99: "Thunderstorm + hail",
    80: "Rain showers: slight", 81: "Rain showers: moderate", 82: "Rain showers: violent",
}


def _icon_file(code: int, daynight: str = "d") -> str:
    """Return path to weather icon, falling back to 01d."""
    name = WEATHER_ICON.get(code, "01") + daynight + ".png"
    path = _ICON_PATH / name
    if path.exists():
        return str(path)
    return str(_ICON_PATH / "01d.png")


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
        self.last_forecast = []
        self.timezone = ZoneInfo(city.get("timezone", "UTC"))
        self.time_offset = datetime.now(self.timezone).utcoffset()
        self.padding = [10] * 4
        self.spacing = 10

        top = BoxLayout(orientation="horizontal", size_hint_y=None, height=200, spacing=5)
        self.today_icon = Image(
            size_hint=(None, None), size=(140, 160),
            allow_stretch=True, keep_ratio=True,
        )
        top.add_widget(self.today_icon)

        ci = BoxLayout(orientation="vertical", size_hint=(None, 1), width=300)
        self.city_label = Label(text=city["name"], font_size=50, size_hint_y=None, height=80)
        self.temp_label = Label(font_size=40, size_hint_y=None, height=30)
        self.code_label = Label(font_size=26, size_hint_y=None, height=50)

        update_box = BoxLayout(orientation="horizontal", size_hint_y=None, height=30, spacing=5)
        self.update_label = Label(font_size=20)
        refresh_btn = Button(
            text="R", size_hint=(None, 1), width=50, font_size=20,
            background_color=(0.5, 0.5, 0.5, 1), color=(1, 1, 1, 1),
        )
        refresh_btn.bind(on_press=lambda i: self.update_weather_async())
        update_box.add_widget(self.update_label)
        update_box.add_widget(refresh_btn)

        for w in (self.city_label, self.temp_label, self.code_label, update_box):
            ci.add_widget(w)
        top.add_widget(ci)
        top.add_widget(BoxLayout(size_hint_x=1))

        clock_box = BoxLayout(orientation="vertical", size_hint=(None, 1), width=200, spacing=5)
        self.clock_label = Label(font_size=80)
        self.date_label = Label(font_size=30)
        clock_box.add_widget(BoxLayout(size_hint_y=2))
        clock_box.add_widget(Label(size_hint_y=None, height=2))
        clock_box.add_widget(self.clock_label)
        clock_box.add_widget(Label(size_hint_y=None, height=20))
        clock_box.add_widget(self.date_label)
        clock_box.add_widget(BoxLayout(size_hint_y=1))
        top.add_widget(clock_box)

        self.add_widget(top)
        self.add_widget(BoxLayout(size_hint_y=1))

        self.hourly_box = ScrollView(
            size_hint_y=None, height=130,
            do_scroll_x=False, do_scroll_y=False,
        )
        self.hourly_layout = BoxLayout(
            orientation="horizontal", size_hint_x=None, spacing=5,
        )
        self.hourly_layout.bind(minimum_width=self.hourly_layout.setter("width"))
        self.hourly_box.add_widget(self.hourly_layout)
        self.add_widget(self.hourly_box)

        self.forecast_box = BoxLayout(orientation="horizontal", size_hint_y=None, height=150)
        self.add_widget(self.forecast_box)

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
                now = datetime.now(self.timezone)
                self.time_offset = now.utcoffset()
            except OSError:
                utc_now = datetime.now(timezone.utc)
                now = utc_now + self.time_offset
            self.clock_label.text = now.strftime("%H:%M")
            self.date_label.text = now.strftime("%A, %d.%m")
        except Exception as exc:
            logger.error("Clock update error for %s: %s", self.city.get("name"), exc)
            try:
                utc_now = datetime.now(timezone.utc)
                now = utc_now + self.time_offset
                self.clock_label.text = now.strftime("%H:%M")
                self.date_label.text = now.strftime("%A, %d.%m")
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
            self.update_label.opacity = 1
            self.clock_label.opacity = 1
            self.date_label.opacity = 1
            self.hourly_box.opacity = 1
            self.forecast_box.opacity = 1
        else:
            self.temp_label.opacity = 0
            self.code_label.opacity = 0
            self.update_label.opacity = 1
            self.clock_label.opacity = 1
            self.date_label.opacity = 1
            self.hourly_box.opacity = 0
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
        if daily:
            self.last_forecast = daily
            today = daily[0]
            cur_code = current.get("weathercode", today.get("weathercode", 0))
            cur_temp = current.get("temperature", today.get("temp_max", ""))
        else:
            today = {}
            cur_code = 0
            cur_temp = ""

        current_time = datetime.now(self.timezone).hour
        dn = "d" if 6 <= current_time < 18 else "n"
        self.today_icon.source = _icon_file(cur_code, dn)

        self.temp_label.text = f"{int(cur_temp)}°C" if isinstance(cur_temp, (int, float)) else str(cur_temp)
        self.code_label.text = WEATHER_DESC.get(cur_code, f"Code {cur_code}")
        self.update_label.text = f"Updated at: {datetime.now(self.timezone).strftime('%H:%M')}"

        # Hourly forecast
        self.hourly_layout.clear_widgets()
        now = datetime.now(self.timezone)
        start_index = 0
        for i, hh in enumerate(hourly):
            if "time" in hh:
                dt = datetime.fromisoformat(hh["time"]).replace(tzinfo=self.timezone)
                if dt > now:
                    start_index = i
                    break

        for hh in hourly[start_index:start_index + 9]:
            if "time" not in hh:
                continue
            dt = datetime.fromisoformat(hh["time"]).replace(tzinfo=self.timezone)
            b = BoxLayout(orientation="vertical", size_hint=(None, 1), width=80)
            hh_hour = dt.hour
            ip = _icon_file(hh["weathercode"], "d" if 6 <= hh_hour < 18 else "n")
            b.add_widget(Label(text=f"{int(hh['temp'])}°C", size_hint_y=None, height=40, font_size=16))
            b.add_widget(Image(source=ip, size_hint_y=None, height=70, allow_stretch=True, keep_ratio=True))
            b.add_widget(Label(text=dt.strftime("%H:%M"), size_hint_y=None, height=30, font_size=16))
            self.hourly_layout.add_widget(b)

        # 5-day forecast
        self.forecast_box.clear_widgets()
        for d in daily:
            dt = datetime.strptime(d["date"], "%Y-%m-%d")
            b = BoxLayout(orientation="vertical", size_hint=(1, 1))
            ip = _icon_file(d["weathercode"], "d")
            b.add_widget(Image(source=ip, size_hint_y=None, height=100, allow_stretch=True, keep_ratio=True))
            b.add_widget(Label(text=dt.strftime("%a"), size_hint_y=None, height=30))
            b.add_widget(Label(text=f"{int(d['temp_max'])}°C/{int(d['temp_min'])}°C", size_hint_y=None, height=30))
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
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
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

        self.carousel.add_widget(PhotoSlide(self.cfg))
        self.carousel.add_widget(ClockSlide(self.carousel))

        for cit in self.cfg.get("cities", []):
            self.carousel.add_widget(WeatherCard(cit, self.cfg))

        self.carousel.add_widget(ManageCitiesCard(self.carousel, self.cfg))
        self.carousel.add_widget(ShutdownRebootTab())

        Window.bind(on_touch_down=self.on_touch_down)

        return self.root_layout

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
