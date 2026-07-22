import json

import pytest

from pixel_level_tool.services.level_converter import (
    ConvertSummary,
    LevelConvertError,
    convert_file,
    convert_folder,
)


def _legacy_pixel_level(level: int = 1) -> dict:
    """A minimal, balanced legacy (NewRefactor.* + $type) Pixel level."""
    return {
        "pixelGrid": {
            "width": 3,
            "height": 1,
            "colorIds": [0, 0, 0],
            "modifiers": [],
            "obstacles": [],
        },
        "levelGridVersion": 1,
        "levelName": f"Pixel Level {level}",
        "mapType": 0,
        "gridRows": 3,
        "gridCols": 3,
        "board": 1,
        "gridCells": [
            {
                "$type": "NewRefactor.CellData, Assembly-CSharp",
                "colorList": [0],
                "effects": None,
                "gridX": 0,
                "gridY": 0,
                "shape": 3,
                "direction": 0,
                "id": 300,
                "isActive": True,
            }
        ],
        "gridLanes": [],
        "obstacles": [],
        "gameMode": 1,
        "difficulty": 0,
        "level": level,
        "category": 0,
    }


def _write(path, data) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_convert_file_migrates_to_new_format_in_place(tmp_path):
    target = tmp_path / "1.json"
    _write(target, _legacy_pixel_level())

    convert_file(target)

    text = target.read_text(encoding="utf-8")
    assert "$type" not in text
    written = json.loads(text)

    cell = written["boxGrid"]["gridCells"][0]
    assert cell["type"] == "Normal"
    assert cell["shape"] == "Rectangle_3x1"
    assert cell["colorList"] == ["Red"]

    assert written["time"] == 60
    assert written["piece"] == 5
    assert written["mapType"] == "None"
    assert written["gameMode"] == "Classic"
    assert written["difficulty"] == "Easy"
    for dropped in ("gridLanes", "levelName", "levelGridVersion"):
        assert dropped not in written


def test_convert_file_does_not_create_backup(tmp_path):
    target = tmp_path / "1.json"
    _write(target, _legacy_pixel_level())

    convert_file(target)

    assert not (tmp_path / "1.json.bak").exists()


def test_convert_file_rejects_non_pixel_level(tmp_path):
    target = tmp_path / "classic.json"
    cargo = _legacy_pixel_level()
    cargo["gridLanes"] = [{"laneId": 1, "cells": [0, 1]}]
    _write(target, cargo)

    with pytest.raises(LevelConvertError):
        convert_file(target)


def test_convert_folder_converts_pixel_and_skips_others(tmp_path):
    _write(tmp_path / "1.json", _legacy_pixel_level(1))
    _write(tmp_path / "2.json", _legacy_pixel_level(2))

    cargo = _legacy_pixel_level(3)
    cargo["gridLanes"] = [{"laneId": 1, "cells": [0]}]
    _write(tmp_path / "3.json", cargo)

    empty = _legacy_pixel_level(4)
    empty["pixelGrid"]["colorIds"] = [-1, -1, -1]
    _write(tmp_path / "4.json", empty)

    (tmp_path / "broken.json").write_text("{ not json", encoding="utf-8")

    summary = convert_folder(tmp_path)

    assert isinstance(summary, ConvertSummary)
    assert {path.name for path in summary.converted} == {"1.json", "2.json"}
    assert {path.name for path, _ in summary.skipped} == {"3.json", "4.json", "broken.json"}

    written = json.loads((tmp_path / "1.json").read_text(encoding="utf-8"))
    assert written["boxGrid"]["gridCells"][0]["type"] == "Normal"


def test_convert_folder_ignores_bak_files(tmp_path):
    _write(tmp_path / "1.json", _legacy_pixel_level(1))
    (tmp_path / "old.json.bak").write_text("{ not json", encoding="utf-8")

    summary = convert_folder(tmp_path)

    assert {path.name for path in summary.converted} == {"1.json"}
    assert summary.skipped == []
