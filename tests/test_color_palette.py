from pixel_level_tool.domain.enums import COLOR_HEX, COLOR_NAMES, COLOR_RGB, ItemColor
from pixel_level_tool.ui.widgets.color_palette import ColorPalette


EXPECTED_PALETTE = [
    (0, "Red", "#E50000"),
    (1, "Green", "#02F300"),
    (2, "Blue", "#1E90FF"),
    (3, "Yellow", "#FDFF00"),
    (4, "Pink", "#FF00A6"),
    (5, "Orange", "#FF5400"),
    (6, "Purple", "#A800FF"),
    (7, "Black", "#14141A"),
    (8, "Brown", "#733D1F"),
    (9, "Cyan", "#33D9F2"),
    (10, "Gray", "#808080"),
    (11, "Light Pink", "#FFADD1"),
    (12, "Lime", "#A6F233"),
    (13, "Periwinkle", "#8C94F2"),
    (14, "Teal", "#1AA6A6"),
    (15, "Violet", "#8C59E6"),
    (16, "White", "#FFFFFF"),
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

    palette.set_selected_color(ItemColor.Blue)

    assert "border: 3px solid #ffffff" in palette._buttons[ItemColor.Blue].styleSheet()
    assert "border: 1px solid #7b828c" in palette._buttons[ItemColor.Red].styleSheet()
