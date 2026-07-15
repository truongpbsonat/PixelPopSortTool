# MarbleSort Pixel Level Tool

Desktop Python editor for MarbleSort `GameMode.Pixel` levels. The tool edits only two data areas:

- Box Ball Grid: `gridRows`, `gridCols`, sparse `gridCells`.
- Pixel Grid: `pixelGrid.width`, `pixelGrid.height`, dense row-major `pixelGrid.colorIds`.

It intentionally does not edit Classic mode, cargo lanes, obstacles, cell effects, pixel modifiers, boosters, runtime gameplay, or Unity scenes.

## Layout

The main window has a resizable splitter:

- Left: Box Ball Grid, shape/direction/active controls, source box canvas.
- Right: Pixel Grid, paint/erase/eyedropper/fill/import controls, pixel canvas.
- Side panel: shared color palette, live color balance, validation messages.

## Setup

```powershell
cd Tools\PixelLevelEditor
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

This creates `.venv` inside the tool folder and installs dependencies locally.

## Run

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1
```

Smoke-test entrypoints:

```powershell
.\dist\MarbleSortPixelLevelTool\MarbleSortPixelLevelTool.exe --version
.\dist\MarbleSortPixelLevelTool\MarbleSortPixelLevelTool.exe --smoke-test
```

## Test

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

Current suite covers shape footprints/rotation, box placement, pixel row-major data, serializer, validator, image import, and GUI smoke startup.

## Build EXE

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1
```

Main artifact:

```text
dist/MarbleSortPixelLevelTool/MarbleSortPixelLevelTool.exe
```

The build script builds a PyInstaller onedir bundle only. Run tests or `--smoke-test` manually when needed.

## Unity JSON

Output JSON is UTF-8, pretty-printed with two-space indent, and writes a final newline. Save is atomic and creates a `.bak` when overwriting from the UI.

Each source box is serialized as:

```json
{
  "$type": "NewRefactor.CellData, Assembly-CSharp",
  "colorList": [0],
  "effects": null,
  "gridX": 0,
  "gridY": 0,
  "shape": 3,
  "direction": 0,
  "id": 300,
  "isActive": true
}
```

The serializer always writes:

- `gridLanes: []`
- root `obstacles: []`
- `pixelGrid.modifiers: []`
- `pixelGrid.obstacles: []`
- `effects: null`

IDs are reassigned deterministically on save, sorted by `gridY`, then `gridX`, starting at `300`.

## ItemColor IDs

| ID | Color |
| ---: | --- |
| 0 | Red |
| 1 | Green |
| 2 | Blue |
| 3 | Yellow |
| 4 | Pink |
| 5 | Orange |
| 6 | Purple |
| 7 | Black |
| 8 | Brown |
| 9 | Cyan |
| 10 | Gray |
| 11 | LightPink |
| 12 | Lime |
| 13 | Periwinkle |
| 14 | Teal |
| 15 | Violet |
| 16 | White |

Empty pixels use `-1`.

## Shape And Direction IDs

| ID | CellShape |
| ---: | --- |
| 0 | Square_3x3 |
| 1 | Rectangle_3x2 |
| 2 | L3x4 |
| 3 | Rectangle_3x1 |
| 4 | Rectangle_6x1 |
| 5 | Rectangle_9x1 |
| 6 | LL3x4 |

| ID | Direction |
| ---: | --- |
| 0 | Up |
| 1 | Down |
| 2 | Left |
| 3 | Right |

Shape masks and rotations mirror `ShapeConfig.asset` plus `ShapeOrientation.TransformOffset`.

## Image Import

Supported formats: PNG, JPG/JPEG, BMP, TGA.

Import uses Pillow, nearest-neighbor resize, alpha threshold to `-1`, and nearest RGB match to the shared ItemColor palette. Image row 0 maps to pixel grid row 0; data is not flipped or transposed.

## Old Level JSON Import

`Import Old JSON` replaces only the current Pixel Grid from the old level's
`pixelBoard.dimensions` and row-major `pixelBoard.colors` data. Other current level data is preserved,
and the import can be undone. Old level color `0` means an empty pixel and is converted to `-1`;
the remaining color IDs are preserved.

## Validation

Save is blocked when errors exist, including invalid dimensions, unsupported Pixel-only data, invalid enum/color IDs, overlap/out-of-bounds boxes, empty source/target, and source-target histogram mismatch.

Warnings do not block save. Color balance is not a proof of solvability; final levels still need Unity play-test.

## Default Output Folder

The app remembers the last save directory in user AppData. A typical Unity folder is:

```text
Assets/Addressable/LevelData/Pixel/
```

The tool does not hardcode any Unity repository path.

## Unsupported Features

Cargo editor, Classic mode, source obstacles, pixel obstacles, pixel modifiers, cell effects, Tunnel, TrioBox, PopMachine, LargeBlock, boosters, and Unity EditorWindow workflows are intentionally out of scope.

## Unity Checklist

1. Save JSON from the tool.
2. Place it under the configured Pixel level data folder.
3. Deserialize with `JsonConvert.DeserializeObject<GridPixelLevelData>` and `TypeNameHandling.Auto`.
4. Confirm each `gridCells` entry has `$type: NewRefactor.CellData, Assembly-CSharp`.
5. Play-test in Unity; balance alone does not guarantee solvability.
