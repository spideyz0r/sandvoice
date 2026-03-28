import logging
import os

import yaml
from jinja2 import Template

logger = logging.getLogger(__name__)


class PluginManifest:
    """Parsed representation of a plugin.yaml manifest.

    Attributes:
        name:              Route key used for dispatch (e.g. ``"weather"``).
        version:           Informational semver string.
        route_description: Route description appended to the LLM routing prompt.
        route_extra_keys:  Additional JSON keys the router should extract.
        env_vars:          Env var names required at runtime.
        config_defaults:   Config key/value pairs merged at lowest priority.
        dependencies:      pip package names (informational only).
        plugin_dir:        Absolute path to the plugin folder.
    """

    __slots__ = (
        "name",
        "version",
        "route_description",
        "route_extra_keys",
        "env_vars",
        "config_defaults",
        "dependencies",
        "plugin_dir",
    )

    def __init__(
        self,
        name,
        version="0.0.0",
        route_description="",
        route_extra_keys=None,
        env_vars=None,
        config_defaults=None,
        dependencies=None,
        plugin_dir="",
    ):
        self.name = name
        self.version = version
        self.route_description = route_description
        self.route_extra_keys = list(route_extra_keys or [])
        self.env_vars = list(env_vars or [])
        self.config_defaults = dict(config_defaults or {})
        self.dependencies = list(dependencies or [])
        self.plugin_dir = plugin_dir


def load_manifest(folder_path):
    """Parse ``plugin.yaml`` from a plugin folder.

    Args:
        folder_path: Absolute path to the plugin folder.

    Returns:
        A :class:`PluginManifest` on success, or ``None`` if the manifest is
        absent, malformed, or missing required fields.
    """
    yaml_path = os.path.join(folder_path, "plugin.yaml")
    if not os.path.isfile(yaml_path):
        return None

    try:
        with open(yaml_path, "r") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception as e:
        logger.warning("Failed to parse %s: %s", yaml_path, e)
        return None

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        logger.warning(
            "plugin.yaml in %s missing required field 'name'; skipping", folder_path
        )
        return None

    route_description = data.get("route_description", "")
    if not isinstance(route_description, str) or not route_description.strip():
        logger.warning(
            "plugin.yaml for '%s' missing required field 'route_description'; skipping",
            name,
        )
        return None

    for list_field in ("route_extra_keys", "env_vars", "dependencies"):
        value = data.get(list_field)
        if value is not None and not isinstance(value, (list, tuple)):
            logger.warning(
                "plugin.yaml for '%s' has non-list '%s'; skipping", name, list_field
            )
            return None

    config_defaults = data.get("config_defaults")
    if config_defaults is not None and not isinstance(config_defaults, dict):
        logger.warning(
            "plugin.yaml for '%s' has non-dict 'config_defaults'; skipping", name
        )
        return None

    return PluginManifest(
        name=name.strip(),
        version=str(data.get("version", "0.0.0")),
        route_description=route_description.strip(),
        route_extra_keys=list(data.get("route_extra_keys") or []),
        env_vars=list(data.get("env_vars") or []),
        config_defaults=dict(data.get("config_defaults") or {}),
        dependencies=list(data.get("dependencies") or []),
        plugin_dir=folder_path,
    )


def check_env_vars(manifest):
    """Return env var names declared in the manifest that are not set in the environment.

    Args:
        manifest: A :class:`PluginManifest` instance.

    Returns:
        List of missing env var name strings (empty list when all are set).
    """
    return [var for var in manifest.env_vars if not os.environ.get(var)]


def build_extra_routes_text(manifests, location=""):
    """Assemble route description lines contributed by plugin manifests.

    The result is a string ready to be appended to the ``route_role`` system
    prompt in :meth:`AI.define_route`.  Each line is indented to match the
    existing ``routes.yaml`` block formatting.

    Jinja2 templates in ``route_description`` (e.g. ``{{ location }}``) are
    rendered using the supplied ``location`` value.

    Args:
        manifests: Iterable of :class:`PluginManifest` objects.
        location:  User-configured location string passed to template rendering.

    Returns:
        A single string (possibly empty) to append to the routing prompt.
    """
    lines = []
    for manifest in sorted(manifests, key=lambda m: m.name):
        if not manifest.route_description:
            continue
        try:
            rendered = Template(manifest.route_description).render(location=location)
        except Exception as e:
            logger.warning(
                "Failed to render route_description template for plugin '%s': %s",
                manifest.name,
                e,
            )
            rendered = manifest.route_description
        lines.append(f"\n            {manifest.name}: {rendered}")
    return "".join(lines)
