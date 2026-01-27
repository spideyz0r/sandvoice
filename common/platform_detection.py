import platform
import logging


def get_platform():
    """
    Get the operating system platform.

    Returns:
        str: 'darwin' for macOS, 'linux' for Linux, or the raw platform.system() value
    """
    system = platform.system().lower()
    return system


def get_architecture():
    """
    Get the system architecture.

    Returns:
        str: Architecture string (e.g., 'arm64', 'aarch64', 'x86_64', 'armv7l')
    """
    return platform.machine().lower()


def is_macos():
    """
    Check if running on macOS.

    Returns:
        bool: True if running on macOS, False otherwise
    """
    return get_platform() == 'darwin'


def is_linux():
    """
    Check if running on Linux.

    Returns:
        bool: True if running on Linux, False otherwise
    """
    return get_platform() == 'linux'


def is_raspberry_pi():
    """
    Check if running on a Raspberry Pi.

    This checks for Linux + ARM architecture, which is a strong indicator
    of Raspberry Pi hardware. More specific detection (reading /proc/cpuinfo)
    could be added if needed.

    Returns:
        bool: True if likely running on Raspberry Pi, False otherwise
    """
    if not is_linux():
        return False

    arch = get_architecture()
    # Raspberry Pi uses ARM architecture
    # Pi 3B: armv7l, Pi 4: aarch64 or armv7l, Pi 5: aarch64
    return arch in ['armv7l', 'aarch64', 'armv6l', 'armv8']


def is_arm_architecture():
    """
    Check if running on ARM architecture (Apple Silicon or Raspberry Pi).

    Returns:
        bool: True if ARM architecture, False otherwise
    """
    arch = get_architecture()
    return 'arm' in arch or 'aarch' in arch


def get_platform_info():
    """
    Get comprehensive platform information for logging and debugging.

    Returns:
        dict: Platform information including system, architecture, release, etc.
    """
    return {
        'system': platform.system(),
        'platform': get_platform(),
        'architecture': get_architecture(),
        'machine': platform.machine(),
        'release': platform.release(),
        'version': platform.version(),
        'is_macos': is_macos(),
        'is_linux': is_linux(),
        'is_raspberry_pi': is_raspberry_pi(),
        'is_arm': is_arm_architecture(),
    }


def log_platform_info(config=None):
    """
    Log platform information for debugging purposes.

    Args:
        config: Optional configuration object with debug flag
    """
    info = get_platform_info()

    if config and config.debug:
        logging.info("=== Platform Information ===")
        logging.info(f"System: {info['system']}")
        logging.info(f"Platform: {info['platform']}")
        logging.info(f"Architecture: {info['architecture']}")
        logging.info(f"Machine: {info['machine']}")
        logging.info(f"Release: {info['release']}")
        logging.info(f"Is macOS: {info['is_macos']}")
        logging.info(f"Is Linux: {info['is_linux']}")
        logging.info(f"Is Raspberry Pi: {info['is_raspberry_pi']}")
        logging.info(f"Is ARM: {info['is_arm']}")
        logging.info("===========================")
