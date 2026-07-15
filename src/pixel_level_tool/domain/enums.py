from __future__ import annotations

from enum import IntEnum


EMPTY_COLOR_ID = -1


class ItemColor(IntEnum):
    Black = 0
    DarkBlue = 1
    White = 2
    Green = 3
    Orange = 4
    LightPink = 5
    DarkPurple = 6
    Red = 7
    SkyBlue = 8
    Yellow = 9
    MagentaPink = 10
    LightGray = 11
    DarkOrange = 12
    LightGreen = 13
    FuchsiaPink = 14
    BrickRed = 15
    MediumGray = 16
    HotPink = 17
    LightYellow = 18
    Olive = 19
    Violet = 20
    OliveGreen = 21
    LimeGreen = 22
    BurntOrange = 23
    Lavender = 24
    Teal = 25
    Salmon = 26
    YellowGreen = 27


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


class LockKeyGate(IntEnum):
    None_ = 0
    Red = 1
    Blue = 2
    Green = 3
    Yellow = 4
    Purple = 5
    Pink = 6


class WoolCrateColor(IntEnum):
    None_ = 0
    Red = 1
    Blue = 2
    Green = 3
    Yellow = 4
    Purple = 5
    Pink = 6


class CellEffectType(IntEnum):
    Frozen = 1
    Hidden = 2
    ArrowLock = 3
    KeyForLockedGate = 5
    ScissorForWoolCrate = 6


class ObstacleType(IntEnum):
    LinkedContainer = 1
    LargeBlock = 3
    Pins = 4
    LockedGate = 5
    WoolCrate = 6
    ColorGate = 7
    Elevator = 8


class GameMode(IntEnum):
    Pixel = 1


class LevelDifficulty(IntEnum):
    Normal = 0


COLOR_NAMES: dict[ItemColor, str] = {
    ItemColor.Black: "Black",
    ItemColor.DarkBlue: "Dark Blue",
    ItemColor.White: "White",
    ItemColor.Green: "Green",
    ItemColor.Orange: "Orange",
    ItemColor.LightPink: "Light Pink",
    ItemColor.DarkPurple: "Dark Purple",
    ItemColor.Red: "Red",
    ItemColor.SkyBlue: "Sky Blue",
    ItemColor.Yellow: "Yellow",
    ItemColor.MagentaPink: "Magenta Pink",
    ItemColor.LightGray: "Light Gray",
    ItemColor.DarkOrange: "Dark Orange",
    ItemColor.LightGreen: "Light Green",
    ItemColor.FuchsiaPink: "Fuchsia Pink",
    ItemColor.BrickRed: "Brick Red",
    ItemColor.MediumGray: "Medium Gray",
    ItemColor.HotPink: "Hot Pink",
    ItemColor.LightYellow: "Light Yellow",
    ItemColor.Olive: "Olive",
    ItemColor.Violet: "Violet",
    ItemColor.OliveGreen: "Olive Green",
    ItemColor.LimeGreen: "Lime Green",
    ItemColor.BurntOrange: "Burnt Orange",
    ItemColor.Lavender: "Lavender",
    ItemColor.Teal: "Teal",
    ItemColor.Salmon: "Salmon",
    ItemColor.YellowGreen: "Yellow-Green",
}


COLOR_HEX: dict[ItemColor, str] = {
    ItemColor.Black: "#1A1A1A",
    ItemColor.DarkBlue: "#1565C0",
    ItemColor.White: "#ffffff",
    ItemColor.Green: "#4CAF50",
    ItemColor.Orange: "#FF8C00",
    ItemColor.LightPink: "#FF69B4",
    ItemColor.DarkPurple: "#7B1FA2",
    ItemColor.Red: "#E53935",
    ItemColor.SkyBlue: "#29B6F6",
    ItemColor.Yellow: "#FFD600",
    ItemColor.MagentaPink: "#EC407A",
    ItemColor.LightGray: "#B0BEC5",
    ItemColor.DarkOrange: "#FF6F00",
    ItemColor.LightGreen: "#66BB6A",
    ItemColor.FuchsiaPink: "#F06292",
    ItemColor.BrickRed: "#C62828",
    ItemColor.MediumGray: "#9E9E9E",
    ItemColor.HotPink: "#F50057",
    ItemColor.LightYellow: "#FDD835",
    ItemColor.Olive: "#827717",
    ItemColor.Violet: "#9C27B0",
    ItemColor.OliveGreen: "#8BC34A",
    ItemColor.LimeGreen: "#A5D6A7",
    ItemColor.BurntOrange: "#E65100",
    ItemColor.Lavender: "#CE93D8",
    ItemColor.Teal: "#00ACC1",
    ItemColor.Salmon: "#FF7043",
    ItemColor.YellowGreen: "#CDDC39",
}


COLOR_RGB: dict[ItemColor, tuple[int, int, int]] = {
    color: tuple(bytes.fromhex(hex_code.removeprefix("#")))
    for color, hex_code in COLOR_HEX.items()
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
