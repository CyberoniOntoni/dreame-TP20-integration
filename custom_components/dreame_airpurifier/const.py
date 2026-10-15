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
