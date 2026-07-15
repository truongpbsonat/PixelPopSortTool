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
    assert ids[0] == int(ItemColor.BrickRed)
    assert ids[1] == int(ItemColor.Green)
    assert ids[2] == EMPTY_COLOR_ID
    assert ids[3] == int(ItemColor.White)

