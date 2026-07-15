from pixel_level_tool.domain.enums import COLOR_HEX, COLOR_NAMES, COLOR_RGB, ItemColor
from pixel_level_tool.ui.widgets.color_palette import ColorPalette


EXPECTED_PALETTE = [
    (0, "Black", "#1A1A1A"),
    (1, "Dark Blue", "#1565C0"),
    (2, "White", "#ffffff"),
    (3, "Green", "#4CAF50"),
    (4, "Orange", "#FF8C00"),
    (5, "Light Pink", "#FF69B4"),
    (6, "Dark Purple", "#7B1FA2"),
    (7, "Red", "#E53935"),
    (8, "Sky Blue", "#29B6F6"),
    (9, "Yellow", "#FFD600"),
    (10, "Magenta Pink", "#EC407A"),
    (11, "Light Gray", "#B0BEC5"),
    (12, "Dark Orange", "#FF6F00"),
    (13, "Light Green", "#66BB6A"),
    (14, "Fuchsia Pink", "#F06292"),
    (15, "Brick Red", "#C62828"),
    (16, "Medium Gray", "#9E9E9E"),
    (17, "Hot Pink", "#F50057"),
    (18, "Light Yellow", "#FDD835"),
    (19, "Olive", "#827717"),
    (20, "Violet", "#9C27B0"),
    (21, "Olive Green", "#8BC34A"),
    (22, "Lime Green", "#A5D6A7"),
    (23, "Burnt Orange", "#E65100"),
    (24, "Lavender", "#CE93D8"),
    (25, "Teal", "#00ACC1"),
    (26, "Salmon", "#FF7043"),
    (27, "Yellow-Green", "#CDDC39"),
]


def test_item_color_uses_standard_ids_names_and_hex_values():
    actual = [
        (int(color), COLOR_NAMES[color], COLOR_HEX[color])
        for color in ItemColor
    ]

    assert actual == EXPECTED_PALETTE


def test_rgb_values_are_derived_from_the_standard_hex_values():
    for color in ItemColor:
        assert COLOR_RGB[color] == tuple(bytes.fromhex(COLOR_HEX[color][1:]))


def test_palette_rows_stay_compact_when_widget_is_tall(qtbot):
    palette = ColorPalette()
    qtbot.addWidget(palette)
    palette.resize(400, 800)
    palette.show()
    qtbot.waitExposed(palette)

    first_button = palette._buttons[ItemColor.Black]
    second_row_button = palette._buttons[ItemColor.LightPink]

    assert second_row_button.y() - first_button.y() == (
        palette.SWATCH_SIZE + palette.layout().verticalSpacing()
    )


def test_selected_color_uses_white_outline(qtbot):
    palette = ColorPalette()
    qtbot.addWidget(palette)

    palette.set_selected_color(ItemColor.DarkBlue)

    assert "border: 3px solid #ffffff" in palette._buttons[ItemColor.DarkBlue].styleSheet()
    assert "border: 1px solid #7b828c" in palette._buttons[ItemColor.Red].styleSheet()
