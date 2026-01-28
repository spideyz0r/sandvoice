import platform


def get_platform():
    """
    Get the operating system platform.

    Returns:
        str: Lowercased platform name derived from platform.system()
             (e.g., 'darwin' for macOS, 'linux' for Linux, 'windows' for Windows)
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


def is_likely_raspberry_pi():
    """
    Check if likely running on a Raspberry Pi.

    This uses a heuristic: Linux + ARM architecture. This will match Raspberry Pi
    devices but may also match other ARM Linux devices (Jetson, ARM servers, etc.).
    For more specific detection, check /proc/device-tree/model or /proc/cpuinfo.

    Returns:
        bool: True if likely running on Raspberry Pi, False otherwise
    """
    # Use generic ARM detection to cover all ARM variants (arm64, aarch64, armv7l, etc.)
    return is_linux() and is_arm_architecture()


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
        'machine': platform.machine().lower(),
        'release': platform.release(),
        'version': platform.version(),
        'is_macos': is_macos(),
        'is_linux': is_linux(),
        'is_likely_raspberry_pi': is_likely_raspberry_pi(),
        'is_arm': is_arm_architecture(),
    }


def log_platform_info(config=None):
    """
    Log platform information for debugging purposes.

    Args:
        config: Optional configuration object with debug flag
    """
    if config and config.debug:
        info = get_platform_info()
        print("=== Platform Information ===")
        print(f"System: {info['system']}")
        print(f"Platform: {info['platform']}")
        print(f"Architecture: {info['architecture']}")
        print(f"Machine: {info['machine']}")
        print(f"Release: {info['release']}")
        print(f"Is macOS: {info['is_macos']}")
        print(f"Is Linux: {info['is_linux']}")
        print(f"Is Raspberry Pi: {info['is_likely_raspberry_pi']}")
        print(f"Is ARM: {info['is_arm']}")
        print("===========================")
