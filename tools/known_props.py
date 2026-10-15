"""Shared helper for the tools: the properties the integration already maps.

Reads PROP_DEFS from the integration's api.py with ast instead of importing it,
so the tools don't need Home Assistant or aiohttp installed.
"""
import ast
from pathlib import Path

INTEGRATION_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "dreame_airpurifier"
INTEGRATION_API = INTEGRATION_DIR / "api.py"
INTEGRATION_CONST = INTEGRATION_DIR / "const.py"


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


def load_unsafe_props(path: Path = INTEGRATION_CONST) -> dict:
    """Return {model: {(siid, piid), ...}} from UNSAFE_PROPS in the integration's const.py:
    properties that crash that model when read, so the tools must never request them."""
    try:
        tree = ast.parse(path.read_text())
    except (OSError, SyntaxError) as ex:
        print(f"⚠️  Could not read unsafe-property list from {path}: {ex}")
        return {}
    for node in tree.body:
        target = getattr(node, "target", None) or (node.targets[0] if isinstance(node, ast.Assign) else None)
        if getattr(target, "id", None) != "UNSAFE_PROPS" or not isinstance(node.value, ast.Dict):
            continue
        out = {}
        for k, v in zip(node.value.keys, node.value.values):
            # values look like frozenset({(3, 10), ...})
            inner = v.args[0] if isinstance(v, ast.Call) and v.args else v
            out[ast.literal_eval(k)] = set(ast.literal_eval(inner))
        return out
    return {}


def unsafe_for(model: str) -> set:
    return load_unsafe_props().get(model, set())
