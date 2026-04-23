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

    def __init__(self):
        self._instance = None
        self._player = None
        self._current_url = None
        self._current_name = None
        self._volume = 80

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
        self._current_url = None
        self._current_name = None

    def is_playing(self) -> bool:
        if self._player:
            return self._player.is_playing()
        return False

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

    def cleanup(self):
        """Release VLC resources."""
        if self._player:
            self._player.stop()
            self._player.release()
            self._player = None
        if self._instance:
            self._instance.release()
            self._instance = None
