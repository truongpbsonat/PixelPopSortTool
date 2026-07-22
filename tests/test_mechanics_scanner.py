from pixel_level_tool.domain.level_models import (
    ArrowLockCellEffectData,
    BoxCellData,
    ElevatorLayerData,
    ElevatorObstacleData,
    FrozenCellEffectData,
    HiddenCellEffectData,
    KeyForLockedGateCellEffectData,
    LargeBlockObstacleData,
    LinkedContainerObstacleData,
    LockedGateObstacleData,
    PixelLevelData,
    ScissorForWoolCrateCellEffectData,
    TunnelCellData,
)
from pixel_level_tool.services.mechanics_scanner import MechanicsScanner


def test_model_scan_is_recursive_unique_and_uses_registry_order():
    stored = BoxCellData(
        0,
        0,
        is_active=False,
        effects=[FrozenCellEffectData(2), KeyForLockedGateCellEffectData()],
    )
    tunnel = TunnelCellData(0, 0, is_active=False, stored_cells=[stored])
    hidden_elevator_cell = BoxCellData(
        0,
        0,
        effects=[HiddenCellEffectData(), ArrowLockCellEffectData(), ScissorForWoolCrateCellEffectData()],
    )
    level = PixelLevelData(
        grid_cells=[tunnel],
        obstacles=[
            LockedGateObstacleData(),
            LinkedContainerObstacleData(),
            LargeBlockObstacleData(),
            ElevatorObstacleData(layers=[ElevatorLayerData([hidden_elevator_cell])]),
        ],
        mechanics=["RemovedMechanic", "Frozen"],
    )

    assert MechanicsScanner().scan(level) == [
        "Tunnel",
        "Frozen",
        "Hidden",
        "ArrowLock",
        "LinkedContainer",
        "LargeBlock",
        "LockedGate",
        "Elevator",
    ]


def test_supporting_effects_and_pixel_data_do_not_create_mechanics():
    level = PixelLevelData(
        grid_cells=[
            BoxCellData(
                0,
                0,
                effects=[KeyForLockedGateCellEffectData(), ScissorForWoolCrateCellEffectData()],
            )
        ]
    )
    level.pixel_grid.modifiers = [{"type": "Ice"}, {"type": "HiddenColor"}]
    level.pixel_grid.obstacles = [{"type": "Frozen"}]

    assert MechanicsScanner().scan(level) == []


def test_document_scan_handles_trio_pop_machine_nested_cells_and_elevator_effects():
    document = {
        "pixelGrid": {
            "modifiers": [{"type": "Ice"}, {"type": "HiddenColor"}],
            "obstacles": [{"type": "Frozen"}],
        },
        "boxGrid": {
            "gridCells": [
                {
                    "type": "PopMachine",
                    "isActive": False,
                    "storedCells": [
                        {
                            "type": "Tunnel",
                            "storedCells": [
                                {"type": "TrioBox", "effects": [{"type": "Frozen"}]}
                            ],
                        }
                    ],
                },
                {"type": "LargeBlock", "effects": [{"type": "Hidden"}]},
            ],
            "obstacles": [
                {"type": "WoolCrate"},
                {
                    "type": "Elevator",
                    "layers": [
                        {
                            "cells": [
                                {
                                    "type": "Normal",
                                    "effects": [
                                        {"type": "Hidden"},
                                        {"type": "ArrowLock"},
                                        {"type": "KeyForLockedGate"},
                                    ],
                                }
                            ]
                        }
                    ],
                },
            ],
        },
    }

    result = MechanicsScanner().scan_document(document)

    assert result.mechanics == [
        "Tunnel",
        "TrioBox",
        "PopMachine",
        "Frozen",
        "Hidden",
        "ArrowLock",
        "WoolCrate",
        "Elevator",
    ]
    assert result.warnings == []


def test_document_scan_reports_unknown_types_without_writing_ids():
    document = {
        "boxGrid": {
            "gridCells": [
                {"type": "Mystery", "effects": [{"type": "UnknownEffect"}]},
                {"type": "LargeBlock"},
            ],
            "obstacles": [{"type": "LinkedObstacle"}],
        }
    }

    result = MechanicsScanner().scan_document(document)

    assert result.mechanics == []
    assert len(result.warnings) == 2
    assert any("Mystery" in warning for warning in result.warnings)
    assert any("LinkedObstacle" in warning for warning in result.warnings)
