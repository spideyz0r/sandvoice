import concurrent.futures
import hashlib
import logging
import os
import re
import shutil
import sqlite3
import threading
from datetime import datetime, timezone

from common.db import _SQLITE_BUSY_TIMEOUT_S

logger = logging.getLogger(__name__)


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


def _content_hash(phrase, voice, tts_model, language=""):
    """Short deterministic hash of phrase + voice + TTS model + language.

    Changes whenever the phrase text, voice, TTS model, or target language
    changes, triggering regeneration of the cached audio file.
    """
    raw = f"{phrase}|{voice}|{tts_model}|{language}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class VoiceFillerCache:
    """Pre-generates and caches short filler phrase audio for wake-word mode.

    Files are stored in ``<sandvoice_db_dir>/voice_filler/`` with human-readable
    names derived from the phrase text (e.g. ``one_sec.mp3``).

    A ``voice_filler_cache`` table in the shared SQLite DB validates content
    hashes so files are only regenerated when the phrase, TTS voice, model,
    or target language changes between boots.

    When ``speech_to_text_task`` is ``transcribe`` and ``speech_to_text_language``
    is set, phrases are translated to that language via a single AI call before
    TTS generation.  The original English phrase is used as the filename slug and
    DB key; only the text fed to TTS changes.

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

        Translates phrases to the configured language (when applicable) via a
        single AI call, then generates TTS files in parallel.

        Blocks until all phrases are ready.  Raises on any failure so the
        WarmPhase can abort boot.
        """
        phrases = self._phrases
        if not phrases:
            logger.debug("voice_filler_phrases is empty — skipping filler warm")
            return

        with self._lock:
            self._ready_files.clear()

        # Detect slug collisions up front to prevent silent overwrites.
        seen_filenames = {}
        for phrase in phrases:
            fn = _slugify(phrase) + ".mp3"
            if fn in seen_filenames:
                raise ValueError(
                    f"voice_filler_phrases contains phrases that map to the same filename {fn!r}: "
                    f"{seen_filenames[fn]!r} and {phrase!r}. Make phrases more distinct."
                )
            seen_filenames[fn] = phrase

        language = self._language

        logger.debug("Voice filler warm started: %d phrase(s), dir=%s", len(phrases), self._filler_dir)
        os.makedirs(self._filler_dir, exist_ok=True)
        self._ensure_table()

        # Check cache first — collect hits and misses before any API calls.
        hits = []   # (phrase, path) — already valid, no work needed
        misses = []  # (phrase, filename, path, expected) — need generation
        for phrase in phrases:
            filename = _slugify(phrase) + ".mp3"
            path = os.path.join(self._filler_dir, filename)
            expected = _content_hash(phrase, self._voice, self._tts_model, language)
            if self._cache_valid(filename, path, expected):
                logger.debug("Voice filler cache hit: %s", filename)
                hits.append((phrase, path))
            else:
                misses.append((phrase, filename, path, expected))

        with self._lock:
            self._ready_files.extend(hits)

        if not misses:
            logger.info("Voice filler ready: %d phrase(s)", len(self._ready_files))
            return

        # Only translate phrases that actually need regeneration.
        miss_phrases = [phrase for phrase, *_ in misses]
        if language:
            logger.info(
                "Translating %d voice filler phrase(s) to '%s'", len(miss_phrases), language
            )
            tts_phrases = self._translate_phrases(miss_phrases, language)
        else:
            tts_phrases = list(miss_phrases)

        to_generate = [
            (phrase, tts_phrase, filename, path, expected)
            for (phrase, filename, path, expected), tts_phrase in zip(misses, tts_phrases)
        ]

        logger.info(
            "Generating %d voice filler file(s) — only happens when phrases, voice config, or language changes",
            len(to_generate),
        )
        max_workers = min(len(to_generate), 4)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {
                ex.submit(self._generate_one, phrase, tts_phrase, filename, path, expected): phrase
                for phrase, tts_phrase, filename, path, expected in to_generate
            }
            for future in concurrent.futures.as_completed(futures):
                future.result()  # re-raises on failure

        logger.info("Voice filler ready: %d phrase(s)", len(self._ready_files))

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

    @property
    def _language(self):
        """Target language for filler phrases, or empty string for no translation.

        Translation is only needed when speech_to_text_task is 'transcribe' and
        a specific language is configured — in that mode the user speaks (and
        expects responses) in that language.  When task is 'translate', Whisper
        already translates input to English and the bot responds in English, so
        English fillers are correct.
        """
        if self._config.speech_to_text_task == "transcribe":
            return self._config.speech_to_text_language or ""
        return ""

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _translate_phrases(self, phrases, language):
        """Translate phrases to target language via a single AI call.

        Returns a list of translated phrases in the same order as the input.
        Falls back to the original phrases on any failure (translation is
        best-effort — boot should not fail because of it).
        """
        numbered = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(phrases))
        prompt = (
            f"Translate these short voice assistant filler phrases to {language}. "
            "Return ONLY the translations as a numbered list in the same order. "
            "Keep them natural and conversational.\n\n"
            + numbered
        )
        try:
            completion = self._ai.openai_client.chat.completions.create(
                model=self._config.gpt_response_model,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = completion.choices[0].message.content.strip()
            translated = []
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                match = re.match(r"^\d+[.)]\s*(.+)$", line)
                if match:
                    translated.append(match.group(1).strip())
            if len(translated) == len(phrases):
                logger.debug("Translated %d phrase(s) to '%s'", len(translated), language)
                return translated
            logger.warning(
                "Translation returned %d phrase(s) for %d input(s) to '%s' — using originals",
                len(translated), len(phrases), language,
            )
            return list(phrases)
        except Exception as e:
            logger.warning(
                "Failed to translate voice filler phrases to '%s': %s — using originals",
                language, e,
            )
            return list(phrases)

    def _cache_valid(self, filename, path, expected_hash):
        if not os.path.isfile(path):
            return False
        return self._get_db_hash(filename) == expected_hash

    def _generate_one(self, phrase, tts_phrase, filename, path, expected_hash):
        try:
            tts_files = self._ai.text_to_speech(tts_phrase)
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
        dir_name = os.path.dirname(self._config.scheduler_db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with sqlite3.connect(self._config.scheduler_db_path, timeout=_SQLITE_BUSY_TIMEOUT_S) as conn:
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
            with sqlite3.connect(self._config.scheduler_db_path, timeout=_SQLITE_BUSY_TIMEOUT_S) as conn:
                row = conn.execute(
                    "SELECT content_hash FROM voice_filler_cache WHERE filename = ?",
                    (filename,),
                ).fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.debug("Failed to read content_hash for '%s' from DB: %s", filename, e)
            return None

    def _upsert_db(self, filename, content_hash):
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self._config.scheduler_db_path, timeout=_SQLITE_BUSY_TIMEOUT_S) as conn:
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
