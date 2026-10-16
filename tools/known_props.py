"""Shared helper for the tools: the properties the integration already maps.

Reads PROP_DEFS from the integration's api.py with ast instead of importing it,
so the tools don't need Home Assistant or aiohttp installed.
"""
import ast
from pathlib import Path

INTEGRATION_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "dreame_airpurifier"
INTEGRATION_API = INTEGRATION_DIR / "api.py"
INTEGRATION_CONST = INTEGRATION_DIR / "const.py"


def _propdef_table(node) -> dict:
    """{(siid, piid): attr} from a tuple literal of PropDef(...) calls."""
    out = {}
    for call in getattr(node, "elts", []):
        if (
            isinstance(call, ast.Call)
            and getattr(call.func, "id", None) == "PropDef"
            and len(call.args) >= 3
            and all(isinstance(a, ast.Constant) for a in call.args[:3])
        ):
            attr, siid, piid = (a.value for a in call.args[:3])
            out[(siid, piid)] = attr
    return out


def load_known_props(model: str | None = None, path: Path = INTEGRATION_API) -> dict:
    """Return {(siid, piid): attr_name} from the integration's api.py: the model's own
    table if MODEL_PROP_DEFS lists it (e.g. the TP20), otherwise PROP_DEFS."""
    try:
        tree = ast.parse(path.read_text())
    except (OSError, SyntaxError) as ex:
        print(f"⚠️  Could not read integration property map from {path}: {ex}")
        return {}
    tables, model_tables = {}, {}
    for node in tree.body:
        target = getattr(node, "target", None) or (node.targets[0] if isinstance(node, ast.Assign) else None)
        name = getattr(target, "id", None)
        if name == "MODEL_PROP_DEFS" and isinstance(node.value, ast.Dict):
            for k, v in zip(node.value.keys, node.value.values):
                model_tables[ast.literal_eval(k)] = getattr(v, "id", None)
        elif name and isinstance(node.value, ast.Tuple):
            table = _propdef_table(node.value)
            if table:
                tables[name] = table
    return tables.get(model_tables.get(model), tables.get("PROP_DEFS", {}))


def load_unsafe_props(path: Path = INTEGRATION_CONST, name: str = "UNSAFE_PROPS") -> dict:
    """Return {model: {(siid, n), ...}} from UNSAFE_PROPS (properties that crash that model
    when read) or UNSAFE_ACTIONS (actions that crash it) in the integration's const.py."""
    try:
        tree = ast.parse(path.read_text())
    except (OSError, SyntaxError) as ex:
        print(f"⚠️  Could not read unsafe-property list from {path}: {ex}")
        return {}
    for node in tree.body:
        target = getattr(node, "target", None) or (node.targets[0] if isinstance(node, ast.Assign) else None)
        if getattr(target, "id", None) != name or not isinstance(node.value, ast.Dict):
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


def unsafe_actions_for(model: str) -> set:
    return load_unsafe_props(name="UNSAFE_ACTIONS").get(model, set())


_ids = None


def request_id() -> int:
    """A fresh id for each cloud request. A fixed id let replies get mixed up between
    clients talking to the device at the same time (this script, HA, the app)."""
    global _ids
    if _ids is None:
        import itertools, random
        _ids = itertools.count(random.randint(1000, 1_000_000))
    return next(_ids)
