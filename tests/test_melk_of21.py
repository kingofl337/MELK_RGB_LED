"""MELK-OF21 (Lotus Lamp X) commands and segment tables, checked against packets
captured from the Lotus Lamp X app.

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


christmas = _load("elkbledom_christmas", "christmas.py")

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

# A full segment table as the app sent it (start, header with checksum, 14 pairs, tail)
CAPTURED_TABLE = [
    "7e07371c00010100ef", "7e3254003ae8ffffef", "7e330000ff0000ff01", "7e330000ffff000002",
    "7e3300ffff80ff0003", "7e33ff008000ff0004", "7e33ff000000ffff05", "7e338000ffff00ff06",
    "7e33ff00000080ff07", "7e3300ffffff000008", "7e3300ff000080ff09", "7e330080ff0080ff0a",
    "7e3300ff8000ff000b", "7e33ff00ff80ff000c", "7e3300ffffff00800d", "7e330080ff00ff800e",
    "7e34000064ffffffef",
]


def hexes(cmds):
    return [bytes(c).hex() for c in cmds]


def test_segment_table_matches_capture():
    cells = []
    for packet in CAPTURED_TABLE[2:-1]:
        b = bytes.fromhex(packet)
        cells += [tuple(b[2:5]), tuple(b[5:8])]
    assert hexes(christmas.segment_table(cells)) == CAPTURED_TABLE


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


def test_christmas_effects():
    assert model.get_segments(KEY) == 28 and model.get_segments("MELK") == 0
    red_green = christmas.frame_for("Red & green", 0, 28)
    assert red_green[:3] == [christmas.RED, christmas.GREEN, christmas.RED]
    chase0 = christmas.frame_for("Candy cane chase", 0, 28)
    chase1 = christmas.frame_for("Candy cane chase", 1, 28)
    assert chase1[1:] == chase0[:-1]
    flip = [christmas.frame_for("Red & green flip", s, 28)[0] for s in range(2)]
    assert flip == [christmas.RED, christmas.GREEN]
    for name in christmas.CHRISTMAS_EFFECTS:
        table = christmas.segment_table(christmas.frame_for(name, 3, 28))
        assert len(table) == 17 and all(len(cmd) == 9 for cmd in table)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
