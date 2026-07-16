from __future__ import annotations

from pathlib import Path

from pixel_level_tool.domain.enums import EMPTY_COLOR_ID, nearest_item_color


class ImageImportError(ValueError):
    pass


def import_image_to_color_ids(
    path: str | Path,
    target_width: int,
    target_height: int,
    alpha_threshold: int = 1,
) -> list[int]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImageImportError("Pillow is required to import images.") from exc

    source_path = Path(path)
    if not source_path.exists():
        raise ImageImportError(f"Image file does not exist: {source_path}")
    if target_width <= 0 or target_height <= 0:
        raise ImageImportError("Target width and height must be greater than 0.")

    try:
        with Image.open(source_path) as image:
            image = image.convert("RGBA")
            source_width, source_height = image.size
            color_ids: list[int] = []

            for row in range(target_height):
                # Use proportional, half-open bounds so the full source image
                # is covered even when its dimensions are not divisible by the
                # target grid dimensions.
                cell_top = row * source_height // target_height
                cell_bottom = (row + 1) * source_height // target_height
                cell_bottom = max(cell_top + 1, cell_bottom)
                cell_bottom = min(source_height, cell_bottom)
                cell_height = cell_bottom - cell_top
                sample_height = max(1, min(8, cell_height // 3))
                sample_top = cell_top + (cell_height - sample_height) // 2

                for column in range(target_width):
                    cell_left = column * source_width // target_width
                    cell_right = (column + 1) * source_width // target_width
                    cell_right = max(cell_left + 1, cell_right)
                    cell_right = min(source_width, cell_right)
                    cell_width = cell_right - cell_left
                    sample_width = max(1, min(8, cell_width // 3))
                    sample_left = cell_left + (cell_width - sample_width) // 2

                    # Ignore transparent samples when calculating the colour;
                    # a cell with no visible samples remains an empty pixel.
                    visible = []
                    for y in range(sample_top, sample_top + sample_height):
                        for x in range(sample_left, sample_left + sample_width):
                            pixel = image.getpixel((x, y))
                            if pixel[3] >= alpha_threshold:
                                visible.append(pixel)
                    if not visible:
                        color_ids.append(EMPTY_COLOR_ID)
                        continue

                    count = len(visible)
                    average_rgb = tuple(
                        sum(pixel[channel] for pixel in visible) // count
                        for channel in range(3)
                    )
                    color_ids.append(int(nearest_item_color(average_rgb)))

            return color_ids
    except Exception as exc:
        if isinstance(exc, ImageImportError):
            raise
        raise ImageImportError(f"Could not import image: {exc}") from exc

