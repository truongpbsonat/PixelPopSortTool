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
            image = image.resize((target_width, target_height), Image.Resampling.NEAREST)
            color_ids: list[int] = []
            for row in range(target_height):
                for column in range(target_width):
                    r, g, b, a = image.getpixel((column, row))
                    if a < alpha_threshold:
                        color_ids.append(EMPTY_COLOR_ID)
                    else:
                        color_ids.append(int(nearest_item_color((r, g, b))))
            return color_ids
    except Exception as exc:
        if isinstance(exc, ImageImportError):
            raise
        raise ImageImportError(f"Could not import image: {exc}") from exc

