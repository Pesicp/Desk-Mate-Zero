#!/usr/bin/env python3
"""Download Meteocons static SVGs and convert to high-res PNGs for WMO weather codes."""

import shutil
import urllib.request
from pathlib import Path

try:
    from cairosvg import svg2png
except ImportError:
    print("cairosvg not installed. Run: pip install cairosvg")
    raise

BASE_DIR = Path("/home/rpi/weather_app")
ICON_DIR = BASE_DIR / "weather_icons"
ICON_DIR.mkdir(parents=True, exist_ok=True)

CDN_BASE = "https://unpkg.com/@meteocons/svg-static@latest/fill"
PNG_SIZE = 512  # High-res for crisp display

# WMO code -> Meteocons icon slug mapping
# codes that share a slug will get copied after download
WMO_TO_METEOCONS = {
    0:  ("clear-day", "clear-night"),
    1:  ("clear-day", "clear-night"),
    2:  ("partly-cloudy-day", "partly-cloudy-night"),
    3:  ("overcast", None),
    45: ("fog-day", "fog-night"),
    48: ("fog-day", "fog-night"),
    51: ("drizzle", None),
    53: ("drizzle", None),
    55: ("drizzle", None),
    56: ("sleet", None),
    57: ("sleet", None),
    61: ("rain", None),
    63: ("rain", None),
    65: ("rain", None),
    66: ("sleet", None),
    67: ("sleet", None),
    71: ("snow", None),
    73: ("snow", None),
    75: ("snow", None),
    77: ("snow", None),
    80: ("rain", None),
    81: ("rain", None),
    82: ("rain", None),
    85: ("snow", None),
    86: ("snow", None),
    95: ("thunderstorms", None),
    96: ("thunderstorms-extreme", None),
    99: ("thunderstorms-extreme", None),
}


def download_svg(slug: str) -> bytes:
    url = f"{CDN_BASE}/{slug}.svg"
    print(f"  Downloading {slug}.svg ...")
    req = urllib.request.Request(url, headers={"User-Agent": "DeskMate-Zero/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def convert_to_png(svg_bytes: bytes, out_path: Path):
    svg2png(bytestring=svg_bytes, write_to=str(out_path), output_width=PNG_SIZE, output_height=PNG_SIZE)


def main():
    print("Setting up Meteocons weather icons...")
    print(f"Target folder: {ICON_DIR}")
    print(f"PNG size: {PNG_SIZE}x{PNG_SIZE}")
    print()

    # Remove old OWM-style files and broken low-quality copies
    old_patterns = ["01*.png", "02*.png", "04*.png", "09*.png", "10*.png", "11*.png", "13*.png", "50*.png"]
    for pattern in old_patterns:
        for f in ICON_DIR.glob(pattern):
            print(f"  Removing old file: {f.name}")
            f.unlink()

    # Also remove any small file (< 5 KB) that might be a leftover low-quality copy
    for f in ICON_DIR.glob("*.png"):
        if f.stat().st_size < 5000:
            print(f"  Removing low-res leftover: {f.name}")
            f.unlink()

    # Track downloaded SVGs to avoid re-downloading
    svg_cache = {}
    rendered = {}  # slug -> Path to rendered PNG

    # First pass: download unique SVGs and render once per slug
    unique_slugs = set()
    for day_slug, night_slug in WMO_TO_METEOCONS.values():
        if day_slug:
            unique_slugs.add(day_slug)
        if night_slug:
            unique_slugs.add(night_slug)

    for slug in sorted(unique_slugs):
        try:
            svg_bytes = download_svg(slug)
            svg_cache[slug] = svg_bytes
            # Render to a temp path first
            tmp_path = ICON_DIR / f"_tmp_{slug}.png"
            convert_to_png(svg_bytes, tmp_path)
            rendered[slug] = tmp_path
            print(f"  Rendered {slug}.png")
        except Exception as exc:
            print(f"  ERROR downloading {slug}: {exc}")

    # Second pass: copy rendered PNGs to all WMO codes that use them
    for code, (day_slug, night_slug) in WMO_TO_METEOCONS.items():
        # Day variant
        if day_slug and day_slug in rendered:
            src = rendered[day_slug]
            # Primary code gets the original render
            # Other codes get copies
            dst = ICON_DIR / f"{code}d.png"
            shutil.copy(src, dst)
            print(f"  -> {dst.name}")

        # Night variant
        if night_slug and night_slug in rendered:
            src = rendered[night_slug]
            dst = ICON_DIR / f"{code}n.png"
            shutil.copy(src, dst)
            print(f"  -> {dst.name}")
        elif night_slug is None and day_slug in rendered:
            # No night variant available: copy day as generic fallback
            src = rendered[day_slug]
            generic = ICON_DIR / f"{code}.png"
            shutil.copy(src, generic)
            print(f"  -> {generic.name} (copy of day)")

    # Clean up temp files
    for tmp in ICON_DIR.glob("_tmp_*.png"):
        tmp.unlink()

    print()
    print("Done.")
    print(f"Icons in {ICON_DIR}:")
    for f in sorted(ICON_DIR.glob("*.png")):
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name:20s}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
