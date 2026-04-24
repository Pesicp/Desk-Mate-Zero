"""Radio Browser API wrapper — free internet radio directory."""

import logging
import random
import socket
import urllib.parse

import requests

logger = logging.getLogger(__name__)
_TIMEOUT = 8
_USER_AGENT = "DeskMate-Zero/1.0"

# Cache for country list (valid for the session)
_countries_cache = None

COUNTRY_TO_CONTINENT = {
    # Europe
    "AL": "Europe", "AD": "Europe", "AT": "Europe", "BY": "Europe", "BE": "Europe",
    "BA": "Europe", "BG": "Europe", "HR": "Europe", "CY": "Europe", "CZ": "Europe",
    "DK": "Europe", "EE": "Europe", "FI": "Europe", "FR": "Europe", "DE": "Europe",
    "GR": "Europe", "HU": "Europe", "IS": "Europe", "IE": "Europe", "IT": "Europe",
    "LV": "Europe", "LI": "Europe", "LT": "Europe", "LU": "Europe", "MT": "Europe",
    "MD": "Europe", "MC": "Europe", "ME": "Europe", "NL": "Europe", "NO": "Europe",
    "PL": "Europe", "PT": "Europe", "RO": "Europe", "RU": "Europe", "SM": "Europe",
    "RS": "Europe", "SK": "Europe", "SI": "Europe", "ES": "Europe", "SE": "Europe",
    "CH": "Europe", "UA": "Europe", "GB": "Europe", "VA": "Europe", "XK": "Europe",
    "MK": "Europe", "IM": "Europe", "JE": "Europe", "AX": "Europe", "FO": "Europe",
    "GI": "Europe", "GG": "Europe", "SJ": "Europe",
    # Asia
    "AF": "Asia", "AM": "Asia", "AZ": "Asia", "BH": "Asia", "BD": "Asia",
    "BT": "Asia", "BN": "Asia", "KH": "Asia", "CN": "Asia", "GE": "Asia",
    "IN": "Asia", "ID": "Asia", "IR": "Asia", "IQ": "Asia", "IL": "Asia",
    "JP": "Asia", "JO": "Asia", "KZ": "Asia", "KW": "Asia", "KG": "Asia",
    "LA": "Asia", "LB": "Asia", "MY": "Asia", "MV": "Asia", "MN": "Asia",
    "MM": "Asia", "NP": "Asia", "KP": "Asia", "OM": "Asia", "PK": "Asia",
    "PS": "Asia", "PH": "Asia", "QA": "Asia", "SA": "Asia", "SG": "Asia",
    "KR": "Asia", "LK": "Asia", "SY": "Asia", "TW": "Asia", "TJ": "Asia",
    "TH": "Asia", "TL": "Asia", "TR": "Asia", "TM": "Asia", "AE": "Asia",
    "UZ": "Asia", "VN": "Asia", "YE": "Asia", "HK": "Asia", "MO": "Asia", "IO": "Asia",
    # North America
    "AG": "North America", "BS": "North America", "BB": "North America",
    "BZ": "North America", "CA": "North America", "CR": "North America",
    "CU": "North America", "DM": "North America", "DO": "North America",
    "SV": "North America", "GD": "North America", "GT": "North America",
    "HT": "North America", "HN": "North America", "JM": "North America",
    "MX": "North America", "NI": "North America", "PA": "North America",
    "KN": "North America", "LC": "North America", "VC": "North America",
    "TT": "North America", "US": "North America", "AI": "North America", "AW": "North America", "BM": "North America", "BQ": "North America", "CW": "North America", "GL": "North America", "GP": "North America", "KY": "North America", "MQ": "North America", "MS": "North America", "PM": "North America", "PR": "North America", "TC": "North America", "VG": "North America", "VI": "North America",
    # South America
    "AR": "South America", "BO": "South America", "BR": "South America",
    "CL": "South America", "CO": "South America", "EC": "South America",
    "FK": "South America", "GF": "South America", "GY": "South America",
    "PY": "South America", "PE": "South America", "SR": "South America",
    "UY": "South America", "VE": "South America",
    # Africa
    "DZ": "Africa", "AO": "Africa", "BJ": "Africa", "BW": "Africa", "BF": "Africa",
    "BI": "Africa", "CM": "Africa", "CV": "Africa", "CF": "Africa", "TD": "Africa",
    "KM": "Africa", "CD": "Africa", "CG": "Africa", "CI": "Africa", "DJ": "Africa",
    "EG": "Africa", "GQ": "Africa", "ER": "Africa", "SZ": "Africa", "ET": "Africa",
    "GA": "Africa", "GM": "Africa", "GH": "Africa", "GN": "Africa", "GW": "Africa",
    "KE": "Africa", "LS": "Africa", "LR": "Africa", "LY": "Africa", "MG": "Africa",
    "MW": "Africa", "ML": "Africa", "MR": "Africa", "MU": "Africa", "MA": "Africa",
    "MZ": "Africa", "NA": "Africa", "NE": "Africa", "NG": "Africa", "RW": "Africa",
    "ST": "Africa", "SN": "Africa", "SC": "Africa", "SL": "Africa", "SO": "Africa",
    "ZA": "Africa", "SS": "Africa", "SD": "Africa", "TZ": "Africa", "TG": "Africa",
    "TN": "Africa", "UG": "Africa", "ZM": "Africa", "ZW": "Africa", "RE": "Africa", "YT": "Africa", "SH": "Africa",
    # Oceania
    "AU": "Oceania", "FJ": "Oceania", "KI": "Oceania", "MH": "Oceania",
    "FM": "Oceania", "NR": "Oceania", "NZ": "Oceania", "PW": "Oceania",
    "PG": "Oceania", "WS": "Oceania", "SB": "Oceania", "TO": "Oceania",
    "TV": "Oceania", "VU": "Oceania", "AS": "Oceania", "CX": "Oceania", "CC": "Oceania", "CK": "Oceania", "NC": "Oceania", "NU": "Oceania", "PF": "Oceania", "WF": "Oceania", "GU": "Oceania", "UM": "Oceania",
    # Antarctica
    "AQ": "Antarctica", "TF": "Antarctica",
}

CONTINENTS = [
    "Africa", "Antarctica", "Asia", "Europe", "North America", "Oceania", "South America",
]


def _discover_server():
    """Return a working Radio Browser API server hostname."""
    try:
        _, _, ips = socket.gethostbyname_ex("all.api.radio-browser.info")
        if ips:
            servers = []
            for ip in ips:
                try:
                    hostname = socket.gethostbyaddr(ip)[0]
                    servers.append(hostname)
                except OSError:
                    pass
            if servers:
                random.shuffle(servers)
                return servers[0]
    except Exception as exc:
        logger.warning("Radio Browser server discovery failed: %s", exc)
    fallbacks = [
        "de1.api.radio-browser.info",
        "nl1.api.radio-browser.info",
        "fr1.api.radio-browser.info",
    ]
    return random.choice(fallbacks)


def _get_base_url():
    server = _discover_server()
    return f"https://{server}"


def search_stations(name: str, limit: int = None):
    """Search stations across all fields (name, tags, etc.)."""
    if not name or not name.strip():
        return []
    base = _get_base_url()
    query = urllib.parse.quote(name.strip())
    url = f"{base}/json/stations/search?name={query}&hidebroken=true"
    if limit:
        url += f"&limit={limit}"
    try:
        resp = requests.get(
            url, timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT}
        )
        resp.raise_for_status()
        data = resp.json()
        return _normalize_stations(data)
    except Exception as exc:
        logger.warning("Radio search failed: %s", exc)
        return []


def get_top_stations(country_code: str, limit: int = None):
    """Get top stations by click count for a country code (e.g. 'US', 'DE')."""
    cc = (country_code or "").strip().upper()
    if not cc:
        return []
    base = _get_base_url()
    url = (
        f"{base}/json/stations/search"
        f"?countrycode={cc}"
        f"&order=clickcount&reverse=true"
        f"&hidebroken=true"
    )
    if limit:
        url += f"&limit={limit}"
    try:
        resp = requests.get(
            url, timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT}
        )
        resp.raise_for_status()
        data = resp.json()
        return _normalize_stations(data)
    except Exception as exc:
        logger.warning("Radio top stations failed: %s", exc)
        return []


def get_stations_by_country(country_code: str, limit: int = None):
    """Alias for get_top_stations with a clearer name."""
    return get_top_stations(country_code, limit)


def get_countries():
    """Fetch all countries with station counts from Radio Browser. Cached per session."""
    global _countries_cache
    if _countries_cache is not None:
        return _countries_cache

    base = _get_base_url()
    url = f"{base}/json/countries"
    try:
        resp = requests.get(
            url, timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT}
        )
        resp.raise_for_status()
        data = resp.json()
        result = []
        for c in data:
            cc = (c.get("iso_3166_1") or "").upper()
            if not cc:
                continue
            result.append(
                {
                    "name": c.get("name", "Unknown"),
                    "code": cc,
                    "stationcount": c.get("stationcount", 0),
                    "continent": COUNTRY_TO_CONTINENT.get(cc, "Other"),
                }
            )
        # Sort by name
        result.sort(key=lambda x: x["name"])
        _countries_cache = result
        return result
    except Exception as exc:
        logger.warning("Country list fetch failed: %s", exc)
        return []


def _normalize_stations(raw_list):
    """Extract relevant fields from Radio Browser response."""
    result = []
    for s in raw_list:
        url = s.get("url_resolved") or s.get("url")
        if not url:
            continue
        result.append(
            {
                "name": (s.get("name") or "Unknown").strip(),
                "url": url,
                "codec": (s.get("codec") or "MP3").upper(),
                "bitrate": s.get("bitrate", 0),
                "country": s.get("country", ""),
                "countrycode": s.get("countrycode", ""),
                "tags": s.get("tags", ""),
                "stationuuid": s.get("stationuuid", ""),
            }
        )
    return result
