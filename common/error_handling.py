import time
import logging
import os
from functools import wraps


def setup_error_logging(config):
    """
    Set up error logging based on configuration.

    Args:
        config: Configuration object with logging settings
    """
    if not config.enable_error_logging:
        return

    log_path = os.path.expanduser(config.error_log_path)
    log_dir = os.path.dirname(log_path)

    # Create log directory if it doesn't exist
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logging.basicConfig(
        filename=log_path,
        level=logging.ERROR,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def retry_with_backoff(max_attempts=3, initial_delay=1):
    """
    Decorator to retry a function with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay in seconds (doubles each retry)

    Returns:
        Decorated function that retries on failure
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    # Log the error if debug is enabled
                    if args and hasattr(args[0], 'config') and args[0].config.debug:
                        logging.error(f"Attempt {attempt + 1}/{max_attempts} failed for {func.__name__}: {e}")

                    # Don't sleep after the last attempt
                    if attempt < max_attempts - 1:
                        time.sleep(delay)
                        delay *= 2  # Exponential backoff

            # All attempts failed, raise the last exception
            raise last_exception

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
