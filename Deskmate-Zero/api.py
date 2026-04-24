"""Open-Meteo API client with threaded helpers, deduplication, and caching."""

import logging
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import requests

logger = logging.getLogger(__name__)

_BASE_FORECAST = "https://api.open-meteo.com/v1/forecast"
_BASE_GEO = "https://geocoding-api.open-meteo.com/v1/search"
_TIMEOUT = 5

# Thread pool limits concurrent API workers
_executor = ThreadPoolExecutor(max_workers=4)

# In-flight request tracking: key -> {"futures": [Future, ...], "lock": Lock}
_inflight = {}
_inflight_lock = threading.Lock()

# Response caches: key -> (timestamp, result)
_forecast_cache = {}
_search_cache = {}
_FORECAST_TTL = 600   # 10 minutes
_SEARCH_TTL = 300     # 5 minutes
_cache_lock = threading.Lock()


def clear_cache():
    """Clear all API response caches."""
    global _forecast_cache, _search_cache
    with _cache_lock:
        _forecast_cache.clear()
        _search_cache.clear()
    logger.info("API caches cleared")


def _get_inflight(key):
    """Return the in-flight entry for key, creating it if necessary."""
    with _inflight_lock:
        if key not in _inflight:
            _inflight[key] = {"callbacks": [], "lock": threading.Lock()}
        return _inflight[key]


def _run_callbacks(entry, result, exc):
    """Call all queued callbacks for an in-flight request."""
    with entry["lock"]:
        cbs = entry["callbacks"][:]
        entry["callbacks"] = []
    for callback, error_callback in cbs:
        if exc is not None:
            logger.error("Async forecast error: %s", exc)
            if error_callback:
                error_callback(exc)
        else:
            callback(result)


def _clear_inflight(key):
    """Remove in-flight tracking entry."""
    with _inflight_lock:
        _inflight.pop(key, None)


def _get_cached(cache, key, ttl):
    """Return cached result if still valid, else None."""
    with _cache_lock:
        if key in cache:
            ts, result = cache[key]
            if time.time() - ts < ttl:
                return result
            del cache[key]
    return None


def _set_cached(cache, key, result):
    """Store result in cache with current timestamp."""
    with _cache_lock:
        cache[key] = (time.time(), result)


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
    """Run fetch_forecast in a background thread with deduplication and caching."""
    key = ("forecast", lat, lon)

    # Check cache first
    cached = _get_cached(_forecast_cache, key, _FORECAST_TTL)
    if cached is not None:
        callback(cached)
        return

    entry = _get_inflight(key)

    with entry["lock"]:
        # If already in flight, queue callback and return
        if entry["callbacks"]:
            entry["callbacks"].append((callback, error_callback))
            return
        # We are the first caller for this key
        entry["callbacks"].append((callback, error_callback))

    def _worker():
        try:
            result = fetch_forecast(lat, lon)
            _set_cached(_forecast_cache, key, result)
            _run_callbacks(entry, result, None)
        except Exception as exc:
            _run_callbacks(entry, None, exc)
        finally:
            _clear_inflight(key)

    _executor.submit(_worker)


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
    """Run search_city in a background thread with deduplication and caching."""
    key = ("search", name.strip().lower())

    cached = _get_cached(_search_cache, key, _SEARCH_TTL)
    if cached is not None:
        callback(cached)
        return

    entry = _get_inflight(key)

    with entry["lock"]:
        if entry["callbacks"]:
            entry["callbacks"].append((callback, error_callback))
            return
        entry["callbacks"].append((callback, error_callback))

    def _worker():
        try:
            result = search_city(name)
            _set_cached(_search_cache, key, result)
            _run_callbacks(entry, result, None)
        except Exception as exc:
            _run_callbacks(entry, None, exc)
        finally:
            _clear_inflight(key)

    _executor.submit(_worker)
