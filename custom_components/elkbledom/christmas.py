"""Christmas effects for strips with addressable segments (e.g. Lotus Lamp X MELK-OF21).

Pure Python, no Home Assistant imports, so it can be tested on its own.

Static patterns are written once as a segment table. Animated effects are driven by
Home Assistant: a new segment table is sent every few seconds.

Segment table (decoded from the Lotus Lamp X app):
    7E 07 37 <n> 00 01 01 00 EF
    7E 32 <3n> 00 CK_HI CK_LO FF FF EF
    n/2 x 7E 33 R G B R G B <index 1..>
    7E 34 00 00 64 FF FF FF EF
CK is the 16-bit sum of every byte of the 7E 32 packet (without CK), the 7E 33 packets
and the 7E 34 packet.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

RGB = tuple[int, int, int]

RED: RGB = (255, 0, 0)
GREEN: RGB = (0, 255, 0)
BLUE: RGB = (0, 0, 255)
ORANGE: RGB = (255, 106, 0)
YELLOW: RGB = (255, 213, 0)
GOLD: RGB = (255, 170, 38)
WHITE: RGB = (255, 255, 255)
WARM_WHITE: RGB = (255, 150, 89)
ICE: RGB = (140, 220, 255)

PATTERNS: dict[str, list[RGB]] = {
    "Candy cane": [RED, WHITE],
    "Red & green": [RED, GREEN],
    "Red, green & white": [RED, GREEN, WHITE],
    "Classic multicolor": [RED, GREEN, BLUE, ORANGE, YELLOW],
    "Gold & white": [GOLD, WHITE],
    "Warm white": [WARM_WHITE],
    "Winter ice": [ICE, WHITE],
}


@dataclass(frozen=True)
class Animation:
    kind: str                     # "chase", "twinkle", "alternate" or "fade"
    colors: list[RGB]
    interval: float = 2.0         # seconds between frames
    sparkle: RGB = WHITE          # twinkle only
    sparkle_share: float = 0.15   # twinkle only
    frames: list[list[RGB]] = field(default_factory=list)  # alternate only
    steps: int = 12               # fade only: steps to fade up (and again to fade down)


ANIMATIONS: dict[str, Animation] = {
    "Candy cane chase": Animation("chase", [RED, RED, WHITE, WHITE]),
    "Christmas chase": Animation("chase", [RED, RED, GREEN, GREEN, WHITE, WHITE]),
    "Multicolor chase": Animation("chase", [RED, GREEN, BLUE, ORANGE, YELLOW]),
    "Christmas twinkle": Animation("twinkle", [RED, GREEN], interval=1.5),
    "Warm white twinkle": Animation("twinkle", [WARM_WHITE], interval=1.5, sparkle_share=0.2),
    "Red & green flip": Animation("alternate", [], interval=2.5, frames=[[RED, GREEN], [GREEN, RED]]),
    # Whole strip fades up and down in red, then in green. Uses the strip's own color and
    # brightness commands (one small packet per step) instead of segment tables.
    "R+G Fade": Animation("fade", [RED, GREEN], interval=0.2, steps=12),
}

CHRISTMAS_EFFECTS: list[str] = [*PATTERNS, *ANIMATIONS]


def repeat(pattern: list[RGB], n: int, offset: int = 0) -> list[RGB]:
    return [pattern[(i + offset) % len(pattern)] for i in range(n)]


def fade_step(anim: Animation, step: int) -> tuple[RGB, float]:
    """Color and brightness level (0-1) for a fade animation at `step`."""
    cycle = 2 * anim.steps  # up then down
    color = anim.colors[(step // cycle) % len(anim.colors)]
    pos = step % cycle
    level = (pos if pos <= anim.steps else cycle - pos) / anim.steps
    return color, level * level  # squared: looks even to the eye


def frame_for(name: str, step: int, n: int, rng: random.Random | None = None) -> list[RGB]:
    """Segment colors for an effect at animation step `step` (patterns ignore the step)."""
    if name in PATTERNS:
        return repeat(PATTERNS[name], n)
    anim = ANIMATIONS[name]
    if anim.kind == "chase":
        return repeat(anim.colors, n, offset=-step)
    if anim.kind == "alternate":
        return repeat(anim.frames[step % len(anim.frames)], n)
    if anim.kind == "fade":
        color, level = fade_step(anim, step)
        return repeat([tuple(round(c * level) for c in color)], n)
    if anim.kind == "twinkle":
        rng = rng or random.Random()
        frame = repeat(anim.colors, n)
        for i in rng.sample(range(n), max(1, round(n * anim.sparkle_share))):
            frame[i] = anim.sparkle
        return frame
    raise ValueError(anim.kind)


def segment_table(cells: list[RGB]) -> list[list[int]]:
    """Commands that set every segment to the given colors."""
    cells = [tuple(max(0, min(255, int(c))) for c in cell) for cell in cells]
    if len(cells) % 2:
        cells.append(cells[-1])
    n = len(cells)
    start = [0x7E, 0x07, 0x37, n, 0x00, 0x01, 0x01, 0x00, 0xEF]
    pairs = [[0x7E, 0x33, *cells[2 * i], *cells[2 * i + 1], i + 1] for i in range(n // 2)]
    tail = [0x7E, 0x34, 0x00, 0x00, 0x64, 0xFF, 0xFF, 0xFF, 0xEF]
    head_wo_ck = [0x7E, 0x32, (3 * n) & 0xFF, 0x00, 0xFF, 0xFF, 0xEF]
    ck = (sum(head_wo_ck) + sum(map(sum, pairs)) + sum(tail)) & 0xFFFF
    header = [0x7E, 0x32, (3 * n) & 0xFF, 0x00, ck >> 8, ck & 0xFF, 0xFF, 0xFF, 0xEF]
    return [start, header, *pairs, tail]
