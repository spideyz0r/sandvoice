import time
import logging
import os
import json
from functools import wraps


def setup_error_logging(config):
    """
    Set up error logging based on configuration.

    Configures logging handlers for SandVoice debug output and error logging.
    Only adds new handlers if they don't already exist (idempotent).

    Args:
        config: Configuration object with logging settings
    """
    # Use getattr with defaults for compatibility with minimal config mocks
    debug = getattr(config, 'debug', False)
    enable_error_logging = getattr(config, 'enable_error_logging', False)

    # Only proceed if we need to add handlers
    if not debug and not enable_error_logging:
        return

    # Set logging level based on debug mode
    log_level = logging.INFO if debug else logging.ERROR

    # Configure root logger level only when adding SandVoice handlers
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Check if we already have SandVoice handlers to avoid duplicates
    has_sandvoice_console = any(
        getattr(h, '_sandvoice_console', False) for h in logger.handlers
    )
    has_sandvoice_file = any(
        getattr(h, '_sandvoice_file', False) for h in logger.handlers
    )

    # Add console handler when debug is enabled (if not already present)
    if debug and not has_sandvoice_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_formatter = logging.Formatter(
            '%(asctime)s.%(msecs)03d %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        console_handler._sandvoice_console = True  # Mark as ours
        logger.addHandler(console_handler)

    # Add file handler if error logging is enabled (if not already present)
    if enable_error_logging and not has_sandvoice_file:
        error_log_path = getattr(config, 'error_log_path', '')
        if not error_log_path:
            logging.error("enable_error_logging is True but error_log_path is not set")
            return
        log_path = os.path.expanduser(error_log_path)
        log_dir = os.path.dirname(log_path)

        # Create log directory if it doesn't exist
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(logging.ERROR)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        file_handler._sandvoice_file = True  # Mark as ours
        logger.addHandler(file_handler)


def retry_with_backoff(max_attempts=3, initial_delay=1):
    """
    Decorator to retry a function with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay in seconds (doubles each retry)

    Returns:
        Decorated function that retries on failure

    Note:
        Non-retryable exceptions (FileNotFoundError, PermissionError, ValueError)
        are raised immediately without retry.
    """
    # Exceptions that should not be retried (non-transient errors)
    NON_RETRYABLE_EXCEPTIONS = (FileNotFoundError, PermissionError, ValueError, KeyError, json.JSONDecodeError)

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
                except NON_RETRYABLE_EXCEPTIONS:
                    # Don't retry non-transient errors
                    raise
                except Exception as e:
                    last_exception = e

                    # Log the error if debug is enabled
                    if args:
                        config = getattr(args[0], 'config', None)
                        debug_enabled = getattr(config, 'debug', False) if config is not None else False
                        if debug_enabled:
                            logging.error(f"Attempt {attempt + 1}/{attempts} failed for {func.__name__}: {e}")

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
