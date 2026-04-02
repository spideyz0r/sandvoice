import io
import threading
import unittest
from unittest.mock import patch

from common.terminal_ui import TerminalUI, _ANSI_RE, _SPINNER_FRAMES, _GREEN, _YELLOW


def _make_ui(ansi: bool = False) -> TerminalUI:
    """Return a TerminalUI with ANSI forced on or off for testing."""
    ui = TerminalUI(wake_phrase="test bot")
    ui._use_ansi = ansi
    return ui


class TestTerminalUIInit(unittest.TestCase):
    def test_default_attributes(self):
        ui = TerminalUI()
        self.assertEqual(ui._wake_phrase, "sand voice")
        self.assertIsNone(ui._spinner_thread)

    def test_custom_wake_phrase(self):
        ui = TerminalUI(wake_phrase="hey bot")
        self.assertEqual(ui._wake_phrase, "hey bot")

    def test_non_tty_disables_ansi(self):
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = False
            ui = TerminalUI()
        self.assertFalse(ui._use_ansi)

    def test_dumb_term_disables_ansi(self):
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            with patch.dict("os.environ", {"TERM": "dumb"}):
                ui = TerminalUI()
        self.assertFalse(ui._use_ansi)

    def test_empty_term_disables_ansi(self):
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            with patch.dict("os.environ", {"TERM": ""}):
                ui = TerminalUI()
        self.assertFalse(ui._use_ansi)

    def test_tty_with_xterm_enables_ansi(self):
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            with patch.dict("os.environ", {"TERM": "xterm-256color"}):
                ui = TerminalUI()
        self.assertTrue(ui._use_ansi)


# ── set_state ─────────────────────────────────────────────────────────────────

class TestSetState(unittest.TestCase):
    def test_plain_output_state_only(self):
        ui = _make_ui(ansi=False)
        with patch("builtins.print") as mock_print:
            ui.set_state("waiting")
        mock_print.assert_called_once_with("[waiting]")

    def test_plain_output_state_with_detail(self):
        ui = _make_ui(ansi=False)
        with patch("builtins.print") as mock_print:
            ui.set_state("processing", detail="weather")
        mock_print.assert_called_once_with("[processing (weather)]")

    def test_ansi_writes_to_stdout(self):
        ui = _make_ui(ansi=True)
        with patch("sys.stdout") as mock_stdout:
            ui.set_state("waiting")
        mock_stdout.write.assert_called()
        output = mock_stdout.write.call_args[0][0]
        # Should contain the state label and ANSI reset
        self.assertIn("waiting", output)
        self.assertIn("\033[", output)

    def test_set_state_stops_spinner(self):
        ui = _make_ui(ansi=False)
        ui._spinner_thread = threading.Thread(target=lambda: None, daemon=True)
        ui._spinner_thread.start()
        ui._spinner_stop.clear()
        with patch("builtins.print"):
            ui.set_state("listening")
        self.assertTrue(ui._spinner_stop.is_set())


# ── start_spinner / stop_spinner ──────────────────────────────────────────────

class TestSpinner(unittest.TestCase):
    def test_start_spinner_plain_output(self):
        ui = _make_ui(ansi=False)
        with patch("builtins.print") as mock_print:
            ui.start_spinner("transcribing")
        mock_print.assert_called_once_with("[transcribing...]")

    def test_stop_spinner_plain_output(self):
        ui = _make_ui(ansi=False)
        with patch("builtins.print") as mock_print:
            ui.stop_spinner("transcribing", 1.23)
        mock_print.assert_called_once_with("[transcribing 1.23s]")

    def test_start_spinner_ansi_starts_thread(self):
        ui = _make_ui(ansi=True)
        with patch("sys.stdout"):
            ui.start_spinner("routing")
            self.assertIsNotNone(ui._spinner_thread)
            self.assertTrue(ui._spinner_thread.is_alive())
            ui.close()  # clean up inside patch so thread doesn't outlive it

    def test_stop_spinner_ansi_stops_thread(self):
        ui = _make_ui(ansi=True)
        with patch("sys.stdout"):
            ui.start_spinner("routing")
            ui.stop_spinner("routing", 0.55)
        self.assertTrue(ui._spinner_stop.is_set())

    def test_double_start_replaces_thread(self):
        ui = _make_ui(ansi=True)
        with patch("sys.stdout"):
            ui.start_spinner("first")
            first_thread = ui._spinner_thread
            ui.start_spinner("second")
            # Old thread should have been stopped and replaced
            self.assertIsNot(ui._spinner_thread, first_thread)
            ui.close()  # stop thread inside patch so it doesn't outlive the mock

    def test_start_spinner_uses_green(self):
        ui = _make_ui(ansi=True)
        with patch("sys.stdout"):
            ui.start_spinner("transcribing")
            self.assertEqual(ui._spinner_color, _GREEN)
            ui.close()

    def test_start_warm_spinner_plain_output(self):
        ui = _make_ui(ansi=False)
        with patch("builtins.print") as mock_print:
            ui.start_warm_spinner("warming up")
        mock_print.assert_called_once_with("[warming up...]")

    def test_start_warm_spinner_uses_yellow(self):
        ui = _make_ui(ansi=True)
        with patch("sys.stdout"):
            ui.start_warm_spinner("warming up")
            self.assertEqual(ui._spinner_color, _YELLOW)
            ui.close()

    def test_start_warm_spinner_ansi_starts_thread(self):
        ui = _make_ui(ansi=True)
        with patch("sys.stdout"):
            ui.start_warm_spinner("warming up")
            self.assertIsNotNone(ui._spinner_thread)
            self.assertTrue(ui._spinner_thread.is_alive())
            ui.close()

    def test_warm_spinner_then_stop_spinner(self):
        ui = _make_ui(ansi=False)
        with patch("builtins.print") as mock_print:
            ui.start_warm_spinner("warming up")
            ui.stop_spinner("ready", 2.34)
        calls = [c.args[0] for c in mock_print.call_args_list]
        self.assertIn("[warming up...]", calls)
        self.assertIn("[ready 2.34s]", calls)


# ── print_exchange ────────────────────────────────────────────────────────────

class TestPrintExchange(unittest.TestCase):
    def _capture(self, ui: TerminalUI, speaker: str, text: str) -> str:
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            ui._use_ansi = False  # disable newline emission
            ui.print_exchange(speaker, text)
        return buf.getvalue()

    def test_user_line_format(self):
        ui = _make_ui(ansi=False)
        out = self._capture(ui, "you", "hello")
        # Plain output: should contain "you" and the text
        self.assertIn("you", out)
        self.assertIn("hello", out)

    def test_bot_line_format(self):
        ui = _make_ui(ansi=False)
        out = self._capture(ui, "testbot", "hi there")
        self.assertIn("testbot", out)
        self.assertIn("hi there", out)

    def test_bot_gets_trailing_blank_line(self):
        ui = _make_ui(ansi=False)
        out = self._capture(ui, "testbot", "response")
        self.assertTrue(out.endswith("\n\n"))

    def test_user_has_no_trailing_blank_line(self):
        ui = _make_ui(ansi=False)
        out = self._capture(ui, "you", "question")
        self.assertFalse(out.endswith("\n\n"))

    def test_multiline_text_indents_continuation(self):
        ui = _make_ui(ansi=False)
        out = self._capture(ui, "you", "line one\nline two")
        self.assertIn("line one", out)
        self.assertIn("line two", out)
        lines = out.splitlines()
        # continuation line should be indented further than first line
        self.assertGreater(len(lines[1]) - len(lines[1].lstrip()), 0)

    def test_ansi_emits_leading_newline(self):
        ui = _make_ui(ansi=True)
        writes = []
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.write.side_effect = writes.append
            mock_stdout.flush = lambda: None
            with patch("builtins.print"):
                ui.print_exchange("you", "hi")
        self.assertTrue(any("\n" in w for w in writes))

    def test_empty_text_does_not_raise(self):
        ui = _make_ui(ansi=False)
        with patch("builtins.print"):
            ui.print_exchange("you", "")

    def test_none_text_does_not_raise(self):
        ui = _make_ui(ansi=False)
        with patch("builtins.print"):
            ui.print_exchange("you", None)


# ── close ─────────────────────────────────────────────────────────────────────

class TestClose(unittest.TestCase):
    def test_close_plain_no_output(self):
        ui = _make_ui(ansi=False)
        with patch("builtins.print") as mock_print:
            ui.close()
        mock_print.assert_not_called()

    def test_close_ansi_clears_line(self):
        ui = _make_ui(ansi=True)
        with patch("sys.stdout") as mock_stdout:
            ui.close()
        output = "".join(call[0][0] for call in mock_stdout.write.call_args_list)
        self.assertIn("\r\033[K", output)

    def test_close_stops_spinner(self):
        ui = _make_ui(ansi=True)
        with patch("sys.stdout"):
            ui.start_spinner("waiting")
            ui.close()  # single patch scope so thread never writes outside it
        self.assertTrue(ui._spinner_stop.is_set())

    def test_close_idempotent(self):
        ui = _make_ui(ansi=False)
        ui.close()
        ui.close()  # should not raise


# ── status line helpers ───────────────────────────────────────────────────────

class TestStatusLine(unittest.TestCase):
    def test_status_line_contains_wake_phrase(self):
        ui = _make_ui(ansi=True)
        line = ui._status_line("\033[32mwaiting\033[0m")
        self.assertIn("test bot", line)

    def test_status_line_contains_right_text(self):
        ui = _make_ui(ansi=True)
        line = ui._status_line("waiting")
        self.assertIn("waiting", line)

    def test_status_line_uses_separator(self):
        ui = _make_ui(ansi=True)
        line = ui._status_line("x")
        self.assertIn("─", line)

    def test_ansi_re_strips_codes(self):
        text = "\033[32mhello\033[0m world"
        self.assertEqual(_ANSI_RE.sub("", text), "hello world")

    def test_cols_returns_int(self):
        ui = _make_ui()
        self.assertIsInstance(ui._cols(), int)
        self.assertGreater(ui._cols(), 0)


# ── spinner frames ────────────────────────────────────────────────────────────

class TestSpinnerFrames(unittest.TestCase):
    def test_frames_defined(self):
        self.assertGreater(len(_SPINNER_FRAMES), 0)

    def test_spin_loop_cycles_frames(self):
        ui = _make_ui(ansi=True)
        ui._spinner_label = "test"
        written = []

        call_count = {"n": 0}

        def fake_wait(timeout=None):
            call_count["n"] += 1
            if call_count["n"] >= 3:
                return True  # signal stop on 3rd call so 2 frames are written first
            return False

        with patch("sys.stdout") as mock_stdout:
            mock_stdout.write.side_effect = written.append
            mock_stdout.flush = lambda: None
            with patch.object(ui._spinner_stop, "wait", side_effect=fake_wait):
                ui._spin_loop()  # runs synchronously, no real time passes

        # Should have written 2 frames (iterations 1 and 2 before stop on iteration 3)
        self.assertGreaterEqual(len(written), 2)


if __name__ == "__main__":
    unittest.main()
