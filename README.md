# MarbleSort Pixel Level Tool

Desktop Python editor for MarbleSort `GameMode.Pixel` levels. The tool edits three data areas:

- Box Ball Grid: `gridRows`, `gridCols`, sparse `gridCells`.
- Pixel Grid: `pixelGrid.width`, `pixelGrid.height`, dense row-major `pixelGrid.colorIds`.
- Box Grid effects and source-grid obstacles defined by `NewRefactor.MyLevelData`.

It intentionally does not edit Classic mode, cargo lanes/cargo effects, pixel modifiers, boosters, runtime gameplay, or Unity scenes.

## Layout

The main window has a resizable splitter:

- Left: Box Ball Grid, shape/direction/active controls, source box canvas, **Auto Gen Box**.
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

Before a level is saved, the editor replaces its `mechanics` array with the mechanics discovered from the
current Box Grid data. The IDs are unique and always follow the runtime `MarbleFlowMechanicIds.AllActive`
order; stale entries are not merged back in.

Use **Scan Mechanics In Folder** to scan every `*.json` file recursively. Choose **Preview / Dry Run** to
review totals without writing, or **Update Files** to atomically rewrite only changed files. The operation
has progress/cancel controls, continues after individual file failures, and reports Total, Changed,
Unchanged, Failed, per-file errors, and unknown-type warnings. This batch path preserves unrelated JSON
fields and can discover TrioBox and PopMachine data even though those cells are not editable in the UI.

## Test

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

Current suite covers shape footprints/rotation, box placement, pixel row-major data, serializer, validator, image import, Auto Gen Box (balancing, gameplay model, difficulty bands, tunnel queues and dig depth, wall reachability, arrow lock keys, linked container tray pressure), and GUI smoke
startup.

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

## Auto Gen Box

**Auto Gen Box** (button under the Box Ball Grid) replaces the whole Box Ball Grid with boxes generated
from the current Pixel Grid at a chosen difficulty, in one undoable step. The output matches the shape of
the hand-written level files: a solid rectangle of `Square_3x3` boxes on a 3-cell lattice, every box
mono-color and `isActive: false`, `piece` at 5, and the difficulty carried by the `Hidden` effect. It also
rewrites `difficulty` and the Hard / Super Hard `themeId`, and clears `obstacles` because they referenced
the replaced boxes — the only obstacles it writes back are the `LinkedContainer`s it generates itself.

### Assumed runtime rules

The generator plays the level while it builds it, using this model of `GameMode.Pixel`:

- The pixel grid is eaten **from the top row downwards, independently per column**. A column's
  *frontier* is its topmost unfilled pixel, the same value the editor already draws as a line.
- A picked box takes one of `piece` tray slots and keeps draining balls into any column whose
  frontier matches its color, until the box is empty.
- The player loses when all `piece` slots hold a box that cannot drain.
- Every box on the grid can be picked, so the layout decides how much searching is needed.
- A **tunnel** is the one exception: it is a queue, only its head can be taken, and taking the head
  reveals the next box. An emptied tunnel does not vanish — it keeps its slot as a wall. So a box
  buried in a tunnel forces the player to pull everything in front of it into the tray first.
- A **LinkedContainer** ties two boxes together: tapping either one sends **both** down, so the pick
  costs two tray slots at the same instant rather than one at a time.
- An **ArrowLock** box cannot be opened until a box in the direction its arrow points at has been
  opened. That is a pure ordering constraint — it never changes what lands in the tray.
- Two arbitrary choices make it deterministic: a ball fills the left-most matching column, and the
  oldest tray box drains first.

If the Unity runtime differs, `services/pixel_gameplay.py` is the only file to change.

### Pipeline

1. **Balance** — a box holds exactly nine balls, so **every color needs a pixel count divisible by 9**.
   Surplus pixels are deleted, starting at the bottom of the picture (eaten last) and preferring columns
   away from the centre; a column is only emptied as a last resort. The count is confirmed before
   anything changes.
2. **Walkthrough** — the box multiset is fully determined by the pixel histogram (`count / 9` boxes per
   color), so only the pick order is open. A depth-first search with memoisation finds an order that
   wins at the target `piece`, exploring "drains completely" first so the order also reads naturally.
   A plain greedy walk is far too weak here: on level 10 it demands `piece = 6` for a picture that is
   playable at 3.
3. **Layout** — the boxes fill the smallest lattice of 3x3 slots that holds them all, no larger than the
   slot limit. Walkthrough order maps onto the slots front row first (`gridY = 0`, drawn at the bottom),
   scrambled by difficulty. A picture too big for the whole lattice overflows into tunnels, and
   **Tunnels → Always, as a mechanic** plants them even when everything fits. Any slot the boxes do not
   fill is a **wall** (see [Walls](#walls)).
4. **Queue** — each tunnel gets a contiguous block of the walkthrough, buried by difficulty (see
   [Tunnels](#tunnels)).
5. **Hide** — a difficulty-driven share of boxes gets `Hidden`, spent on the rarest colors first and
   never on the front row.
6. **Link** — if the level opted in, pairs of neighbouring boxes get a `LinkedContainer` (see
   [Linked containers](#linked-containers)).
7. **Lock** — if the level opted in, a share of the boxes gets `ArrowLock` (see
   [Arrow locks](#arrow-locks)).
8. **Certify** — the level is replayed **three times** — in walkthrough order, in the order the tunnel
   queues force, and in the order the links force with both halves of a pair charged to the tray at
   once — every arrow lock is checked to open after its key, its histograms are checked against the
   pixel grid, and the report shows the measured numbers.

### Difficulty

`piece` stays at 5 at every difficulty, like the level files. The dial is `Hidden`: a hidden box shows no
color, so the player cannot tell whether picking it wastes a tray slot.

| Difficulty | Hidden boxes | Layout | Tunnels | Dig depth | Walls |
| --- | --- | --- | --- | --- | --- |
| Easy | 0% | walkthrough order, eat the grid front row first | 1 x 3 boxes | 0 — released exactly when needed | 0 |
| Medium | 15% | walkthrough order | 1 x 4 boxes | 1 box in the way | 0 |
| Hard | 40% | next box within 4 boxes of the front row | 2 x 4 boxes | 2 boxes in the way | 2 — one pinched box |
| SuperHard | 60% | next box anywhere on the grid | 2 x 5 boxes | 3 boxes in the way | 4 — two pinched boxes |

`ArrowLock` and `LinkedContainer` are **per-level opt-ins**, not difficulty side effects: they only appear
when the dialog's own tick box asks for them. Once ticked, the difficulty sets the dose:

| Difficulty | ArrowLock boxes | Linked pairs | Link pairing |
| --- | --- | --- | --- |
| Easy | 8% | 2 | sync — both colors are wanted at once |
| Medium | 15% | 3 | sync |
| Hard | 25% | 3 | stall — the partner is not wanted for a while |
| SuperHard | 33% | 4 | stall |

`Hidden` is spent where it actually removes information: **on the rarest colors first**. Hiding one of a
dozen identical boxes hides nothing, because the player just uses a visible one of the same color instead;
hiding the only box of a color forces a hunt. Level 10 shows this exactly — of its 30 boxes it hides every
LightPink (1/1), Lime (2/2) and Red (2/2), about half of Orange, White and Yellow, and **none of the 12
Black ones**. The generator reproduces that ordering, spreads a partly-hidden color over distinct slot rows
so the hidden boxes stay scattered rather than forming a solid band, and never hides the front row, so the
player can always read what is immediately available.

The report lists the hidden count per color and per slot row so the mix can be checked at a glance.

### Capacity

Every shape uses exactly one grid cell per ball, and a `Square_3x3` box covers a 3x3 block, so the box
grid is a lattice of 3-cell slots: `gridCols = 3 x slot columns`. The default limit of 8x8 slots means
`gridCols` / `gridRows` up to 24 and up to **64 boxes / 576 balls**, which covers any normal picture
without a single tunnel. Level 10's 270 balls become a 5x6 slot lattice, exactly `gridCols 15`,
`gridRows 18`.

A tunnel lifts that ceiling: its `storedCells` live off-grid, so a picture with more boxes than the whole
lattice holds still fits. Lower **Max box slots** in the dialog to force that path.

### Tunnels

A tunnel is a queue, and an emptied one stays on the grid as a **wall** — so it pays for itself twice: it
stores boxes *and* eats a surface slot forever. A picture overflowing an `N` slot grid therefore needs room
for `boxes - (N - tunnels)` stored boxes, not `boxes - N`.

**Tunnels** in the dialog decides when they appear:

- **Only when the boxes overflow the slot limit** (default) — the picture decides, and a picture that fits
  gets no tunnel unasked.
- **Always, as a mechanic** — the difficulty's tunnel count and depth are planted even when everything fits,
  which is how the hand-made tunnel levels are built.

The queue order is the difficulty dial, and it is meant to be **annoying, not unfair**:

- **Dig depth 1** (Easy) releases every stored box exactly at the step the pixel grid needs its color, so
  the tunnel never gets in the way.
- **A wider window** reverses that many consecutive boxes, putting the soonest-needed one at the *back*: the
  player pops one wrong color after another and only then reaches the one they came for. Reversal rather
  than a shuffle is what makes the dig depth exactly `window - 1`, and therefore something the tray can be
  checked against.

Two things keep it fair. Each tunnel holds a **contiguous block** of the walkthrough, so everything dug out
to reach a buried box was needed within a few steps anyway — the tray takes the hit for a moment instead of
holding dead boxes for the rest of the level. And digging is **certified against `piece`**: the generator
starts from the always-winnable depth 1 and widens one tunnel at a time, keeping a widening only while the
forced pick order still wins. If `piece` cannot hold the digging, the report says the window was narrowed
and by how much, per tunnel.

Tunnels are parked on the **back rows, outermost column first**, like the hand-made levels: a permanent wall
hurts least at the edges, and the outer columns keep the middle of the grid readable. A tunnel shows the
color of its head, the only box it is currently offering. `Hidden` is never spent on stored boxes — a tunnel
already conceals everything behind its head — so the report measures the hidden share against the surface
boxes, the only ones that could carry it.

### Walls

**Every lattice slot the boxes do not fill is a wall.** A wall blocks the way in to the boxes beside it and
never opens up, so walling two sides of a box leaves the player one way around to it — which is the whole
point, and also why walling *every* side would strand a box for good.

Walls are the most expensive knob here, because each one eats a slot *and* narrows its neighbours, so they
are used sparingly:

- Only **Hard** and **SuperHard** reserve any (2 and 4). Easy and Medium keep the grid solid.
- The count is capped at **one wall per four boxes**, so a small picture cannot be strangled by the same
  pinch a large one shrugs off.
- **Wall (slot bỏ trống)** in the dialog overrides it; `0` switches walls off entirely.

Placement follows the hand-made levels: walls go down as **mirrored pairs flanking one box** on the middle
rows, never on neighbouring rows — two pinches side by side would merge into a bar that cuts the grid in
half. Anything the pinches cannot spend falls back to the corners, where a wall costs its slot without
narrowing anything. Leftovers the packing forced are placed the same way rather than piling up wherever the
lattice ran out.

Every placement is checked by a flood fill from outside the lattice: boxes are walked straight through
(the designer confirmed every box on the grid can be picked, so boxes narrow nothing), walls and tunnels
are not, and a candidate that would seal any box off is rejected. The finished level is re-checked before
it is returned. The report lists the wall slots and which boxes ended up pinched.

Reserving walls **grows the lattice**, because the boxes still need their own slots: level 10's 30 boxes fit
a 5x6 exactly, but at Hard the 2 reserved walls make it a 4x8. Set walls to `0` to get the tight rectangle
back.

### Arrow locks

An `ArrowLock` box shows an arrow and **cannot be opened until a box in that direction has been opened**.
Tick **Có ArrowLock trong level này** to put them in the level; the difficulty then decides how many.

Two rules decide where an arrow can go, and both come straight from what the mechanic does:

- The arrow points at a **real box on the neighbouring slot** — never at a wall, never at a tunnel, never
  off the edge of the grid. A lock with nothing openable in its direction has no key and the box is dead for
  the rest of the level. (The validator rejects it too, but the generator never gets that far.)
- That key box is opened **earlier than the locked one in the certified walkthrough**. Otherwise the order
  the solver proved wins would be illegal, and the level would need a solution nobody has checked.

Per box, the direction chosen is the one whose key is opened **as late as still allowed**, so the lock stays
shut for as long as it can instead of pointing at something cleared in the first few taps. The report gives
each locked slot, its direction, the slot of its key, and how many picks later than the key it opens.

Arrow is a hard mechanic even in small doses, so it is rationed: the share is capped at **one locked box per
three boxes**, so the grid can never end up with nothing tappable on it, and locks are **never chained** — a
key that is itself locked would make the player clear two locks to open one box, which reads as a bug rather
than as difficulty. `Hidden` boxes are skipped (a box showing neither its color nor an open state is
unreadable) and so are linked boxes, because a `LinkedContainer` may not target an `ArrowLock` box.

### Linked containers

A `LinkedContainer` ties **two boxes that sit side by side** on the grid: tapping either one sends both down
the conveyor, so one tap spends **two tray slots at the same instant**. Tick **Có LinkedContainer trong
level này** to put them in the level.

The difficulty of the mechanic is entirely in *which* two boxes get tied, which is what **Kiểu
LinkedContainer** selects:

- **sync** (Easy, Medium) — the two colors are wanted within a pick or two of each other, so the tray drains
  both straight away and the link is close to a freebie.
- **stall** (Hard, SuperHard) — a wanted box is deliberately tied to one the board will not want for a while.
  The partner arrives with no column to pour into, squats in a tray slot, and the conveyor runs full. Use it
  carefully: this is the knob that makes a level feel cramped.

Fairness is enforced by replay rather than by construction. Each candidate pair is tried against a **full
run with both halves charged to the tray at once**, and kept only if the level still wins at the chosen
`piece` — a group of two fails on a tray with one slot free even though the second box would have drained the
moment the first emptied, because the game never gives the player that pause. Pairs that do not survive are
dropped and the report says how many, so asking for four pairs on a tight picture yields the two it can
actually carry instead of an unplayable level.

Two more constraints come from the validator: the two halves must **look alike** (a hidden box is never tied
to a visible one), and neither may carry an `ArrowLock`. Links are planned before locks for exactly that
reason. The report lists each pair's slots and how far apart in the pick order the two halves sit.

### What the art has to look like

The box count must factor into the slot rectangle for a solid grid — 30 boxes give a clean 5x6, while a
prime count leaves empty slots, which are walls, and the report says so. Beyond that, how *forced* a level can be is set by
the art, because each column exposes only its own topmost pixel:

- **Full-width horizontal color bands** force the path: one color is at the frontier at a time, and bands
  of one box worth of pixels keep every column in lockstep.
- **Side-by-side vertical stripes** are the most forgiving shape, even at `piece = 1`, because every
  color stays at some column's frontier forever.
- **Finely mixed colors** stop a whole box from draining at once, which pushes `piece` up.

The report always states the measured forced-step ratio and the minimum `piece` a perfect player needs.

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
editing TrioBox/PopMachine/LargeBlockCellData, boosters, and Unity EditorWindow workflows are intentionally out of scope.

## Unity Checklist

1. Save JSON from the tool.
2. Place it under the configured Pixel level data folder.
3. Deserialize with `JsonConvert.DeserializeObject<GridPixelLevelData>` and `TypeNameHandling.Auto`.
4. Confirm every cell/effect/obstacle has its `NewRefactor.*Data, Assembly-CSharp` discriminator.
5. Play-test in Unity; balance alone does not guarantee solvability.
