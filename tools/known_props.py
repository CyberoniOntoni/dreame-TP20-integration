"""Shared helper for the tools: the properties the integration already maps.

Reads PROP_DEFS from the integration's api.py with ast instead of importing it,
so the tools don't need Home Assistant or aiohttp installed.
"""
import ast
from pathlib import Path

INTEGRATION_API = Path(__file__).resolve().parent.parent / "custom_components" / "dreame_airpurifier" / "api.py"


def load_known_props(path: Path = INTEGRATION_API) -> dict:
    """Return {(siid, piid): attr_name} for every PropDef in the integration."""
    known = {}
    try:
        tree = ast.parse(path.read_text())
    except (OSError, SyntaxError) as ex:
        print(f"⚠️  Could not read integration property map from {path}: {ex}")
        return known
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "PropDef"
            and len(node.args) >= 3
            and all(isinstance(a, ast.Constant) for a in node.args[:3])
        ):
            attr, siid, piid = (a.value for a in node.args[:3])
            known[(siid, piid)] = attr
    return known
