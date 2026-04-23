# DeskMate Zero

# Description
- **Picture slideshow** — New picture every 60 minutes, picture changes on touch.
- **Fullscreen Clock** — When Wi-Fi is on, it shows time from the first weather card. When Wi-Fi is off, it shows system/network time.
- **Internet Radio** — Browse and stream thousands of free internet radio stations via the Radio Browser API. Search by country or station name. Radio keeps playing in the background while you browse other cards. Sidebar layout with volume, stop, favorites (♡/♥), country browse, and a fake audio visualizer. A small indicator appears on all slides when radio is playing.
- **Weather Forecast** — Shows temperature, current condition, current icon, hourly (8 hours), and daily (5 days) forecasts. Icons are high-resolution 512×512 Meteocons auto-discovered by WMO weather code.
  - Also shows time in the selected city. When Wi-Fi is off the clock keeps ticking, the weather disappears. Has a manual refresh button.
- **Add City** — Add and remove cities. Limit is 10 cities for better performance. Duplicates cannot be added.
- **Power, Wi-Fi** — Power off, reboot. Turn Wi-Fi on or off, connect, disconnect, forget networks with ease.
- **Double press/touch to lock/unlock the screen** — Disabled for the Add City card.
  - It is set up really fast to avoid accidental lock: **0.2 seconds**. With 2 fingers it works best.
  - If the touch is not responding, you have locked the screen.
  - You can see if it is locked: touch the screen and a message appears at the top of the screen: "Double tap to unlock"

---

# Installation Guide

I used a **Raspberry Pi Zero 2W** and the [Spotpear RPI-Touch-Case bundle](https://de.aliexpress.com/item/1005004999310505.html) (7-inch touchscreen).

- All commands are designed for **Raspberry Pi OS Lite (64-bit)** with Python 3.
- You only need the screws and threads that come with the touchscreen in the RPI-Touch-Case bundle.
- Case STL files can be found on [Printables](https://www.printables.com/model/1402602).
- If you run into problems, check the **Troubleshooting** section at the bottom.

---

## 1. Preparation

1. Download and install the [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
2. Using Raspberry Pi Imager:
   - Select **Raspberry Pi OS Lite (64-bit)**.
   - Edit settings (⚙️). If you do not see the settings icon, press **Next** and it will appear.
     - **Hostname:** `rpi`
     - **Enable SSH** (password authentication)
     - **Username:** `rpi` (strongly recommended; all folder structures and scripts assume this username)
     - **Password:** `yourpassword`
     - **Configure Wi-Fi** (input your network name and password)
     - Set country, locale, timezone, and keyboard layout
   - Flash the SD card and insert it into your Pi.
   - Connect your Pi to the display.
3. Boot the Pi and connect via SSH from your computer's terminal:
   - **Windows** (PowerShell or Windows Terminal):
     ```powershell
     ssh rpi@rpi.local
     ```
   - **macOS or Linux** (Terminal):
     ```bash
     ssh rpi@rpi.local
     ```
   - If you cannot connect via hostname, use your local IP address. You can find it on the Pi display.
   - When asked for a password, enter the one you set during imaging.

---

## 2. System Setup

1. **Update the system and install required packages:**
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install -y git python3-pip python3-setuptools python3-venv python3-dbus network-manager \
       libmtdev1 libxrender1 libgles2 libegl1 libgl1 libsdl2-dev mesa-utils vlc
   ```

2. **Enable and start Network Manager:**
   ```bash
   sudo systemctl enable NetworkManager
   sudo systemctl start NetworkManager
   ```

---

## 3. Python Environment and App Setup

1. **Create the application folder and virtual environment:**
   ```bash
   mkdir -p ~/weather_app
   python3 -m venv ~/weather_app/venv
   ```

2. **Activate the virtual environment:**
   ```bash
   source ~/weather_app/venv/bin/activate
   ```

3. **Copy the project files into `~/weather_app/`**  
   Clone the repository and copy the code files into `~/weather_app/`:
   ```bash
   git clone https://github.com/Pesicp/Desk-Mate-Zero.git
   cp Desk-Mate-Zero/*.py Desk-Mate-Zero/requirements.txt ~/weather_app/
   ```
   Or download the ZIP from [GitHub](https://github.com/Pesicp/Desk-Mate-Zero) and extract it, then copy the files:
   ```bash
   cp main.py ui.py api.py system.py config.py radio_api.py radio_player.py setup_meteocons.py fix_sleet.py requirements.txt ~/weather_app/
   ```
   > **Important:** If this is your first install, also copy the default `config.json`:
   > ```bash
   > cp config.json ~/weather_app/
   > ```
   > If you already have a `config.json` with your saved cities, **do not overwrite it** or you will lose your settings.

4. **Install Python dependencies:**
   ```bash
   cd ~/weather_app
   pip install -r requirements.txt
   ```
   > **Note for Raspberry Pi OS Trixie (Python 3.13+):**  
   > If `kivy` fails to build with `No module named 'cgi'`, install it from apt instead:
   > ```bash
   > sudo apt install -y python3-kivy
   > deactivate
   > rm -rf ~/weather_app/venv
   > python3 -m venv ~/weather_app/venv --system-site-packages
   > source ~/weather_app/venv/bin/activate
   > pip install requests tzdata feedparser python-vlc
   > ```

---

## 4. Weather Icons

The app uses the free **Meteocons** icon set. Icons are downloaded as SVG and converted to 512x512 PNGs so they look crisp on the display. They are named by WMO weather code — the app auto-discovers them.

1. **Install the converter (one time):**
   ```bash
   source ~/weather_app/venv/bin/activate
   pip install cairosvg
   ```

2. **Download and convert icons (copy-paste):**
   ```bash
   cd ~/weather_app
   python setup_meteocons.py
   ```
   This downloads static SVGs from the Meteocons CDN, converts them to 512x512 PNGs, and names them by WMO code.

3. **To add a missing icon later**, edit `setup_meteocons.py`, add the WMO code and Meteocons slug, then re-run the script.

**WMO weather codes reference:**
| Code | Meaning |
|------|---------|
| 0, 1 | Clear / Mainly clear |
| 2 | Partly cloudy |
| 3 | Overcast |
| 45, 48 | Fog / Rime fog |
| 51, 53, 55 | Drizzle |
| 56, 57 | Freezing drizzle |
| 61, 63, 65 | Rain |
| 66, 67 | Freezing rain |
| 71, 73, 75 | Snow |
| 77 | Snow grains |
| 80, 81, 82 | Rain showers |
| 85, 86 | Snow showers |
| 95, 96, 99 | Thunderstorm |

---

## 5. Slideshow Pictures

1. **Create the pictures folder:**
   ```bash
   mkdir -p /home/rpi/pictures/
   cd /home/rpi/pictures/
   ```

2. **Download your pictures with `wget`, for example:**
   ```bash
   wget https://yourpictureurl.com/image.jpg
   ```

   Here are some nice pictures to start with:
   ```bash
   wget https://images.wallpaperscraft.com/image/single/waterfall_cliff_stone_141850_1024x600.jpg
   wget https://images.wallpaperscraft.com/image/single/sea_sunset_horizon_131804_1024x600.jpg
   wget https://images.wallpaperscraft.com/image/single/boat_mountains_lake_135258_1024x600.jpg
   wget https://images.wallpaperscraft.com/image/single/ocean_beach_aerial_view_134429_1024x600.jpg
   wget https://images.wallpaperscraft.com/image/single/mountains_lake_grass_137616_1024x600.jpg
   wget https://images.wallpaperscraft.com/image/single/sea_sunset_art_131736_1024x600.jpg
   wget https://images.wallpaperscraft.com/image/single/autumn_forest_park_128379_1024x600.jpg
   wget https://images.wallpaperscraft.com/image/single/sunflowers_field_sunset_123231_1024x600.jpg
   wget https://images.wallpaperscraft.com/image/single/landscape_mountains_sun_140434_1024x600.jpg
   wget https://images.wallpaperscraft.com/image/single/lake_mountains_solitude_124541_1024x600.jpg
   wget https://images.wallpaperscraft.com/image/single/bench_autumn_park_125807_1024x600.jpg
   wget https://images.wallpaperscraft.com/image/single/autumn_path_foliage_131773_1024x600.jpg
   wget https://images.wallpaperscraft.com/image/single/tree_horizon_sunset_128367_1024x600.jpg
   ```

---

## 6. Display / Touchscreen Configuration

For Raspberry Pi OS Lite, Kivy needs access to the framebuffer or display server. Depending on your touchscreen, you may need to edit `/boot/config.txt`.

1. **Edit `/boot/firmware/config.txt`:**
   ```bash
   sudo nano /boot/firmware/config.txt
   ```

2. **Add the display overlays and GPU memory:**  
   For the Spotpear 7-inch DSI touchscreen, fix your `config.txt`:
   ```bash
   sudo nano /boot/firmware/config.txt
   ```

   Delete old `dtoverlay` and replace with:
   ```ini
   dtoverlay=vc4-kms-v3d
   dtoverlay=vc4-kms-dsi-7inch
   ```
   Also add or change:
   ```ini
   gpu_mem=128
   ```
   If you have `display_auto_detect=1`, change it to:
   ```ini
   display_auto_detect=0
   ```
   Save, then reboot:
   ```bash
   sudo reboot
   ```

   > **Why both overlays?** No `/dev/dri/` means the DRM driver isn't loading. You replaced the V3D driver with just the DSI display overlay. `vc4-kms-v3d` is what creates the DRM device (`/dev/dri/card0`) that SDL2 needs to render. Without it, the app starts but the screen stays black.

   *Check your display manufacturer's documentation for the exact DSI overlay name.*

3. **Disable console blanking** so the screen never goes black:
   ```bash
   sudo nano /boot/firmware/cmdline.txt
   ```
   Add `consoleblank=0` to the end of the existing line, then save and exit.

   > **Why?** Console blanking is a Linux power-saving feature that turns the display off after ~10–15 minutes of inactivity. Since DeskMate is designed as a 24/7 display (clock, weather, slideshow), the screen would go black and stay black until you physically interact with it. Setting `consoleblank=0` keeps the display on permanently.

4. **Enable console auto-login so the display stays active:**
   ```bash
   sudo raspi-config
   ```
   Navigate to **System Options → Boot / Auto Login → Console Autologin**.

5. **Reboot:**
   ```bash
   sudo reboot
   ```

---

## 7. Passwordless Sudo (Required)

The app calls `sudo` for Wi-Fi management, shutdown, and reboot. To prevent the UI from freezing while waiting for a password, add passwordless sudo for the required commands.

1. **Create a sudoers file:**
   ```bash
   sudo nano /etc/sudoers.d/deskmate
   ```

2. **Paste the following (replace `rpi` if you used a different username):**
   ```
   rpi ALL=(ALL) NOPASSWD: /usr/bin/nmcli, /sbin/shutdown, /sbin/reboot, /usr/sbin/rfkill
   ```

   > **Note:** If the paths above do not match your system, verify them with `which nmcli`, `which shutdown`, `which reboot`, and `which rfkill`.

3. **Save and exit** (`Ctrl+O`, `Enter`, `Ctrl+X`).

4. **Set correct permissions:**
   ```bash
   sudo chmod 440 /etc/sudoers.d/deskmate
   ```

---

## 8. Run the App

1. **Activate the virtual environment (if not already active):**
   ```bash
   source ~/weather_app/venv/bin/activate
   ```

2. **Run the app:**
   ```bash
   python3 ~/weather_app/main.py
   ```

3. **To exit, press `Ctrl+C` in the terminal.**

---

## 9. Make it Auto-Start on Boot

1. **Create the systemd service:**
   ```bash
   sudo nano /etc/systemd/system/weather_app.service
   ```

2. **Paste the following, then save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`):**
   ```ini
   [Unit]
   Description=Weather Display App
   After=network.target

   [Service]
   ExecStart=/home/rpi/weather_app/venv/bin/python /home/rpi/weather_app/main.py
   WorkingDirectory=/home/rpi/weather_app
   User=rpi
   Group=rpi
   Environment="PATH=/home/rpi/weather_app/venv/bin:/usr/bin"
   Environment="SDL_VIDEODRIVER=KMSDRM"
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

3. **Enable and start the service:**
   ```bash
   sudo systemctl enable weather_app.service
   sudo systemctl start weather_app.service
   ```

4. **Check the status:**
   ```bash
   sudo systemctl status weather_app.service
   ```

5. **Reboot to test auto-start:**
   ```bash
   sudo reboot
   ```

---

## 10. Security (Optional but Recommended)

1. **Disable unneeded services:**
   ```bash
   sudo systemctl disable avahi-daemon
   sudo systemctl stop avahi-daemon
   sudo systemctl disable bluetooth
   sudo systemctl stop bluetooth
   sudo apt purge --ignore-missing wolfram-engine libreoffice* minecraft-pi -y || true
   sudo apt autoremove -y
   ```

2. **Install and configure the UFW firewall:**
   ```bash
   sudo apt install ufw -y
   sudo ufw reset
   sudo ufw default deny incoming
   sudo ufw default allow outgoing
   ```
   > ⚠️ `ufw reset` will erase any existing firewall rules you have configured.

3. **Allow SSH only from your local subnet:**
   ```bash
   SUBNET=$(ip -o -f inet addr show wlan0 | awk '/scope global/ {print $4}')
   sudo ufw allow from $SUBNET to any port 22 proto tcp
   ```
   *If `wlan0` is not your active interface, replace it with `eth0` or run `ip link` to find the correct name.*

4. **Allow outgoing traffic for weather updates:**
   ```bash
   sudo ufw allow out 80/tcp
   sudo ufw allow out 443/tcp
   ```

5. **Enable the firewall:**
   ```bash
   sudo ufw enable
   sudo ufw status verbose
   ```
   Confirm with `y` (Yes).

---

## 11. System Cleanup (Optional)

Free up SD card space and reduce the attack surface by removing packages you don't need.

### What is safe to purge on a display-only device

These commands are tailored for **Raspberry Pi OS Lite (64-bit, Trixie)** on a **Pi Zero 2W**. If a package is not installed, the command will simply skip it.

```bash
# Big space savers (~290 MB): Pi 5 kernel, compiler toolchain, kernel headers, dev libs, EEPROM updater, cloud-init
sudo apt purge -y linux-image-6.12.75+rpt-rpi-2712 build-essential gcc-14-aarch64-linux-gnu g++-14-aarch64-linux-gnu cpp-14-aarch64-linux-gnu cpp-aarch64-linux-gnu cpp-14 cpp linux-headers-6.12.75+rpt-common-rpi libpython3.13-dev rpi-eeprom cloud-init mkvtoolnix

# Smaller cleanups: hotkey daemon, modem manager, swap, duplicate logger, first-boot wizard
sudo dphys-swapfile swapoff
sudo apt purge -y triggerhappy modemmanager dphys-swapfile rsyslog piwiz

# Clean up
sudo apt autoremove -y
sudo apt autoclean

# After setup is complete, remove git too (only needed to clone the repo)
sudo apt purge -y git
sudo apt autoremove -y
```

### Clean up logs and temp files

```bash
# Keep only the last 7 days of systemd journals
sudo journalctl --vacuum-time=7d

# Clear old archived logs
sudo find /var/log -type f \( -name "*.gz" -o -name "*.old" -o -name "*.1" \) -delete 2>/dev/null || true

# Truncate active log files to zero (keeps the files, removes content)
sudo find /var/log -type f -exec truncate -s 0 {} \; 2>/dev/null || true

# Clean temp directories
sudo rm -rf /tmp/* /var/tmp/* 2>/dev/null || true
```

---

## 12. Auto-Update OS Security Only (Optional)

Keep the operating system secure without ever touching the weather app.

**What this does:**
- Checks daily for **security updates only**
- Auto-installs critical system packages: kernel, OpenSSL, OpenSSH, UFW, firmware
- **Never** updates Python, Kivy, pip, or the weather app
- Auto-reboots at 4 AM if a kernel update requires it

### Set it up

1. **Install the package:**
   ```bash
   sudo apt update
   sudo apt install -y unattended-upgrades apt-listchanges
   ```

2. **Configure security-only updates:**
   ```bash
   sudo nano /etc/apt/apt.conf.d/50unattended-upgrades
   ```
   Paste exactly:
   ```
   Unattended-Upgrade::Allowed-Origins {
       "${distro_id}:${distro_codename}-security";
   };
   Unattended-Upgrade::Package-Whitelist {
       "ufw"; "openssh-server"; "openssh-client"; "openssl";
       "libc6"; "libc-bin"; "systemd"; "systemd-sysv";
       "linux-image*"; "linux-headers*"; "firmware-*"; "raspi-firmware"; "raspberrypi*";
   };
   Unattended-Upgrade::Package-Blacklist {
       "python3-kivy"; "python3-pip"; "kivy";
   };
   Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
   Unattended-Upgrade::Remove-Unused-Dependencies "true";
   Unattended-Upgrade::Automatic-Reboot "true";
   Unattended-Upgrade::Automatic-Reboot-Time "04:00";
   Unattended-Upgrade::Download-Upgradeable-Packages "true";
   ```
   Save: `Ctrl+O`, `Enter`, `Ctrl+X`.

3. **Enable the auto-upgrade timer:**
   ```bash
   sudo nano /etc/apt/apt.conf.d/20auto-upgrades
   ```
   Paste exactly:
   ```
   APT::Periodic::Update-Package-Lists "1";
   APT::Periodic::Download-Upgradeable-Packages "1";
   APT::Periodic::AutocleanInterval "7";
   APT::Periodic::Unattended-Upgrade "1";
   ```
   Save: `Ctrl+O`, `Enter`, `Ctrl+X`.

4. **Set weekly schedule (Monday 04:00):**
   ```bash
   sudo systemctl edit apt-daily-upgrade.timer
   ```
   Paste exactly:
   ```ini
   [Timer]
   OnCalendar=
   OnCalendar=Mon *-*-* 04:00:00
   Persistent=true
   ```
   Save: `Ctrl+O`, `Enter`, `Ctrl+X`.

5. **Add 1-hour boot delay (so updates don't slow down startup):**
   ```bash
   sudo systemctl edit apt-daily-upgrade.service
   ```
   Paste exactly:
   ```ini
   [Service]
   ExecStartPre=/bin/bash -c 'UPTIME=$(awk "{print int($1/60)}" /proc/uptime); if [ "$UPTIME" -lt 60 ]; then sleep 3600; fi'
   ```
   Save: `Ctrl+O`, `Enter`, `Ctrl+X`.

6. **Reload and verify:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart apt-daily-upgrade.timer
   sudo systemctl status apt-daily-upgrade.timer
   ```
   You should see `Trigger: Mon ... 04:00:00`.

7. **Read the update log after the first run:**
   ```bash
   cat /var/log/unattended-upgrades/unattended-upgrades.log
   ```

> **Manual app updates:** When you want new features, update the app yourself:
> ```bash
> cd ~/weather_app
> git pull
> sudo systemctl restart weather_app.service
> ```

---

## Troubleshooting

- **If the device freezes, unplug and replug the power.**
- **If you exit SSH, reactivate the virtual environment before running manually:**
  ```bash
  source /home/rpi/weather_app/venv/bin/activate
  python3 ~/weather_app/main.py
  ```
- **If the SSH terminal freezes or shows a blank screen, close it and open a new terminal window.**
- **Finding timezone strings:**  
  Timezone values in `config.json` must be valid IANA names (e.g. `Europe/Berlin`, `Asia/Tokyo`).  
  You can find your timezone at [https://en.wikipedia.org/wiki/List_of_tz_database_time_zones](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones).
- **No audio from radio:**
  1. Check that VLC is installed:
     ```bash
     which cvlc
     ```
  2. List ALSA audio devices:
     ```bash
     aplay -l
     ```
     If your Spotpear DSI speaker is not the default device, create `~/.asoundrc` to select the correct card. For example, if the DSI audio is card 1:
     ```
     defaults.pcm.card 1
     defaults.ctl.card 1
     ```
  3. Test audio manually:
     ```bash
     cvlc --aout=alsa --no-video "https://stream.example.com/radio"
     ```
     If you hear sound, the app should work. If not, check `~/.local/share/deskmate/deskmate.log` for VLC errors.

- **Black screen / app starts but nothing displays:**
  1. Check that the DRM device exists:
     ```bash
     ls /dev/dri/
     ```
     You should see `card0`. If `/dev/dri/` is empty, `vc4-kms-v3d` is not loading. Verify `/boot/firmware/config.txt` contains **both** `dtoverlay=vc4-kms-dsi-7inch` and `dtoverlay=vc4-kms-v3d`.
  2. Check the service logs for window provider errors:
     ```bash
     sudo journalctl -u weather_app.service -f
     ```
     Look for `Window: Unable to find any valuable Window provider` — that means SDL2 can't open the display.
  3. Make sure you rebooted after editing `config.txt`:
     ```bash
     sudo reboot
     ```

- **Check logs when running as a service:**
  ```bash
  sudo journalctl -u weather_app.service -f
  ```
  Or read the app log file:
  ```bash
  cat ~/.local/share/deskmate/deskmate.log
  ```

---

# Enjoy
