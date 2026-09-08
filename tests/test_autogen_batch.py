import json
import random
from pathlib import Path

import pytest

from pixel_level_tool.domain.enums import EMPTY_COLOR_ID, LevelDifficulty
from pixel_level_tool.domain.level_models import PixelGridData, PixelLevelData
from pixel_level_tool.services.autogen_batch import (
    STATUS_CANCELLED,
    STATUS_ERROR,
    STATUS_JAM,
    STATUS_OK,
    STATUS_SKIPPED,
    REPORT_COLUMNS,
    collect_sources,
    generate_folder,
    level_key_from_stem,
    load_level_source,
    natural_key,
    report_row,
)
from pixel_level_tool.services.autogen_config import load_autogen_config, save_autogen_config
from pixel_level_tool.services.box_autogen import AutoGenOptions
from pixel_level_tool.services.level_serializer import (
    LevelSerializationError,
    load_level,
    save_level,
)

Image = pytest.importorskip("PIL.Image", reason="Pillow is needed to read picture folders")


def _picture_level(level_number: int, *, seed: int = 7, size: int = 9) -> PixelLevelData:
    """A speckled square: enough colours to be worth generating, small enough to be quick."""
    rng = random.Random(seed)
    ids = [rng.randrange(1, 4) for _ in range(size * size)]
    return PixelLevelData(
        level=level_number, piece=5, pixel_grid=PixelGridData(size, size, ids)
    )


def _speckled_level(
    level_number: int, *, colors: int = 9, size: int = 12, seed: int | None = None
) -> PixelLevelData:
    """A busier picture than `_picture_level`, so the tier read off it is higher."""
    rng = random.Random(seed if seed is not None else level_number)
    ids = [rng.randrange(1, colors + 1) for _ in range(size * size)]
    return PixelLevelData(
        level=level_number, piece=5, pixel_grid=PixelGridData(size, size, ids)
    )


def _write_picture(path, *, size: int = 9) -> None:
    image = Image.new("RGBA", (size * 2, size * 2), (255, 0, 0, 255))
    for y in range(size):
        for x in range(size * 2):
            image.putpixel((x, y), (0, 0, 255, 255))
    image.save(path)


def _write_old_format_level(path, *, level=None, colors=None, size=6, piece=5) -> None:
    """A level file in the shape the game's own exports use.

    Three things the current reader refuses, all in one file: the picture lives
    under `colors` rather than `colorIds`, the palette runs past `ItemColor`
    (18 here), and the boxes are a `gridBoard` of capacities this editor does
    not build. This is what a folder of art from the game actually looks like.
    """
    if colors is None:
        rng = random.Random(4)
        colors = [rng.choice([-1, 5, 15, 18]) for _ in range(size * size)]
    document = {
        "time": 60,
        "piece": piece,
        "gameMode": 0,
        "difficulty": 0,
        "category": 0,
        "pixelGrid": {
            "width": size,
            "height": size,
            "colors": colors,
            "pixelEffects": [],
            "obstacles": [],
        },
        "gridBoard": {
            "columns": 3,
            "rows": 5,
            "cells": [
                {
                    "column": 0,
                    "row": 0,
                    "entity": {
                        "type": "Box",
                        "id": 1,
                        "color": 18,
                        "capacity": 20,
                        "effects": [],
                    },
                }
            ],
            "obstacles": [],
            "boxGroups": [],
        },
    }
    if level is not None:
        document["level"] = level
    Path(path).write_text(json.dumps(document, indent=4), encoding="utf-8")

def _source_folder(tmp_path, *, levels=(1, 2), pictures=()):
    folder = tmp_path / "src"
    folder.mkdir()
    for number in levels:
        save_level(folder / f"{number}.json", _picture_level(number, seed=number))
    for name in pictures:
        _write_picture(folder / name)
    return folder


# --------------------------------------------------------------------------- #
# Which files a folder offers
# --------------------------------------------------------------------------- #
def test_natural_key_orders_numbers_first_and_by_value():
    names = ["10.png", "2.png", "mario.png", "1.2.json"]
    assert sorted(names, key=natural_key) == ["1.2.json", "2.png", "10.png", "mario.png"]


def test_collect_sources_reads_the_level_number_off_the_file_name(tmp_path):
    folder = _source_folder(tmp_path, levels=(2, 10), pictures=("3.png", "7.2.png"))

    sources = collect_sources(folder)

    assert [(source.path.name, source.kind, source.key) for source in sources] == [
        ("2.json", "level", (2, 0)),
        ("3.png", "image", (3, 0)),
        ("7.2.png", "image", (7, 2)),
        ("10.json", "level", (10, 0)),
    ]
    assert all(source.numbered for source in sources)


def test_collect_sources_numbers_unnamed_pictures_around_the_taken_numbers(tmp_path):
    folder = _source_folder(tmp_path, levels=(1,), pictures=("cat.png", "dog.png", "2.png"))

    sources = collect_sources(folder, start_level=1)

    by_name = {source.path.name: source for source in sources}
    assert by_name["1.json"].level == 1 and by_name["2.png"].level == 2
    # 1 and 2 are spoken for, so the unnamed pair takes the next free numbers.
    assert (by_name["cat.png"].level, by_name["cat.png"].numbered) == (3, False)
    assert (by_name["dog.png"].level, by_name["dog.png"].numbered) == (4, False)


def test_collect_sources_never_reads_a_preset_as_a_level(tmp_path):
    folder = _source_folder(tmp_path, levels=(1,))
    save_autogen_config(folder, 1, 0, AutoGenOptions())

    assert (folder / "genlv1.json").exists()
    assert [source.path.name for source in collect_sources(folder)] == ["1.json"]


def test_collect_sources_can_be_limited_to_one_kind(tmp_path):
    folder = _source_folder(tmp_path, levels=(1,), pictures=("2.png",))

    assert [s.path.name for s in collect_sources(folder, include_images=False)] == ["1.json"]
    assert [s.path.name for s in collect_sources(folder, include_levels=False)] == ["2.png"]


# --------------------------------------------------------------------------- #
# Generating the folder
# --------------------------------------------------------------------------- #
def test_generate_folder_writes_one_level_per_source(tmp_path):
    folder = _source_folder(tmp_path, levels=(1, 2), pictures=("3.png",))
    out = tmp_path / "out"

    summary = generate_folder(
        collect_sources(folder), out, AutoGenOptions(difficulty=int(LevelDifficulty.Easy)),
        image_width=9, image_height=9,
    )

    assert summary.total == 3 and summary.failed == 0
    assert summary.written == 3
    assert sorted(path.name for path in out.iterdir()) == ["1.json", "2.json", "3.json"]
    generated = load_level(out / "3.json")
    assert generated.level == 3
    assert generated.grid_cells, "the picture from the image was turned into boxes"


def test_generate_folder_reports_progress_and_stops_when_cancelled(tmp_path):
    folder = _source_folder(tmp_path, levels=(1, 2, 3))
    out = tmp_path / "out"
    seen = []

    summary = generate_folder(
        collect_sources(folder),
        out,
        AutoGenOptions(),
        progress=lambda index, total, source: seen.append((index, total, source.path.name)),
        should_cancel=lambda: len(seen) >= 2,
    )

    assert seen == [(1, 3, "1.json"), (2, 3, "2.json")]
    assert summary.cancelled
    assert [item.status for item in summary.items] == [STATUS_OK, STATUS_OK, STATUS_CANCELLED]
    # A cancel keeps what it already generated.
    assert sorted(path.name for path in out.iterdir()) == ["1.json", "2.json"]


def test_generate_folder_takes_the_level_number_from_inside_the_file(tmp_path):
    folder = tmp_path / "src"
    folder.mkdir()
    # A file named after nothing in particular, carrying level 12.
    save_level(folder / "boss-fight.json", _picture_level(12))
    out = tmp_path / "out"

    summary = generate_folder(collect_sources(folder), out, AutoGenOptions())

    assert [path.name for path in out.iterdir()] == ["12.json"]
    assert summary.items[0].level == 12


def test_generate_folder_skips_a_second_source_for_the_same_level(tmp_path):
    folder = _source_folder(tmp_path, levels=(1,), pictures=("1.png",))
    out = tmp_path / "out"

    summary = generate_folder(
        collect_sources(folder), out, AutoGenOptions(), image_width=9, image_height=9
    )

    statuses = [item.status for item in summary.items]
    assert statuses.count(STATUS_SKIPPED) == 1
    assert "trùng" in next(item.detail for item in summary.items if item.status == STATUS_SKIPPED)


def test_generate_folder_leaves_existing_files_alone_when_asked(tmp_path):
    folder = _source_folder(tmp_path, levels=(1,))
    out = tmp_path / "out"
    out.mkdir()
    (out / "1.json").write_text("keep me", encoding="utf-8")

    summary = generate_folder(collect_sources(folder), out, AutoGenOptions(), overwrite=False)

    assert summary.items[0].status == STATUS_SKIPPED
    assert (out / "1.json").read_text(encoding="utf-8") == "keep me"


def test_generate_folder_records_the_file_it_could_not_read(tmp_path):
    folder = _source_folder(tmp_path, levels=(1,))
    (folder / "2.json").write_text("{ not json", encoding="utf-8")
    out = tmp_path / "out"

    summary = generate_folder(collect_sources(folder), out, AutoGenOptions())

    broken = next(item for item in summary.items if item.source.path.name == "2.json")
    assert broken.status == STATUS_ERROR and "không đọc được" in broken.detail
    # One bad file does not stop the folder.
    assert (out / "1.json").exists()


# --------------------------------------------------------------------------- #
# Knobs: presets, per-level difficulty, seeds
# --------------------------------------------------------------------------- #
def test_a_levels_own_preset_beats_the_dialog(tmp_path):
    folder = _source_folder(tmp_path, levels=(1,))
    presets = tmp_path / "cfg"
    save_autogen_config(presets, 1, 0, AutoGenOptions(difficulty=int(LevelDifficulty.Hard)))
    out = tmp_path / "out"

    summary = generate_folder(
        collect_sources(folder),
        out,
        AutoGenOptions(difficulty=int(LevelDifficulty.Easy)),
        preset_folder=presets,
        write_presets=False,
    )

    assert summary.items[0].difficulty == int(LevelDifficulty.Hard)


def test_the_dialog_wins_when_presets_are_switched_off(tmp_path):
    folder = _source_folder(tmp_path, levels=(1,))
    presets = tmp_path / "cfg"
    save_autogen_config(presets, 1, 0, AutoGenOptions(difficulty=int(LevelDifficulty.Hard)))
    out = tmp_path / "out"

    summary = generate_folder(
        collect_sources(folder),
        out,
        AutoGenOptions(difficulty=int(LevelDifficulty.Easy)),
        preset_folder=presets,
        use_presets=False,
        write_presets=False,
        use_level_difficulty=False,
    )

    assert summary.items[0].difficulty == int(LevelDifficulty.Easy)


def test_each_level_keeps_its_own_difficulty_when_asked(tmp_path):
    folder = tmp_path / "src"
    folder.mkdir()
    easy = _picture_level(1)
    easy.difficulty = int(LevelDifficulty.Easy)
    hard = _picture_level(2, seed=2)
    hard.difficulty = int(LevelDifficulty.Hard)
    save_level(folder / "1.json", easy)
    save_level(folder / "2.json", hard)
    out = tmp_path / "out"

    summary = generate_folder(
        collect_sources(folder),
        out,
        AutoGenOptions(difficulty=int(LevelDifficulty.Medium)),
        use_level_difficulty=True,
    )

    assert [item.difficulty for item in summary.items] == [
        int(LevelDifficulty.Easy),
        int(LevelDifficulty.Hard),
    ]


def test_the_written_preset_carries_the_seed_that_built_the_grid(tmp_path):
    folder = _source_folder(tmp_path, levels=(1,))
    presets = tmp_path / "cfg"
    out = tmp_path / "out"

    summary = generate_folder(
        collect_sources(folder),
        out,
        AutoGenOptions(difficulty=int(LevelDifficulty.Easy)),
        preset_folder=presets,
    )

    item = summary.items[0]
    assert item.preset == presets / "genlv1.json"
    assert load_autogen_config(presets, 1, 0).seed == item.seed

    # Reading that preset back rebuilds the very same file.
    again = generate_folder(
        collect_sources(folder), tmp_path / "out2", AutoGenOptions(), preset_folder=presets
    )
    assert again.items[0].seed == item.seed
    assert (tmp_path / "out2" / "1.json").read_text(encoding="utf-8") == (
        out / "1.json"
    ).read_text(encoding="utf-8")


def test_report_row_matches_the_report_columns(tmp_path):
    folder = _source_folder(tmp_path, levels=(1,))
    summary = generate_folder(collect_sources(folder), tmp_path / "out", AutoGenOptions())

    row = report_row(summary.items[0])
    assert len(row) == len(REPORT_COLUMNS)
    assert row[0] == "1.json" and row[1] == "1" and row[2] == "xong"


# --------------------------------------------------------------------------- #
# The progress locks, and the relief that keeps a folder run playable
# --------------------------------------------------------------------------- #
# A folder run is `auto_generate_boxes` once per file, so every rule the single
# level action is held to holds here too - the colour read before placement, the
# two ceilings on a lock's number, the base-first ordering and the relief ladder
# that steps the obstacles down rather than shipping a level that cannot be won.
# What a folder run adds is *scale*: nobody opens a hundred reports, so the two
# outcomes that make a level quietly different from its tier have to be on the
# row. That is what these pin.
def _lock_worthy_level(level_number: int, *, size: int = 21) -> PixelLevelData:
    """A picture big enough to be worth locking: long runs, several colours."""
    ids: list[int] = []
    color = 1
    while len(ids) < size * size:
        ids.extend([color] * 9)
        color = color % 6 + 1
    return PixelLevelData(
        level=level_number, piece=5, pixel_grid=PixelGridData(size, size, ids[: size * size])
    )


def test_the_report_row_carries_both_progress_locks(tmp_path):
    """Hidden, tunnel and wall were on the row; the two locks were invisible."""
    folder = tmp_path / "src"
    folder.mkdir()
    save_level(folder / "1.json", _lock_worthy_level(1))
    summary = generate_folder(
        collect_sources(folder),
        tmp_path / "out",
        AutoGenOptions(
            difficulty=int(LevelDifficulty.Hard), seed=7, frozen_boxes=3, blocks=2
        ),
    )

    item = summary.items[0]
    assert item.written
    assert item.frozen or item.slabs, "a Hard picture this size should carry a lock"
    row = report_row(item)
    assert len(row) == len(REPORT_COLUMNS)
    frozen_at = REPORT_COLUMNS.index("Frozen")
    slab_at = REPORT_COLUMNS.index("Slab")
    assert row[frozen_at] == str(item.frozen)
    assert row[slab_at] == str(item.slabs)


def test_a_row_says_when_the_obstacles_were_stepped_down_to_stay_playable(tmp_path):
    """`obstacle_relief` is the whole "reduce the obstacles" rule; the row has to show it."""
    folder = tmp_path / "src"
    folder.mkdir()
    for number in (1, 2, 3, 4):
        save_level(folder / f"{number}.json", _picture_level(number, seed=number))
    summary = generate_folder(
        collect_sources(folder),
        tmp_path / "out",
        AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard), seed=4),
    )

    for item in summary.items:
        if not item.written:
            continue
        if item.bare:
            assert "ship lưới base trần" in item.detail
            assert item.frozen == 0 and item.slabs == 0
        elif item.relief_steps:
            assert f"obs hạ {item.relief_steps} bậc" in item.detail
    # The counters are what the headline reads, so they have to agree with the rows.
    assert summary.relieved == sum(
        1 for item in summary.items if item.written and item.relief_steps
    )
    assert summary.bare == sum(1 for item in summary.items if item.written and item.bare)


def test_no_folder_run_ever_writes_a_level_the_validator_rejects(tmp_path):
    """The rule that survives the batch: obstacles never cost a written level its proof."""
    folder = tmp_path / "src"
    folder.mkdir()
    for number in (1, 2, 3):
        save_level(folder / f"{number}.json", _lock_worthy_level(number, size=18 + number))
    for difficulty in tuple(LevelDifficulty):
        summary = generate_folder(
            collect_sources(folder),
            tmp_path / f"out{int(difficulty)}",
            AutoGenOptions(
                difficulty=int(difficulty), seed=5, frozen_boxes=3, blocks=2
            ),
        )
        for item in summary.items:
            if not item.written:
                continue
            assert item.validation_errors == 0, (
                f"level {item.level} at {difficulty.name} was written with "
                f"{item.validation_errors} validation error(s): {item.detail}"
            )
            # A written row is either a clean level or a jam, and a jam is the
            # *picture* being unwinnable on its own belt - not the obstacles,
            # which the relief ladder has already stepped down or removed.
            assert item.status in (STATUS_OK, STATUS_JAM)


# --------------------------------------------------------------------------- #
# The picture that cannot be won at all, one row per level
# --------------------------------------------------------------------------- #
def _jammed_level(level_number: int, *, colors: int = 6, size: int = 12) -> PixelLevelData:
    """A speckled picture on a belt far too narrow for it: `piece` 3 against 6 needed.

    A folder run is where this case actually bites - a hundred pictures scaled
    off one sheet of art, all carrying whatever `piece` the template had - so the
    fixture is the folder version of it rather than one level.
    """
    rng = random.Random(level_number)
    ids = [rng.randrange(1, colors + 1) for _ in range(size * size)]
    return PixelLevelData(
        level=level_number, piece=3, pixel_grid=PixelGridData(size, size, ids)
    )


def _jammed_folder(tmp_path, *, levels=(1, 2, 3)):
    folder = tmp_path / "src"
    # parents=True so one test can set up two runs side by side under its tmp_path.
    folder.mkdir(parents=True)
    for number in levels:
        save_level(folder / f"{number}.json", _jammed_level(number))
    return folder


def _jammed_run(tmp_path, **knobs):
    folder = _jammed_folder(tmp_path)
    options = AutoGenOptions(
        difficulty=int(LevelDifficulty.SuperHard),
        seed=4,
        # The repair's job is to stop a picture jamming, and a repaired picture is
        # not the case under test - `test_picture_repair` owns that one.
        repair_picture=False,
        **knobs,
    )
    return generate_folder(collect_sources(folder), tmp_path / "out", options)


def test_a_folder_run_floors_the_burial_on_every_picture_that_cannot_be_won(tmp_path):
    summary = _jammed_run(tmp_path)

    assert summary.written == 3, "a jammed level is still written, as it always was"
    assert all(item.status == STATUS_JAM for item in summary.items)
    assert summary.unburied == 3
    assert summary.unburied == sum(
        1 for item in summary.items if item.written and item.unburied
    ), "the headline counter has to agree with the rows"


def test_the_row_says_the_burial_came_down_and_names_the_piece_that_undoes_it(tmp_path):
    summary = _jammed_run(tmp_path)

    for item in summary.items:
        assert "chôn box hạ về Easy" in item.detail
        assert "nâng piece lên" in item.detail, "the fix is a number, on the row itself"
        assert "SuperHard" in item.detail, "and the tier it would come back to"


def test_the_hidden_column_is_marked_so_a_hundred_rows_can_be_scanned(tmp_path):
    summary = _jammed_run(tmp_path)
    hidden = REPORT_COLUMNS.index("Ẩn")

    for item in summary.items:
        assert report_row(item)[hidden].endswith(" ↓")
        assert report_row(item)[hidden].removesuffix(" ↓") == str(item.hidden_boxes)


def test_the_burial_floor_is_apart_from_the_relief_ladder_in_the_report(tmp_path):
    """Two different readings, so a row must not report one as the other."""
    summary = _jammed_run(tmp_path)

    for item in summary.items:
        assert item.unburied
        assert not item.bare, "the level still carries the obstacles laid on top"
        assert item.walls or item.frozen or item.slabs or item.tunnels


def test_switching_the_floor_off_writes_the_same_levels_buried_at_their_tier(tmp_path):
    floored = _jammed_run(tmp_path / "on")
    kept = _jammed_run(tmp_path / "off", jam_relief=False)

    assert kept.written == floored.written == 3
    assert kept.unburied == 0
    assert all("chôn box hạ về Easy" not in item.detail for item in kept.items)
    assert sum(item.hidden_boxes for item in kept.items) > sum(
        item.hidden_boxes for item in floored.items
    ), "the whole point: the tier's burial is what the floor took away"


def test_a_folder_of_pictures_that_play_is_untouched_by_any_of_this(tmp_path):
    folder = _source_folder(tmp_path, levels=(1, 2))

    summary = generate_folder(
        collect_sources(folder),
        tmp_path / "out",
        AutoGenOptions(difficulty=int(LevelDifficulty.Hard), seed=4),
    )

    assert summary.unburied == 0
    assert all("chôn box hạ về Easy" not in item.detail for item in summary.items)
    hidden = REPORT_COLUMNS.index("Ẩn")
    assert all("↓" not in report_row(item)[hidden] for item in summary.items)


# --------------------------------------------------------------------------- #
# The roll count, which the run owns rather than each picture
# --------------------------------------------------------------------------- #
def test_the_folder_roll_count_reaches_every_level(tmp_path):
    folder = _source_folder(tmp_path, levels=(1, 2))

    summary = generate_folder(
        collect_sources(folder),
        tmp_path / "out",
        AutoGenOptions(difficulty=int(LevelDifficulty.Hard), seed=40),
        shuffle_attempts=4,
        write_presets=True,
        preset_folder=tmp_path / "cfg",
    )

    assert summary.written == 2
    for item in summary.items:
        saved = load_autogen_config(tmp_path / "cfg", item.level)
        assert saved.shuffle_attempts == 4, "the preset records the run it came from"
        assert saved.seed == item.seed, "and the roll that actually won"


def test_none_leaves_every_level_with_the_count_it_asked_for(tmp_path):
    folder = _source_folder(tmp_path, levels=(1,))

    summary = generate_folder(
        collect_sources(folder),
        tmp_path / "out",
        AutoGenOptions(difficulty=int(LevelDifficulty.Hard), seed=40, shuffle_attempts=3),
        write_presets=True,
        preset_folder=tmp_path / "cfg",
    )

    assert load_autogen_config(tmp_path / "cfg", 1).shuffle_attempts == 3


def test_the_roll_count_outranks_a_preset(tmp_path):
    """The doses defer to a level's own preset. This one cannot afford to.

    `write_presets` is on by default, so after one batch run every level has a
    preset carrying that run's roll count - and a dial that deferred to it would
    be dead in the workflow it exists for. It is safe to override precisely
    because it is not a design decision: every roll is a complete certified
    level and the shuffle only picks between them.
    """
    folder = _source_folder(tmp_path, levels=(1,))
    preset_dir = tmp_path / "cfg"
    preset_dir.mkdir()
    save_autogen_config(
        preset_dir,
        1,
        0,
        AutoGenOptions(difficulty=int(LevelDifficulty.Easy), seed=7, shuffle_attempts=1),
    )

    summary = generate_folder(
        collect_sources(folder),
        tmp_path / "out",
        AutoGenOptions(difficulty=int(LevelDifficulty.SuperHard), shuffle_attempts=2),
        preset_folder=preset_dir,
        use_presets=True,
        # Written back so the count the run actually used can be read rather than
        # inferred; the tier it writes back is the preset's, which is the point.
        write_presets=True,
        shuffle_attempts=5,
    )

    item = summary.items[0]
    written = load_autogen_config(preset_dir, 1)
    assert item.difficulty == int(LevelDifficulty.Easy), "the preset still owns the tier"
    assert written.difficulty == int(LevelDifficulty.Easy)
    assert written.shuffle_attempts == 5, "but the run owns how many times it rolled"
    assert item.seed in range(7, 7 + 5), "and the winning roll came out of that window"


def test_a_forced_count_is_floored_at_one_roll(tmp_path):
    """0 means "no override" at the UI; a 0 that reaches here must not mean no rolls."""
    folder = _source_folder(tmp_path, levels=(1,))

    summary = generate_folder(
        collect_sources(folder),
        tmp_path / "out",
        AutoGenOptions(difficulty=int(LevelDifficulty.Hard), seed=40),
        shuffle_attempts=0,
        write_presets=True,
        preset_folder=tmp_path / "cfg",
    )

    assert summary.written == 1
    assert load_autogen_config(tmp_path / "cfg", 1).shuffle_attempts == 1


# --------------------------------------------------------------------------- #
# The tier, read off every picture instead of typed once
# --------------------------------------------------------------------------- #
def test_picture_difficulty_reads_the_tier_off_each_picture(tmp_path):
    """One folder, two pictures, two tiers - and no number typed anywhere."""
    folder = tmp_path / "src"
    folder.mkdir()
    plain = _picture_level(1)
    plain.difficulty = int(LevelDifficulty.Easy)
    speckled = _speckled_level(2, colors=9)
    speckled.difficulty = int(LevelDifficulty.Easy)
    save_level(folder / "1.json", plain)
    save_level(folder / "2.json", speckled)

    summary = generate_folder(
        collect_sources(folder),
        tmp_path / "out",
        AutoGenOptions(difficulty=int(LevelDifficulty.Easy)),
        picture_difficulty=True,
    )

    tiers = [item.difficulty for item in summary.items]
    assert tiers[0] < tiers[1], "the busier picture came out the harder level"
    assert tiers[1] >= int(LevelDifficulty.Hard)
    # Neither of them is the Easy that was passed in, which is the whole point:
    # nobody typed a tier for either level.
    assert int(LevelDifficulty.Easy) not in tiers


def test_picture_difficulty_outranks_a_preset_and_the_level_file(tmp_path):
    """Ticked for the whole run, so no earlier run's number gets to overrule it.

    `write_presets` is on in the workflow this exists for, so by the second batch
    every level carries a preset with a tier in it - a picture-tier box that
    deferred to that would be dead exactly where it is needed.
    """
    folder = tmp_path / "src"
    folder.mkdir()
    level = _speckled_level(1, colors=9, seed=3)
    level.difficulty = int(LevelDifficulty.Easy)
    save_level(folder / "1.json", level)
    presets = tmp_path / "cfg"
    save_autogen_config(presets, 1, 0, AutoGenOptions(difficulty=int(LevelDifficulty.Easy)))

    summary = generate_folder(
        collect_sources(folder),
        tmp_path / "out",
        AutoGenOptions(difficulty=int(LevelDifficulty.Easy)),
        preset_folder=presets,
        use_presets=True,
        use_level_difficulty=True,
        picture_difficulty=True,
    )

    assert summary.items[0].difficulty > int(LevelDifficulty.Easy), (
        "the nine-colour picture, not the Easy in the preset and in the file"
    )
    # And the preset written back says how the tier was chosen, not just what it
    # came out as, so the next run rebuilds the same level.
    assert load_autogen_config(presets, 1).auto_difficulty is True


def test_without_the_box_the_preset_still_owns_the_tier(tmp_path):
    folder = _source_folder(tmp_path, levels=(1,))
    presets = tmp_path / "cfg"
    save_autogen_config(presets, 1, 0, AutoGenOptions(difficulty=int(LevelDifficulty.Hard)))

    summary = generate_folder(
        collect_sources(folder),
        tmp_path / "out",
        AutoGenOptions(difficulty=int(LevelDifficulty.Easy)),
        preset_folder=presets,
        write_presets=False,
    )

    assert summary.items[0].difficulty == int(LevelDifficulty.Hard)


# --------------------------------------------------------------------------- #
# A source that is not a current level file
# --------------------------------------------------------------------------- #
def test_a_name_that_opens_with_a_number_keeps_that_number():
    # The plain pair, unchanged.
    assert level_key_from_stem("7") == (7, 0)
    assert level_key_from_stem("7.2") == (7, 2)
    # A label after the number is a label, not a category: `3mau` is "3 màu".
    assert level_key_from_stem("4.3mau") == (4, 0)
    assert level_key_from_stem("12_final") == (12, 0)
    assert level_key_from_stem("8 copy") == (8, 0)
    # No number, or a number that runs straight into the word, claims nothing.
    assert level_key_from_stem("cat") is None
    assert level_key_from_stem("2024art") is None


def test_an_old_format_level_file_is_read_as_a_source(tmp_path):
    folder = tmp_path / "src"
    folder.mkdir()
    _write_old_format_level(folder / "4.3mau.json", level=4)

    level, legacy = load_level_source(folder / "4.3mau.json")

    assert legacy is True
    assert level.level == 4, "the number inside the file"
    assert level.piece == 5 and level.time == 60, "and the rest of its own numbers"
    painted = [value for value in level.pixel_grid.color_ids if value != EMPTY_COLOR_ID]
    assert painted, "the picture came through"
    assert 18 not in painted, "the out-of-range colour was folded onto a free one"
    assert not level.grid_cells, "the old boxes are left behind for Auto Gen Box"


def test_a_current_level_file_is_still_read_the_current_way(tmp_path):
    folder = _source_folder(tmp_path, levels=(1,))

    level, legacy = load_level_source(folder / "1.json")

    assert legacy is False
    assert level.level == 1


def test_a_picture_neither_reader_can_use_keeps_the_current_complaint(tmp_path):
    """The legacy path is a fall-back, not a way to swallow a broken file."""
    path = tmp_path / "1.json"
    path.write_text(
        json.dumps({"pixelGrid": {"width": 3, "height": 3, "colors": "nope"}}),
        encoding="utf-8",
    )

    with pytest.raises(LevelSerializationError):
        load_level_source(path)


def test_a_folder_of_old_format_files_generates(tmp_path):
    """The workflow this is for: point the run at the exports and press go."""
    folder = tmp_path / "src"
    folder.mkdir()
    for number in (4, 5):
        _write_old_format_level(folder / f"{number}.3mau.json", level=number)
    out = tmp_path / "out"

    sources = collect_sources(folder)
    assert [(source.level, source.numbered) for source in sources] == [(4, True), (5, True)]

    summary = generate_folder(sources, out, AutoGenOptions(), picture_difficulty=True)

    assert summary.written == 2
    assert sorted(path.name for path in out.iterdir()) == ["4.json", "5.json"]
    for item in summary.items:
        assert item.detail.startswith("đọc theo định dạng cũ · ")
    # And what comes out is a current level file: it reads back without the
    # legacy path being involved at all.
    reread, legacy = load_level_source(out / "4.json")
    assert legacy is False and reread.grid_cells


def test_an_old_format_file_with_no_number_inside_keeps_the_one_from_its_name(tmp_path):
    folder = tmp_path / "src"
    folder.mkdir()
    _write_old_format_level(folder / "9.3mau.json", level=None)

    level, legacy = load_level_source(folder / "9.3mau.json", fallback_level=9)

    assert legacy is True
    assert level.level == 9, "otherwise every such file would land on the reader's default"


def test_the_shape_that_used_to_be_a_read_error_is_now_a_source(tmp_path):
    """A picture sitting under "colors" is a level to generate, not a row to fix.

    Two rounds of this: it first loaded as a blank grid, so the run reported
    `sinh box thất bại: Paint the pixel grid before generating boxes` about a
    fully painted level; then it was reported as a read error naming the field
    to rename. Neither is any use to somebody holding a folder of these, so now
    it is read the way Import Old JSON reads it.
    """
    folder = tmp_path / "src"
    folder.mkdir()
    save_level(folder / "1.json", _picture_level(1))
    document = {
        "pixelGrid": {"width": 12, "height": 12, "colors": [7] * 144},
        "boxGrid": {},
        "level": 2,
        "piece": 5,
    }
    (folder / "2.json").write_text(json.dumps(document), encoding="utf-8")

    summary = generate_folder(collect_sources(folder), tmp_path / "out", AutoGenOptions())

    old_shape = next(item for item in summary.items if item.source.path.name == "2.json")
    assert old_shape.written and old_shape.status == STATUS_OK
    assert "đọc theo định dạng cũ" in old_shape.detail
    assert "không đọc được" not in old_shape.detail
    assert "Paint the pixel grid" not in old_shape.detail


def test_a_file_neither_reader_can_use_is_a_read_error_not_a_gen_failure(tmp_path):
    """The row still has to point at the file, not at the picture inside it."""
    folder = tmp_path / "src"
    folder.mkdir()
    save_level(folder / "1.json", _picture_level(1))
    document = {"pixelGrid": {"width": 12, "height": 12, "colors": "nope"}, "level": 2}
    (folder / "2.json").write_text(json.dumps(document), encoding="utf-8")

    summary = generate_folder(collect_sources(folder), tmp_path / "out", AutoGenOptions())

    good = next(item for item in summary.items if item.source.path.name == "1.json")
    bad = next(item for item in summary.items if item.source.path.name == "2.json")
    assert good.written, "one unreadable file does not stop the run"
    assert bad.status == STATUS_ERROR and not bad.written
    assert "không đọc được" in bad.detail, "the file, not the box generator"
    assert "Paint the pixel grid" not in bad.detail
