import os
import re
import shutil
import sys
import threading

_GREEN = "\033[32m"
_DIM = "\033[2m"
_DIM_CYAN = "\033[2;36m"
_RESET = "\033[0m"

_SPINNER_FRAMES = ["●  ", "●● ", "●●●", " ●●", "  ●"]

# ANSI escape sequence pattern used to strip codes when measuring visible width
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")

_SPEAKER_COL_WIDTH = 8  # width of the speaker label column in conversation output


class TerminalUI:
    """ANSI terminal UI for wake-word mode.

    Renders an in-place status line, animated spinner, and formatted
    conversation output.  Falls back to plain ``print()`` when stdout is
    not a TTY or ``$TERM`` is ``dumb``.
    """

    def __init__(self, wake_phrase: str = "sand voice"):
        """
        Args:
            wake_phrase: Name shown in the status line (e.g. ``"sand voice"``).
        """
        self._wake_phrase = wake_phrase
        self._use_ansi = (
            sys.stdout.isatty()
            and os.environ.get("TERM", "") not in ("dumb", "")
        )
        self._lock = threading.Lock()
        self._spinner_stop = threading.Event()
        self._spinner_thread: threading.Thread | None = None
        self._spinner_label = ""

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _cols(self) -> int:
        try:
            return shutil.get_terminal_size((80, 24)).columns
        except Exception:
            return 80

    def _status_line(self, right_ansi: str) -> str:
        """Build a full-width status line.

        ``right_ansi`` may contain ANSI codes; visible width is measured by
        stripping them before computing the separator length.
        """
        prefix = f" ◉  {self._wake_phrase}  "
        visible_right = _ANSI_RE.sub("", right_ansi)
        gap = self._cols() - len(prefix) - len(visible_right) - 1
        sep = "─" * max(0, gap)
        return f"{_GREEN}{prefix}{_RESET}{_DIM}{sep}{_RESET} {right_ansi}"

    def _write_status(self, text: str) -> None:
        """Overwrite the current line with ``text`` (no newline)."""
        sys.stdout.write(f"\r\033[K{text}")
        sys.stdout.flush()

    def _clear_status(self) -> None:
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_state(self, state: str, detail: str = "") -> None:
        """Update the status line in place.  Stops any running spinner first.

        Args:
            state:  Short label shown on the right side of the status line
                    (e.g. ``"waiting"``, ``"listening"``, ``"processing"``).
            detail: Optional extra detail appended after a separator
                    (e.g. a route name or timing value).
        """
        self._stop_spinner_thread()
        right_text = state + (f" · {detail}" if detail else "")
        if self._use_ansi:
            right_ansi = f"{_GREEN}{right_text}{_RESET}"
            with self._lock:
                self._write_status(self._status_line(right_ansi))
        else:
            label = state + (f" ({detail})" if detail else "")
            print(f"[{label}]")

    def start_spinner(self, label: str) -> None:
        """Start an animated ●●● spinner in the status line.

        Args:
            label: Phase name shown next to the spinner (e.g. ``"transcribing"``).
        """
        self._stop_spinner_thread()
        self._spinner_label = label
        self._spinner_stop.clear()
        if self._use_ansi:
            self._spinner_thread = threading.Thread(
                target=self._spin_loop, daemon=True, name="terminal-ui-spinner"
            )
            self._spinner_thread.start()
        else:
            print(f"[{label}...]")

    def stop_spinner(self, label: str, elapsed_s: float) -> None:
        """Stop the spinner and replace it with ``label + elapsed time``.

        Args:
            label:     Phase name (e.g. ``"transcribing"``).
            elapsed_s: Elapsed seconds to display inline.
        """
        self._stop_spinner_thread()
        if self._use_ansi:
            right_ansi = f"{_DIM_CYAN}{label} {elapsed_s:.2f}s{_RESET}"
            with self._lock:
                self._write_status(self._status_line(right_ansi))
        else:
            print(f"[{label} {elapsed_s:.2f}s]")

    def print_exchange(self, speaker: str, text: str | None) -> None:
        """Print a conversation turn after clearing the status line.

        When using ANSI, the current status line is cleared and a newline is
        emitted before the exchange is printed on subsequent lines.

        Args:
            speaker: ``"you"`` for user input, bot name for the assistant.
            text:    The spoken/typed text.
        """
        self._stop_spinner_thread()
        with self._lock:
            if self._use_ansi:
                self._clear_status()  # erase stranded status line before scrolling
                sys.stdout.write("\n")
                sys.stdout.flush()

            indent = "  "
            if speaker == "you":
                label = "you"
                speaker_str = f"{_DIM}{label}{_RESET}" if self._use_ansi else label
            else:
                label = speaker
                speaker_str = f"{_GREEN}{label}{_RESET}" if self._use_ansi else label
            pad = " " * max(0, _SPEAKER_COL_WIDTH - len(label))

            continuation = " " * (len(indent) + _SPEAKER_COL_WIDTH)
            lines = (text or "").splitlines() or [""]
            print(f"{indent}{speaker_str}{pad}{lines[0]}")
            for line in lines[1:]:
                print(f"{continuation}{line}")
            if speaker != "you":
                print()  # blank line after bot response

    def close(self) -> None:
        """Stop any running spinner and clear the status line."""
        self._stop_spinner_thread()
        if self._use_ansi:
            with self._lock:
                self._clear_status()

    # ── Spinner internals ─────────────────────────────────────────────────────

    def _stop_spinner_thread(self) -> None:
        self._spinner_stop.set()
        t = self._spinner_thread
        if t is not None and t.is_alive() and threading.current_thread() is not t:
            t.join(timeout=0.5)  # spin loop exits within 0.2s; bound in case stdout blocks
        self._spinner_thread = None

    def _spin_loop(self) -> None:
        i = 0
        while not self._spinner_stop.wait(0.2):
            frame = _SPINNER_FRAMES[i % len(_SPINNER_FRAMES)]
            i += 1
            right_ansi = f"{self._spinner_label} {_GREEN}{frame}{_RESET}"
            with self._lock:
                self._write_status(self._status_line(right_ansi))
