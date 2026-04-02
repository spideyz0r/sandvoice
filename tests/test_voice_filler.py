import logging
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock

from common.voice_filler import VoiceFillerCache, _slugify, _content_hash


class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(_slugify("One sec."), "one_sec")

    def test_with_comma(self):
        self.assertEqual(_slugify("Got it, checking now."), "got_it_checking_now")

    def test_multiple_spaces(self):
        self.assertEqual(_slugify("  hello   world  "), "hello_world")

    def test_empty_after_strip(self):
        self.assertEqual(_slugify("!!!"), "phrase")

    def test_numbers(self):
        self.assertEqual(_slugify("Step 2 done."), "step_2_done")


class TestContentHash(unittest.TestCase):
    def test_deterministic(self):
        h1 = _content_hash("One sec.", "alloy", "tts-1")
        h2 = _content_hash("One sec.", "alloy", "tts-1")
        self.assertEqual(h1, h2)

    def test_length(self):
        self.assertEqual(len(_content_hash("phrase", "voice", "model")), 16)

    def test_differs_on_phrase(self):
        h1 = _content_hash("One sec.", "alloy", "tts-1")
        h2 = _content_hash("Two sec.", "alloy", "tts-1")
        self.assertNotEqual(h1, h2)

    def test_differs_on_voice(self):
        h1 = _content_hash("One sec.", "alloy", "tts-1")
        h2 = _content_hash("One sec.", "nova", "tts-1")
        self.assertNotEqual(h1, h2)

    def test_differs_on_model(self):
        h1 = _content_hash("One sec.", "alloy", "tts-1")
        h2 = _content_hash("One sec.", "alloy", "tts-1-hd")
        self.assertNotEqual(h1, h2)

    def test_differs_on_language(self):
        h1 = _content_hash("One sec.", "alloy", "tts-1", "")
        h2 = _content_hash("One sec.", "alloy", "tts-1", "pt")
        self.assertNotEqual(h1, h2)

    def test_no_language_matches_empty_string(self):
        h1 = _content_hash("One sec.", "alloy", "tts-1")
        h2 = _content_hash("One sec.", "alloy", "tts-1", "")
        self.assertEqual(h1, h2)


class TestVoiceFillerCacheBase(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "sandvoice.db")

        self.config = Mock()
        self.config.scheduler_db_path = self._db_path
        self.config.bot_voice_model = "alloy"
        self.config.text_to_speech_model = "tts-1"
        self.config.voice_filler_phrases = [
            "One sec.",
            "Got it, checking now.",
        ]
        self.config.speech_to_text_task = "translate"
        self.config.speech_to_text_language = ""
        self.config.gpt_response_model = "gpt-3.5-turbo"

        self.ai = Mock()

    def tearDown(self):
        logging.disable(logging.NOTSET)
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_cache(self):
        return VoiceFillerCache(self.config, self.ai)


class TestVoiceFillerWarm(TestVoiceFillerCacheBase):
    def test_warm_generates_missing_files(self):
        # ai.text_to_speech returns a temp file
        def fake_tts(phrase):
            tmp = tempfile.NamedTemporaryFile(
                suffix=".mp3", delete=False, dir=self._tmpdir
            )
            tmp.write(b"audio")
            tmp.close()
            return [tmp.name]

        self.ai.text_to_speech.side_effect = fake_tts

        cache = self._make_cache()
        cache.warm()

        filler_dir = os.path.join(self._tmpdir, "voice_filler")
        self.assertTrue(os.path.isdir(filler_dir))
        self.assertTrue(os.path.isfile(os.path.join(filler_dir, "one_sec.mp3")))
        self.assertTrue(os.path.isfile(os.path.join(filler_dir, "got_it_checking_now.mp3")))

    def test_warm_skips_empty_phrases(self):
        self.config.voice_filler_phrases = []
        cache = self._make_cache()
        cache.warm()
        self.ai.text_to_speech.assert_not_called()

    def test_warm_raises_on_tts_failure(self):
        self.ai.text_to_speech.side_effect = RuntimeError("TTS failed")
        cache = self._make_cache()
        with self.assertRaises(RuntimeError):
            cache.warm()

    def test_warm_uses_cache_hit(self):
        """Second warm call should skip generation for already-valid files."""
        def fake_tts(phrase):
            tmp = tempfile.NamedTemporaryFile(
                suffix=".mp3", delete=False, dir=self._tmpdir
            )
            tmp.write(b"audio")
            tmp.close()
            return [tmp.name]

        self.ai.text_to_speech.side_effect = fake_tts

        cache = self._make_cache()
        cache.warm()
        call_count_after_first = self.ai.text_to_speech.call_count

        # Second warm — files exist and hash is valid; should not regenerate
        cache2 = self._make_cache()
        cache2.warm()
        self.assertEqual(self.ai.text_to_speech.call_count, call_count_after_first)

    def test_warm_regenerates_on_voice_change(self):
        """Changing the voice should trigger regeneration."""
        def fake_tts(phrase):
            tmp = tempfile.NamedTemporaryFile(
                suffix=".mp3", delete=False, dir=self._tmpdir
            )
            tmp.write(b"audio")
            tmp.close()
            return [tmp.name]

        self.ai.text_to_speech.side_effect = fake_tts

        cache = self._make_cache()
        cache.warm()
        calls_first = self.ai.text_to_speech.call_count

        # Change voice — hash will differ
        self.config.bot_voice_model = "nova"
        cache2 = self._make_cache()
        cache2.warm()
        self.assertGreater(self.ai.text_to_speech.call_count, calls_first)


class TestPickRandomPath(TestVoiceFillerCacheBase):
    def test_returns_none_when_empty(self):
        cache = self._make_cache()
        self.assertIsNone(cache.pick_random_path())

    def test_returns_path_after_warm(self):
        def fake_tts(phrase):
            tmp = tempfile.NamedTemporaryFile(
                suffix=".mp3", delete=False, dir=self._tmpdir
            )
            tmp.write(b"audio")
            tmp.close()
            return [tmp.name]

        self.ai.text_to_speech.side_effect = fake_tts

        cache = self._make_cache()
        cache.warm()

        path = cache.pick_random_path()
        self.assertIsNotNone(path)
        self.assertTrue(path.endswith(".mp3"))
        self.assertTrue(os.path.isfile(path))

    def test_pick_is_random(self):
        """With 2+ phrases, pick_random_path should return varying results."""
        def fake_tts(phrase):
            tmp = tempfile.NamedTemporaryFile(
                suffix=".mp3", delete=False, dir=self._tmpdir
            )
            tmp.write(b"audio")
            tmp.close()
            return [tmp.name]

        self.ai.text_to_speech.side_effect = fake_tts
        self.config.voice_filler_phrases = [
            "One sec.",
            "Got it, checking now.",
            "Okay, give me a moment.",
            "Let me check that.",
            "Sure, one moment.",
        ]

        cache = self._make_cache()
        cache.warm()

        results = {cache.pick_random_path() for _ in range(30)}
        # With 5 phrases and 30 draws, extremely unlikely to always hit the same one
        self.assertGreater(len(results), 1)


class TestSQLiteTable(TestVoiceFillerCacheBase):
    def test_table_created_on_warm(self):
        def fake_tts(phrase):
            tmp = tempfile.NamedTemporaryFile(
                suffix=".mp3", delete=False, dir=self._tmpdir
            )
            tmp.write(b"audio")
            tmp.close()
            return [tmp.name]

        self.ai.text_to_speech.side_effect = fake_tts
        cache = self._make_cache()
        cache.warm()

        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT filename FROM voice_filler_cache ORDER BY filename"
            ).fetchall()
        filenames = [r[0] for r in rows]
        self.assertIn("one_sec.mp3", filenames)
        self.assertIn("got_it_checking_now.mp3", filenames)


class TestVoiceFillerTranslation(TestVoiceFillerCacheBase):
    """Tests for language-aware phrase translation during warm()."""

    def _fake_tts(self, phrase):
        tmp = tempfile.NamedTemporaryFile(
            suffix=".mp3", delete=False, dir=self._tmpdir
        )
        tmp.write(b"audio")
        tmp.close()
        return [tmp.name]

    def _make_completion(self, text):
        """Build a minimal mock that looks like an OpenAI chat completion."""
        choice = Mock()
        choice.message.content = text
        completion = Mock()
        completion.choices = [choice]
        return completion

    def test_no_translation_when_task_is_translate(self):
        """Default task=translate should not call the AI for translation."""
        self.config.speech_to_text_task = "translate"
        self.config.speech_to_text_language = "pt"
        self.ai.text_to_speech.side_effect = self._fake_tts

        cache = self._make_cache()
        cache.warm()

        self.ai.openai_client.chat.completions.create.assert_not_called()

    def test_no_translation_when_language_empty(self):
        """task=transcribe but no language set — no translation call."""
        self.config.speech_to_text_task = "transcribe"
        self.config.speech_to_text_language = ""
        self.ai.text_to_speech.side_effect = self._fake_tts

        cache = self._make_cache()
        cache.warm()

        self.ai.openai_client.chat.completions.create.assert_not_called()

    def test_translation_called_when_transcribe_and_language_set(self):
        """task=transcribe + language triggers a single translation AI call."""
        self.config.speech_to_text_task = "transcribe"
        self.config.speech_to_text_language = "pt"
        self.ai.text_to_speech.side_effect = self._fake_tts
        self.ai.openai_client.chat.completions.create.return_value = self._make_completion(
            "1. Um segundo.\n2. Entendido, verificando agora."
        )

        cache = self._make_cache()
        cache.warm()

        self.ai.openai_client.chat.completions.create.assert_called_once()
        # TTS should be called with the translated phrases, not the originals
        tts_calls = [call.args[0] for call in self.ai.text_to_speech.call_args_list]
        self.assertIn("Um segundo.", tts_calls)
        self.assertIn("Entendido, verificando agora.", tts_calls)

    def test_filenames_use_original_english_slugs(self):
        """Even with translation, filenames are based on the original English phrase."""
        self.config.speech_to_text_task = "transcribe"
        self.config.speech_to_text_language = "pt"
        self.ai.text_to_speech.side_effect = self._fake_tts
        self.ai.openai_client.chat.completions.create.return_value = self._make_completion(
            "1. Um segundo.\n2. Entendido, verificando agora."
        )

        cache = self._make_cache()
        cache.warm()

        filler_dir = os.path.join(self._tmpdir, "voice_filler")
        self.assertTrue(os.path.isfile(os.path.join(filler_dir, "one_sec.mp3")))
        self.assertTrue(os.path.isfile(os.path.join(filler_dir, "got_it_checking_now.mp3")))

    def test_falls_back_to_originals_on_translation_failure(self):
        """If the AI call raises, warm() still succeeds using English phrases."""
        self.config.speech_to_text_task = "transcribe"
        self.config.speech_to_text_language = "pt"
        self.ai.text_to_speech.side_effect = self._fake_tts
        self.ai.openai_client.chat.completions.create.side_effect = RuntimeError("API error")

        cache = self._make_cache()
        cache.warm()  # must not raise

        tts_calls = [call.args[0] for call in self.ai.text_to_speech.call_args_list]
        self.assertIn("One sec.", tts_calls)
        self.assertIn("Got it, checking now.", tts_calls)

    def test_falls_back_when_translation_count_mismatch(self):
        """If the AI returns fewer phrases than expected, fall back to originals."""
        self.config.speech_to_text_task = "transcribe"
        self.config.speech_to_text_language = "pt"
        self.ai.text_to_speech.side_effect = self._fake_tts
        # Only 1 translation returned for 2 phrases
        self.ai.openai_client.chat.completions.create.return_value = self._make_completion(
            "1. Um segundo."
        )

        cache = self._make_cache()
        cache.warm()

        tts_calls = [call.args[0] for call in self.ai.text_to_speech.call_args_list]
        self.assertIn("One sec.", tts_calls)
        self.assertIn("Got it, checking now.", tts_calls)

    def test_language_change_triggers_regeneration(self):
        """Changing speech_to_text_language invalidates the cache and regenerates files."""
        self.config.speech_to_text_task = "transcribe"
        self.config.speech_to_text_language = ""
        self.ai.text_to_speech.side_effect = self._fake_tts

        # First warm — no language, English files
        cache = self._make_cache()
        cache.warm()
        calls_first = self.ai.text_to_speech.call_count

        # Now switch to Portuguese — hash changes, must regenerate
        self.config.speech_to_text_language = "pt"
        self.ai.openai_client.chat.completions.create.return_value = self._make_completion(
            "1. Um segundo.\n2. Entendido, verificando agora."
        )
        cache2 = self._make_cache()
        cache2.warm()

        self.assertGreater(self.ai.text_to_speech.call_count, calls_first)


if __name__ == "__main__":
    unittest.main()
