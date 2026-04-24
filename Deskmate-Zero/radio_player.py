"""VLC-based audio player for internet radio."""

import logging

logger = logging.getLogger(__name__)

try:
    import vlc

    _VLC_AVAILABLE = True
except ImportError:
    _VLC_AVAILABLE = False
    logger.warning("python-vlc not installed. Radio playback disabled.")


class RadioPlayer:
    """VLC radio player. Create once and reuse."""

    def __init__(self, volume=20):
        self._instance = None
        self._player = None
        self._current_url = None
        self._current_name = None
        self._volume = volume
        self._paused = False

        if _VLC_AVAILABLE:
            try:
                self._instance = vlc.Instance(
                    "--aout=alsa",
                    "--quiet",
                    "--no-video",
                )
                self._player = self._instance.media_player_new()
                self._player.audio_set_volume(self._volume)
                logger.info("VLC radio player initialized")
            except Exception as exc:
                logger.error("VLC init failed: %s", exc)
                self._instance = None
                self._player = None

    def play(self, url: str, name: str = "") -> bool:
        """Start playing a stream URL."""
        if not self._player:
            logger.error("VLC not available")
            return False
        try:
            self.stop()
            media = self._instance.media_new(url)
            self._player.set_media(media)
            self._player.play()
            self._paused = False
            self._current_url = url
            self._current_name = name
            logger.info("Playing: %s", name or url)
            return True
        except Exception as exc:
            logger.error("Play failed: %s", exc)
            return False

    def stop(self):
        """Stop playback."""
        if self._player:
            self._player.stop()
        self._paused = False
        self._current_url = None
        self._current_name = None

    def is_playing(self) -> bool:
        if self._player:
            return self._player.is_playing()
        return False

    def get_state(self) -> str:
        """Return 'playing', 'paused', or 'stopped'."""
        if not self._player:
            return "stopped"
        if getattr(self, "_paused", False):
            return "paused"
        if self._player.is_playing():
            return "playing"
        return "stopped"

    def pause(self):
        """Pause playback."""
        if self._player and self._player.is_playing():
            self._player.pause()
            self._paused = True

    def resume(self):
        """Resume from pause."""
        if self._player and getattr(self, "_paused", False):
            self._player.pause()
            self._paused = False

    def set_volume(self, vol: int):
        """Set volume 0-100."""
        self._volume = max(0, min(100, vol))
        if self._player:
            self._player.audio_set_volume(self._volume)

    def get_volume(self) -> int:
        return self._volume

    @property
    def current_name(self):
        return self._current_name or ""

    @property
    def current_url(self):
        return self._current_url or ""

    def set_equalizer_preset(self, preset_id: int) -> bool:
        """Enable equalizer with a preset (0=flat, 3=dance, 5=fullbass, 9=live, 11=pop, 13=rock, etc.)."""
        if not self._player or not _VLC_AVAILABLE:
            return False
        try:
            eq = vlc.libvlc_audio_equalizer_new_from_preset(preset_id)
            if eq is None:
                return False
            self._player.set_equalizer(eq)
            # Release previous equalizer to avoid leaking C handles
            if getattr(self, "_active_equalizer", None) is not None:
                try:
                    vlc.libvlc_audio_equalizer_release(self._active_equalizer)
                except Exception:
                    pass
            self._active_equalizer = eq
            logger.info("Equalizer preset %s applied", preset_id)
            return True
        except Exception as exc:
            logger.error("Equalizer preset failed: %s", exc)
            return False

    def disable_equalizer(self) -> bool:
        """Disable the equalizer."""
        if not self._player or not _VLC_AVAILABLE:
            return False
        try:
            self._player.set_equalizer(None)
            if getattr(self, "_active_equalizer", None) is not None:
                try:
                    vlc.libvlc_audio_equalizer_release(self._active_equalizer)
                except Exception:
                    pass
                self._active_equalizer = None
            logger.info("Equalizer disabled")
            return True
        except Exception as exc:
            logger.error("Disable equalizer failed: %s", exc)
            return False

    def has_equalizer(self) -> bool:
        """Return True if the VLC equalizer API is available."""
        if not _VLC_AVAILABLE or not self._player:
            return False
        try:
            if not hasattr(self._player, "set_equalizer"):
                return False
            eq = vlc.libvlc_audio_equalizer_new()
            if eq:
                vlc.libvlc_audio_equalizer_release(eq)
            return eq is not None
        except Exception:
            return False

    def cleanup(self):
        """Release VLC resources."""
        if self._player:
            self._player.stop()
            self._player.release()
            self._player = None
        if self._instance:
            self._instance.release()
            self._instance = None
