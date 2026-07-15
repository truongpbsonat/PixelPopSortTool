from __future__ import annotations

from dataclasses import dataclass

from pixel_level_tool.domain.enums import CellShape, Direction


Offset = tuple[int, int]


@dataclass(frozen=True)
class ShapeDefinition:
    shape: CellShape
    rows: int
    columns: int
    mask: tuple[tuple[bool, ...], ...]

    @property
    def ball_count(self) -> int:
        return sum(1 for row in self.mask for active in row if active)


SHAPE_DEFINITIONS: dict[CellShape, ShapeDefinition] = {
    CellShape.Square_3x3: ShapeDefinition(
        CellShape.Square_3x3,
        rows=3,
        columns=3,
        mask=((True, True, True), (True, True, True), (True, True, True)),
    ),
    CellShape.Rectangle_3x2: ShapeDefinition(
        CellShape.Rectangle_3x2,
        rows=3,
        columns=2,
        mask=((True, True), (True, True), (True, True)),
    ),
    CellShape.L3x4: ShapeDefinition(
        CellShape.L3x4,
        rows=4,
        columns=3,
        mask=((True, True, True), (False, True, False), (False, True, False), (False, True, False)),
    ),
    CellShape.Rectangle_3x1: ShapeDefinition(
        CellShape.Rectangle_3x1,
        rows=1,
        columns=3,
        mask=((True, True, True),),
    ),
    CellShape.Rectangle_6x1: ShapeDefinition(
        CellShape.Rectangle_6x1,
        rows=1,
        columns=6,
        mask=((True, True, True, True, True, True),),
    ),
    CellShape.Rectangle_9x1: ShapeDefinition(
        CellShape.Rectangle_9x1,
        rows=1,
        columns=9,
        mask=((True, True, True, True, True, True, True, True, True),),
    ),
    CellShape.LL3x4: ShapeDefinition(
        CellShape.LL3x4,
        rows=4,
        columns=3,
        mask=((True, True, True), (False, False, True), (False, False, True), (False, False, True)),
    ),
}


def transform_offset(lx: int, ly: int, base_columns: int, base_rows: int, direction: Direction) -> Offset:
    if direction == Direction.Up:
        return lx, ly
    if direction == Direction.Left:
        return ly, lx
    if direction == Direction.Right:
        return base_rows - 1 - ly, lx
    if direction == Direction.Down:
        return base_columns - 1 - lx, base_rows - 1 - ly
    return lx, ly


def oriented_dimensions(shape: CellShape, direction: Direction) -> tuple[int, int]:
    definition = SHAPE_DEFINITIONS[shape]
    if direction in (Direction.Left, Direction.Right):
        return definition.rows, definition.columns
    return definition.columns, definition.rows


def footprint(shape: CellShape, direction: Direction) -> tuple[Offset, ...]:
    definition = SHAPE_DEFINITIONS[shape]
    offsets: list[Offset] = []
    for ly, row in enumerate(definition.mask):
        for lx, active in enumerate(row):
            if active:
                offsets.append(transform_offset(lx, ly, definition.columns, definition.rows, direction))
    return tuple(sorted(offsets, key=lambda item: (item[1], item[0])))


def ball_count(shape: CellShape) -> int:
    return SHAPE_DEFINITIONS[shape].ball_count

