import csv
import random

import pytest

pytest.importorskip("PySide6")
Image = pytest.importorskip("PIL.Image", reason="Pillow is needed to read picture folders")

from PySide6.QtWidgets import QFileDialog, QMessageBox

from pixel_level_tool.domain.level_models import PixelGridData, PixelLevelData
from pixel_level_tool.services.autogen_batch import REPORT_COLUMNS
from pixel_level_tool.services.level_serializer import save_level
from pixel_level_tool.ui.auto_gen_folder_window import AutoGenFolderWindow


def _picture_level(level_number: int, *, seed: int = 7, size: int = 9) -> PixelLevelData:
    rng = random.Random(seed)
    ids = [rng.randrange(1, 4) for _ in range(size * size)]
    return PixelLevelData(level=level_number, piece=5, pixel_grid=PixelGridData(size, size, ids))


def _source_folder(tmp_path, *, levels=(1, 2), pictures=()):
    folder = tmp_path / "src"
    folder.mkdir()
    for number in levels:
        save_level(folder / f"{number}.json", _picture_level(number, seed=number))
    for name in pictures:
        image = Image.new("RGBA", (18, 18), (255, 0, 0, 255))
        for y in range(9):
            for x in range(18):
                image.putpixel((x, y), (0, 0, 255, 255))
        image.save(folder / name)
    return folder


def _window(qtbot, tmp_path, *, levels=(1, 2), pictures=()):
    source = _source_folder(tmp_path, levels=levels, pictures=pictures)
    window = AutoGenFolderWindow()
    qtbot.addWidget(window)
    window.form.source_edit.setText(str(source))
    window.form.output_edit.setText(str(tmp_path / "out"))
    window.form.preset_edit.setText(str(tmp_path / "cfg"))
    window.form.pixel_width.setValue(9)
    window.form.pixel_height.setValue(9)
    # Pinned to one roll so these tests do not each pay the form's ten; the
    # default itself is covered by its own test below.
    window.form.shuffle_attempts.setValue(1)
    window.form.refresh_sources()
    return window, source, tmp_path / "out"


def _run_and_wait(qtbot, window, timeout=120_000):
    window.start_run()
    qtbot.waitUntil(lambda: window.summary is not None, timeout=timeout)
    qtbot.waitUntil(lambda: not window.running, timeout=timeout)


# --------------------------------------------------------------------------- #
# Listing and preview
# --------------------------------------------------------------------------- #
def test_window_lists_every_source_with_the_level_it_becomes(qtbot, tmp_path):
    window, _, _ = _window(qtbot, tmp_path, levels=(1, 2), pictures=("cat.png",))

    assert window.source_table.rowCount() == 3
    names = [window.source_table.item(row, 0).text() for row in range(3)]
    assert names == ["1.json", "2.json", "cat.png"]
    kinds = [window.source_table.item(row, 1).text() for row in range(3)]
    assert kinds == ["level", "level", "ảnh"]
    # The picture has no number of its own, and the row says where it landed.
    assert "(tự đánh)" in window.source_table.item(2, 2).text()


def test_selecting_a_row_previews_that_picture(qtbot, tmp_path):
    window, _, _ = _window(qtbot, tmp_path, levels=(1,), pictures=("cat.png",))

    window.source_table.selectRow(0)
    assert window.preview.grid is not None
    assert (window.preview.grid.width, window.preview.grid.height) == (9, 9)
    assert "1.json" in window.preview_label.text() and "màu" in window.preview_label.text()

    # The 18x18 picture is over the 9x9 cap, so it is fitted to it - and being
    # square, it fits square.
    window.source_table.selectRow(1)
    assert (window.preview.grid.width, window.preview.grid.height) == (9, 9)
    assert "cat.png" in window.preview_label.text()


def test_the_preview_follows_the_size_the_run_would_use(qtbot, tmp_path):
    """The knob is only believable if the picture under it moves when it is turned."""
    window, source, _ = _window(qtbot, tmp_path, levels=(1,), pictures=("cat.png",))
    # A picture with a shape, so "kept" and "squashed" are different answers.
    image = Image.new("RGBA", (20, 10), (255, 0, 0, 255))
    image.save(source / "cat.png")
    window.form.refresh_sources()
    window.form.pixel_width.setValue(32)
    window.form.pixel_height.setValue(32)

    window.source_table.selectRow(1)
    # Inside the cap, so the art's own size stands and nothing is resampled.
    assert (window.preview.grid.width, window.preview.grid.height) == (20, 10)
    assert "20x10" in window.preview_label.text()

    # Turning it off redraws at the typed size, without needing a reselect.
    window.form.size_from_image.setChecked(False)
    assert (window.preview.grid.width, window.preview.grid.height) == (32, 32)
    assert "32x32" in window.preview_label.text()


def test_the_arrows_walk_the_source_list(qtbot, tmp_path):
    window, _, _ = _window(qtbot, tmp_path, levels=(1, 2, 3))

    window.source_table.selectRow(0)
    window.next_action.trigger()
    assert window.source_table.currentRow() == 1
    window.prev_action.trigger()
    assert window.source_table.currentRow() == 0
    # Walking off the end stays on the end rather than wrapping.
    window.prev_action.trigger()
    assert window.source_table.currentRow() == 0


# --------------------------------------------------------------------------- #
# Running
# --------------------------------------------------------------------------- #
def test_running_the_folder_fills_the_log_and_writes_the_levels(qtbot, tmp_path):
    window, _, out = _window(qtbot, tmp_path, levels=(1, 2), pictures=("cat.png",))

    _run_and_wait(qtbot, window)

    assert sorted(path.name for path in out.iterdir()) == ["1.json", "2.json", "3.json"]
    assert window.result_table.rowCount() == 3
    assert window.result_table.item(0, 0).text() == "1.json"
    # Every source row is marked with how it ended.
    assert [window.source_table.item(row, 3).text() for row in range(3)] == ["xong"] * 3
    assert "3 xong" in window.progress_label.text()
    assert window.export_action.isEnabled()


def test_only_the_selected_rows_are_generated_when_asked(qtbot, tmp_path):
    window, _, out = _window(qtbot, tmp_path, levels=(1, 2, 3))
    window.only_selected.setChecked(True)
    window.source_table.selectRow(1)

    _run_and_wait(qtbot, window)

    assert [path.name for path in out.iterdir()] == ["2.json"]
    assert window.result_table.rowCount() == 1


def test_a_run_without_an_output_folder_says_so_instead_of_starting(qtbot, tmp_path, monkeypatch):
    window, _, _ = _window(qtbot, tmp_path, levels=(1,))
    window.form.output_edit.setText("")
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args[2]))

    window.start_run()

    assert warnings and "folder xuất" in warnings[0]
    assert window.worker is None


# --------------------------------------------------------------------------- #
# After the run
# --------------------------------------------------------------------------- #
def test_double_clicking_a_result_row_asks_the_editor_to_open_it(qtbot, tmp_path):
    window, _, out = _window(qtbot, tmp_path, levels=(1,))
    _run_and_wait(qtbot, window)

    opened = []
    window.open_level_requested.connect(opened.append)
    window._open_generated_level(window.result_table.item(0, 0))

    assert opened == [str(out / "1.json")]


def test_clear_log_empties_the_table_and_the_source_marks(qtbot, tmp_path):
    window, _, _ = _window(qtbot, tmp_path, levels=(1,))
    _run_and_wait(qtbot, window)

    window.clear_log()

    assert window.result_table.rowCount() == 0
    assert window.source_table.item(0, 3).text() == ""
    assert not window.export_action.isEnabled()


def test_the_log_exports_to_csv(qtbot, tmp_path, monkeypatch):
    window, _, _ = _window(qtbot, tmp_path, levels=(1, 2))
    _run_and_wait(qtbot, window)

    target = tmp_path / "report.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    window.export_csv()

    with open(target, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == list(REPORT_COLUMNS)
    assert [row[0] for row in rows[1:]] == ["1.json", "2.json"]


# --------------------------------------------------------------------------- #
# The picture that cannot be won at all
# --------------------------------------------------------------------------- #
def _jammed_window(qtbot, tmp_path, *, levels=(1, 2), **knobs):
    """A folder of speckled pictures on `piece` 3, which none of them can be won on.

    The folder run is where the burial floor matters most - a hundred pictures
    scaled off one template all carry that template's `piece` - so the headline
    has to name the count, not leave it to be found row by row.
    """
    from pixel_level_tool.domain.enums import LevelDifficulty
    from pixel_level_tool.services.box_autogen import AutoGenOptions

    source = tmp_path / "src"
    source.mkdir()
    for number in levels:
        rng = random.Random(number)
        ids = [rng.randrange(1, 7) for _ in range(12 * 12)]
        save_level(
            source / f"{number}.json",
            PixelLevelData(level=number, piece=3, pixel_grid=PixelGridData(12, 12, ids)),
        )
    window = AutoGenFolderWindow()
    qtbot.addWidget(window)
    window.form.source_edit.setText(str(source))
    window.form.output_edit.setText(str(tmp_path / "out"))
    window.form.preset_edit.setText(str(tmp_path / "cfg"))
    window.form.shuffle_attempts.setValue(1)
    # These levels are about what a pinned SuperHard does to a picture that
    # cannot be won, so the tier is not handed to the picture here.
    window.form.picture_difficulty.setChecked(False)
    window.form.refresh_sources()
    window.form.options = AutoGenOptions(
        difficulty=int(LevelDifficulty.SuperHard), seed=4, repair_picture=False, **knobs
    )
    return window


def test_the_headline_names_how_many_levels_had_their_burial_floored(qtbot, tmp_path):
    window = _jammed_window(qtbot, tmp_path)

    _run_and_wait(qtbot, window)

    assert window.summary.unburied == 2
    assert "2 hạ chôn box về Easy" in window.progress_label.text()
    assert "nâng piece" in window.progress_label.text(), "the headline says the fix too"


def test_the_headline_says_nothing_when_no_picture_jammed(qtbot, tmp_path):
    window, _, _ = _window(qtbot, tmp_path, levels=(1, 2))

    _run_and_wait(qtbot, window)

    assert window.summary.unburied == 0
    assert "chôn box" not in window.progress_label.text()


def test_the_params_label_warns_when_the_floor_is_switched_off(qtbot, tmp_path):
    window = _jammed_window(qtbot, tmp_path, jam_relief=False)

    assert "KHÔNG hạ chôn box khi tranh kẹt" in window.form.params_label.text()

    from pixel_level_tool.services.box_autogen import AutoGenOptions

    window.form.options = AutoGenOptions(difficulty=1)
    assert "KHÔNG hạ chôn box" not in window.form.params_label.text()


# --------------------------------------------------------------------------- #
# The roll count, as its own field on the folder form
# --------------------------------------------------------------------------- #
def test_the_roll_count_field_defaults_to_ten_rolls_for_the_whole_folder(qtbot, tmp_path):
    """A folder run is unattended, so the rolling nobody is there to do is the default."""
    from pixel_level_tool.ui.widgets.auto_gen_folder_form import (
        DEFAULT_FOLDER_SHUFFLE,
        AutoGenFolderForm,
    )

    form = AutoGenFolderForm()
    qtbot.addWidget(form)

    assert DEFAULT_FOLDER_SHUFFLE == 10
    assert form.shuffle_attempts.value() == DEFAULT_FOLDER_SHUFFLE
    assert form.shuffle_override == DEFAULT_FOLDER_SHUFFLE
    assert form.run_kwargs()["shuffle_attempts"] == DEFAULT_FOLDER_SHUFFLE
    assert "xóc 10 lần (cả folder)" in form.params_label.text()


def test_zero_still_hands_the_roll_count_back_to_the_params(qtbot, tmp_path):
    window, _, _ = _window(qtbot, tmp_path, levels=(1,))

    window.form.shuffle_attempts.setValue(0)

    assert window.form.shuffle_attempts.specialValueText() == "Theo tham số"
    assert window.form.shuffle_override is None
    assert window.form.run_kwargs()["shuffle_attempts"] is None


def test_a_typed_roll_count_reaches_the_run_and_the_summary_line(qtbot, tmp_path):
    window, _, _ = _window(qtbot, tmp_path, levels=(1,))

    window.form.shuffle_attempts.setValue(6)

    assert window.form.shuffle_override == 6
    assert window.form.run_kwargs()["shuffle_attempts"] == 6
    # The label beside the params button would otherwise still be quoting the
    # dialog's own count, which the run is about to override.
    assert "xóc 6 lần (cả folder)" in window.form.params_label.text()


def test_clearing_the_field_hands_the_count_back_to_the_params_dialog(qtbot, tmp_path):
    from pixel_level_tool.services.box_autogen import AutoGenOptions

    window, _, _ = _window(qtbot, tmp_path, levels=(1,))
    window.form.options = AutoGenOptions(difficulty=1, shuffle_attempts=3)
    # The tier box says "(cả folder)" too, and this test is about the rolls.
    window.form.picture_difficulty.setChecked(False)

    window.form.shuffle_attempts.setValue(6)
    assert "xóc 6 lần (cả folder)" in window.form.params_label.text()

    window.form.shuffle_attempts.setValue(0)
    assert "xóc 3 lần" in window.form.params_label.text()
    assert "cả folder" not in window.form.params_label.text()
    assert window.form.shuffle_override is None


def test_the_field_rolls_every_level_in_a_real_folder_run(qtbot, tmp_path):
    from pixel_level_tool.services.autogen_config import load_autogen_config

    window, _, _ = _window(qtbot, tmp_path, levels=(1, 2))
    window.form.shuffle_attempts.setValue(3)

    _run_and_wait(qtbot, window)

    assert window.summary.written == 2
    for item in window.summary.items:
        assert load_autogen_config(tmp_path / "cfg", item.level).shuffle_attempts == 3


# --------------------------------------------------------------------------- #
# The tier, taken off each picture instead of typed in the params dialog
# --------------------------------------------------------------------------- #
def test_the_tier_is_read_off_each_picture_by_default(qtbot, tmp_path):
    """What "Sinh cả folder" is for: no params dialog opened, per-level tiers anyway."""
    from pixel_level_tool.ui.widgets.auto_gen_folder_form import AutoGenFolderForm

    form = AutoGenFolderForm()
    qtbot.addWidget(form)

    assert form.picture_difficulty.isChecked()
    assert form.run_kwargs()["picture_difficulty"] is True
    assert "độ khó theo ảnh từng level" in form.params_label.text()
    # The level-file tier box is inert while the picture is answering, and says so
    # rather than reading as a second opinion the run might still take.
    assert not form.use_level_difficulty.isEnabled()
    assert "không có tác dụng" in form.use_level_difficulty.toolTip()

    form.picture_difficulty.setChecked(False)
    assert form.use_level_difficulty.isEnabled()
    assert "theo ảnh từng level" not in form.params_label.text()


def test_a_real_run_gives_each_level_the_tier_of_its_own_picture(qtbot, tmp_path):
    from pixel_level_tool.services.autogen_config import load_autogen_config

    window, source, _ = _window(qtbot, tmp_path, levels=(1,))
    # A busier picture than the fixture's, so a tier read off it cannot be the
    # Easy the params dialog would otherwise have handed over.
    rng = random.Random(9)
    save_level(
        source / "1.json",
        PixelLevelData(
            level=1,
            piece=5,
            pixel_grid=PixelGridData(12, 12, [rng.randrange(1, 10) for _ in range(144)]),
        ),
    )
    window.form.refresh_sources()

    _run_and_wait(qtbot, window)

    item = window.summary.items[0]
    assert item.difficulty > 0, "the picture's tier, not the dialog's Easy"
    # And the preset written beside it records how that tier was chosen, so the
    # next run over the same folder rebuilds the same level.
    assert load_autogen_config(tmp_path / "cfg", 1).auto_difficulty is True


def test_an_old_format_export_previews_and_generates_from_the_window(qtbot, tmp_path):
    """The preview reads the same way the run does, or a valid source looks broken."""
    import json

    from pixel_level_tool.domain.enums import EMPTY_COLOR_ID

    window, source, out = _window(qtbot, tmp_path, levels=())
    rng = random.Random(4)
    (source / "4.3mau.json").write_text(
        json.dumps(
            {
                "time": 60,
                "piece": 5,
                "gameMode": 0,
                "difficulty": 0,
                "level": 4,
                "category": 0,
                "pixelGrid": {
                    "width": 9,
                    "height": 9,
                    "colors": [rng.choice([-1, 5, 15, 18]) for _ in range(81)],
                },
                "gridBoard": {"columns": 3, "rows": 5, "cells": []},
            }
        ),
        encoding="utf-8",
    )
    window.form.refresh_sources()

    window.source_table.selectRow(0)
    assert window.preview.grid is not None, "the old shape draws rather than reading as broken"
    assert any(value != EMPTY_COLOR_ID for value in window.preview.grid.color_ids)
    assert "không đọc được" not in window.preview_label.text()

    _run_and_wait(qtbot, window)

    assert [path.name for path in out.iterdir()] == ["4.json"], "its own level number"
    assert "đọc theo định dạng cũ" in window.summary.items[0].detail
