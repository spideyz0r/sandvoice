import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from common.prompt import build_system_role

_FIXED_NOW = datetime(2026, 4, 17, 10, 30, 0)


def _config(**kwargs):
    defaults = dict(
        botname="Sandbot",
        language="English",
        timezone="America/Toronto",
        location="Toronto, ON",
        verbosity="brief",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestBuildSystemRoleBrief(unittest.TestCase):
    def setUp(self):
        self.patcher = patch("common.prompt.datetime")
        mock_dt = self.patcher.start()
        mock_dt.datetime.now.return_value = _FIXED_NOW

    def tearDown(self):
        self.patcher.stop()

    def test_contains_botname(self):
        result = build_system_role(_config())
        self.assertIn("Sandbot", result)

    def test_contains_language(self):
        result = build_system_role(_config())
        self.assertIn("English", result)

    def test_contains_timezone(self):
        result = build_system_role(_config())
        self.assertIn("America/Toronto", result)

    def test_contains_location(self):
        result = build_system_role(_config())
        self.assertIn("Toronto, ON", result)

    def test_contains_fixed_datetime(self):
        result = build_system_role(_config())
        self.assertIn("2026-04-17 10:30:00", result)

    def test_brief_verbosity_instruction(self):
        result = build_system_role(_config(verbosity="brief"))
        self.assertIn("Verbosity: brief", result)
        self.assertNotIn("Verbosity: normal", result)
        self.assertNotIn("Verbosity: detailed", result)

    def test_no_extra_info_not_appended(self):
        result = build_system_role(_config())
        self.assertNotIn("Consider the following", result)

    def test_extra_info_appended(self):
        result = build_system_role(_config(), extra_info="It is raining.")
        self.assertIn("Consider the following to answer your question: It is raining.", result)

    def test_extra_info_none_omitted(self):
        result = build_system_role(_config(), extra_info=None)
        self.assertNotIn("Consider the following", result)

    def test_exact_output_brief_no_extra(self):
        cfg = _config()
        result = build_system_role(cfg)
        expected = f"""
            Your name is Sandbot.
            You are an assistant written in Python by Breno Brand.
            You must answer in English.
            The person that is talking to you is in the America/Toronto time zone.
            The person that is talking to you is located in Toronto, ON.
            Current date and time to be considered when answering the message: 2026-04-17 10:30:00.
            Never answer as a chat, for example reading your name in a conversation.
            DO NOT reply to messages with the format "Sandbot": <message here>.
            Never use symbols, always spell it out. For example say degrees instead of using the symbol. Don't say km/h, but kilometers per hour, and so on.
            Reply in a natural and human way.
            Verbosity: brief. Keep answers short by default (1-3 sentences). Avoid long lists and excessive detail unless the user explicitly asks to expand, asks for details, or says they want a longer answer.
            """
        self.assertEqual(result, expected)

    def test_exact_output_brief_with_extra(self):
        cfg = _config()
        result = build_system_role(cfg, extra_info="Weather is sunny.")
        expected = f"""
            Your name is Sandbot.
            You are an assistant written in Python by Breno Brand.
            You must answer in English.
            The person that is talking to you is in the America/Toronto time zone.
            The person that is talking to you is located in Toronto, ON.
            Current date and time to be considered when answering the message: 2026-04-17 10:30:00.
            Never answer as a chat, for example reading your name in a conversation.
            DO NOT reply to messages with the format "Sandbot": <message here>.
            Never use symbols, always spell it out. For example say degrees instead of using the symbol. Don't say km/h, but kilometers per hour, and so on.
            Reply in a natural and human way.
            Verbosity: brief. Keep answers short by default (1-3 sentences). Avoid long lists and excessive detail unless the user explicitly asks to expand, asks for details, or says they want a longer answer.
            Consider the following to answer your question: Weather is sunny."""
        self.assertEqual(result, expected)


class TestBuildSystemRoleNormal(unittest.TestCase):
    def setUp(self):
        self.patcher = patch("common.prompt.datetime")
        mock_dt = self.patcher.start()
        mock_dt.datetime.now.return_value = _FIXED_NOW

    def tearDown(self):
        self.patcher.stop()

    def test_normal_verbosity_instruction(self):
        result = build_system_role(_config(verbosity="normal"))
        self.assertIn("Verbosity: normal", result)
        self.assertNotIn("Verbosity: brief", result)
        self.assertNotIn("Verbosity: detailed", result)

    def test_exact_output_normal_no_extra(self):
        cfg = _config(verbosity="normal")
        result = build_system_role(cfg)
        expected = f"""
            Your name is Sandbot.
            You are an assistant written in Python by Breno Brand.
            You must answer in English.
            The person that is talking to you is in the America/Toronto time zone.
            The person that is talking to you is located in Toronto, ON.
            Current date and time to be considered when answering the message: 2026-04-17 10:30:00.
            Never answer as a chat, for example reading your name in a conversation.
            DO NOT reply to messages with the format "Sandbot": <message here>.
            Never use symbols, always spell it out. For example say degrees instead of using the symbol. Don't say km/h, but kilometers per hour, and so on.
            Reply in a natural and human way.
            Verbosity: normal. Be concise but complete. Expand when the user explicitly asks for more detail.
            """
        self.assertEqual(result, expected)


class TestBuildSystemRoleDetailed(unittest.TestCase):
    def setUp(self):
        self.patcher = patch("common.prompt.datetime")
        mock_dt = self.patcher.start()
        mock_dt.datetime.now.return_value = _FIXED_NOW

    def tearDown(self):
        self.patcher.stop()

    def test_detailed_verbosity_instruction(self):
        result = build_system_role(_config(verbosity="detailed"))
        self.assertIn("Verbosity: detailed", result)
        self.assertNotIn("Verbosity: brief", result)
        self.assertNotIn("Verbosity: normal", result)

    def test_exact_output_detailed_no_extra(self):
        cfg = _config(verbosity="detailed")
        result = build_system_role(cfg)
        expected = f"""
            Your name is Sandbot.
            You are an assistant written in Python by Breno Brand.
            You must answer in English.
            The person that is talking to you is in the America/Toronto time zone.
            The person that is talking to you is located in Toronto, ON.
            Current date and time to be considered when answering the message: 2026-04-17 10:30:00.
            Never answer as a chat, for example reading your name in a conversation.
            DO NOT reply to messages with the format "Sandbot": <message here>.
            Never use symbols, always spell it out. For example say degrees instead of using the symbol. Don't say km/h, but kilometers per hour, and so on.
            Reply in a natural and human way.
            Verbosity: detailed. Provide thorough, structured answers by default. Include steps/examples when helpful. If the user asks for a short answer, comply.
            """
        self.assertEqual(result, expected)


class TestBuildSystemRoleFallback(unittest.TestCase):
    def setUp(self):
        self.patcher = patch("common.prompt.datetime")
        mock_dt = self.patcher.start()
        mock_dt.datetime.now.return_value = _FIXED_NOW

    def tearDown(self):
        self.patcher.stop()

    def test_unknown_verbosity_falls_back_to_brief(self):
        result = build_system_role(_config(verbosity="unknown"))
        self.assertIn("Verbosity: brief", result)

    def test_missing_verbosity_attribute_falls_back_to_brief(self):
        cfg = SimpleNamespace(
            botname="Sandbot", language="English",
            timezone="UTC", location="Somewhere",
        )
        result = build_system_role(cfg)
        self.assertIn("Verbosity: brief", result)


class TestBuildSystemRoleSystemPromptExtra(unittest.TestCase):
    def setUp(self):
        self.patcher = patch("common.prompt.datetime")
        mock_dt = self.patcher.start()
        mock_dt.datetime.now.return_value = _FIXED_NOW

    def tearDown(self):
        self.patcher.stop()

    def test_absent_leaves_prompt_unchanged(self):
        result = build_system_role(_config())
        self.assertIn("Sandbot", result)
        self.assertIn("Verbosity: brief", result)
        self.assertNotIn("Always respond formally.", result)
        self.assertNotIn("Consider the following", result)

    def test_set_appended_before_extra_info(self):
        cfg = _config(system_prompt_extra="Always respond formally.")
        result = build_system_role(cfg, extra_info="Weather is sunny.")
        formal_pos = result.index("Always respond formally.")
        extra_pos = result.index("Consider the following")
        self.assertLess(formal_pos, extra_pos)

    def test_set_appended_after_persona(self):
        cfg = _config(system_prompt_extra="Always respond formally.")
        result = build_system_role(cfg)
        self.assertIn("Always respond formally.", result)
        verbosity_pos = result.index("Verbosity: brief")
        extra_pos = result.index("Always respond formally.")
        self.assertLess(verbosity_pos, extra_pos)

    def test_blank_value_not_injected(self):
        cfg = _config(system_prompt_extra="   ")
        result = build_system_role(cfg)
        baseline = build_system_role(_config())
        self.assertEqual(result, baseline)

    def test_none_value_not_injected(self):
        cfg = _config(system_prompt_extra=None)
        result = build_system_role(cfg)
        baseline = build_system_role(_config())
        self.assertEqual(result, baseline)

    def test_both_system_prompt_extra_and_extra_info_present(self):
        cfg = _config(system_prompt_extra="Custom instruction.")
        result = build_system_role(cfg, extra_info="It is raining.")
        self.assertIn("Custom instruction.", result)
        self.assertIn("Consider the following to answer your question: It is raining.", result)
        custom_pos = result.index("Custom instruction.")
        extra_info_pos = result.index("Consider the following")
        self.assertLess(custom_pos, extra_info_pos)

    def test_value_is_stripped(self):
        cfg = _config(system_prompt_extra="  Trimmed text.  ")
        result = build_system_role(cfg)
        self.assertIn("Trimmed text.", result)
        self.assertNotIn("  Trimmed text.  ", result)


if __name__ == "__main__":
    unittest.main()
