import concurrent.futures
import hashlib
import logging
import os
import re
import shutil
import sqlite3
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_DEFAULT_PHRASES = [
    "One sec.",
    "Got it, checking now.",
    "Okay, give me a moment.",
    "Let me check that.",
    "Sure, one moment.",
]


def _slugify(phrase):
    """Convert a phrase to a safe filename stem.

    >>> _slugify("One sec.")
    'one_sec'
    >>> _slugify("Got it, checking now.")
    'got_it_checking_now'
    """
    s = phrase.lower()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", "_", s.strip())
    return s or "phrase"


def _content_hash(phrase, voice, tts_model):
    """Short deterministic hash of phrase + voice + TTS model.

    Changes whenever the phrase text, voice, or TTS model changes,
    triggering regeneration of the cached audio file.
    """
    raw = f"{phrase}|{voice}|{tts_model}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class VoiceFillerCache:
    """Pre-generates and caches short filler phrase audio for wake-word mode.

    Files are stored in ``<sandvoice_db_dir>/voice_filler/`` with human-readable
    names derived from the phrase text (e.g. ``one_sec.mp3``).

    A ``voice_filler_cache`` table in the shared SQLite DB validates content
    hashes so files are only regenerated when the phrase, TTS voice, or model
    changes between boots.

    Intended usage::

        cache = VoiceFillerCache(config, ai)
        cache.warm()                   # call from WarmPhase — blocks, raises on failure
        path = cache.pick_random_path()  # call on the hot path — instant
    """

    def __init__(self, config, ai):
        self._config = config
        self._ai = ai
        self._lock = threading.Lock()
        self._ready_files = []   # list of (phrase, abs_path)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def warm(self):
        """Generate any missing or stale phrase files.

        Blocks until all phrases are ready.  Raises on any failure so the
        WarmPhase can abort boot.
        """
        phrases = self._phrases
        if not phrases:
            logger.debug("voice_filler_phrases is empty — skipping filler warm")
            return

        os.makedirs(self._filler_dir, exist_ok=True)
        self._ensure_table()

        to_generate = []
        for phrase in phrases:
            filename = _slugify(phrase) + ".mp3"
            path = os.path.join(self._filler_dir, filename)
            expected = _content_hash(phrase, self._voice, self._tts_model)
            if self._cache_valid(filename, path, expected):
                logger.debug("Voice filler cache hit: %s", filename)
                with self._lock:
                    self._ready_files.append((phrase, path))
            else:
                to_generate.append((phrase, filename, path, expected))

        if to_generate:
            logger.info(
                "Generating %d voice filler file(s) — only happens when phrases or voice config changes",
                len(to_generate),
            )
            max_workers = min(len(to_generate), 4)
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = {
                    ex.submit(self._generate_one, phrase, filename, path, expected): phrase
                    for phrase, filename, path, expected in to_generate
                }
                for future in concurrent.futures.as_completed(futures):
                    future.result()  # re-raises on failure

        logger.debug("Voice filler ready: %d phrase(s)", len(self._ready_files))

    def pick_random_path(self):
        """Return a random pre-generated file path, or None if none available."""
        import random
        with self._lock:
            if not self._ready_files:
                return None
            return random.choice(self._ready_files)[1]

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def _filler_dir(self):
        db_dir = os.path.dirname(self._config.scheduler_db_path)
        return os.path.join(db_dir, "voice_filler")

    @property
    def _phrases(self):
        return list(self._config.voice_filler_phrases or [])

    @property
    def _voice(self):
        return self._config.bot_voice_model

    @property
    def _tts_model(self):
        return self._config.text_to_speech_model

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _cache_valid(self, filename, path, expected_hash):
        if not os.path.isfile(path):
            return False
        return self._get_db_hash(filename) == expected_hash

    def _generate_one(self, phrase, filename, path, expected_hash):
        try:
            tts_files = self._ai.text_to_speech(phrase)
            if not tts_files:
                raise RuntimeError(f"TTS returned no files for phrase: {phrase!r}")
            shutil.move(tts_files[0], path)
            self._upsert_db(filename, expected_hash)
            logger.debug("Generated voice filler: %s", filename)
            with self._lock:
                self._ready_files.append((phrase, path))
        except Exception as e:
            logger.error("Failed to generate voice filler '%s': %s", filename, e)
            raise

    def _ensure_table(self):
        with sqlite3.connect(self._config.scheduler_db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS voice_filler_cache (
                    filename     TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    created_at   TEXT NOT NULL
                )
            """)
            conn.commit()

    def _get_db_hash(self, filename):
        try:
            with sqlite3.connect(self._config.scheduler_db_path) as conn:
                row = conn.execute(
                    "SELECT content_hash FROM voice_filler_cache WHERE filename = ?",
                    (filename,),
                ).fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def _upsert_db(self, filename, content_hash):
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self._config.scheduler_db_path) as conn:
            conn.execute(
                """
                INSERT INTO voice_filler_cache (filename, content_hash, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(filename) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    created_at   = excluded.created_at
                """,
                (filename, content_hash, now),
            )
            conn.commit()
