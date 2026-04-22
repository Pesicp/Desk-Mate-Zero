# DeskMate Zero

# Description
- **Picture slideshow** — New picture every 60 minutes, picture changes on touch.
- **Fullscreen Clock** — When Wi-Fi is on, it shows time from the first weather card. When Wi-Fi is off, it shows system/network time.
- **Weather Forecast** — Shows temperature, current condition, weather, hourly (9 hours in advance), daily (5 days), and current.
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
   sudo apt install -y python3-pip python3-setuptools python3-venv python3-dbus network-manager \
       libmtdev1 libxrender1 libgles2-mesa libegl1-mesa libgl1-mesa-glx libsdl2-dev mesa-utils
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
   cp main.py ui.py api.py system.py config.py requirements.txt ~/weather_app/
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

---

## 4. Weather Icons

1. **Create the icons folder:**
   ```bash
   mkdir -p ~/weather_app/weather_icons
   cd ~/weather_app/weather_icons
   ```

2. **Download weather icons:**
   ```bash
   wget https://openweathermap.org/img/wn/{01d,01n,02d,02n,03d,03n,04d,04n,09d,09n,10d,10n,11d,11n,13d,13n,50d,50n}.png
   ```

3. **For high-quality icons (optional):**
   ```bash
   rm -rf ~/weather_app/weather_icons/*
   wget https://openweathermap.org/img/wn/{01d,01n,02d,02n,03d,03n,04d,04n,09d,09n,10d,10n,11d,11n,13d,13n,50d,50n}@2x.png
   for f in *@2x.png; do mv "$f" "${f/@2x/}"; done
   ```

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

1. **Edit `/boot/config.txt`:**
   ```bash
   sudo nano /boot/config.txt
   ```

2. **Add the correct overlay for your display and increase GPU memory:**  
   For the Spotpear 7-inch DSI touchscreen, add:
   ```ini
   dtoverlay=vc4-kms-dsi-7inch
   gpu_mem=128
   ```
   *Check your display manufacturer's documentation for the exact overlay name.*

3. **Disable console blanking** so the screen never goes black:
   ```bash
   sudo nano /boot/cmdline.txt
   ```
   Add `consoleblank=0` to the end of the existing line, then save and exit.

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

## 11. Auto-Update in Background (Optional)

1. **Create the update script:**
   ```bash
   sudo nano /usr/local/bin/weather_safe_update.sh
   ```

2. **Paste the following, then save and exit:**
   ```bash
   #!/bin/bash
   sleep 60
   LAST_UPDATE_FILE="/var/lib/weather_last_update"
   [ ! -f "$LAST_UPDATE_FILE" ] && echo "$(date +%Y-%m-%d)" > "$LAST_UPDATE_FILE"
   LAST_RUN=$(cat "$LAST_UPDATE_FILE")
   TODAY=$(date +%Y-%m-%d)
   if [ "$LAST_RUN" != "$TODAY" ]; then
       # Example update commands:
       # git -C /home/rpi/weather_app pull
       # pip3 install --upgrade -r /home/rpi/weather_app/requirements.txt
       echo "$TODAY" > "$LAST_UPDATE_FILE"
       echo "Update finished at $(date)"
   else
       echo "Already updated today, skipping."
   fi
   ```

3. **Make it executable:**
   ```bash
   sudo chmod +x /usr/local/bin/weather_safe_update.sh
   ```

4. **Create the systemd service:**
   ```bash
   sudo nano /etc/systemd/system/weather_safe_update.service
   ```
   Paste:
   ```ini
   [Unit]
   Description=Silent safe update for Weather Pi

   [Service]
   Type=oneshot
   ExecStart=/usr/local/bin/weather_safe_update.sh
   ```

5. **Create the daily timer:**
   ```bash
   sudo nano /etc/systemd/system/weather_safe_update.timer
   ```
   Paste:
   ```ini
   [Unit]
   Description=Daily timer for Weather Pi safe update

   [Timer]
   OnCalendar=*-*-* 04:00:00
   Persistent=true
   AccuracySec=1min

   [Install]
   WantedBy=timers.target
   ```

6. **Create the on-boot timer:**
   ```bash
   sudo nano /etc/systemd/system/weather_safe_update-onboot.service
   ```
   Paste:
   ```ini
   [Unit]
   Description=Run safe update on boot if missed

   [Service]
   Type=oneshot
   ExecStart=/usr/local/bin/weather_safe_update.sh boot
   ```

7. **Create the corresponding boot timer:**
   ```bash
   sudo nano /etc/systemd/system/weather_safe_update-onboot.timer
   ```
   Paste:
   ```ini
   [Unit]
   Description=Trigger safe update on boot if missed

   [Timer]
   OnBootSec=1min
   Unit=weather_safe_update-onboot.service
   Persistent=true

   [Install]
   WantedBy=timers.target
   ```

8. **Enable the timers:**
   ```bash
   sudo systemctl enable --now weather_safe_update.timer
   sudo systemctl enable --now weather_safe_update-onboot.timer
   ```

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
