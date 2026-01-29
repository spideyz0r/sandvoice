import pyaudio
from common.platform_detection import is_macos


def get_audio_instance():
    """
    Create and return a PyAudio instance.

    Returns:
        pyaudio.PyAudio: PyAudio instance, or None if initialization fails
    """
    try:
        return pyaudio.PyAudio()
    except Exception:
        return None


def get_device_count(audio=None):
    """
    Get the number of available audio devices.

    Args:
        audio: Optional PyAudio instance (will create one if not provided)

    Returns:
        int: Number of available devices, or 0 if PyAudio unavailable
    """
    should_cleanup = False
    if audio is None:
        audio = get_audio_instance()
        should_cleanup = True

    if audio is None:
        return 0

    try:
        count = audio.get_device_count()
        return count
    except Exception:
        return 0
    finally:
        if should_cleanup and audio is not None:
            audio.terminate()


def get_default_input_device(audio=None):
    """
    Get the default input device info.

    Args:
        audio: Optional PyAudio instance (will create one if not provided)

    Returns:
        dict: Device info dictionary, or None if no default input device
    """
    should_cleanup = False
    if audio is None:
        audio = get_audio_instance()
        should_cleanup = True

    if audio is None:
        return None

    try:
        device_info = audio.get_default_input_device_info()
        return device_info
    except Exception:
        return None
    finally:
        if should_cleanup and audio is not None:
            audio.terminate()


def get_default_output_device(audio=None):
    """
    Get the default output device info.

    Args:
        audio: Optional PyAudio instance (will create one if not provided)

    Returns:
        dict: Device info dictionary, or None if no default output device
    """
    should_cleanup = False
    if audio is None:
        audio = get_audio_instance()
        should_cleanup = True

    if audio is None:
        return None

    try:
        device_info = audio.get_default_output_device_info()
        return device_info
    except Exception:
        return None
    finally:
        if should_cleanup and audio is not None:
            audio.terminate()


def get_optimal_channels(device_info=None):
    """
    Determine the optimal number of channels for audio recording.

    macOS typically works better with mono (1 channel).
    Other platforms (Linux/Pi) can use stereo (2 channels) if the device supports it.

    Args:
        device_info: Optional device info dictionary from PyAudio

    Returns:
        int: Recommended number of channels (1 or 2)
    """
    # macOS works best with mono
    if is_macos():
        return 1

    # For other platforms, check device capabilities
    if device_info is not None:
        max_channels = device_info.get('maxInputChannels', 1)
        # Use stereo if device supports it, otherwise mono
        return 2 if max_channels >= 2 else 1

    # Default to stereo for non-macOS platforms if no device info
    return 2


def get_all_devices(audio=None):
    """
    Get information about all available audio devices.

    Args:
        audio: Optional PyAudio instance (will create one if not provided)

    Returns:
        list: List of device info dictionaries
    """
    should_cleanup = False
    if audio is None:
        audio = get_audio_instance()
        should_cleanup = True

    if audio is None:
        return []

    try:
        devices = []
        device_count = audio.get_device_count()
        for i in range(device_count):
            try:
                device_info = audio.get_device_info_by_index(i)
                devices.append(device_info)
            except Exception:
                # Skip devices that can't be queried
                continue
        return devices
    except Exception:
        return []
    finally:
        if should_cleanup and audio is not None:
            audio.terminate()


def get_device_summary():
    """
    Get a summary of audio device configuration for logging and debugging.

    Returns:
        dict: Summary of audio device information
    """
    audio = get_audio_instance()

    if audio is None:
        return {
            'pyaudio_available': False,
            'device_count': 0,
            'default_input': None,
            'default_output': None,
            'optimal_channels': get_optimal_channels(),  # Platform-based default
        }

    try:
        default_input = get_default_input_device(audio)
        default_output = get_default_output_device(audio)
        optimal_channels = get_optimal_channels(default_input)

        return {
            'pyaudio_available': True,
            'device_count': get_device_count(audio),
            'default_input': {
                'name': default_input.get('name') if default_input else None,
                'index': default_input.get('index') if default_input else None,
                'max_channels': default_input.get('maxInputChannels') if default_input else None,
            } if default_input else None,
            'default_output': {
                'name': default_output.get('name') if default_output else None,
                'index': default_output.get('index') if default_output else None,
                'max_channels': default_output.get('maxOutputChannels') if default_output else None,
            } if default_output else None,
            'optimal_channels': optimal_channels,
        }
    finally:
        audio.terminate()


def log_device_info(config=None):
    """
    Log audio device information for debugging purposes.

    Args:
        config: Optional configuration object with debug flag
    """
    if config and config.debug:
        summary = get_device_summary()

        print("=== Audio Device Information ===")
        print(f"PyAudio Available: {summary['pyaudio_available']}")
        print(f"Device Count: {summary['device_count']}")

        if summary['default_input']:
            print(f"Default Input: {summary['default_input']['name']}")
            print(f"  Index: {summary['default_input']['index']}")
            print(f"  Max Channels: {summary['default_input']['max_channels']}")
        else:
            print("Default Input: None")

        if summary['default_output']:
            print(f"Default Output: {summary['default_output']['name']}")
            print(f"  Index: {summary['default_output']['index']}")
            print(f"  Max Channels: {summary['default_output']['max_channels']}")
        else:
            print("Default Output: None")

        print(f"Optimal Channels: {summary['optimal_channels']}")
        print("================================")
