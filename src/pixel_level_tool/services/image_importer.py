from __future__ import annotations

from pathlib import Path

from pixel_level_tool.domain.enums import EMPTY_COLOR_ID, nearest_item_color


class ImageImportError(ValueError):
    pass


def image_grid_size(
    path: str | Path, max_width: int, max_height: int
) -> tuple[int, int]:
    """The pixel-grid size one image asks for, fitted inside a cap.

    A folder run used to sample every image at the one size typed into the form,
    which is right for a folder of photographs and wrong for a folder of pixel
    art: a 29x29 piece of art forced through a 16x16 grid loses a third of its
    rows and columns, and a 40x24 one comes back square. The size is a property
    of each picture, so it is read off each picture.

    An image already inside the cap keeps its **own size exactly** and nothing is
    resampled - the grid is the art, cell for cell. A larger one is scaled by the
    tighter of the two ratios, so its shape survives the fit rather than being
    squashed into the cap's aspect. The cap is what keeps a 4000x3000 photograph
    from asking for a twelve-million-cell grid.
    """
    if max_width <= 0 or max_height <= 0:
        raise ImageImportError("Giới hạn chiều rộng và chiều cao phải lớn hơn 0.")
    source_path = Path(path)
    if not source_path.exists():
        raise ImageImportError(f"Image file does not exist: {source_path}")
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - Pillow is a hard dependency
        raise ImageImportError("Pillow is required to import images.") from exc
    try:
        with Image.open(source_path) as image:
            width, height = image.size
    except Exception as exc:
        raise ImageImportError(f"Không đọc được kích thước ảnh: {exc}") from exc
    if width <= 0 or height <= 0:
        raise ImageImportError(f"Ảnh {source_path.name} không có kích thước hợp lệ.")
    if width <= max_width and height <= max_height:
        return width, height
    # Integer-only, and floored, so the result never spills over the cap by a
    # rounding step. The max(1, ...) is for a picture so long and thin that its
    # short side floors to nothing.
    scale = min(max_width / width, max_height / height)
    return max(1, int(width * scale)), max(1, int(height * scale))


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

