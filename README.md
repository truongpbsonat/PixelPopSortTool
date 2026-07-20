# MarbleSort Pixel Level Tool

Desktop Python editor for MarbleSort `GameMode.Pixel` levels. The tool edits three data areas:

- Box Ball Grid: `gridRows`, `gridCols`, sparse `gridCells`.
- Pixel Grid: `pixelGrid.width`, `pixelGrid.height`, dense row-major `pixelGrid.colorIds`.
- Box Grid effects and source-grid obstacles defined by `NewRefactor.MyLevelData`.

It intentionally does not edit Classic mode, cargo lanes/cargo effects, pixel modifiers, boosters, runtime gameplay, or Unity scenes.

## Layout

The main window has a resizable splitter:

- Left: Box Ball Grid, shape/direction/active controls, source box canvas.
- Right: Pixel Grid, paint/erase/eyedropper/fill/import/trim-border controls, pixel canvas.
- Side tabs: shared color palette, selected-box effect inspector, obstacle list/properties, and validation messages.

The **Replace Color** action changes every Color A to Color B in both grids of the current level and
can be undone/redone as a single operation.

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

## Level Folder Workflow

Use **Open Folder** (`Ctrl+O`) to select the folder containing numbered level files. The editor recognizes
`<level>.json` and category variants such as `<level>.<category>.json`, opens the matching/current level
or the first available level, and enables **Prev** / **Next** (`Alt+Left` / `Alt+Right`) for fast navigation.
Enter a number in **Level** and click **Load Level** to open that level directly from the selected folder.

Use **Open File** (`Ctrl+Shift+O`) to open an individual JSON file without changing the selected level
folder. Saving that directly opened file continues to use its own path; folder navigation and **Load Level**
continue to use the folder selected with **Open Folder**.

While working in a selected level folder, **Save** (`Ctrl+S`) writes directly to the numbered file for the
Level currently shown in the editor. **Save As** is the only action that opens a file dialog and allows a
custom folder or file name. Saving overwrites the existing file directly and does not create a `.json.bak` copy.

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

Output JSON is UTF-8, pretty-printed with two-space indent, and writes a final newline. Save is atomic (write to a temp file, then replace).

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
- `pixelGrid.modifiers: []`
- `pixelGrid.obstacles: []`
- `effects: null` when a box has no effects

Box IDs are reassigned deterministically on save, sorted by `gridY`, then `gridX`, starting at `300`.
Elevator hidden cells continue in the same range. Obstacle IDs use Unity's type-specific ranges
(`3001`, `5001`, `6001`, `6501`, `7001`, `8001`, and `8501`), and linked target IDs are remapped automatically.
The tool accepts any integer `levelGridVersion` and preserves the loaded value when saving.

## Box Effects And Obstacles

Supported effects are Frozen, Hidden, ArrowLock, KeyForLockedGate, and ScissorForWoolCrate.
Select one box and use the **Box Inspector** tab to add, edit, or remove effects.

Tunnel grid cells can be opened, round-tripped without losing `color`, `direction`, or `storedCells`,
and are shown on the Box Grid with a direction-aware tunnel icon and stored-box count. Select a tunnel
to view its color-coded `storedCells` in JSON order and edit each stored box from **Box Inspector**.
To create one, choose **Tunnel** in the **Type** field above the Box Grid, then click an empty grid cell.
New tunnels start with one stored box using the selected shape, direction, color, and active state.
The **Box Inspector** also changes an existing tunnel's direction and can add, delete, or reorder its
stored boxes. At least one stored box is always retained so the tunnel remains valid.

Supported source-grid obstacles are LinkedContainer, LargeBlockObstacle, Pins, LockedGate,
WoolCrate, ColorGate, and Elevator. Ctrl-click boxes to create target-based or area obstacles from
the **Obstacles** tab. Elevator layers are ordered from bottom to top and contain full Normal box data.

Cargo data is deliberately fail-fast: non-empty `gridLanes`, LinkedCargo, and KeyForCargo cannot be
opened or saved. Unsupported grid-cell subtypes are also rejected instead of being silently discarded.

## ItemColor IDs

| ID | Color | Hex |
| ---: | --- | --- |
| 0 | Red | `#E50000` |
| 1 | Green | `#02F300` |
| 2 | Blue | `#1E90FF` |
| 3 | Yellow | `#FDFF00` |
| 4 | Pink | `#FF00A6` |
| 5 | Orange | `#FF5400` |
| 6 | Purple | `#A800FF` |
| 7 | Black | `#14141A` |
| 8 | Brown | `#733D1F` |
| 9 | Cyan | `#33D9F2` |
| 10 | Gray | `#808080` |
| 11 | Light Pink | `#FFADD1` |
| 12 | Lime | `#A6F233` |
| 13 | Periwinkle | `#8C94F2` |
| 14 | Teal | `#1AA6A6` |
| 15 | Violet | `#8C59E6` |
| 16 | White | `#FFFFFF` |

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

Import uses Pillow, samples the centered one-third of each source region (clamped to 1x1 through 8x8), averages visible RGB values, applies the alpha threshold to `-1`, and uses the nearest RGB match to the shared ItemColor palette. Image row 0 maps to pixel grid row 0; data is not flipped or transposed.

## Old Level JSON Import

`Import Old JSON` replaces only the current Pixel Grid from the old level's
`pixelBoard.dimensions` and row-major `pixelBoard.colors` data. Other current level data is preserved,
and the import can be undone. Old level color `0` means an empty pixel and is converted to `-1`;
supported color IDs are preserved. Each unsupported old color ID is consistently replaced by a
different current color that was not already used in the imported level.

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

Cargo editor, LinkedCargo, KeyForCargo, Classic mode, pixel obstacles, pixel modifiers,
TrioBox, PopMachine, LargeBlockCellData, boosters, and Unity EditorWindow workflows are intentionally out of scope.

## Unity Checklist

1. Save JSON from the tool.
2. Place it under the configured Pixel level data folder.
3. Deserialize with `JsonConvert.DeserializeObject<GridPixelLevelData>` and `TypeNameHandling.Auto`.
4. Confirm every cell/effect/obstacle has its `NewRefactor.*Data, Assembly-CSharp` discriminator.
5. Play-test in Unity; balance alone does not guarantee solvability.
