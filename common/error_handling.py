import time
import logging
import json
from functools import wraps

logger = logging.getLogger(__name__)

_LOG_LEVELS = {
    "debug":   logging.DEBUG,
    "info":    logging.INFO,
    "warning": logging.WARNING,
}

_NON_RETRYABLE_EXCEPTIONS = (
    FileNotFoundError, PermissionError, ValueError, KeyError, json.JSONDecodeError
)


def setup_error_logging(config):
    """
    Configure SandVoice logging handlers based on log_level.

    Always installs a console handler (find-or-create, idempotent). Re-calling with
    a different log_level updates the handler level in place.

    Args:
        config: Configuration object with log_level
    """
    level = _LOG_LEVELS.get(getattr(config, "log_level", "warning"), logging.WARNING)

    root = logging.getLogger()
    root.setLevel(level)

    # Find existing console handler or create one (idempotent, level-update safe)
    console = next((h for h in root.handlers if getattr(h, "_sandvoice_console", False)), None)
    if console is None:
        console = logging.StreamHandler()
        console._sandvoice_console = True
        root.addHandler(console)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))


def retry_with_backoff(max_attempts=3, initial_delay=1):
    """
    Decorator to retry a function with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay in seconds (doubles each retry)

    Returns:
        Decorated function that retries on failure

    Note:
        Non-retryable exceptions (FileNotFoundError, PermissionError, ValueError,
        KeyError, json.JSONDecodeError) are raised immediately without retry.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None

            # Use config.api_retry_attempts if available, otherwise use decorator parameter
            attempts = max_attempts
            if args:
                config = getattr(args[0], 'config', None)
                if config is not None:
                    attempts = getattr(config, 'api_retry_attempts', max_attempts)

            for attempt in range(attempts):
                try:
                    return func(*args, **kwargs)
                except _NON_RETRYABLE_EXCEPTIONS:
                    raise
                except Exception as e:
                    last_exception = e
                    logger.debug("Attempt %d/%d failed for %s: %s", attempt + 1, attempts, getattr(func, "__name__", repr(func)), e)

                    # Don't sleep after the last attempt
                    if attempt < attempts - 1:
                        time.sleep(delay)
                        delay *= 2  # Exponential backoff

            # All attempts failed, raise the last exception if available
            if last_exception is not None:
                raise last_exception
            raise RuntimeError("All retry attempts failed, but no exception was captured.")

        return wrapper
    return decorator


def format_user_error(error_type, user_message, debug_info=None):
    """
    Format error message for end users.

    Args:
        error_type: Type of error (e.g., "API Error", "Network Error")
        user_message: User-friendly message explaining what happened
        debug_info: Optional debug information (only shown if debug enabled)

    Returns:
        Formatted error message string
    """
    message = f"{error_type}: {user_message}"

    if debug_info:
        message += f"\nDebug info: {debug_info}"

    return message


def handle_api_error(e, service_name="API"):
    """
    Convert API exceptions to user-friendly messages.

    Args:
        e: Exception object
        service_name: Name of the service that failed

    Returns:
        User-friendly error message
    """
    error_message = str(e)

    # Network/connection errors
    if "ConnectionError" in type(e).__name__ or "Timeout" in type(e).__name__:
        return format_user_error(
            "Network Error",
            f"Unable to reach {service_name}. Check your internet connection and try again.",
            error_message
        )

    # Authentication errors
    if "401" in error_message or "Unauthorized" in error_message:
        return format_user_error(
            "Authentication Error",
            f"{service_name} authentication failed. Check your API key.",
            error_message
        )

    # Rate limiting
    if "429" in error_message or "rate limit" in error_message.lower():
        return format_user_error(
            "Rate Limit Error",
            f"{service_name} rate limit exceeded. Please wait a moment and try again.",
            error_message
        )

    # Generic API error
    return format_user_error(
        "Service Error",
        f"{service_name} encountered an error. Please try again.",
        error_message
    )


def handle_file_error(e, operation="access", filename="file"):
    """
    Convert file I/O exceptions to user-friendly messages.

    Args:
        e: Exception object
        operation: Operation that failed (e.g., "read", "write", "access")
        filename: Name of the file

    Returns:
        User-friendly error message
    """
    error_message = str(e)

    if isinstance(e, FileNotFoundError):
        return format_user_error(
            "File Error",
            f"Could not find {filename}.",
            error_message
        )

    if isinstance(e, PermissionError):
        return format_user_error(
            "Permission Error",
            f"No permission to {operation} {filename}.",
            error_message
        )

    return format_user_error(
        "File Error",
        f"Could not {operation} {filename}.",
        error_message
    )
