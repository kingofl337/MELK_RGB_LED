"""MELK-OF21 (Lotus Lamp X) commands, checked against packets captured from the
Lotus Lamp X app.

Run with:  python -m pytest tests   (or: python tests/test_melk_of21.py)
"""
import importlib.util
import json
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).parents[1] / "custom_components" / "elkbledom"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# model.py only needs the HomeAssistant type
ha = types.ModuleType("homeassistant")
ha_core = types.ModuleType("homeassistant.core")
ha_core.HomeAssistant = object
sys.modules.setdefault("homeassistant", ha)
sys.modules.setdefault("homeassistant.core", ha_core)
model_module = _load("elkbledom_model", "model.py")

models = {m["name"]: m for m in json.loads((ROOT / "models.json").read_text())}
model = model_module.Model()
model._models = models
KEY = "MELK-OF21"

def hexes(cmds):
    return [bytes(c).hex() for c in cmds]


def test_model_detected_from_advertised_name():
    assert model.detect_model("MELK-OF21   8F") == KEY


def test_model_commands_match_capture():
    assert bytes(model.get_turn_on_cmd(KEY)).hex() == "7e0704ff00010201ef"
    assert bytes(model.get_turn_off_cmd(KEY)).hex() == "7e07040000000201ef"
    assert bytes(model.get_color_cmd(KEY, 255, 0, 0)).hex() == "7e070503ff000010ef"
    assert bytes(model.get_color_cmd(KEY, 0, 0, 255)).hex() == "7e0705030000ff10ef"
    # Home Assistant brightness 0-255 is sent as 0-100 %
    assert bytes(model.get_brightness_cmd(KEY, 255)).hex() == "7e04016401ff0201ef"
    assert bytes(model.get_brightness_cmd(KEY, 128)).hex() == "7e04013201ff0201ef"
    assert bytes(model.get_effect_cmd(KEY, 0x02)).hex() == "7e07030206ffff00ef"


def test_login_is_the_apps_clock_and_query():
    login = model.get_login_cmds(KEY, 11, 21, 58, 5)
    assert hexes(login) == ["7e06830b153a0500ef", "7e0737ffffff00ffef"]
    assert model.get_login_cmds("MELK", 1, 2, 3, 4) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
