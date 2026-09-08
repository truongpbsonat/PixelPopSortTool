import random

import pytest

pytest.importorskip("PySide6")
Image = pytest.importorskip("PIL.Image", reason="Pillow is needed to read picture folders")

from PySide6.QtWidgets import QDialog, QMessageBox

from pixel_level_tool.domain.enums import LevelDifficulty
from pixel_level_tool.domain.level_models import PixelGridData, PixelLevelData
from pixel_level_tool.services.box_autogen import AutoGenOptions
from pixel_level_tool.services.level_serializer import load_level, save_level
from pixel_level_tool.ui.dialogs.auto_gen_folder_dialog import AutoGenFolderDialog
from pixel_level_tool.ui.main_window import MainWindow


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


def _window(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pixel_level_tool.services.settings_service.app_data_dir", lambda: tmp_path / "app-data"
    )
    window = MainWindow()
    qtbot.addWidget(window)
    return window


# --------------------------------------------------------------------------- #
# The setup dialog
# --------------------------------------------------------------------------- #
def test_dialog_counts_what_the_source_folder_offers(qtbot, tmp_path):
    folder = _source_folder(tmp_path, levels=(1, 2), pictures=("cat.png",))
    dialog = AutoGenFolderDialog(source_folder=str(folder))
    qtbot.addWidget(dialog)

    assert len(dialog.sources) == 3
    text = dialog.summary_label.text()
    assert "1 ảnh" in text and "2 file level" in text
    # The unnumbered picture is told where it landed, not left to be discovered
    # in the output folder afterwards.
    assert "cat.png" in text


def test_dialog_refuses_to_run_without_an_output_folder(qtbot, tmp_path, monkeypatch):
    folder = _source_folder(tmp_path, levels=(1,))
    dialog = AutoGenFolderDialog(source_folder=str(folder))
    qtbot.addWidget(dialog)
    dialog.output_edit.setText("")
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args[2]))

    dialog._accept()

    assert dialog.result() != QDialog.DialogCode.Accepted
    assert warnings and "folder xuất" in warnings[0]


def test_dialog_hands_back_the_options_the_auto_gen_box_dialog_returned(qtbot, tmp_path):
    folder = _source_folder(tmp_path, levels=(1,))
    dialog = AutoGenFolderDialog(
        source_folder=str(folder),
        options=AutoGenOptions(difficulty=int(LevelDifficulty.Hard), seed=99),
    )
    qtbot.addWidget(dialog)

    assert dialog.options.difficulty == int(LevelDifficulty.Hard)
    assert "seed 99" in dialog.params_label.text()
    # The label quotes the run, and by default the run takes the tier off each
    # picture; untick that and it quotes the number handed in.
    assert "độ khó theo ảnh từng level" in dialog.params_label.text()
    dialog.picture_difficulty.setChecked(False)
    assert "độ khó 2" in dialog.params_label.text()


# --------------------------------------------------------------------------- #
# The window action
# --------------------------------------------------------------------------- #
def _run_folder_action(
    window, monkeypatch, *, source, output, presets=None, setup=None, rolls=1
):
    """Drive Auto Gen Folder with the two dialogs answered for us.

    ``rolls`` is pinned to one so a test does not pay the form's ten rolls per
    level; pass ``None`` to run on whatever the form defaults to.
    """
    reports = []

    def fake_exec(dialog):
        dialog.source_edit.setText(str(source))
        dialog.output_edit.setText(str(output))
        dialog.preset_edit.setText(str(presets) if presets is not None else "")
        dialog.use_presets.setChecked(presets is not None)
        dialog.write_presets.setChecked(presets is not None)
        dialog.pixel_width.setValue(9)
        dialog.pixel_height.setValue(9)
        if rolls is not None:
            dialog.shuffle_attempts.setValue(rolls)
        if setup is not None:
            setup(dialog)
        dialog._refresh_sources()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(
        "pixel_level_tool.ui.main_window.AutoGenFolderDialog.exec", fake_exec, raising=False
    )
    monkeypatch.setattr(
        "pixel_level_tool.ui.main_window.AutoGenBatchReportDialog.exec",
        lambda self: reports.append(self._summary),
        raising=False,
    )
    window.auto_gen_boxes_folder()
    return reports


def test_auto_gen_folder_generates_the_whole_folder(qtbot, monkeypatch, tmp_path):
    window = _window(qtbot, monkeypatch, tmp_path)
    source = _source_folder(tmp_path, levels=(1, 2), pictures=("3.png",))
    output = tmp_path / "out"
    presets = tmp_path / "cfg"

    reports = _run_folder_action(
        window, monkeypatch, source=source, output=output, presets=presets
    )

    assert len(reports) == 1
    summary = reports[0]
    assert summary.total == 3 and summary.generated + summary.jammed == 3
    assert sorted(path.name for path in output.iterdir()) == ["1.json", "2.json", "3.json"]
    assert sorted(path.name for path in presets.iterdir()) == [
        "genlv1.json",
        "genlv2.json",
        "genlv3.json",
    ]
    # The folders are remembered, so the next run opens on them.
    assert window.settings.get("autogen_batch_source_dir") == str(source)
    assert window.settings.get("autogen_batch_output_dir") == str(output)
    assert window.settings.get("autogen_config_dir") == str(presets)


def test_the_editor_keeps_one_workbench_window_and_opens_levels_from_it(
    qtbot, monkeypatch, tmp_path
):
    window = _window(qtbot, monkeypatch, tmp_path)
    source = _source_folder(tmp_path, levels=(1, 2))

    window.open_auto_gen_folder_window()
    bench = window.auto_gen_folder_window
    qtbot.addWidget(bench)
    assert bench.isVisible()

    # Asking again raises the same window rather than stacking a second one.
    window.open_auto_gen_folder_window()
    assert window.auto_gen_folder_window is bench

    # A row in the workbench's log routes the file back into the editor.
    bench.open_level_requested.emit(str(source / "2.json"))
    assert window.path == source / "2.json"
    assert window.level.level == 2


def test_the_report_table_exports_every_row_to_csv(qtbot, monkeypatch, tmp_path):
    import csv

    from PySide6.QtWidgets import QFileDialog

    from pixel_level_tool.services.autogen_batch import REPORT_COLUMNS, collect_sources, generate_folder
    from pixel_level_tool.ui.dialogs.auto_gen_batch_report_dialog import AutoGenBatchReportDialog

    source = _source_folder(tmp_path, levels=(1, 2))
    summary = generate_folder(collect_sources(source), tmp_path / "out", AutoGenOptions())
    dialog = AutoGenBatchReportDialog(summary)
    qtbot.addWidget(dialog)

    assert dialog.table.rowCount() == 2
    assert dialog.table.item(0, 0).text() == "1.json"

    target = tmp_path / "report.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    dialog.export_csv()

    with open(target, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == list(REPORT_COLUMNS)
    assert [row[0] for row in rows[1:]] == ["1.json", "2.json"]


def test_auto_gen_folder_reloads_the_open_level_it_overwrote(qtbot, monkeypatch, tmp_path):
    window = _window(qtbot, monkeypatch, tmp_path)
    source = _source_folder(tmp_path, levels=(1, 2))
    window._load_path(source / "1.json", from_level_folder=True)
    assert not window.level.grid_cells, "the fixture level has a picture but no boxes yet"

    _run_folder_action(window, monkeypatch, source=source, output=source)

    assert window.level.grid_cells, "the regenerated file is what is on screen"
    # BoxCellData carries a per-instance uid, so the grids are compared by what
    # a designer would see rather than by object equality.
    written = load_level(source / "1.json")
    assert [(cell.grid_x, cell.grid_y, int(cell.color)) for cell in window.level.grid_cells] == [
        (cell.grid_x, cell.grid_y, int(cell.color)) for cell in written.grid_cells
    ]
    assert not window.dirty


def test_auto_gen_folder_keeps_unsaved_work_and_warns_instead(qtbot, monkeypatch, tmp_path):
    window = _window(qtbot, monkeypatch, tmp_path)
    source = _source_folder(tmp_path, levels=(1,))
    window._load_path(source / "1.json", from_level_folder=True)
    window._set_dirty(True)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args[2]))

    _run_folder_action(window, monkeypatch, source=source, output=source)

    assert warnings and "chưa lưu" in warnings[0]
    assert not window.level.grid_cells, "the level on screen was left as the designer had it"
    # Closing a dirty window asks a modal question qtbot's teardown cannot answer.
    window._set_dirty(False)


def test_the_report_headline_names_the_levels_whose_burial_was_floored(
    qtbot, tmp_path
):
    """The report is opened once per folder run, so the count belongs on its first line."""
    from pixel_level_tool.services.autogen_batch import (
        REPORT_COLUMNS,
        collect_sources,
        generate_folder,
    )
    from pixel_level_tool.ui.dialogs.auto_gen_batch_report_dialog import (
        AutoGenBatchReportDialog,
    )

    source = tmp_path / "src"
    source.mkdir()
    for number in (1, 2):
        rng = random.Random(number)
        ids = [rng.randrange(1, 7) for _ in range(12 * 12)]
        save_level(
            source / f"{number}.json",
            PixelLevelData(level=number, piece=3, pixel_grid=PixelGridData(12, 12, ids)),
        )
    summary = generate_folder(
        collect_sources(source),
        tmp_path / "out",
        AutoGenOptions(
            difficulty=int(LevelDifficulty.SuperHard), seed=4, repair_picture=False
        ),
    )

    dialog = AutoGenBatchReportDialog(summary)
    qtbot.addWidget(dialog)

    assert summary.unburied == 2
    text = dialog._headline(summary)
    assert "2 hạ chôn box về Easy (nâng piece)" in text
    assert "2 KẸT" in text, "the jam is still said, and this is the actionable half of it"
    # And the row's own Ẩn column is marked, so the table can be scanned.
    hidden = REPORT_COLUMNS.index("Ẩn")
    assert dialog.table.item(0, hidden).text().endswith(" ↓")


def test_the_one_shot_dialog_passes_the_folder_roll_count_through(qtbot, monkeypatch, tmp_path):
    """`main_window` builds its own kwargs by hand, so the field is wired twice.

    The window path goes through `AutoGenFolderForm.run_kwargs`; this one does
    not, and a field added to the form alone would be silently dropped here.
    """
    from pixel_level_tool.services.autogen_config import load_autogen_config

    window = _window(qtbot, monkeypatch, tmp_path)
    source = _source_folder(tmp_path, levels=(1, 2))
    presets = tmp_path / "cfg"

    reports = _run_folder_action(
        window,
        monkeypatch,
        source=source,
        output=tmp_path / "out",
        presets=presets,
        setup=lambda dialog: dialog.shuffle_attempts.setValue(4),
    )

    assert reports and reports[0].written == 2
    for level in (1, 2):
        assert load_autogen_config(presets, level).shuffle_attempts == 4


def test_theo_tham_so_hands_the_count_back_to_the_params_dialog(qtbot, monkeypatch, tmp_path):
    from pixel_level_tool.services.autogen_config import load_autogen_config

    window = _window(qtbot, monkeypatch, tmp_path)
    source = _source_folder(tmp_path, levels=(1,))
    presets = tmp_path / "cfg"

    def setup(dialog):
        dialog.form.options = AutoGenOptions(shuffle_attempts=2)
        dialog.shuffle_attempts.setValue(0)  # "Theo tham số"

    _run_folder_action(
        window,
        monkeypatch,
        source=source,
        output=tmp_path / "out",
        presets=presets,
        setup=setup,
    )

    assert load_autogen_config(presets, 1).shuffle_attempts == 2


def test_the_one_shot_dialog_runs_the_folder_defaults_without_the_params_dialog(
    qtbot, monkeypatch, tmp_path
):
    """The whole point of the action: press Sinh cả folder and get both defaults.

    Ten rolls per level and a tier read off each picture, with the params dialog
    never opened - which is the flow the folder run exists for.
    """
    from pixel_level_tool.services.autogen_config import load_autogen_config

    window = _window(qtbot, monkeypatch, tmp_path)
    source = _source_folder(tmp_path, levels=(1,))
    presets = tmp_path / "cfg"

    reports = _run_folder_action(
        window,
        monkeypatch,
        source=source,
        output=tmp_path / "out",
        presets=presets,
        rolls=None,
    )

    assert reports and reports[0].written == 1
    saved = load_autogen_config(presets, 1)
    assert saved.shuffle_attempts == 10
    assert saved.auto_difficulty is True
