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
- Side tabs: shared color palette, selected-box effect inspector, obstacle list/properties,
  validation messages, and the **Auto Gen Report** — the last Auto Gen Box run's numbers, kept in a
  tab beside Validation rather than in a dialog, and cleared when another level is opened.

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

Current suite covers shape footprints/rotation, box placement, pixel row-major data, serializer, validator, image import, Auto Gen Box (balancing, gameplay model, difficulty bands, tunnel queues and dig depth, wall reachability, arrow lock keys, linked container tray pressure, obstacle relief on a belt-tight picture, the certified base grid, a scattered 72-box picture built from level 15's own multiset, picture repair, scenario easing and seed shuffling), and GUI smoke
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
mono-color and `isActive: false`, and the difficulty carried by the `Hidden` effect. It also
rewrites `difficulty` and the Hard / Super Hard `themeId`, and clears `obstacles` because they referenced
the replaced boxes — the only obstacles it writes back are the `LinkedContainer`s it generates itself.

### Assumed runtime rules

The generator plays the level while it builds it, using this model of `GameMode.Pixel`:

- The pixel grid is cleared in **one fixed pass**: the top row first, and inside a row from the
  **right edge leftwards**. An empty cell is not a stop — a ball skips it and lands on the next
  painted pixel — so the whole picture collapses into a single sequence of colors.
- The *frontier* is therefore **one cell**, not one per column. Exactly one color can be spent at any
  moment, and every other box on the conveyor is waiting rather than working.
- A tap pours a whole nine-ball box onto the **conveyor**, which is as wide as the level's own
  `piece`: `piece x 9` balls, so **45 balls at the `piece: 5` every hand-made level ships**. A tap is
  legal only while nine slots are free.
- The player loses when **no tap is legal and nothing on the conveyor can drain** — the belt is jammed
  with colors the picture is not asking for.
- Every box on the grid can be picked, so the layout decides how much searching is needed.
- A **tunnel** is the one exception: it is a queue, only its head can be taken, and taking the head
  reveals the next box. An emptied tunnel does not vanish — it keeps its slot as a wall. So a box
  buried in a tunnel forces the player to pull everything in front of it onto the belt first.
- A **LinkedContainer** ties two boxes together: tapping either one sends **both** down, so the pick
  needs room for eighteen balls at the same instant rather than nine at a time.
- An **ArrowLock** box cannot be opened until a box in the direction its arrow points at has been
  opened. That is a pure ordering constraint — it never changes what lands on the belt.
- One arbitrary choice makes it deterministic: when several boxes carry the frontier color, the
  oldest one pays.

If the Unity runtime differs, `services/pixel_gameplay.py` and `services/picture_scan.py` are the only
files to change. The belt size lives in one constant, `picture_scan.DEFAULT_BELT_SLOTS`.

### The belt is a budget, not a veto

Because the play order is fixed, a picture has a **lower bound** on the conveyor it needs: no play can
hold less than the one that taps every box as late as legally possible. `picture_scan.belt_demand`
computes it in one pass and the scan panel shows it.

**That number is not a gate.** A level is *made* hard by deliberately putting spare boxes on the
conveyor — digging a buried box out of a tunnel, or a `stall` link parking a partner there — so what
the belt has to hold is the picture's own demand **plus** whatever the obstacles add. The picture's
demand is therefore read as *how much room is left over for obstacles*:

| Picture | Belt needed | Room left for burial |
| --- | --- | --- |
| 12 colors in solid bands | 8 / 45 | 37 balls — four spare boxes |
| level 10 as painted | 40 / 45 | 5 balls — links and burial barely fit |
| level 5 as exported | 42 / 45 | 3 balls |
| 10 colors scattered | 61 / 45 | none; the search fails and says where |

Layout matters far more than color count: a twelve-color picture in bands leaves four boxes of
headroom, while a six-colour one painted as noise leaves none. If the search fails, the fix is to
**raise the level's `piece`**, **gather each color into contiguous runs along the play order** (top
down, right to left), or use fewer colors.

That leftover room is also what the obstacles are set from: a picture leaving five balls cannot carry
the same burial and the same stalled links as one leaving thirty-seven, so the obstacles it gets are
the same mechanics in a gentler form — see
[Hard picture, gentler obstacles](#hard-picture-gentler-obstacles).

### Pipeline

1. **Balance** — a box holds exactly nine balls, so **every color needs a pixel count divisible by 9**.
   Deleting is the *last* of four ways to get there, not the first (see [Color balancing](#color-balancing)):
   the color is painted up into empty cells beside it, a full picture has its colors settle each other by
   recoloring, a walled-in color borrows from one that still has room, and only a picture with nowhere left
   to grow loses pixels — at most eight in total. The dialog states which of the four this picture needs
   before anything changes.
2. **Scan** — the picture is read in play order and measured: color count, how many contiguous runs
   each color breaks into, how much conveyor the picture needs at its worst moment, and where the
   outline has holes. Tick **Lấy độ khó từ ảnh** to let the scan name the difficulty. The scan also
   states the **`piece` this picture needs** — see [The belt a picture needs](#the-belt-a-picture-needs)
   — and whether the level's current one is enough.
3. **Repair** (only when the picture cannot be won on the belt it has) — the jam is never about a
   picture being *large*, it is about colours coming in **short runs**: a tap pours nine balls, a run of
   four spends four, and the other five sit on the belt until that colour is wanted again. So short runs
   are merged into the colour beside them and exactly as many pixels are handed back **against that
   colour's own run**, which means every colour keeps its pixel count to the pixel — the box multiset
   comes off the histogram, so a repaired picture builds the *same boxes* and only the order they are
   wanted in changes. It aims one box past merely winning, so the player has room to be wrong. Level 15
   as shipped needs a 54-ball belt on `piece: 5`; 40 merges (94 of its 648 pixels recoloured) bring it to
   32/45 — piece 4 — with its 72 boxes untouched. Every move is listed in the report with the cell it
   happened on, and **Sửa tranh cho chơi được** turns it off.
4. **Walkthrough** — the box multiset is fully determined by the pixel histogram (`count / 9` boxes per
   color), so only the pick order is open. A depth-first search with memoisation finds an order that
   wins on the belt, paying the frontier first so the order also reads naturally; the picks that are
   not the frontier color are ranked by how soon they pay off, because a box tapped early holds
   conveyor room until then.
5. **Base grid** — the boxes laid out with **no mechanic on them at all**: every box the histogram asks
   for, in walkthrough order on the smallest lattice that holds them, whatever does not fit stored in
   tunnels that hand each box over *exactly* when the picture asks for it (dig window 1) — and the whole
   thing replayed and **proven to win**. This is the level's floor, and it is why difficulty can never be
   the thing that makes a level unwinnable: everything after this changes a grid that already had a
   winning line. A typed tunnel count is ignored here — that is a request for a mechanic, and the floor
   carries none. The report states it on its own line (`Lưới box gốc (chưa obstacle): THẮNG ĐƯỢC`).
6. **Pick the mechanics** — the difficulty says which obstacles this level runs and in what order it
   wants them; the picture says which of those it can pay for. The survivors are the level's mechanics,
   as many as this level's roll of the tier's [obstacle budget](#obstacle-budget) allows.
7. **Layout** — the boxes fill the smallest lattice of 3x3 slots that holds them all, no larger than the
   slot limit. Walkthrough order maps onto the slots front row first (`gridY = 0`, drawn at the bottom),
   scrambled by difficulty. A picture too big for the whole lattice overflows into tunnels whether the
   tier bought them or not. Any slot the boxes do not fill is a **wall** (see [Walls](#walls)); when the
   tier did not buy walls the tunnels give a box back instead, so the surface fills its rectangle exactly.
8. **Queue** — each tunnel gets a contiguous block of the walkthrough, buried by difficulty (see
   [Tunnels](#tunnels)).
9. **Hide** — a difficulty-driven share of boxes gets `Hidden`, spent on the rarest colors first and
   never on the front row.
10. **Link** — pairs of neighbouring boxes get a `LinkedContainer` (see
   [Linked containers](#linked-containers)).
11. **Lock** — a share of the boxes gets `ArrowLock` (see [Arrow locks](#arrow-locks)).
12. **Slab and freeze** — the two locks that open on **progress** rather than on another box:
   `LargeBlock` over a rectangle of boxes first, then `Frozen` over single boxes (see
   [Progress locks](#progress-locks)). The slab goes first because it is much the more
   constrained of the two — a grid has only a handful of late-wanted rectangles, while a Frozen
   box fits almost anywhere.
13. **Certify** — the level is replayed **three times** — in walkthrough order, in the order the tunnel
   queues force, and in the order the links force with both halves of a pair charged to the belt at
   once — every arrow lock is checked to open after its key, its histograms are checked against the
   pixel grid, and the report shows the measured numbers. `piece` is written as the peak number of
   boxes the walkthrough actually held at once, so it reports rather than limits.
   **`LevelValidator` runs here too**, on the ids the level will be saved with: the replays prove the
   grid can be *played*, and the validator proves it can be *loaded*. Its verdict goes into the report
   (`validate lưới vừa sinh: 0 lỗi, 1 cảnh báo`) with every message listed, and an error leads the
   report banner ahead of a jam — a jam is the picture asking for a wider belt, a validator error on a
   generated grid is a bug in the generator. Previously the validator only ran because the main window
   refreshes every panel after a change, and its result sat in the Validation tab while Auto Gen Box
   raised the Report tab over it.

Steps 7–12 are one unit and can run more than once. The finished layer is read back rather than
trusted, on two separate questions:

* **Did the conveyor pay for it?** A burial shallower than asked for or a pair count short of the
  request is the belt saying no, and the answer is a gentler *form* of the same mechanic — the whole
  layer rebuilt a tier down. See [Hard picture, gentler obstacles](#hard-picture-gentler-obstacles).
* **Is the layout playable at all?** Three failures are invisible to any replay, because the gameplay
  model taps a queue by index, walks no route across the grid and counts no pixels: a **wall that seals
  a box in**, a **lock that opens too late** (see [Progress locks](#progress-locks)), and a
  **tunnel whose mouth faces no box** — a mouth pointing at a wall, at another tunnel or off the edge of
  the lattice is sealed for the whole level, so the tunnel's boxes can never be had. Both are read off
  the finished layout, and a layer with either is **never shipped** (the mouth case used to go out with
  only a warning). Small grids are where it bites: two tunnels on a four-box grid have nothing to point
  at. Such a layer is dropped, a gentler form is tried, and if every form is unplayable the certified
  **base grid ships instead** — a level with no mechanics beats a broken one, and the report says so.

### Difficulty

The conveyor is the level's own `piece x 9` at every difficulty, so the bite comes from the obstacles
rather than from the belt. The main dial is `Hidden`: a hidden box shows no color, so the player cannot
tell whether tapping it wastes belt room.

**Lấy độ khó từ ảnh** reads the tier off the picture instead, by color count:

| Colors | Tier |
| --- | --- |
| 1–3 | Easy |
| 4–8 | Medium |
| 9–12 | Hard |
| 13+ | SuperHard |

A picture whose colors are broken into many small runs along the play order is pushed **up one tier**,
because it forces the player to keep more colors on the belt at once. It is never pushed down: twelve
colors in neat bands are still twelve colors to read.

### Obstacle budget

All seven mechanics are read off the level the same way. There is no per-obstacle tick box standing
between a tier and its dose any more: the difficulty decides **which** mechanics run, and the picture
decides how much of each it can pay for.

Two separate limits shape that. The first is how many **kinds** run at once, which is what a player
feels first — a level carrying two mechanics reads as a level with a rule, one carrying five reads as a
level with a syllabus:

| Difficulty | Kinds it runs | How it picks them | Locks (own budget) |
| --- | --- | --- | --- |
| Easy | 1–2 | drawn at random from all five | 0–1 |
| Medium | 3–4 | drawn at random from all five | 1–2 |
| Hard | 4–5 | `Hidden` › Wall › Tunnel › `ArrowLock` › `LinkedContainer` | 1–2 |
| SuperHard | 4–5 | `Hidden` › Wall › Tunnel › `ArrowLock` › `LinkedContainer` | 2 |

That column is a **range, and it is rolled per level** from the seed — not filled to its ceiling. Used
as a ceiling it was decoration: there are only five mechanics, so a Hard ceiling of six meant every
Hard level carried all five, every time, and two seeds gave the same syllabus twice. Now a Hard level
runs four or five of them and the report says which roll it got (`level này rút 4 loại trong khoảng
4-5`), so re-rolling the seed varies the mechanics and not just the layout. The ceiling is clamped to
the number of mechanics that exist, and the floor comes down with it.

**Easy and Medium draw their mix instead of reading the order from the top.** A priority list plus a
small dose meant the same two or three mechanics on every single gentle level: every Easy level was
`Hidden` and an arrow, every Medium one `Hidden`, an arrow and a pair. That is right for the hard
tiers, where the order *is* the tier — a Hard level without its wall and its tunnel is not Hard — but at
the gentle end any of the seven reads as gentle once it is dosed down, so which ones a level gets
should vary. Untick **Xóc ngẫu nhiên mix obstacle ở mức Dễ/Vừa** to pin every tier to its canonical
mix. Wall still cannot land at Easy whichever position it is drawn in: the Easy profile spends no
walls at all, so it is turned down on affordability rather than on order.

**The two locks are budgeted apart from the other five**, in the last column. A `Frozen` box or a
`LargeBlock` slab spends no conveyor and takes no grid slot away from anything — it is derived from the
winning line rather than laid on top of it (see [Progress locks](#progress-locks)) — so charging it
against the same budget would only let it push a belt-spending mechanic off a level that could
comfortably afford both.

Three things are booked **before** the budget opens, because none of them is the budget's to refuse:

* a count the designer typed (see [Asking for exact counts](#asking-for-exact-counts)),
* a mechanic ticked on by hand in the dialog,
* tunnels for a picture too big for the lattice.

Those can push a level past its ceiling on purpose, and the report says so by name rather than quietly
dropping what was asked for. A picture too small to pay for the tier's minimum is generated anyway, with
each mechanic it could not afford listed with the reason.

The second limit is the **dose** of each mechanic, which is what the rest of this section covers. Each
one also has an **easy form and a hard one**, so an easy tier spends the same mechanics in their gentle
shape rather than dropping them:

| Mechanic | Easy / Medium | Hard / SuperHard |
| --- | --- | --- |
| `Hidden` | few, rarest colors only | up to 60%, scattered over the back rows |
| `ArrowLock` | points at the box opened **just before** it, so the arrows read as a route | reaches for the **earliest** legal key, so the box stays shut as long as possible |
| `LinkedContainer` | `sync`, and must clear **clean** — after the tap the conveyor is empty again | `stall`, the partner squats on the belt for several picks |
| Tunnels | dig window 1, released exactly when needed | buried 3–4 deep |
| Walls | none | 2–4 slots, pinching boxes to a single approach |

| Difficulty | Hidden boxes | Layout | Tunnels | Dig depth | Walls |
| --- | --- | --- | --- | --- | --- |
| Easy | 8% | walkthrough order, eat the grid front row first | 1 x 3 boxes, back row | 0 — released exactly when needed | 0 |
| Medium | 15% | walkthrough order | 1 x 4 boxes, back row | 1 box in the way | 0 |
| Hard | 40% | next box within 4 boxes of the front row | 2 x 4 boxes, front row | 2 boxes in the way | 2 — one pinched box |
| SuperHard | 60% | next box anywhere on the grid | 2 x 5 boxes, anywhere | 3 boxes in the way | 4 — two pinched boxes |

### Hard picture, gentler obstacles

A hard picture and hard obstacles are two difficulties that add up in the same place — the conveyor —
and the tier is read off the *picture*. So the hardest pictures are exactly the ones asking for the
hardest obstacle forms while having no belt left to pay for them. Left alone, that produces a level
where the burial is trimmed by the belt check and the `stall` links are dropped one at a time by the
belt check: still winnable, but what survives is whatever the checks happened to leave rather than a
design. On level 10 at SuperHard, all three linked pairs were refused and the level shipped with none.

**Tự hạ độ khó obstacle** (on by default, in the Obstacle column of the dialog) prices that instead —
by measuring, not by guessing. The obstacle layer is built at the tier's own form and the result is
read back: a queue buried shallower than asked for, or fewer pairs tied than requested, is the belt
saying it cannot pay. When it says no, the **whole layer is rebuilt one tier gentler**, where the
mechanic fits instead of being refused, and so on down to Easy.

What changes is the **form**, never the mechanics: a relieved Hard level still carries its wall, its
tunnel, its links, its locks and its hidden boxes — every dose the gentler tier would zero is held at
one, because removing a mechanic is the [obstacle budget](#obstacle-budget)'s decision, not relief's.
A step down is only taken when it **buys something back**: a gentler form that loses just as much has
bought nothing, so the level stays where it was. Numbers the designer typed still outrank the relieved
table exactly as they outrank the tier's.

The Auto Gen Report states it on one line under the mechanics — the form that shipped, the rung-by-rung
ladder that got there, and which knobs came out softer — plus the straight answer to *did the
obstacles make this harder*: the belt peak of the bare walkthrough against the belt peak of the play
the obstacles force, and how much conveyor is left over at that moment. Untick the box to hold a level
to its tier's own form; the report then says which mechanics the belt cut.

`ArrowLock` and `LinkedContainer` follow the difficulty like everything else. Their dialog tick boxes are
**three-state**: left blank (the default) the tier decides, ticked the level always has that mechanic,
unticked it never does.

| Difficulty | ArrowLock boxes | Linked pairs | Link pairing |
| --- | --- | --- | --- |
| Easy | 8% | 2 | sync — both colors are wanted at once |
| Medium | 15% | 3 | sync |
| Hard | 25% | 3 | stall — the partner is not wanted for a while |
| SuperHard | 33% | 4 | stall |

Two of those doses are then read off the picture itself:

* **`ArrowLock`** thins out with the picture's fragmentation. A lock never costs conveyor — the key is
  always a box the certified order opens *earlier*, so a player following that order is never held up —
  what it costs is an alternative, one fewer box that could have been tapped instead. A fragmented
  picture hardly has any alternatives, because the colour it needs next all but dictates the pick, so a
  picture measured at 50% fragmentation gets half the locks. It never drops to zero: reading the picture
  thins a dose, it does not cancel a mechanic the budget just paid for.
* **Tunnels and `LinkedContainer`** are measured exactly rather than estimated. Every burial depth is
  replayed against the real belt and the deepest one that still wins is kept; every candidate pair is
  replayed the same way and dropped if it loses, or — at the easy tiers — if the conveyor is not back to
  empty afterwards. The scan panel reports the belt's spare room as a *reading* for the designer, not as
  a cap: a link or a dig that happens away from the picture's tightest moment costs nothing there.

`Hidden` is spent where it actually removes information: **on the rarest colors first**. Hiding one of a
dozen identical boxes hides nothing, because the player just uses a visible one of the same color instead;
hiding the only box of a color forces a hunt. Level 10 shows this exactly — of its 30 boxes it hides every
LightPink (1/1), Lime (2/2) and Red (2/2), about half of Orange, White and Yellow, and **none of the 12
Black ones**. The generator reproduces that ordering, spreads a partly-hidden color over distinct slot rows
so the hidden boxes stay scattered rather than forming a solid band, and never hides the front row, so the
player can always read what is immediately available.

The report lists the hidden count per color and per slot row so the mix can be checked at a glance.

### Re-rolling the scenario

Three knobs sit above every table below, because they change *which* scenario is built rather than how
one mechanic is dosed:

| Knob | What it does |
| --- | --- |
| **Hạ độ khó** | Build the level `N` notches below what the difficulty box (or the picture, under **Lấy độ khó từ ảnh**) says. A Hard picture becomes a Medium level: `difficulty`, `themeId`, the [obstacle budget](#obstacle-budget) and every dose follow the eased tier. Easy is the floor. |
| **Dạng obstacle nhẹ đi** | Build the obstacles in a lower tier's *form* while the level stays at its own tier — `difficulty` and `themeId` do not move and the mechanic count does not change. 1 notch turns a Hard level's `stall` links into `sync` ones, points its arrows at the box opened just before, digs shallower and drops a wall. This is the deliberate version of [relief](#hard-picture-gentler-obstacles), which only reacts to what the belt refuses; the two stack, and relief starts from wherever this leaves off. |
| **Xóc lại** | Roll the whole run `N` times on consecutive seeds and keep the best: **winnable** first, then **not stripped to the bare base grid**, then **more mechanics**, then **a harder obstacle form**, then **more conveyor left over**. Every roll is a complete, certified level — the shuffle only picks between them — and the report names the winning roll's seed, so setting that seed with one roll rebuilds it exactly. A seed that cannot be built is skipped rather than failing the run. |

### Asking for exact counts

Every table above is the **Auto** answer. Each mechanic also takes a plain number, typed in before
generating, which says how much of it this level gets regardless of the difficulty:

| Knob | Auto means | An exact number means |
| --- | --- | --- |
| **Số box ẩn** | the `Hidden` share of the difficulty (or the `%` knob) | exactly this many boxes carry `Hidden` |
| **Tunnel** | *Theo độ khó* lets the obstacle budget decide; `overflow` builds none unless the picture spills; `mechanic` always uses the difficulty's dose for a grid this size | **Số tunnel**: build this many, filled to the difficulty's depth, even when everything fits |
| **Số tunnel tối đa** | the ceiling is measured off the picture: one tunnel per eight boxes, at most a third of the lattice | pin the ceiling for this level only |
| **Số box ArrowLock** | the `ArrowLock` share of the difficulty (or the `%` knob) | lock exactly this many boxes |
| **Số cặp LinkedContainer** | the difficulty's pair count | tie exactly this many pairs |

A number **outranks the share or ceiling next to it**, and the dialog greys that neighbour out so no
knob looks live while being ignored — `Số box ẩn` disables the `%` field, `Số tunnel` disables `Số tunnel
tối đa`. `0` is a real answer meaning *none of this mechanic*; only **Auto** hands the decision back to the
difficulty.

A typed number is also an answer to *whether* the level has that mechanic at all, not just how much:
any count above zero books it in even when the tier's [obstacle budget](#obstacle-budget) would not have
reached that far, and a typed `0` switches it off however much the tier wanted it. It outranks the
relieved table as well: [relief](#hard-picture-gentler-obstacles) swaps which table the Auto answers are
read from, and a typed number was never read from a table.

The safety caps still apply, because they are what keeps a level playable: at most one locked box per
three, one linked pair per four, and no `Hidden` on the always-visible front row. The tunnel count is a
**floor rather than a cap** — an overflowing picture still gets the extra tunnels its boxes need. Whenever
a request is clipped or exceeded the report says so by name, so a number that could not be honoured never
reads as one that was.

### Capacity

Every shape uses exactly one grid cell per ball, and a `Square_3x3` box covers a 3x3 block, so the box
grid is a lattice of 3-cell slots: `gridCols = 3 x slot columns`. The default limit of 8x8 slots means
`gridCols` / `gridRows` up to 24 and up to **64 boxes / 576 balls**, which covers any normal picture
without a single tunnel. Level 10's 270 balls become a 5x6 slot lattice, exactly `gridCols 15`,
`gridRows 18`.

A tunnel lifts that ceiling: its `storedCells` live off-grid, so a picture with more boxes than the whole
lattice holds still fits. Lower **Max box slots** in the dialog to force that path.

### The belt a picture needs

The conveyor is the one thing a picture can genuinely be too big for, and the tool reads the exact number
out rather than leaving it to be guessed at. Two readings, from either end:

- **Lower bound** (`peak_balls`) — replay the picture tapping every box as late as legally possible and take
  the worst moment. No play holds less than that, so a belt under it is a proof of failure.
- **The width that works** (`peak_tap`) — the same play, counting the whole box a tap pours in at once. A tap
  is only legal while nine slots are free, so a belt that merely *matches* the lower bound can be one where
  nothing may ever be tapped again. At `peak_tap` that play is legal from start to finish, and it always
  exists, so this is a width that is known to win rather than an estimate.

**Where it jams, and why.** The number alone does not tell a designer what to change, so the scan also
walks the same play and reports the first tap the belt cannot afford: which pixel, which color the picture is
asking for, and — the part that matters — **every color squatting on the belt at that moment, how many balls
each, and how far away the pixel that would finally spend them is**.

That list is always the same story. The frontier is a single cell and a tap pours a **whole** box, so a color
whose run is shorter than nine leaves the rest of that box behind until the picture asks for that color
again. One stray pink pixel costs eight pink balls parked on the belt for the next ninety pixels. Five colors
doing that at once and the belt has under a box of room, so the next tap is illegal and the play is over —
which is why a noisy picture jams at pixel 15 of 729 rather than somewhere near the end. It is not the color
*count* that costs: a twelve-color picture in long bands never leaves a leftover, and a six-color one painted
as scattered specks leaves one on every tap.

Rounded up to whole boxes, `peak_tap` is the level's **`piece`**. The scan panel states it every time
(`Piece cần cho ảnh này: 7 (băng 63 bóng) — level đang để piece=5, THIẾU 18 bóng`).

**A belt too small is a warning, never a refusal.** What boxes a picture needs is fixed by its histogram, so
the box grid is correct whether or not the conveyor is wide enough to play it — refusing to build it would
throw that work away over something the designer may well fix in the level file. So generation always
produces the full grid, and the belt gets the warning instead, in the **Auto Gen Report** rather than in a
modal that is gone the moment it is dismissed: a red banner across the top of the panel names the cell and
the `piece` that fixes it, and the body carries the jam in full — the pixel, the cell on the canvas, the
colors squatting on the belt and how far each one waits.

The Auto Gen Box dialog itself stays short: its scan panel is four lines (six when the picture jams) and the
whole form sits in a scroll area sized to the screen, so the **Sinh box** button is never under the taskbar.
Anything longer than a glance belongs to the report, which is a panel a designer keeps open beside the grid.

Two things stay true whatever the belt says. The generator **never moves `piece`** — that is the designer's
decision, and quietly widening it would ship a level nobody asked for. And the obstacles are still verified,
against the belt the picture *needs* rather than the one it has: certifying against a belt nothing wins on
would only strip the level bare — no burial, no links, everything failing for the same single reason — while
this way the moment `piece` is set to the number in the warning, the level is correct, obstacles and all, with
no need to generate it again.

### Color balancing

Every color must divide into whole nine-ball boxes, and the tool reaches that while keeping as much of the
artwork as it can. Four moves, cheapest first:

1. **Paint** the color up to its next multiple, into empty cells that touch that color. Nothing is lost and
   a cell beside the same color *in its own row* falls inside an existing run, so the conveyor does not even
   notice it. This is all-or-nothing per color — half of what a color needs leaves it just as unbalanced —
   and the colors needing the fewest pixels go first, so a picture with little room left still balances as
   many colors as that room can pay for.
2. **Recolor** a neighbouring color's pixel, which is what a full picture has left. The pixel stays where it
   is and only changes color, so the silhouette survives; two colors whose leftovers add up to nine settle
   each other exactly, and a color short of more than one leftover collects from several. Donor pixels are
   taken from the border with the receiver, never from the middle of a blob.
3. **Borrow** for a color walled in by its neighbours: it has no empty cell of its own, so a color that
   *does* have room is grown by exactly what the walled-in one is short of and hands those pixels over. The
   donor ends the trade on the same count it started with, and nothing is deleted.
4. **Delete**, only for what none of the others can reach: a picture with no empty cell anywhere whose
   colors cannot even settle each other. That residue is whatever the whole picture is short of a multiple
   of nine, so it is **never more than eight pixels**, and they go from the bottom of the picture (eaten
   last) and away from the centre.

The Auto Gen dialog and the Auto Gen Report both name the moves the run made — pixels painted, pixels
recolored between which colors, pixels deleted — so a picture that grew and a picture that lost artwork are
never reported as the same thing.

### Tunnels

A tunnel is a queue, and an emptied one stays on the grid as a **wall** — so it pays for itself twice: it
stores boxes *and* eats a surface slot forever. A picture overflowing an `N` slot grid therefore needs room
for `boxes - (N - tunnels)` stored boxes, not `boxes - N`.

**How many tunnels** is measured off the picture, the way every other obstacle dose is, rather than held to
one fixed ceiling:

- The tier's dose is written for a hand-made 30-box grid, so a picture carrying twice that carries twice the
  dose — a large picture is not run through the same pair of queues a small one gets.
- **Số tunnel tối đa** on `Auto` reads the ceiling off the picture too: one tunnel per eight boxes, and never
  more than a third of the lattice. Type a number to pin it for one level.
- An **overflowing** picture is spread across as many tunnels as it takes to keep every queue down to the
  tier's own depth, up to half the lattice, instead of stacking everything into one deep queue. That is what
  keeps `gridCols` / `gridRows` inside the slot limit no matter how large the picture is: a 40x40 picture
  (177 boxes) lands on an 8x8 lattice with 21 shallow tunnels rather than four queues 29 boxes deep.
- No ceiling can refuse a tunnel the picture cannot be built without: a ceiling bounds what a tier spends by
  choice, and is lifted whenever the boxes genuinely need more room.

**Tunnel** in the dialog decides when they appear:

- **Theo độ khó** (default) — the [obstacle budget](#obstacle-budget) decides. Easy runs two mechanics and
  never reaches tunnels; Hard and SuperHard run everything, so they plant the difficulty's count and depth.
- **Chỉ khi số box vượt giới hạn slot** — the picture decides, and a picture that fits gets no tunnel.
- **Luôn luôn, như một cơ chế** — the difficulty's tunnel count and depth are planted even when everything
  fits, which is how the hand-made tunnel levels are built.

A picture that overflows the lattice gets its tunnels whichever of the three is chosen: the level does not
exist without them.

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

**Vị trí tunnel** decides where they are parked, and it is the dial for how much of the grid the player has
to route around, because a tunnel is a hole that never fills back in:

| Placement | Where | What it costs the player |
| --- | --- | --- |
| `back` | the row furthest from the player, outermost column first — what the hand-made levels do | almost nothing: an edge hole on the row drained last |
| `front` | mirrored onto `slot_y == 0`, the row eaten first | the tunnel stands in the way from the opening tap |
| `random` | any slot the lattice can spare | can land mid-grid, so boxes must be approached the long way |
| `auto` (default) | the difficulty decides: Easy/Medium `back`, Hard `front`, SuperHard `random` | |

Every candidate slot is checked against the reachability flood **before** it is taken, and one that would
seal a box away from every approach is skipped — a level with an unreachable box is not a harder level, it
is a broken one. A placement that cannot seat all its tunnels falls back to the back rows for the rest
rather than failing the run, and the report names the placement that was actually used.

A tunnel shows the color of its head, the only box it is currently offering. `Hidden` is never spent on
stored boxes — a tunnel already conceals everything behind its head — so the report measures the hidden
share against the surface boxes, the only ones that could carry it.

A tunnel's `direction` is the side it **hands its queue out** on, so it is aimed at the neighbouring slot
that really holds a box: never off the lattice (a corner tunnel has two such sides), and never at a wall or
another tunnel, both of which are permanent and would seal the mouth for the whole level. When several sides
qualify, the mouth turns towards the **front row** first — the part of the grid the player drains first, the
way the hand-made levels point their edge tunnels inwards. The report lists each tunnel's slot and facing,
and warns if a cramped or wall-heavy lattice left a mouth with no box on any side.

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
The difficulty decides whether the level has them and how many; **ArrowLock — để mờ là theo độ khó** in the
dialog is a three-state box that can force that either way for one level.

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
the conveyor, so one tap spends **two tray slots at the same instant**. The difficulty decides whether the
level has them; **LinkedContainer — để mờ là theo độ khó** in the dialog is a three-state box that can force
that either way for one level.

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

### Progress locks

`Frozen` and `LargeBlock` are the two mechanics that open on a **number** rather than on another box:
the runtime lifts them once the picture has lost that many pixels. That one difference changes
everything about how they are generated.

**They are derived, not imposed.** A lock's count can only be written once the play order exists, so
both run *after* the belt has had its say, in stages 11 and 12. The count is then read out of that
order: `tap_progress` says how much of the picture is already gone when the winning line reaches the
box behind the lock, and the count is written at most **one box (9 balls)** below that. So the
certified line never waits on a lock, no lock can cost the level its proof, and neither appears in the
relief ladder the other five go through. What a lock takes is the player's **freedom to tap early** —
the box cannot be dumped on the conveyor to clear a slot, and in a slab's case four of them go at once.

**The deadlock rule.** The picture is cleared by a single frontier. If the colour the frontier wants
has only one box left and that box is frozen, nothing clears — and because the lock opens on progress,
nothing clearing means the lock **never opens**. That is not a hard level, it is a dead file. So a lock
only ever goes on a colour that still has another box to serve the frontier while it is shut. The
hand-made level 59 does exactly this by hand: all four of its Frozen boxes are Red or White, its two
most common colours.

**How the number is chosen.** Two independent dials:

| Difficulty | Frozen boxes | Opens at (share of picture) | Slabs | Slab opens at | Window |
| --- | --- | --- | --- | --- | --- |
| Easy | 5% of surface | 3–6% | 0 | — | 40% |
| Medium | 10% | 5–10% | 2 | 25%, 38% | 30% |
| Hard | 15% | 10–20% | 2 | 30%, 45% | 15% |
| SuperHard | 20% | 15–30% | 3 | 35%, 50%, 62% | 6% |

The slab column is what the tier *asks* for; the margin measured from the level decides the size those
slabs come out at and scales the share they open at — see **Slabs** below.

The share says *when in the level* the pressure happens. The **window** says how tight it is: a lock
only goes on a box the winning line wants within that share of the picture after the lock lifts, so a
small window means the player spends the whole stretch before it unable to touch a box they are about
to need. If no box on the grid falls inside the window the search widens; if none can bear the tier's
number at all, the count is trimmed down and the report says how many locks that happened to.

**Slabs.** A `LargeBlock` is `Frozen` applied to a rectangle with one shared counter, and it is
**opaque** — the colours under it cannot be read until it lifts. It lifts in one piece, so its count is
bounded by the **earliest** box under it, which makes the regions the play order visits last the ones
worth covering.

Its **size and its break count both come off the margin measured from the level** — `spare_boxes`, the
whole boxes of conveyor still free at the picture's tightest moment. That number is the level's own
statement of how much of itself it can afford to have shut away:

| Margin measured | Slab size | Opens at |
| --- | --- | --- |
| 3+ spare boxes | `3×3` box slots (`9×9` cells) | the tier's share, in full |
| 2 spare boxes | `2×2` slots (`6×6` cells) | 87% of it |
| 1 spare box | `2×2` | 73% of it |
| 0 spare boxes | `2×2` | 60% of it |

A picture already filling its belt is being asked for enough without a ninth of its grid going dark
for half the level. The slab itself spends no conveyor — it cannot, it is derived from the winning
line — so this is not a price being paid; it is the one measurement the level makes of itself.

A slab **stacks with `Hidden` rather than replacing it**: the slab lifts, `Hidden` does not, so a box
carrying both is dark while the slab is up and dark afterwards too. The Hidden the tier bought is left
exactly where it was spent.

Two things a slab never covers. While it is shut it is a **wall**, so a rectangle that would strand a
box or a tunnel mouth is not laid at all — deliberately the strict reading, and if the runtime turns
out to let the player route across a closed slab this only ever refused a rectangle it could have
kept. And it never covers **half of a `LinkedContainer`**: tapping either half takes both, so a pair
with one half under a shut slab cannot be tapped at all until it lifts, and that is a delay the
gameplay replay has no way to see.

**Rounding and margin.** Counts are written as **odd numbers**, always rounded *down* (the value is a
safety ceiling, and rounding up would step over it). **Biên an toàn** is the gap kept below that
ceiling, 9 balls by default. Raise it to 45 if the runtime turns out to count balls *poured onto the
conveyor* rather than balls *cleared off the picture*: the two readings can differ by a full belt.

Neither lock is ever combined with something that would make its count undefined — a slab never covers
a frozen box, two slabs never overlap, and a `LinkedContainer` half is never frozen (the validator
makes both halves of a pair carry identical effects, and the two halves have different ceilings).

The report states what is shut away and for how long:

```
Khoá theo tiến độ: giữ 63/270 bóng (23% bức tranh)
  Frozen: 3/3 box (mục tiêu 15% box mặt ngoài, mở ở 10%-20% bức tranh)
  slot (x, y) → count, còn dư trước lúc cần: (1, 4) → 29 dư 61, (3, 3) → 37 dư 35
  LargeBlock: 1/1 slab (mục tiêu mở ở 30%, 45% bức tranh)
  ô lưới (x, y, w, h) → count, che, còn dư: (0, 15, 6, 6) → 81 che 4 box dư 27
```

### Saved config (`genlv{level}.json`)

A generated level records the *outcome*, not the knobs that produced it: nothing in the level file says
which difficulty, hidden share or seed built that grid. So the options are written beside it, in one
folder picked once through **Auto Gen Config Folder** on the toolbar and remembered in `settings.json`
under `autogen_config_dir`. The file name mirrors the level file: `1.json` pairs with `genlv1.json`, and
the category variant `1.2.json` with `genlv1.2.json`.

- **Written on Save.** Every successful Auto Gen Box run is remembered for the level in hand, and a
  Save (or Save As) writes it out. A save with no folder picked yet asks once; declining leaves the
  level saved and only the config unwritten.
- **Read on open.** Opening a level reads its preset and the next **Auto Gen Box** dialog opens on it —
  nothing is regenerated behind your back. A level with no preset opens on the plain defaults instead of
  inheriting the last level's.
- **Seed included.** The dialog has a `Seed` knob (Auto = derived from level number and difficulty), and
  the value saved is the seed the run actually used. Reopening the level and pressing **Sinh box**
  therefore rebuilds the *same* grid; change the number or set it back to Auto to reroll.

The file is plain camelCase JSON, safe to hand-edit or keep in git. `null` means Auto — "let the
difficulty decide" — which is not the same as `0`, which switches that knob off. That holds for the two
obstacle toggles as well: `useArrowLock` and `useLinkedContainer` are `null`, `true` or `false`, matching
the three states of their tick boxes. An unknown key is ignored and a missing one keeps its default, so
presets survive new knobs being added.

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

`Import Old JSON` replaces only the current Pixel Grid; every other field of the open level is
preserved, and the import can be undone. Three export shapes are recognised, tried in this order:

| Shape | Size from | Colors from | Empty is |
| --- | --- | --- | --- |
| `pixelBoard` | `pixelBoard.dimensions.cols` / `.rows` | `pixelBoard.colors`, row-major | `0` |
| `pixelGrid` | `pixelGrid.width` / `.height` | `pixelGrid.colors` (or `colorIds`), row-major | `-1` |
| `map` | largest `r` / `c` seen | `map[].color` at `map[].r` / `map[].c` | absent cells |

**The empty value differs by shape and is not guessed.** The oldest `pixelBoard` and `map` exports
write `0` for an empty cell, so `0` there is converted to `-1`. The `pixelGrid` shape already writes
`-1` like the current files, so there `0` is a real color (Red) and is kept.

Color IDs that the current `ItemColor` palette already has are preserved. Any ID past the end of the
palette — `pixelGrid` exports routinely carry `17`, `18`, `23` — is consistently folded onto a current
color that the imported picture was not already using, so **two source colors never merge into one**
and every color keeps its exact pixel count. Import fails rather than merging if the picture carries
more distinct colors than the palette has room for.

Only the picture is imported. A `pixelGrid` export's `gridBoard` is deliberately ignored: its boxes
carry a per-box `capacity` (8 to 54 balls in level 5), while the editor only builds `Square_3x3` boxes
of exactly nine, so importing them would mean inventing a box grid that is not the one in the file.
Use **Auto Gen Box** to rebuild the boxes from the imported picture.

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
