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


class MapType(IntEnum):
    None_ = 0
    Map1 = 1
    Map2 = 2
    Map3 = 3
    Map4 = 4
    Map5 = 5


class GameMode(IntEnum):
    Classic = 0


class LevelDifficulty(IntEnum):
    Easy = 0
    Medium = 1
    Hard = 2
    SuperHard = 3


def enum_name(member: IntEnum) -> str:
    """Serialized enum name expected by Pop-Sort-2 (``None_`` maps back to ``None``)."""
    return member.name.removesuffix("_")


def enum_name_from_value(enum_type: type[IntEnum], value: int, fallback: IntEnum) -> str:
    """Enum name for an int the UI may set freely; unknown values clamp to ``fallback``."""
    try:
        member = enum_type(value)
    except ValueError:
        member = fallback
    return enum_name(member)


def enum_value_from_name(enum_type: type[IntEnum], name: str, fallback: IntEnum) -> int:
    """Parse a Pop-Sort-2 enum name back to its int value (``None`` -> ``None_``)."""
    try:
        return int(enum_type[name])
    except KeyError:
        pass
    if name == "None":
        try:
            return int(enum_type["None_"])
        except KeyError:
            pass
    return int(fallback)


COLOR_NAMES: dict[ItemColor, str] = {
    ItemColor.Red: "Red",
    ItemColor.Green: "Green",
    ItemColor.Blue: "Blue",
    ItemColor.Yellow: "Yellow",
    ItemColor.Pink: "Pink",
    ItemColor.Orange: "Orange",
    ItemColor.Purple: "Purple",
    ItemColor.Black: "Black",
    ItemColor.Brown: "Brown",
    ItemColor.Cyan: "Cyan",
    ItemColor.Gray: "Gray",
    ItemColor.LightPink: "Light Pink",
    ItemColor.Lime: "Lime",
    ItemColor.Periwinkle: "Periwinkle",
    ItemColor.Teal: "Teal",
    ItemColor.Violet: "Violet",
    ItemColor.White: "White",
}


COLOR_HEX: dict[ItemColor, str] = {
    ItemColor.Red: "#E50000",
    ItemColor.Green: "#02F300",
    ItemColor.Blue: "#1E90FF",
    ItemColor.Yellow: "#FDFF00",
    ItemColor.Pink: "#FF00A6",
    ItemColor.Orange: "#FF5400",
    ItemColor.Purple: "#A800FF",
    ItemColor.Black: "#14141A",
    ItemColor.Brown: "#733D1F",
    ItemColor.Cyan: "#33D9F2",
    ItemColor.Gray: "#808080",
    ItemColor.LightPink: "#FFADD1",
    ItemColor.Lime: "#A6F233",
    ItemColor.Periwinkle: "#8C94F2",
    ItemColor.Teal: "#1AA6A6",
    ItemColor.Violet: "#8C59E6",
    ItemColor.White: "#FFFFFF",
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
