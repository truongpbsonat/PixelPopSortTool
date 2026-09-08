"""Auto Gen Box over a whole folder, from pictures or from level files.

The single-level action reads the picture off the level in hand. A folder run
reads it off every file in one folder instead, and that folder holds one of two
things: the pictures themselves (``*.png`` and friends) or the level files a
picture already lives in (``*.json``). Either way the output is the same - one
level file per picture, written into the output folder - so a batch of art can
be turned into playable levels without opening them one at a time.

Which level a file becomes is read off its name: ``7.png`` and ``7.json`` both
build level 7, ``7.2.png`` its category variant, and ``4.3mau.json`` level 4 -
a name that opens with a number keeps it however it goes on to describe itself.
A name with no number at all still has to land somewhere, so it takes the next
free number from ``start_level`` - that is what makes a folder of
``cat.png``/``dog.png`` usable without renaming anything first.

A level file also *carries* its number, and that is the one that counts: the
file name is only how the folder is sorted, while ``level``/``category`` inside
the document is the level's identity, and it is what the output file and the
preset beside it are named after.

A ``*.json`` source does not have to be a *current* level file. The exports this
tool is pointed at write their picture under ``pixelGrid.colors``, or under the
older ``pixelBoard``/``map`` shapes, with colour ids past the end of
``ItemColor`` - so when the current reader refuses one, the picture is read the
way **Import Old JSON** reads it and handed back to the current reader inside
its own document. See :func:`load_level_source`.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Iterable, Sequence

from pixel_level_tool.domain.level_models import PixelGridData, PixelLevelData
from pixel_level_tool.services.autogen_config import (
    FILE_PREFIX,
    AutoGenConfigError,
    load_autogen_config,
    save_autogen_config,
)
from pixel_level_tool.services.box_autogen import (
    AutoGenError,
    AutoGenOptions,
    AutoGenResult,
    auto_generate_boxes,
    balance_summary,
    jam_headline,
)
from pixel_level_tool.services.image_importer import ImageImportError, import_image_to_color_ids
from pixel_level_tool.services.legacy_level_importer import (
    LegacyLevelImportError,
    legacy_pixel_grid_from_dict,
)
from pixel_level_tool.services.level_serializer import (
    LevelSerializationError,
    level_from_dict,
    load_level_document,
    save_level,
)

# Everything Pillow reads that a designer is likely to hand over as level art.
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".tga", ".gif", ".webp")

_LEVEL_KEY_PATTERN = re.compile(r"^(?P<level>\d+)(?:\.(?P<category>\d+))?$")
# A name that *starts* with a number and then says something else about itself -
# `4.3mau.json`, `12_final.png`. The number is still the level; the rest is the
# exporter's label, not a category, so it is read and dropped. A separator is
# required so `2024art.png` stays unnumbered rather than becoming level 2024.
_LEADING_LEVEL_PATTERN = re.compile(r"^(?P<level>\d+)[._\- ].*$")
_DIGITS = re.compile(r"(\d+)")

# Statuses a row can end on. Only ``ok`` and ``jam`` wrote a level file.
STATUS_OK = "ok"
STATUS_JAM = "jam"
STATUS_ERROR = "error"
STATUS_SKIPPED = "skipped"
STATUS_CANCELLED = "cancelled"


class AutoGenBatchError(ValueError):
    pass


def natural_key(name: str) -> tuple:
    """Sort ``10.png`` after ``2.png``, the way the folder reads on screen.

    Each run is tagged with its kind before its value, so a number is never
    compared against a word - which is what a plain ``int``/``str`` mix would do
    the moment a folder holds both ``1.png`` and ``mario.png``. Numbers sort
    ahead of words, the way Explorer lists the same folder.
    """
    return tuple(
        (0, int(part), "") if part.isdigit() else (1, 0, part.lower())
        for part in _DIGITS.split(name)
        if part != ""
    )


def level_key_from_stem(stem: str) -> tuple[int, int] | None:
    """The (level, category) a file name claims, or ``None`` when it claims none.

    ``7`` is level 7 and ``7.2`` its category variant - that pair is the whole
    rule for a name that is nothing but numbers. Everything else falls to the
    leading-number rule: `4.3mau.json` is level 4 with `3mau` a note the
    exporter left about its palette, not category 3.
    """
    match = _LEVEL_KEY_PATTERN.fullmatch(stem)
    if match is not None:
        return int(match.group("level")), int(match.group("category") or 0)
    match = _LEADING_LEVEL_PATTERN.fullmatch(stem)
    if match is None:
        return None
    return int(match.group("level")), 0


def output_file_name(level: int, category: int = 0) -> str:
    return f"{level}.json" if category == 0 else f"{level}.{category}.json"


@dataclass(frozen=True)
class BatchSource:
    """One input file and the level it is going to become."""

    path: Path
    kind: str  # "image" | "level"
    level: int
    category: int = 0
    # True when the number came from the file name rather than from a counter.
    numbered: bool = True

    @property
    def key(self) -> tuple[int, int]:
        return self.level, self.category


@dataclass
class BatchItem:
    """What one source turned into, whether or not it produced a level."""

    source: BatchSource
    status: str
    detail: str = ""
    level: int = 0
    category: int = 0
    output: Path | None = None
    preset: Path | None = None
    difficulty: int = 0
    boxes: int = 0
    hidden_boxes: int = 0
    tunnels: int = 0
    walls: int = 0
    # The two locks that open on a number rather than on another box. Read off
    # the run the same way the other mechanics are, because a folder run is the
    # only place a designer sees a hundred levels at once - and a lock that
    # quietly landed nowhere is exactly what one row per level is for.
    frozen: int = 0
    slabs: int = 0
    # How far the picture pushed the obstacle forms down, and whether it pushed
    # them all the way off. `bare` is the loudest thing a row can say: every
    # form was unplayable, so the level shipped as the certified base grid with
    # no mechanics on it at all.
    relief_steps: int = 0
    bare: bool = False
    # The burial was floored at Easy because this picture cannot be won on the
    # belt its level ships with. Kept apart from `relief_steps` because it is not
    # a rung on that ladder: the obstacle forms did not move, only what the player
    # cannot see. A folder run is where this matters most - a hundred pictures
    # scaled off one sheet of art, and the ones with the wrong `piece` are exactly
    # the rows a designer needs to pick out.
    unburied: bool = False
    # What the level was measured to add up to, against the tier it ships as.
    # `difficulty` above is the label; this is whether the label is true, and a
    # folder run is the only place a hundred of those can be checked at once.
    notch: float = 0.0
    difficulty_matched: bool = True
    belt_required: int = 0
    belt_slots: int = 0
    seed: int = 0
    validation_errors: int = 0

    @property
    def written(self) -> bool:
        return self.output is not None


@dataclass
class BatchSummary:
    total: int
    items: list[BatchItem] = field(default_factory=list)
    cancelled: bool = False

    def _count(self, status: str) -> int:
        return sum(1 for item in self.items if item.status == status)

    @property
    def generated(self) -> int:
        return self._count(STATUS_OK)

    @property
    def jammed(self) -> int:
        return self._count(STATUS_JAM)

    @property
    def failed(self) -> int:
        return self._count(STATUS_ERROR)

    @property
    def skipped(self) -> int:
        return self._count(STATUS_SKIPPED)

    @property
    def written(self) -> int:
        return sum(1 for item in self.items if item.written)

    @property
    def relieved(self) -> int:
        """Levels whose obstacles were stepped down to keep the level playable."""
        return sum(1 for item in self.items if item.written and item.relief_steps)

    @property
    def bare(self) -> int:
        """Levels that shipped with no mechanics at all because every form faulted."""
        return sum(1 for item in self.items if item.written and item.bare)

    @property
    def unburied(self) -> int:
        """Levels whose burial was floored because the picture cannot be won at all.

        Always a subset of :attr:`jammed`, and the actionable half of it: every
        one of these rows is a picture whose `piece` is too small, and raising it
        hands the level its tier's own burial back.
        """
        return sum(1 for item in self.items if item.written and item.unburied)


def collect_sources(
    folder: str | Path,
    *,
    start_level: int = 1,
    include_images: bool = True,
    include_levels: bool = True,
) -> list[BatchSource]:
    """The files in ``folder`` a run can build a level out of, in name order.

    Presets (``genlv*.json``) sit in the same folder as the levels they belong
    to often enough that reading one as a picture would be a routine accident,
    so they are never a source. Sub-folders are left alone: a folder run writes
    a flat batch of numbered levels, and recursing would collide two ``1.json``
    from different sub-folders onto the same output name.
    """
    root = Path(folder)
    try:
        entries = [path for path in root.iterdir() if path.is_file()]
    except OSError as exc:
        raise AutoGenBatchError(f"Không đọc được folder {root}: {exc}") from exc

    candidates: list[tuple[Path, str]] = []
    for path in sorted(entries, key=lambda item: natural_key(item.name)):
        suffix = path.suffix.lower()
        if suffix == ".json":
            if not include_levels or path.stem.lower().startswith(FILE_PREFIX):
                continue
            candidates.append((path, "level"))
        elif suffix in IMAGE_SUFFIXES and include_images:
            candidates.append((path, "image"))

    taken: set[tuple[int, int]] = set()
    for path, _ in candidates:
        key = level_key_from_stem(path.stem)
        if key is not None:
            taken.add(key)
    next_number = max(1, start_level)

    sources: list[BatchSource] = []
    for path, kind in candidates:
        key = level_key_from_stem(path.stem)
        if key is None:
            while (next_number, 0) in taken:
                next_number += 1
            key = (next_number, 0)
            taken.add(key)
            next_number += 1
            numbered = False
        else:
            numbered = True
        sources.append(BatchSource(path, kind, key[0], key[1], numbered))
    return sources


def describe_sources(sources: Sequence[BatchSource]) -> str:
    if not sources:
        return "Không tìm thấy ảnh hay file level nào trong folder này."
    images = sum(1 for source in sources if source.kind == "image")
    levels = len(sources) - images
    parts = []
    if images:
        parts.append(f"{images} ảnh")
    if levels:
        parts.append(f"{levels} file level")
    return " và ".join(parts) + f" → sinh {len(sources)} level."


def load_level_source(
    path: str | Path, *, fallback_level: int | None = None, fallback_category: int = 0
) -> tuple[PixelLevelData, bool]:
    """The level in one ``*.json`` source, read the current way or the old way.

    A folder of art from the game is rarely a folder of *current* level files:
    the exports carry their picture under ``pixelGrid.colors`` (not
    ``colorIds``), or under the older ``pixelBoard``/``map`` shapes, and colour
    ids past the end of :class:`ItemColor`. The current reader refuses all of
    that, which used to make every such file a `không đọc được` row.

    So when it refuses, the picture is read the way **Import Old JSON** reads it
    - the same importer, so the same palette folding - and handed back to the
    current reader inside the document it came from. That way only the *picture*
    comes from the legacy path and everything else about the level (its number,
    ``time``, ``piece``, tier, theme) is still parsed by the one reader that
    knows those fields, whichever spelling the old file used for them.

    The old file's *boxes* are deliberately not read, exactly as in Import Old
    JSON: they carry capacities this editor does not build, and Auto Gen Box is
    about to lay a fresh box grid anyway.

    Returns the level and whether it came off the legacy path.
    """
    document = load_level_document(path)
    try:
        return level_from_dict(document), False
    except LevelSerializationError as current_error:
        try:
            grid = legacy_pixel_grid_from_dict(document)
        except LegacyLevelImportError:
            # Not an old-format picture either, so the current reader's
            # complaint is the one worth showing - it names the exact field.
            raise current_error from None
        patched = dict(document)
        patched["pixelGrid"] = {
            "width": grid.width,
            "height": grid.height,
            "colorIds": list(grid.color_ids),
        }
        level = level_from_dict(patched)
        # The oldest shapes carry no level number at all, so the number the
        # folder read off the file name stands rather than everything landing
        # on the reader's default of 1 and colliding.
        if "level" not in document and fallback_level is not None:
            level.level = fallback_level
            level.category = fallback_category
        return level, True


def build_level_from_image(
    source: BatchSource,
    *,
    width: int,
    height: int,
    alpha_threshold: int = 1,
    time: int = 60,
    piece: int = 5,
) -> PixelLevelData:
    color_ids = import_image_to_color_ids(source.path, width, height, alpha_threshold)
    return PixelLevelData(
        level=source.level,
        category=source.category,
        level_name=f"Pixel Level {source.level}",
        time=time,
        piece=piece,
        pixel_grid=PixelGridData(width, height, color_ids),
    )


def _result_detail(result: AutoGenResult) -> str:
    """The one line a designer reads off a row: what stopped it, or what it cost."""
    parts: list[str] = []
    if result.jam is not None:
        parts.append(jam_headline(result))
    # What the picture made of the obstacles it was asked for. Said before the
    # balance and the validator because it is the difference between the level
    # the tier describes and the level that shipped - and in a folder run
    # nobody is going to open a hundred reports to find it out.
    if result.obstacle_relief.unburied:
        parts.append(
            f"chôn box hạ về Easy (box ẩn {result.hidden_boxes}) vì tranh chưa thắng được"
            f" — nâng piece lên {result.scan.required_piece} là trả lại mức"
            f" {result.obstacle_relief.tier_label}"
        )
    if result.obstacle_free:
        parts.append("obs không đặt được cái nào, ship lưới base trần")
    elif result.obstacle_relief.relieved:
        parts.append(
            f"obs hạ {result.obstacle_relief.steps} bậc xuống mức "
            f"{result.obstacle_relief.label} để level còn qua được"
        )
    # The sum, which is the one thing a row can say that the columns cannot: a
    # level wearing a label it does not play like. Louder than the relief note
    # above, because relief is a means and this is the outcome.
    if not result.score.reached:
        parts.append(
            f"độ khó tổng hợp chỉ {result.score.notch:.2f} = {result.score.label},"
            f" thiếu {result.score.shortfall:.2f} nấc so với {result.score.target_label}"
        )
    elif result.climb.climbed:
        parts.append(
            f"đã siết {len(result.climb.added)} loại obs để lên đủ mức"
            f" ({result.climb.start:.2f} → {result.climb.final:.2f})"
        )
    if result.added_pixels or result.moved_pixels or result.removed_pixels:
        parts.append(
            "cân bằng: "
            + balance_summary(result.added_pixels, result.moved_pixels, result.removed_pixels)
        )
    errors = result.validation_errors
    if errors:
        parts.append(f"validate lỗi: {errors[0].message}")
    return " · ".join(parts)


def generate_folder(
    sources: Sequence[BatchSource],
    output_folder: str | Path,
    options: AutoGenOptions,
    *,
    image_width: int = 16,
    image_height: int = 16,
    alpha_threshold: int = 1,
    image_time: int = 60,
    image_piece: int = 5,
    preset_folder: str | Path | None = None,
    use_presets: bool = True,
    write_presets: bool = True,
    use_level_difficulty: bool = False,
    picture_difficulty: bool = False,
    overwrite: bool = True,
    shuffle_attempts: int | None = None,
    progress: Callable[[int, int, BatchSource], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> BatchSummary:
    """Run Auto Gen Box over ``sources`` and write one level file per source.

    ``options`` is the base every level is generated on. A per-level preset
    (``genlv{level}.json`` in ``preset_folder``) replaces it wholesale where one
    exists and ``use_presets`` is on, because a preset is the exact set of knobs
    that level was tuned with - mixing half of it into the dialog's numbers would
    produce a grid nobody chose. ``use_level_difficulty`` only applies where no
    preset was used: it takes the tier off the level file being read instead of
    off the dialog, so a folder of levels keeps its own easy/hard mix.

    ``picture_difficulty`` is the other answer to the tier question, and the one
    a folder run is usually after: read it off every picture, the way the params
    dialog's *Lấy độ khó từ ảnh* does for a single level. It is asked for once for
    the whole run, so it outranks the preset and ``use_level_difficulty`` both - a
    designer ticking "take the tier off the picture, for every level" is not
    asking to be overruled by a number some earlier run wrote into
    ``genlv{level}.json``. The rest of the preset still stands: only the tier
    moves, and the doses left on Auto follow it there.

    ``shuffle_attempts`` is the other knob a folder run overrides rather than
    inherits. Two reasons, and both are about it not being a design decision. It
    is the run's **cost** dial - N rolls per level times a hundred levels is the
    whole wall-clock of a batch - so it belongs to the run rather than to any one
    picture. And it changes nothing about what a level *is*: every roll is a
    complete, certified level and the shuffle only picks between them, so forcing
    it cannot produce a grid nobody chose, which is exactly why the doses do
    defer to a preset. ``None`` leaves each level with whatever its preset or
    ``options`` asked for.

    A jam does not stop the run and does not withhold the file: the single-level
    action ships an unwinnable grid too, with the jam on its report, and the
    batch report is where that is said here.
    """
    out_root = Path(output_folder)
    presets_root = Path(preset_folder) if preset_folder is not None else None
    summary = BatchSummary(total=len(sources))
    seen: dict[tuple[int, int], Path] = {}

    for index, source in enumerate(sources, start=1):
        if should_cancel is not None and should_cancel():
            summary.cancelled = True
            summary.items.extend(
                BatchItem(
                    remaining,
                    STATUS_CANCELLED,
                    "đã huỷ",
                    level=remaining.level,
                    category=remaining.category,
                )
                for remaining in sources[index - 1 :]
            )
            break
        if progress is not None:
            progress(index, summary.total, source)

        item = BatchItem(source, STATUS_ERROR, level=source.level, category=source.category)
        summary.items.append(item)

        # ------------------------------------------------------------ picture
        try:
            if source.kind == "image":
                level = build_level_from_image(
                    source,
                    width=image_width,
                    height=image_height,
                    alpha_threshold=alpha_threshold,
                    time=image_time,
                    piece=image_piece,
                )
            else:
                level, legacy = load_level_source(
                    source.path,
                    fallback_level=source.level,
                    fallback_category=source.category,
                )
                # The number inside the file is the level's identity; the file
                # name is only how the folder was sorted.
                item.level = level.level
                item.category = level.category
                if legacy:
                    # Said on the row because the old palette does not survive
                    # whole: colour ids past ItemColor are folded onto free ones,
                    # the way Import Old JSON folds them.
                    item.detail = "đọc theo định dạng cũ · "
        except (
            ImageImportError,
            LegacyLevelImportError,
            LevelSerializationError,
            OSError,
            ValueError,
            TypeError,
        ) as exc:
            item.detail = f"không đọc được: {exc}"
            continue

        key = (item.level, item.category)
        if key in seen:
            item.status = STATUS_SKIPPED
            item.detail = f"trùng {output_file_name(*key)} với {seen[key].name}"
            continue

        target = out_root / output_file_name(*key)
        if target.exists() and not overwrite:
            item.status = STATUS_SKIPPED
            item.detail = f"đã có {target.name}, không ghi đè"
            seen[key] = source.path
            continue

        # -------------------------------------------------------------- knobs
        item_options = options
        preset_used = False
        if use_presets and presets_root is not None:
            preset = None
            try:
                preset = load_autogen_config(presets_root, item.level, item.category)
            except AutoGenConfigError as exc:
                item.detail += (
                    f"cấu hình {FILE_PREFIX}{item.level}.json hỏng ({exc}), dùng tham số chung · "
                )
            if preset is not None:
                item_options = preset
                preset_used = True
        if picture_difficulty:
            # Asked for this run, so it beats the preset too - see the docstring.
            item_options = replace(item_options, auto_difficulty=True)
        elif use_level_difficulty and source.kind == "level" and not preset_used:
            item_options = replace(
                item_options, difficulty=level.difficulty, auto_difficulty=False
            )
        # Last, so it beats the preset as well - see the docstring for why this
        # one is allowed to and the doses are not.
        if shuffle_attempts is not None:
            item_options = replace(item_options, shuffle_attempts=max(1, shuffle_attempts))

        # ----------------------------------------------------------- generate
        try:
            result = auto_generate_boxes(level, item_options)
        except (AutoGenError, ValueError, TypeError) as exc:
            item.detail += f"sinh box thất bại: {exc}"
            continue

        try:
            out_root.mkdir(parents=True, exist_ok=True)
            save_level(target, result.level)
        except (LevelSerializationError, OSError, ValueError) as exc:
            item.detail += f"không ghi được {target.name}: {exc}"
            continue

        seen[key] = source.path
        item.output = target
        item.status = STATUS_JAM if result.jam is not None else STATUS_OK
        item.detail += _result_detail(result)
        item.difficulty = result.difficulty
        item.boxes = result.surface_boxes + result.tunnel_boxes
        item.hidden_boxes = result.hidden_boxes
        item.tunnels = result.tunnel_count
        item.walls = len(result.wall_slots)
        item.frozen = len(result.frozen)
        item.slabs = len(result.slabs)
        item.relief_steps = result.obstacle_relief.steps
        item.bare = result.obstacle_free
        item.unburied = result.obstacle_relief.unburied
        item.notch = result.score.notch
        item.difficulty_matched = result.score.reached
        item.belt_required = result.solution.required_belt
        item.belt_slots = result.belt_slots
        item.seed = result.seed
        item.validation_errors = len(result.validation_errors)

        # The seed is the only part of a run that is not in the dialog, so a
        # preset written without it would not rebuild this grid.
        if write_presets and presets_root is not None:
            try:
                item.preset = save_autogen_config(
                    presets_root,
                    item.level,
                    item.category,
                    replace(item_options, seed=result.seed),
                )
            except (AutoGenConfigError, OSError) as exc:
                item.detail = (item.detail + " · " if item.detail else "") + (
                    f"không lưu được cấu hình: {exc}"
                )

    return summary


REPORT_COLUMNS = (
    "File nguồn",
    "Level",
    "Kết quả",
    "Độ khó",
    "Đo được",
    "Box",
    "Ẩn",
    "Tunnel",
    "Wall",
    "Frozen",
    "Slab",
    "Băng",
    "Seed",
    "File ra",
    "Ghi chú",
)

_STATUS_LABELS = {
    STATUS_OK: "xong",
    STATUS_JAM: "KẸT",
    STATUS_ERROR: "lỗi",
    STATUS_SKIPPED: "bỏ qua",
    STATUS_CANCELLED: "đã huỷ",
}


def status_label(status: str) -> str:
    return _STATUS_LABELS.get(status, status)


def report_row(item: BatchItem) -> tuple[str, ...]:
    wrote = item.written
    return (
        item.source.path.name,
        output_file_name(item.level, item.category).removesuffix(".json"),
        status_label(item.status),
        str(item.difficulty) if wrote else "",
        # The notch, and a mark when it did not reach the label beside it.
        (f"{item.notch:.2f}" + ("" if item.difficulty_matched else " !")) if wrote else "",
        str(item.boxes) if wrote else "",
        # A down-arrow when the burial was floored, so the column can be scanned:
        # a 2 beside a SuperHard label is a picture whose `piece` is too small,
        # not a level that was built wrong.
        (str(item.hidden_boxes) + (" ↓" if item.unburied else "")) if wrote else "",
        str(item.tunnels) if wrote else "",
        str(item.walls) if wrote else "",
        str(item.frozen) if wrote else "",
        str(item.slabs) if wrote else "",
        f"{item.belt_required}/{item.belt_slots}" if wrote else "",
        str(item.seed) if wrote else "",
        item.output.name if item.output is not None else "",
        item.detail,
    )


def report_rows(summary: BatchSummary) -> Iterable[tuple[str, ...]]:
    return (report_row(item) for item in summary.items)


def write_report_csv(summary: BatchSummary, path: str | Path) -> Path:
    """The report as a spreadsheet. utf-8-sig so Excel reads the columns right."""
    target = Path(path)
    with open(target, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(REPORT_COLUMNS)
        writer.writerows(report_rows(summary))
    return target
