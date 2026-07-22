import json

from pixel_level_tool.services.mechanics_batch import scan_mechanics_in_folder


def _write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


def test_folder_scan_is_recursive_preserves_unknown_fields_and_continues_after_failure(tmp_path):
    changed = tmp_path / "nested" / "changed.json"
    unchanged = tmp_path / "unchanged.json"
    broken = tmp_path / "broken.json"
    _write(
        changed,
        {
            "customRuntimeField": {"keep": True},
            "mechanics": ["Old"],
            "boxGrid": {
                "gridCells": [
                    {
                        "type": "PopMachine",
                        "storedCells": [{"type": "Normal", "effects": [{"type": "Frozen"}]}],
                    }
                ],
                "obstacles": [{"type": "Pins"}],
            },
        },
    )
    _write(
        unchanged,
        {
            "mechanics": ["Hidden"],
            "boxGrid": {
                "gridCells": [{"type": "Normal", "effects": [{"type": "Hidden"}]}],
                "obstacles": [],
            },
        },
    )
    broken.write_text("{not json", encoding="utf-8")

    summary = scan_mechanics_in_folder(tmp_path)

    assert summary.total == 3
    assert summary.changed == 1
    assert summary.unchanged == 1
    assert summary.failed == 1
    saved = json.loads(changed.read_text(encoding="utf-8"))
    assert saved["mechanics"] == ["PopMachine", "Frozen", "Pins"]
    assert saved["customRuntimeField"] == {"keep": True}
    assert unchanged.read_text(encoding="utf-8").startswith("{")
    assert broken.read_text(encoding="utf-8") == "{not json"


def test_folder_scan_dry_run_reports_changes_without_writing(tmp_path):
    path = tmp_path / "level.json"
    original = {
        "mechanics": ["Stale"],
        "boxGrid": {"gridCells": [{"type": "Tunnel", "storedCells": None}], "obstacles": None},
    }
    _write(path, original)

    summary = scan_mechanics_in_folder(tmp_path, dry_run=True)

    assert summary.changed == 1
    assert summary.unchanged == 0
    assert json.loads(path.read_text(encoding="utf-8")) == original
