"""Open-Meteo API client with threaded helpers."""

import logging
import threading
import urllib.parse
from typing import Callable

import requests

logger = logging.getLogger(__name__)

_BASE_FORECAST = "https://api.open-meteo.com/v1/forecast"
_BASE_GEO = "https://geocoding-api.open-meteo.com/v1/search"
_TIMEOUT = 5


def fetch_forecast(lat: float, lon: float):
    """Return (daily_list, current_dict, hourly_list, timezone_str)."""
    url = (
        f"{_BASE_FORECAST}?latitude={lat}&longitude={lon}"
        "&hourly=temperature_2m,weathercode"
        "&daily=temperature_2m_max,temperature_2m_min,weathercode,sunrise,sunset"
        "&current_weather=true&timezone=auto"
    )
    try:
        resp = requests.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("Forecast fetch failed: %s", exc)
        return [], {}, [], "UTC"

    current = data.get("current_weather", {})
    tz = data.get("timezone", "UTC")

    daily = []
    for i, d in enumerate(data.get("daily", {}).get("time", [])[:5]):
        daily.append(
            {
                "date": d,
                "temp_max": data["daily"]["temperature_2m_max"][i],
                "temp_min": data["daily"]["temperature_2m_min"][i],
                "weathercode": data["daily"]["weathercode"][i],
                "sunrise": data["daily"]["sunrise"][i],
                "sunset": data["daily"]["sunset"][i],
            }
        )

    hourly = []
    hourly_times = data.get("hourly", {}).get("time", [])
    hourly_temps = data.get("hourly", {}).get("temperature_2m", [])
    hourly_codes = data.get("hourly", {}).get("weathercode", [])
    for i in range(len(hourly_times)):
        hourly.append(
            {
                "time": hourly_times[i],
                "temp": hourly_temps[i],
                "weathercode": hourly_codes[i],
            }
        )

    return daily, current, hourly, tz


def fetch_forecast_async(
    lat: float, lon: float, callback: Callable, error_callback: Callable = None
):
    """Run fetch_forecast in a background thread."""

    def _worker():
        try:
            result = fetch_forecast(lat, lon)
            callback(result)
        except Exception as exc:
            logger.error("Async forecast error: %s", exc)
            if error_callback:
                error_callback(exc)

    threading.Thread(target=_worker, daemon=True).start()


def search_city(name: str):
    """Return list of geocoding results."""
    if not name or not name.strip():
        return []
    query = urllib.parse.quote(name.strip())
    url = f"{_BASE_GEO}?name={query}&count=5"
    try:
        resp = requests.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception as exc:
        logger.warning("City search failed: %s", exc)
        return []


def search_city_async(
    name: str, callback: Callable, error_callback: Callable = None
):
    """Run search_city in a background thread."""

    def _worker():
        try:
            result = search_city(name)
            callback(result)
        except Exception as exc:
            logger.error("Async city search error: %s", exc)
            if error_callback:
                error_callback(exc)

    threading.Thread(target=_worker, daemon=True).start()
