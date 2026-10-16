"""Constants for Dreame Air Purifier integration."""
from dataclasses import dataclass

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


@dataclass(frozen=True, slots=True)
class ModelProfile:
    """How a model's controls behave. Property numbers live in api.py (per-model PROP_DEFS)."""

    modes: dict[int, str]   # mode value -> preset name shown in HA
    manual_mode: int        # the mode in which fan speed can be set
    speed_count: int        # fan speeds run 1..speed_count
    timer_max: int          # hours
    # Air quality level value -> state key, for models whose app names the levels.
    # Keys are translated in strings.json (entity.sensor.air_quality.state).
    aq_levels: dict[int, str] | None = None
    # (siid, aiid) of the action that toggles power, or None if the model has no
    # known safe way to switch power from here.
    power_action: tuple[int, int] | None = (2, 3)

    @property
    def mode_by_name(self) -> dict[str, int]:
        return {v: k for k, v in self.modes.items()}


# PM10 (and the default for models without a profile)
DEFAULT_PROFILE = ModelProfile(modes=MODE_NAMES, manual_mode=MODE_CUSTOM, speed_count=10, timer_max=24)

PROFILES: dict[str, ModelProfile] = {
    # TP20: modes and speeds confirmed by reading and writing them on the device;
    # 12 h is the longest timer the Dreame app offers (1 h and 2 h were written).
    "dreame.airp.u2630": ModelProfile(
        modes={0: "AI Purify", 2: "Sleep", 3: "Custom"}, manual_mode=3, speed_count=3, timer_max=12,
        # The app shows five levels. 3.4 was seen at 1-4, rising with PM2.5; order assumed ascending.
        aq_levels={1: "excellent", 2: "good", 3: "moderate", 4: "poor", 5: "bad"},
        # 2.1 power is read-only (-4002), and action 2/3 crashes the TP20: it goes dead,
        # needs its power button, and can lose its Wi-Fi connection. No power control.
        power_action=None,
    ),
}


def profile_for(model: str) -> ModelProfile:
    return PROFILES.get(model, DEFAULT_PROFILE)

SWIVEL_OPTIONS = (0, 45, 90, 180)

# Properties (siid, piid) that must never be read on a given model.
# dreame.airp.u2630 (TP20): reading 3.10 makes the device stop responding and reboot.
UNSAFE_PROPS: dict[str, frozenset[tuple[int, int]]] = {
    "dreame.airp.u2630": frozenset({(3, 10)}),
}

# Actions (siid, aiid) that must never be called on a given model.
# dreame.airp.u2630 (TP20): action 2/3 (toggle power on the PM10) crashes it; it stays
# off until its power button is pressed and may then not reconnect to Wi-Fi.
UNSAFE_ACTIONS: dict[str, frozenset[tuple[int, int]]] = {
    "dreame.airp.u2630": frozenset({(2, 3)}),
}
