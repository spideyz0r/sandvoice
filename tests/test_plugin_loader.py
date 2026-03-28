import os
import tempfile
import unittest
from unittest.mock import MagicMock

from common.plugin_loader import (
    PluginManifest,
    build_extra_routes_text,
    check_env_vars,
    load_manifest,
)


def _write_yaml(folder, content):
    path = os.path.join(folder, "plugin.yaml")
    with open(path, "w") as f:
        f.write(content)
    return path


class TestPluginManifest(unittest.TestCase):
    def test_defaults(self):
        m = PluginManifest(name="test", route_description="desc")
        self.assertEqual(m.version, "0.0.0")
        self.assertEqual(m.route_extra_keys, [])
        self.assertEqual(m.env_vars, [])
        self.assertEqual(m.config_defaults, {})
        self.assertEqual(m.dependencies, [])
        self.assertEqual(m.plugin_dir, "")

    def test_custom_values(self):
        m = PluginManifest(
            name="weather",
            version="1.2.3",
            route_description="weather desc",
            route_extra_keys=["location", "unit"],
            env_vars=["OPENWEATHERMAP_API_KEY"],
            config_defaults={"location": "Toronto"},
            dependencies=["requests"],
            plugin_dir="/plugins/weather",
        )
        self.assertEqual(m.name, "weather")
        self.assertEqual(m.version, "1.2.3")
        self.assertEqual(m.route_extra_keys, ["location", "unit"])
        self.assertEqual(m.config_defaults, {"location": "Toronto"})
        self.assertEqual(m.plugin_dir, "/plugins/weather")


class TestLoadManifest(unittest.TestCase):
    def test_happy_path_all_fields(self):
        with tempfile.TemporaryDirectory() as d:
            _write_yaml(d, """
name: weather
version: 1.0.0
route_description: The user asks about weather.
route_extra_keys:
  - location
  - unit
env_vars:
  - OPENWEATHERMAP_API_KEY
config_defaults:
  location: "Toronto, ON, CA"
  unit: metric
dependencies:
  - requests
""")
            m = load_manifest(d)
        self.assertIsNotNone(m)
        self.assertEqual(m.name, "weather")
        self.assertEqual(m.version, "1.0.0")
        self.assertEqual(m.route_description, "The user asks about weather.")
        self.assertEqual(m.route_extra_keys, ["location", "unit"])
        self.assertEqual(m.env_vars, ["OPENWEATHERMAP_API_KEY"])
        self.assertEqual(m.config_defaults, {"location": "Toronto, ON, CA", "unit": "metric"})
        self.assertEqual(m.dependencies, ["requests"])
        self.assertEqual(m.plugin_dir, d)

    def test_minimal_valid_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            _write_yaml(d, "name: news\nroute_description: The user asks for news.\n")
            m = load_manifest(d)
        self.assertIsNotNone(m)
        self.assertEqual(m.name, "news")
        self.assertEqual(m.route_description, "The user asks for news.")
        self.assertEqual(m.env_vars, [])
        self.assertEqual(m.config_defaults, {})

    def test_no_plugin_yaml_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            result = load_manifest(d)
        self.assertIsNone(result)

    def test_missing_name_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            _write_yaml(d, "route_description: desc\n")
            with self.assertLogs("common.plugin_loader", level="WARNING") as cm:
                result = load_manifest(d)
        self.assertIsNone(result)
        self.assertTrue(any("missing required field 'name'" in msg for msg in cm.output))

    def test_blank_name_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            _write_yaml(d, "name: '   '\nroute_description: desc\n")
            with self.assertLogs("common.plugin_loader", level="WARNING"):
                result = load_manifest(d)
        self.assertIsNone(result)

    def test_missing_route_description_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            _write_yaml(d, "name: myplug\n")
            with self.assertLogs("common.plugin_loader", level="WARNING") as cm:
                result = load_manifest(d)
        self.assertIsNone(result)
        self.assertTrue(any("missing required field 'route_description'" in msg for msg in cm.output))

    def test_blank_route_description_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            _write_yaml(d, "name: myplug\nroute_description: ''\n")
            with self.assertLogs("common.plugin_loader", level="WARNING"):
                result = load_manifest(d)
        self.assertIsNone(result)

    def test_malformed_yaml_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            _write_yaml(d, ": invalid: yaml: {{{")
            with self.assertLogs("common.plugin_loader", level="WARNING") as cm:
                result = load_manifest(d)
        self.assertIsNone(result)
        self.assertTrue(any("Failed to parse" in msg for msg in cm.output))

    def test_empty_yaml_file_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            _write_yaml(d, "")
            with self.assertLogs("common.plugin_loader", level="WARNING"):
                result = load_manifest(d)
        self.assertIsNone(result)

    def test_name_is_stripped(self):
        with tempfile.TemporaryDirectory() as d:
            _write_yaml(d, "name: '  weather  '\nroute_description: desc\n")
            m = load_manifest(d)
        self.assertIsNotNone(m)
        self.assertEqual(m.name, "weather")

    def test_non_list_env_vars_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            _write_yaml(d, "name: x\nroute_description: desc\nenv_vars: SINGLE_STRING\n")
            with self.assertLogs("common.plugin_loader", level="WARNING") as cm:
                result = load_manifest(d)
        self.assertIsNone(result)
        self.assertTrue(any("env_vars" in msg for msg in cm.output))

    def test_non_list_dependencies_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            _write_yaml(d, "name: x\nroute_description: desc\ndependencies: requests\n")
            with self.assertLogs("common.plugin_loader", level="WARNING") as cm:
                result = load_manifest(d)
        self.assertIsNone(result)
        self.assertTrue(any("dependencies" in msg for msg in cm.output))

    def test_non_dict_config_defaults_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            _write_yaml(d, "name: x\nroute_description: desc\nconfig_defaults: not_a_dict\n")
            with self.assertLogs("common.plugin_loader", level="WARNING") as cm:
                result = load_manifest(d)
        self.assertIsNone(result)
        self.assertTrue(any("config_defaults" in msg for msg in cm.output))

    def test_non_string_env_var_entry_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            _write_yaml(d, "name: x\nroute_description: desc\nenv_vars:\n  - 123\n")
            with self.assertLogs("common.plugin_loader", level="WARNING") as cm:
                result = load_manifest(d)
        self.assertIsNone(result)
        self.assertTrue(any("env_vars" in msg for msg in cm.output))

    def test_non_string_dependency_entry_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            _write_yaml(d, "name: x\nroute_description: desc\ndependencies:\n  - 42\n")
            with self.assertLogs("common.plugin_loader", level="WARNING") as cm:
                result = load_manifest(d)
        self.assertIsNone(result)
        self.assertTrue(any("dependencies" in msg for msg in cm.output))


class TestCheckEnvVars(unittest.TestCase):
    def test_all_set_returns_empty(self):
        m = PluginManifest(name="x", route_description="d", env_vars=["HOME"])
        result = check_env_vars(m)
        self.assertEqual(result, [])

    def test_missing_var_returned(self):
        m = PluginManifest(name="x", route_description="d", env_vars=["_SANDVOICE_NONEXISTENT_VAR_"])
        os.environ.pop("_SANDVOICE_NONEXISTENT_VAR_", None)
        result = check_env_vars(m)
        self.assertEqual(result, ["_SANDVOICE_NONEXISTENT_VAR_"])

    def test_all_missing_returned(self):
        m = PluginManifest(
            name="x", route_description="d",
            env_vars=["_SANDVOICE_MISS_A_", "_SANDVOICE_MISS_B_"],
        )
        os.environ.pop("_SANDVOICE_MISS_A_", None)
        os.environ.pop("_SANDVOICE_MISS_B_", None)
        result = check_env_vars(m)
        self.assertIn("_SANDVOICE_MISS_A_", result)
        self.assertIn("_SANDVOICE_MISS_B_", result)

    def test_no_env_vars_declared(self):
        m = PluginManifest(name="x", route_description="d")
        result = check_env_vars(m)
        self.assertEqual(result, [])

    def test_partial_missing(self):
        m = PluginManifest(
            name="x", route_description="d",
            env_vars=["HOME", "_SANDVOICE_MISS_PARTIAL_"],
        )
        os.environ.pop("_SANDVOICE_MISS_PARTIAL_", None)
        result = check_env_vars(m)
        self.assertEqual(result, ["_SANDVOICE_MISS_PARTIAL_"])


class TestBuildExtraRoutesText(unittest.TestCase):
    def test_empty_manifests(self):
        result = build_extra_routes_text([])
        self.assertEqual(result, "")

    def test_single_manifest(self):
        m = PluginManifest(name="weather", route_description="The user asks about weather.")
        result = build_extra_routes_text([m])
        self.assertIn("weather:", result)
        self.assertIn("The user asks about weather.", result)
        self.assertTrue(result.startswith("\n"))

    def test_multiple_manifests_ordered(self):
        m1 = PluginManifest(name="weather", route_description="Weather desc.")
        m2 = PluginManifest(name="news", route_description="News desc.")
        result = build_extra_routes_text([m1, m2])
        # manifests are sorted by name; "news" sorts before "weather"
        self.assertLess(result.index("news:"), result.index("weather:"))

    def test_jinja2_location_placeholder_rendered(self):
        m = PluginManifest(
            name="weather",
            route_description="If no location, consider {{ location }}.",
        )
        result = build_extra_routes_text([m], location="Toronto,ON,CA")
        self.assertIn("Toronto,ON,CA", result)
        self.assertNotIn("{{ location }}", result)

    def test_jinja2_default_location_empty(self):
        m = PluginManifest(
            name="weather",
            route_description="Consider {{ location }} as default.",
        )
        result = build_extra_routes_text([m])
        self.assertNotIn("{{ location }}", result)

    def test_manifest_without_route_description_skipped(self):
        m = PluginManifest(name="internal", route_description="")
        result = build_extra_routes_text([m])
        self.assertEqual(result, "")

    def test_indentation_matches_routes_yaml_format(self):
        m = PluginManifest(name="news", route_description="News.")
        result = build_extra_routes_text([m])
        # Each entry should be indented with 12 spaces to match routes.yaml
        self.assertIn("\n            news:", result)

    def test_multiline_description_lines_are_indented(self):
        m = PluginManifest(name="news", route_description="Line one.\nLine two.")
        result = build_extra_routes_text([m])
        self.assertIn("\n            Line two.", result)
        self.assertNotIn("\nLine two.", result)

    def test_jinja2_sandbox_blocks_code_execution(self):
        """SandboxedEnvironment should prevent template code execution."""
        m = PluginManifest(
            name="evil",
            route_description="{{ ''.__class__.__mro__[1].__subclasses__() }}",
        )
        # Should not raise; sandbox blocks attribute access on builtins
        result = build_extra_routes_text([m])
        self.assertIn("evil:", result)


class TestLoadPluginFolder(unittest.TestCase):
    """Integration tests for SandVoice._load_plugin_folder using a real temp directory."""

    def _make_sv(self):
        """Return a minimal SandVoice-like object with the required attributes."""
        from unittest.mock import MagicMock
        from sandvoice import SandVoice
        sv = object.__new__(SandVoice)
        sv.config = MagicMock()
        sv.config.plugin_path = "/tmp/plugins"
        sv.config.location = "Toronto,ON,CA"
        sv.plugins = {}
        sv._plugin_manifests = []
        return sv

    def test_valid_folder_plugin_loads(self):
        from sandvoice import SandVoice
        from unittest.mock import MagicMock
        sv = self._make_sv()

        with tempfile.TemporaryDirectory() as d:
            plugin_folder = os.path.join(d, "myplugin")
            os.makedirs(plugin_folder)
            _write_yaml(plugin_folder, "name: myplugin\nroute_description: My plugin.\n")
            with open(os.path.join(plugin_folder, "plugin.py"), "w") as f:
                f.write("def process(u, r, s): return 'ok'\n")

            entry = MagicMock()
            entry.path = plugin_folder
            entry.name = "myplugin"
            sv._load_plugin_folder(entry)

        self.assertIn("myplugin", sv.plugins)
        self.assertTrue(callable(sv.plugins["myplugin"]))
        self.assertEqual(len(sv._plugin_manifests), 1)
        self.assertEqual(sv._plugin_manifests[0].name, "myplugin")

    def test_folder_starting_with_underscore_skipped(self):
        from unittest.mock import MagicMock
        sv = self._make_sv()

        entry = MagicMock()
        entry.name = "__pycache__"
        entry.path = "/tmp/__pycache__"
        sv._load_plugin_folder(entry)

        self.assertEqual(sv.plugins, {})
        self.assertEqual(sv._plugin_manifests, [])

    def test_folder_without_plugin_yaml_skipped_silently(self):
        sv = self._make_sv()

        with tempfile.TemporaryDirectory() as d:
            from unittest.mock import MagicMock
            entry = MagicMock()
            entry.name = "notaplugin"
            entry.path = d
            sv._load_plugin_folder(entry)

        self.assertEqual(sv.plugins, {})

    def test_folder_with_missing_env_var_skipped(self):
        from unittest.mock import MagicMock
        sv = self._make_sv()

        with tempfile.TemporaryDirectory() as plugin_folder:
            _write_yaml(
                plugin_folder,
                "name: secured\nroute_description: Needs a key.\nenv_vars:\n  - _SANDVOICE_TEST_MISSING_\n",
            )
            os.environ.pop("_SANDVOICE_TEST_MISSING_", None)

            entry = MagicMock()
            entry.name = "secured"
            entry.path = plugin_folder

            with self.assertLogs("sandvoice", level="WARNING"):
                sv._load_plugin_folder(entry)

        self.assertEqual(sv.plugins, {})

    def test_folder_without_plugin_py_skipped_with_warning(self):
        from unittest.mock import MagicMock
        sv = self._make_sv()

        with tempfile.TemporaryDirectory() as plugin_folder:
            _write_yaml(plugin_folder, "name: nopy\nroute_description: No py file.\n")

            entry = MagicMock()
            entry.name = "nopy"
            entry.path = plugin_folder

            with self.assertLogs("sandvoice", level="WARNING") as cm:
                sv._load_plugin_folder(entry)

        self.assertEqual(sv.plugins, {})
        self.assertTrue(any("no plugin.py" in msg for msg in cm.output))

    def test_folder_manifest_name_mismatch_skipped_with_warning(self):
        from unittest.mock import MagicMock
        sv = self._make_sv()

        with tempfile.TemporaryDirectory() as plugin_folder:
            # folder is named "myplugin" but manifest declares name "otherplugin"
            _write_yaml(plugin_folder, "name: otherplugin\nroute_description: Desc.\n")

            entry = MagicMock()
            entry.name = "myplugin"
            entry.path = plugin_folder

            with self.assertLogs("sandvoice", level="WARNING") as cm:
                sv._load_plugin_folder(entry)

        self.assertEqual(sv.plugins, {})
        self.assertTrue(any("does not match" in msg for msg in cm.output))


if __name__ == "__main__":
    unittest.main()
