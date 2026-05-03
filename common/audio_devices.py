import logging
import platform
import re

logger = logging.getLogger(__name__)


def find_hw_input_device(pa):
    """Return the index of the first real hardware input device on Linux.

    On Linux the PyAudio default input is often a virtual 'default' device
    that may not deliver audio from the actual USB mic. Explicitly picking
    the first hw: input device ensures we use the real hardware.

    Returns None on macOS/non-Linux (let PyAudio pick the system default).
    Returns None (and logs a warning) if device enumeration fails.
    """
    if platform.system().lower() != "linux":
        return None
    try:
        for i in range(pa.get_device_count()):
            dev = pa.get_device_info_by_index(i)
            if dev.get("maxInputChannels", 0) > 0 and re.search(r'hw:\d+,\d+', dev.get("name", "")):
                logger.debug("Selected hw input device index=%s name=%s", i, dev.get("name", ""))
                return i
    except Exception as e:
        logger.warning("Failed to enumerate audio input devices, using default: %s", e)
    return None
