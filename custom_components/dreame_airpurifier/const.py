"""Constants for Dreame Air Purifier integration."""

DOMAIN = "dreame_airpurifier"
SCAN_INTERVAL = 30

CONF_COUNTRY = "country"
COUNTRY_OPTIONS = ["us", "cn", "eu", "sg", "kr"]

# ── MiOT mode values ───────────────────────────────────────────────────
MODE_AUTO = 0
MODE_COMFORT = 2
MODE_CUSTOM = 3
MODE_PET = 4

MODE_NAMES: dict[int, str] = {
    MODE_AUTO: "Auto",
    MODE_COMFORT: "Comfort",
    MODE_CUSTOM: "Custom",
    MODE_PET: "Pet",
}
MODE_NAME_TO_VALUE: dict[str, int] = {v: k for k, v in MODE_NAMES.items()}

SWIVEL_OPTIONS = (0, 45, 90, 180)

# Properties (siid, piid) that must never be read on a given model.
# dreame.airp.u2630 (TP20): reading 3.10 makes the device stop responding and reboot.
UNSAFE_PROPS: dict[str, frozenset[tuple[int, int]]] = {
    "dreame.airp.u2630": frozenset({(3, 10)}),
}
