from __future__ import annotations

from enum import IntEnum


EMPTY_COLOR_ID = -1


class ItemColor(IntEnum):
    Red = 0
    Green = 1
    Blue = 2
    Yellow = 3
    Pink = 4
    Orange = 5
    Purple = 6
    Black = 7
    Brown = 8
    Cyan = 9
    Gray = 10
    LightPink = 11
    Lime = 12
    Periwinkle = 13
    Teal = 14
    Violet = 15
    White = 16


class CellShape(IntEnum):
    Square_3x3 = 0
    Rectangle_3x2 = 1
    L3x4 = 2
    Rectangle_3x1 = 3
    Rectangle_6x1 = 4
    Rectangle_9x1 = 5
    LL3x4 = 6


class Direction(IntEnum):
    Up = 0
    Down = 1
    Left = 2
    Right = 3


class GameMode(IntEnum):
    Pixel = 1


class LevelDifficulty(IntEnum):
    Normal = 0


COLOR_RGB: dict[ItemColor, tuple[int, int, int]] = {
    ItemColor.Red: (225, 59, 53),
    ItemColor.Green: (68, 176, 83),
    ItemColor.Blue: (61, 119, 226),
    ItemColor.Yellow: (244, 204, 64),
    ItemColor.Pink: (238, 99, 164),
    ItemColor.Orange: (241, 139, 47),
    ItemColor.Purple: (135, 77, 209),
    ItemColor.Black: (39, 42, 50),
    ItemColor.Brown: (139, 91, 56),
    ItemColor.Cyan: (67, 190, 211),
    ItemColor.Gray: (142, 151, 163),
    ItemColor.LightPink: (248, 164, 199),
    ItemColor.Lime: (145, 211, 69),
    ItemColor.Periwinkle: (135, 153, 229),
    ItemColor.Teal: (43, 143, 141),
    ItemColor.Violet: (177, 101, 222),
    ItemColor.White: (238, 241, 245),
}


def is_valid_color_id(value: int) -> bool:
    return value == EMPTY_COLOR_ID or value in {int(c) for c in ItemColor}


def nearest_item_color(rgb: tuple[int, int, int]) -> ItemColor:
    r, g, b = rgb
    return min(
        COLOR_RGB,
        key=lambda color: (COLOR_RGB[color][0] - r) ** 2
        + (COLOR_RGB[color][1] - g) ** 2
        + (COLOR_RGB[color][2] - b) ** 2,
    )

