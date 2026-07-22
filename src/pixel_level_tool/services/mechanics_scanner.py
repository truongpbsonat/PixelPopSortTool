from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from pixel_level_tool.domain.level_models import (
    ArrowLockCellEffectData,
    ColorGateObstacleData,
    ElevatorObstacleData,
    FrozenCellEffectData,
    HiddenCellEffectData,
    LargeBlockObstacleData,
    LinkedContainerObstacleData,
    LockedGateObstacleData,
    PinsObstacleData,
    PixelLevelData,
    TunnelCellData,
    WoolCrateObstacleData,
)


ALL_ACTIVE_MECHANICS: tuple[str, ...] = (
    "Tunnel",
    "TrioBox",
    "PopMachine",
    "Frozen",
    "Hidden",
    "ArrowLock",
    "LinkedContainer",
    "LargeBlock",
    "ColorGate",
    "Pins",
    "LockedGate",
    "WoolCrate",
    "Elevator",
)

_CELL_MECHANIC_BY_TYPE = {
    "Tunnel": "Tunnel",
    "TrioBox": "TrioBox",
    "PopMachine": "PopMachine",
}
_EFFECT_MECHANIC_BY_TYPE = {
    "Frozen": "Frozen",
    "Hidden": "Hidden",
    "ArrowLock": "ArrowLock",
}
_OBSTACLE_MECHANIC_BY_TYPE = {
    "LinkedContainer": "LinkedContainer",
    "LargeBlock": "LargeBlock",
    "ColorGate": "ColorGate",
    "Pins": "Pins",
    "LockedGate": "LockedGate",
    "WoolCrate": "WoolCrate",
    "Elevator": "Elevator",
}
_KNOWN_IGNORED_CELL_TYPES = {"Normal", "LargeBlock"}
_KNOWN_IGNORED_EFFECT_TYPES = {"KeyForLockedGate", "ScissorForWoolCrate"}


class MechanicsScanError(ValueError):
    pass


@dataclass
class MechanicsScanResult:
    mechanics: list[str]
    warnings: list[str] = field(default_factory=list)


class MechanicsScanner:
    def scan(self, level: PixelLevelData) -> list[str]:
        return self.scan_level(level).mechanics

    def scan_level(self, level: PixelLevelData) -> MechanicsScanResult:
        if not isinstance(level, PixelLevelData):
            raise MechanicsScanError("Expected PixelLevelData.")

        discovered: set[str] = set()
        warnings: list[str] = []
        for cell in level.grid_cells or []:
            self._scan_model_cell(cell, discovered, warnings)
        for obstacle in level.obstacles or []:
            mechanic = self._model_obstacle_mechanic(obstacle)
            if mechanic is None:
                warnings.append(f"Unknown obstacle runtime type: {type(obstacle).__name__}.")
                continue
            discovered.add(mechanic)
            if isinstance(obstacle, ElevatorObstacleData):
                for layer in obstacle.layers or []:
                    for cell in layer.cells or []:
                        self._scan_model_effects(cell.effects, discovered, warnings)
        return MechanicsScanResult(self._ordered(discovered), warnings)

    def scan_document(self, document: dict[str, Any]) -> MechanicsScanResult:
        if not isinstance(document, dict):
            raise MechanicsScanError("Root JSON must be an object.")

        box_grid = document.get("boxGrid")
        if box_grid is None:
            box_grid = {}
        if not isinstance(box_grid, dict):
            raise MechanicsScanError("boxGrid must be an object or null.")

        discovered: set[str] = set()
        warnings: list[str] = []
        for cell in self._optional_list(box_grid.get("gridCells"), "boxGrid.gridCells"):
            self._scan_document_cell(cell, discovered, warnings, "boxGrid.gridCells")
        for obstacle in self._optional_list(box_grid.get("obstacles"), "boxGrid.obstacles"):
            if not isinstance(obstacle, dict):
                raise MechanicsScanError("boxGrid.obstacles entries must be objects.")
            type_name = obstacle.get("type")
            mechanic = _OBSTACLE_MECHANIC_BY_TYPE.get(type_name)
            if mechanic is None:
                warnings.append(f"Unknown obstacle type: {type_name!r}.")
                continue
            discovered.add(mechanic)
            if type_name == "Elevator":
                self._scan_elevator_document_effects(obstacle, discovered, warnings)
        return MechanicsScanResult(self._ordered(discovered), warnings)

    def _scan_model_cell(self, cell: object, discovered: set[str], warnings: list[str]) -> None:
        type_name = type(cell).__name__
        if isinstance(cell, TunnelCellData):
            discovered.add("Tunnel")
        elif type_name == "TrioBoxCellData":
            discovered.add("TrioBox")
        elif type_name in {"PopMachineData", "PopMachineCellData"}:
            discovered.add("PopMachine")
        elif type_name != "BoxCellData":
            if type_name != "LargeBlockCellData":
                warnings.append(f"Unknown cell runtime type: {type_name}.")

        if type_name in {"BoxCellData", "TrioBoxCellData"}:
            self._scan_model_effects(getattr(cell, "effects", None), discovered, warnings)
        if isinstance(cell, TunnelCellData) or type_name in {"PopMachineData", "PopMachineCellData"}:
            for stored_cell in getattr(cell, "stored_cells", None) or []:
                self._scan_model_cell(stored_cell, discovered, warnings)

    @staticmethod
    def _scan_model_effects(effects: Iterable[object] | None, discovered: set[str], warnings: list[str]) -> None:
        for effect in effects or []:
            if isinstance(effect, FrozenCellEffectData):
                discovered.add("Frozen")
            elif isinstance(effect, HiddenCellEffectData):
                discovered.add("Hidden")
            elif isinstance(effect, ArrowLockCellEffectData):
                discovered.add("ArrowLock")
            elif type(effect).__name__ not in {
                "KeyForLockedGateCellEffectData",
                "ScissorForWoolCrateCellEffectData",
            }:
                warnings.append(f"Unknown cell effect runtime type: {type(effect).__name__}.")

    @staticmethod
    def _model_obstacle_mechanic(obstacle: object) -> str | None:
        mapping = (
            (LinkedContainerObstacleData, "LinkedContainer"),
            (LargeBlockObstacleData, "LargeBlock"),
            (ColorGateObstacleData, "ColorGate"),
            (PinsObstacleData, "Pins"),
            (LockedGateObstacleData, "LockedGate"),
            (WoolCrateObstacleData, "WoolCrate"),
            (ElevatorObstacleData, "Elevator"),
        )
        return next((mechanic for obstacle_type, mechanic in mapping if isinstance(obstacle, obstacle_type)), None)

    def _scan_document_cell(
        self,
        cell: object,
        discovered: set[str],
        warnings: list[str],
        location: str,
    ) -> None:
        if not isinstance(cell, dict):
            raise MechanicsScanError(f"{location} entries must be objects.")
        type_name = cell.get("type")
        mechanic = _CELL_MECHANIC_BY_TYPE.get(type_name)
        if mechanic is not None:
            discovered.add(mechanic)
        elif type_name not in _KNOWN_IGNORED_CELL_TYPES:
            warnings.append(f"Unknown cell type: {type_name!r} at {location}.")

        if type_name in {"Normal", "TrioBox"}:
            self._scan_document_effects(cell.get("effects"), discovered, warnings, f"{location}.effects")
        if type_name in {"Tunnel", "PopMachine"}:
            stored_cells = self._optional_list(cell.get("storedCells"), f"{location}.storedCells")
            for stored_cell in stored_cells:
                self._scan_document_cell(
                    stored_cell,
                    discovered,
                    warnings,
                    f"{location}.storedCells",
                )

    def _scan_document_effects(
        self,
        effects: object,
        discovered: set[str],
        warnings: list[str],
        location: str,
    ) -> None:
        for effect in self._optional_list(effects, location):
            if not isinstance(effect, dict):
                raise MechanicsScanError(f"{location} entries must be objects.")
            type_name = effect.get("type")
            mechanic = _EFFECT_MECHANIC_BY_TYPE.get(type_name)
            if mechanic is not None:
                discovered.add(mechanic)
            elif type_name not in _KNOWN_IGNORED_EFFECT_TYPES:
                warnings.append(f"Unknown cell effect type: {type_name!r} at {location}.")

    def _scan_elevator_document_effects(
        self,
        obstacle: dict[str, Any],
        discovered: set[str],
        warnings: list[str],
    ) -> None:
        for layer in self._optional_list(obstacle.get("layers"), "Elevator.layers"):
            if not isinstance(layer, dict):
                raise MechanicsScanError("Elevator.layers entries must be objects.")
            for cell in self._optional_list(layer.get("cells"), "Elevator.layers[].cells"):
                if not isinstance(cell, dict):
                    raise MechanicsScanError("Elevator layer cells must be objects.")
                self._scan_document_effects(
                    cell.get("effects"),
                    discovered,
                    warnings,
                    "Elevator.layers[].cells[].effects",
                )

    @staticmethod
    def _optional_list(value: object, location: str) -> list[Any]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise MechanicsScanError(f"{location} must be an array or null.")
        return value

    @staticmethod
    def _ordered(discovered: set[str]) -> list[str]:
        return [mechanic for mechanic in ALL_ACTIVE_MECHANICS if mechanic in discovered]
