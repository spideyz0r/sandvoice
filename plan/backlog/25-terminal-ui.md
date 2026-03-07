# Terminal UI

**Status**: 📋 Backlog
**Priority**: 25
**Platforms**: macOS M1, Raspberry Pi 3B

---

## Overview

Replace the current flat emoji-based terminal output with a high-end CLI UI experience: ANSI colors, animated waiting indicators, inline timing, and clear visual separation between status and conversation. No external UI libraries — pure ANSI escape codes, lightweight enough for Raspberry Pi.

---

## Problem Statement

Current output is minimal and hard to read at a glance:

```
⏸️  Waiting for wake word ('sand voice')...
🎤 Listening...
⚙️  Processing...
🔊 Responding...
You: como está o tempo?
Sandbot: Agora em Stoney Creek...
```

- Emoji-dependent (breaks on some terminals/Pi)
- No timing information
- No visual hierarchy between status and conversation
- No feedback during async waits (transcribing, routing, LLM)
- State changes scroll the terminal rather than updating in place

---

## Proposed Design

### Status line (updates in place)

```
 ◉  sand voice  ──────────────────────────────────── waiting
 ◉  sand voice  ──────────────────────────────── ● listening
 ◉  sand voice  ─────────── transcribing ●●●
 ◉  sand voice  ──────────────── routing ●●●
 ◉  sand voice  ─── weather › cache:hit-fresh  0.05s
 ◉  sand voice  ──────────────────── responding ███████░░░
```

- Bot name in green, dim separator line, state label on the right
- Animated `●●●` dots cycle during async waits (transcribing, routing, LLM)
- Phase label replaced inline when phase completes, with elapsed time
- Playback progress bar advances as audio plays (based on estimated duration)

### Conversation output (scrolling, below status)

```
  you      como está o tempo?
  sandbot  Agora em Stoney Creek: névoa, 1,1°C (sensação −3,6°C),
           vento NNE ≈19 km/h, umidade 95%.
```

- `you` dimmed/grey, `sandbot` in green
- Multi-line responses indented to align with first line
- Blank line between exchanges

### Color palette

| Element | Color |
|---|---|
| Bot name / sandbot label | Bright green |
| Status label (waiting, listening...) | Green |
| Animated dots | Green |
| Separator line | Dim white |
| `you` label | Dim |
| Timing info | Dim cyan |
| Error states | Red |
| Normal text | Default terminal color |

---

## Implementation Notes

### New module: `common/terminal_ui.py`

Encapsulates all ANSI rendering. Public API:

```python
class TerminalUI:
    def set_state(self, state: str, detail: str = "") -> None:
        # Updates status line in place; starts/stops dot animation

    def start_spinner(self, label: str) -> None:
        # Starts animated ●●● in the status line

    def stop_spinner(self, label: str, elapsed_s: float) -> None:
        # Replaces spinner with completed label + timing

    def print_exchange(self, speaker: str, text: str) -> None:
        # Prints a conversation turn below the status line

    def start_playback_bar(self, duration_s: float) -> None:
        # Starts a progress bar that fills over duration_s seconds

    def close(self) -> None:
        # Clears status line, resets cursor
```

### Spinner thread
- Dedicated daemon thread cycles `● `, `●● `, `●●●`, ` ●●`, `  ●` at ~200ms
- Uses `\r` + ANSI clear-to-EOL to update in place
- Stops cleanly when `stop_spinner()` called

### TTY guard
```python
self._tty = sys.stdout.isatty()
# If not a TTY, fall back to plain print() with no ANSI
```

### Integration points
- `common/wake_word.py` — replace all state `print()` calls with `ui.set_state()`
- `sandvoice.py` — instantiate `TerminalUI`, pass to `WakeWordMode`
- `--cli` mode — simpler variant (no spinner, no in-place updates)
- Integrates naturally with Plan 23 timing output (spinner stop shows elapsed time inline)

### Pi compatibility
- No `curses`, no `rich`, no `blessed`
- Pure ANSI codes: `\033[2K` (clear line), `\033[1A` (cursor up), `\033[0m` (reset), `\033[32m` (green)
- Test on 80-column terminal width; truncate separator line accordingly
- If `$TERM` is `dumb` or not set, fall back to plain output

---

## Files to Touch

| File | Change |
|---|---|
| `common/terminal_ui.py` | New module — all ANSI rendering logic |
| `common/wake_word.py` | Replace `print()` state changes with `ui.*` calls |
| `sandvoice.py` | Instantiate `TerminalUI`, pass to `WakeWordMode` |
| `tests/test_terminal_ui.py` | New — mock TTY, assert correct ANSI sequences |

---

## Out of Scope

- Full-screen / curses takeover
- Mouse support
- `rich` or any third-party UI library
- Windows terminal compatibility (not a target platform)

---

## Acceptance Criteria

- [ ] Status line updates in place (no scroll) during state transitions
- [ ] Animated dots visible during transcribing, routing, LLM wait
- [ ] Green color on bot name and state labels
- [ ] Inline elapsed time shown when each phase completes
- [ ] Conversation output clearly separated from status line
- [ ] Falls back to plain text when not a TTY
- [ ] Works on 80-column terminal (Pi default)
- [ ] No external dependencies added
- [ ] >80% test coverage on `terminal_ui.py`
