import shutil
import urllib.request
from pathlib import Path
from cairosvg import svg2png

ICON_DIR = Path("/home/rpi/weather_app/weather_icons")
url = "https://unpkg.com/@meteocons/svg-static@latest/fill/sleet.svg"
req = urllib.request.Request(url, headers={"User-Agent": "DeskMate-Zero/1.0"})
with urllib.request.urlopen(req, timeout=60) as resp:
    svg = resp.read()

tmp = ICON_DIR / "_tmp_sleet.png"
svg2png(bytestring=svg, write_to=str(tmp), output_width=512, output_height=512)

for code in [56, 57, 66, 67]:
    shutil.copy(tmp, ICON_DIR / f"{code}d.png")
    shutil.copy(tmp, ICON_DIR / f"{code}.png")
    if code == 56:
        shutil.copy(tmp, ICON_DIR / f"{code}n.png")

tmp.unlink()
print("sleet icons created")
for code in [56, 57, 66, 67]:
    print(f"  {code}d.png exists: {(ICON_DIR / f'{code}d.png').exists()}")
