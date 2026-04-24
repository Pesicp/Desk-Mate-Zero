"""System-level wrappers: Wi-Fi, power, network."""

import logging
import subprocess
import threading
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


def _run(cmd: list) -> subprocess.CompletedProcess:
    """Run a subprocess command, returning the CompletedProcess."""
    return subprocess.run(cmd, capture_output=True, text=True)


def _get_wifi_device() -> str:
    """Return the first Wi-Fi device name, falling back to wlan0."""
    try:
        result = _run(["nmcli", "-t", "-f", "DEVICE,TYPE", "device"])
        for line in result.stdout.splitlines():
            if ":" in line:
                dev, dtype = line.split(":", 1)
                if dtype == "wifi":
                    return dev
    except Exception as exc:
        logger.warning("Failed to detect Wi-Fi device: %s", exc)
    return "wlan0"


def get_current_network() -> Optional[str]:
    """Return the SSID of the currently connected Wi-Fi network."""
    try:
        result = _run(["nmcli", "-t", "-f", "ACTIVE,SSID", "device", "wifi"])
        for line in result.stdout.splitlines():
            if line.startswith("yes:"):
                return line.split(":", 1)[1]
    except Exception as exc:
        logger.warning("Failed to get current network: %s", exc)
    return None


def scan_networks() -> List[dict]:
    """Return a list of nearby Wi-Fi networks."""
    networks = []
    try:
        # Trigger a fresh rescan; without this only cached (often just
        # the currently-connected AP) results are returned.
        _run(["sudo", "nmcli", "device", "wifi", "rescan"])
        import time
        time.sleep(2)

        result = _run(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"])
        if result.returncode != 0:
            logger.warning("nmcli scan failed: %s", result.stderr)
            return networks

        for line in result.stdout.strip().splitlines():
            if ":" not in line:
                continue
            parts = line.rsplit(":", 2)
            if len(parts) >= 3 and parts[0]:
                ssid, signal, security = parts[0], parts[-2], parts[-1]
                networks.append(
                    {
                        "ssid": ssid,
                        "signal": signal,
                        "security": bool(security),
                    }
                )
    except Exception as exc:
        logger.error("Failed to scan networks: %s", exc)
    return networks


def connect_to_network(ssid: str, password: str = "") -> tuple[bool, str]:
    """Connect to a Wi-Fi network. Returns (success, message)."""
    try:
        if password:
            result = _run(
                ["sudo", "nmcli", "device", "wifi", "connect", ssid, "password", password]
            )
        else:
            result = _run(["sudo", "nmcli", "device", "wifi", "connect", ssid])
        if result.returncode == 0:
            return True, f"Connected to {ssid}"
        return False, f"Failed to connect: {result.stderr.strip() or 'Unknown error'}"
    except Exception as exc:
        logger.error("Connection error: %s", exc)
        return False, f"Connection error: {exc}"


def disconnect_network() -> tuple[bool, str]:
    """Disconnect from the current Wi-Fi network."""
    iface = _get_wifi_device()
    try:
        result = _run(["sudo", "nmcli", "device", "disconnect", iface])
        if result.returncode == 0:
            return True, "Disconnected"
        return False, f"Failed to disconnect: {result.stderr.strip() or 'Unknown error'}"
    except Exception as exc:
        logger.error("Disconnect error: %s", exc)
        return False, f"Disconnect error: {exc}"


def forget_network(ssid: str) -> tuple[bool, str]:
    """Remove a saved Wi-Fi connection."""
    try:
        result = _run(["sudo", "nmcli", "connection", "delete", ssid])
        if result.returncode == 0:
            return True, f"Forgot network {ssid}"
        return False, f"Failed to forget network: {result.stderr.strip() or 'Unknown error'}"
    except Exception as exc:
        logger.error("Forget network error: %s", exc)
        return False, f"Forget network error: {exc}"


def toggle_wifi(enable: bool) -> tuple[bool, str]:
    """Enable or disable Wi-Fi radio."""
    try:
        state = "on" if enable else "off"
        _run(["sudo", "nmcli", "radio", "wifi", state])
        _run(["sudo", "rfkill", "unblock" if enable else "block", "wifi"])
        return True, f"Wi-Fi {'Enabled' if enable else 'Disabled'}"
    except Exception as exc:
        logger.error("Wi-Fi toggle error: %s", exc)
        return False, f"Failed to {'enable' if enable else 'disable'} Wi-Fi"


def shutdown() -> None:
    """Power off the device immediately."""
    try:
        _run(["sudo", "shutdown", "now"])
    except Exception as exc:
        logger.error("Shutdown failed: %s", exc)


def reboot() -> None:
    """Reboot the device immediately."""
    try:
        _run(["sudo", "reboot"])
    except Exception as exc:
        logger.error("Reboot failed: %s", exc)


# --- Async wrappers ---

def _async_call(func, callback: Callable, error_callback: Optional[Callable] = None):
    def _worker():
        try:
            result = func()
            callback(result)
        except Exception as exc:
            logger.error("Async system call error: %s", exc)
            if error_callback:
                error_callback(exc)
    threading.Thread(target=_worker, daemon=True).start()


def get_current_network_async(callback: Callable, error_callback: Optional[Callable] = None):
    _async_call(get_current_network, callback, error_callback)


def scan_networks_async(callback: Callable, error_callback: Optional[Callable] = None):
    _async_call(scan_networks, callback, error_callback)


def connect_to_network_async(
    ssid: str,
    password: str,
    callback: Callable,
    error_callback: Optional[Callable] = None,
):
    def _func():
        return connect_to_network(ssid, password)
    _async_call(_func, callback, error_callback)


def disconnect_network_async(callback: Callable, error_callback: Optional[Callable] = None):
    _async_call(disconnect_network, callback, error_callback)


def forget_network_async(
    ssid: str,
    callback: Callable,
    error_callback: Optional[Callable] = None,
):
    def _func():
        return forget_network(ssid)
    _async_call(_func, callback, error_callback)


def toggle_wifi_async(
    enable: bool,
    callback: Callable,
    error_callback: Optional[Callable] = None,
):
    def _func():
        return toggle_wifi(enable)
    _async_call(_func, callback, error_callback)


# ── SSH helpers ──

def get_ssh_status() -> bool:
    """Return True if the SSH service is active."""
    try:
        result = _run(["systemctl", "is-active", "ssh"])
        return result.returncode == 0 and "active" in result.stdout
    except Exception as exc:
        logger.warning("Failed to get SSH status: %s", exc)
        return False


def toggle_ssh(enable: bool) -> tuple:
    """Start or stop the SSH service. Returns (ok, message)."""
    action = "start" if enable else "stop"
    try:
        result = _run(["sudo", "systemctl", action, "ssh"])
        if result.returncode == 0:
            return True, f"SSH {action}ed"
        return False, f"SSH {action} failed: {result.stderr.strip() or 'unknown error'}"
    except Exception as exc:
        logger.error("SSH toggle error: %s", exc)
        return False, str(exc)


def get_ssh_status_async(callback: Callable, error_callback: Optional[Callable] = None):
    _async_call(get_ssh_status, callback, error_callback)


def toggle_ssh_async(
    enable: bool,
    callback: Callable,
    error_callback: Optional[Callable] = None,
):
    def _func():
        return toggle_ssh(enable)
    _async_call(_func, callback, error_callback)
