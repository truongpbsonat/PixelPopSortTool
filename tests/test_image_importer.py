import pytest

from pixel_level_tool.domain.enums import EMPTY_COLOR_ID, ItemColor
from pixel_level_tool.services.image_importer import import_image_to_color_ids


PIL = pytest.importorskip("PIL.Image")


def test_image_import_alpha_nearest_and_no_y_flip(tmp_path):
    image = PIL.new("RGBA", (2, 2))
    image.putpixel((0, 0), (255, 0, 0, 255))
    image.putpixel((1, 0), (0, 255, 0, 255))
    image.putpixel((0, 1), (0, 0, 255, 0))
    image.putpixel((1, 1), (255, 255, 255, 255))
    path = tmp_path / "sample.png"
    image.save(path)
    ids = import_image_to_color_ids(path, 2, 2, alpha_threshold=1)
    assert ids[0] == int(ItemColor.Red)
    assert ids[1] == int(ItemColor.Green)
    assert ids[2] == EMPTY_COLOR_ID
    assert ids[3] == int(ItemColor.White)


def test_image_import_maps_non_palette_rgb_to_nearest_item_color(tmp_path):
    image = PIL.new("RGB", (2, 1))
    # These values are deliberately not exact palette entries.  They should
    # still import as the visually closest shared palette colors.
    image.putpixel((0, 0), (245, 15, 15))
    image.putpixel((1, 0), (120, 120, 120))
    path = tmp_path / "near-palette.png"
    image.save(path)

    ids = import_image_to_color_ids(path, 2, 1)

    assert ids == [int(ItemColor.Red), int(ItemColor.Gray)]


def test_image_import_averages_only_center_one_third_region(tmp_path):
    image = PIL.new("RGB", (9, 9), (30, 144, 255))
    # A 9x9 source cell produces a 3x3 centered sample.  Four red and five
    # yellow samples average to orange; the blue border must not affect it.
    for index, color in enumerate([(229, 0, 0)] * 4 + [(253, 255, 0)] * 5):
        image.putpixel((3 + index % 3, 3 + index // 3), color)
    path = tmp_path / "center-average.png"
    image.save(path)

    ids = import_image_to_color_ids(path, 1, 1)

    assert ids == [int(ItemColor.Orange)]

