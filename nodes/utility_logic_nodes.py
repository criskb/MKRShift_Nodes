from __future__ import annotations

import json

from ..categories import UTILITY_LOGIC
from ..lib.settings_bundle import parse_settings_bool, parse_settings_payload


TOGGLE_SWITCH_DEFAULTS = {
    "enabled": True,
    "theme": "lime",
}

TOGGLE_SWITCH_THEMES = {"lime", "graphite", "rose", "amber"}


def _normalize_theme(value: object) -> str:
    token = str(value or TOGGLE_SWITCH_DEFAULTS["theme"]).strip().lower()
    return token if token in TOGGLE_SWITCH_THEMES else str(TOGGLE_SWITCH_DEFAULTS["theme"])


def _parse_toggle_settings(settings_json: str) -> dict:
    settings = parse_settings_payload(
        settings_json,
        defaults=TOGGLE_SWITCH_DEFAULTS,
        boolean_keys={"enabled"},
    )
    settings["theme"] = _normalize_theme(settings.get("theme"))
    return settings


class MKRToggleSwitch:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "settings_json": (
                    "STRING",
                    {
                        "default": json.dumps(TOGGLE_SWITCH_DEFAULTS),
                        "multiline": True,
                    },
                ),
            },
            "optional": {
                "state_in": ("BOOLEAN", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("BOOLEAN",)
    RETURN_NAMES = ("state",)
    FUNCTION = "run"
    CATEGORY = UTILITY_LOGIC
    SEARCH_ALIASES = ("switch", "toggle", "boolean", "logic", "light switch")

    def run(self, settings_json: str = "{}", state_in=None):
        settings = _parse_toggle_settings(settings_json)
        enabled = (
            parse_settings_bool(state_in, bool(settings["enabled"]))
            if state_in is not None
            else bool(settings["enabled"])
        )

        return {
            "ui": {
                "toggle_state": [
                    {
                        "enabled": bool(enabled),
                        "theme": str(settings["theme"]),
                        "controlled_by_input": bool(state_in is not None),
                    }
                ]
            },
            "result": (bool(enabled),),
        }
