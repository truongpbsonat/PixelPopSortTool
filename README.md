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

Current suite covers shape footprints/rotation, box placement, pixel row-major data, serializer, validator, image import, Auto Gen Box (balancing, gameplay model, difficulty bands, tunnel queues and dig depth, wall reachability, arrow lock keys, linked container tray pressure, obstacle relief on a belt-tight picture, the certified base grid, a scattered 72-box picture built from level 15's own multiset, picture repair, the two-step reading of a picture's difficulty, the difficulty a level adds up to and
the climb that closes the gap to it, scenario easing and seed shuffling), and GUI smoke
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
   outline has holes. Tick **Lấy độ khó từ ảnh** to let the scan name the difficulty — in two steps,
   see [Difficulty](#difficulty): what the artwork *is* on the three-wide scale, and which of the four
   build tiers to aim at. What comes out of that is a **target**, not a description of the finished
   level; step 12b is where the level is measured against it. The scan also
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
3b. **Thin the dust** (opt-in, and only after step 3 has already failed) — stage 3's merge is a *swap*:
   the speck becomes its neighbour and the neighbour hands the same number of pixels back beside the
   colour's own large region. A colour with **no** large region has nowhere to be paid back from, so no
   swap exists and the pass gives up with the belt still short. What is left is a **one-way** merge: the
   speck becomes its neighbour and nothing comes back. That does change what a colour owns, which is why
   ticking **Bỏ màu quá vụn nếu vẫn không qua được** is opt-in — but it is written to change as little as
   it possibly can:

   - **One box, nine pixels, per step.** That is the smallest edit the histogram permits, because every
     colour has to stay a whole number of boxes or no box grid can be built from it. The nine all go to
     one receiver for the same reason: nine pixels cannot be split into two whole boxes.
   - **The box that lowers the belt most**, found by trying every candidate on a copy. Picking "the
     dustiest colour" sounds right and is wrong — merging a colour's specks into a neighbour lengthens
     *that* neighbour's runs, so it can leave the picture needing a **wider** belt. Measured on a
     half-noise picture: dustiest-first took the belt from 49 to 57 and wanted a quarter of the artwork
     recoloured before it came back; belt-greedy wins on **11%** of the pixels.
   - **Stops the instant the picture wins**, not one box past it. Stage 3 aims for margin; this one is
     only ever buying the win, so that is all it buys.
   - **Puts the artwork back if it cannot win inside 12% of the pixels.** A picture needing more than
     that is noise rather than art with dust on it, and the honest answer for it is a wider `piece` —
     so the level ships as a jam with the picture untouched. Better a jam than a different picture.

   Measured on 24×24 pictures that are part painted bands and part per-pixel noise: 60% noise goes from
   `KẸT` at 49/45 to winnable at 43/45 on **11% of its pixels**, keeping nine of its ten colours; 70%
   noise and pure noise are refused and left exactly as painted. The **major colours always survive** —
   a colour leaves the palette only when the nine pixels taken were the last it had, which is the `màu
   lẻ` case: a colour owning two or three boxes, sprinkled. It stops at **three colours** regardless.
   The report places every step on the canvas (`ô hàng r, cột c`), says how many specks it removed, and
   names any colour that ran out.
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
12b. **Sum, and climb to the target** — the difficulty the finished level *adds up to* is measured:
   the boxes buried out of sight **plus** every obstacle laid on top, weighted into one number on the
   same 0–3 line the four tiers live on. Nothing used to ask this. The tier decides which mechanics and
   relief decides how hard each bites, and both are per-mechanic decisions — so a Hard picture whose
   belt refused the hard forms shipped with a Hard label and an Easy level underneath it, and no
   reading anywhere said so. When the sum lands under the target, one mechanic at a time is taken back
   to its tier's own setting — **cheapest on the conveyor first**: the two progress locks cost nothing
   at all, then `Hidden` and `ArrowLock`, then walls and the scramble, and the two that really spend
   belt (tunnel burial, `LinkedContainer`) last. Each rung is a **full rebuild and a re-score**, kept
   only if the result is playable *and* the total actually went up — which is what stops it undoing
   relief, since a rung the belt still refuses comes back trimmed and scores no higher. It never
   overrules the designer: a mechanic switched off by hand, or forms eased on purpose with
   **Hạ độ khó obstacle**, caps the climb instead of being compensated for. A level that still cannot
   reach its tier ships saying how far short it came. See
   [Difficulty](#difficulty). Untick **Tự tăng obstacle cho tới khi đủ độ khó của tranh** to ship
   whatever relief left.
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
* **Is the layout playable at all?** Five failures are invisible to any replay, because the gameplay
  model taps a queue by index, walks no route across the grid and counts no pixels: a **wall that seals
  a box in**, a **lock that opens too late** (see [Progress locks](#progress-locks)), and three ways a
  tunnel's queue can be shut in — a **mouth facing no box** (a wall, another tunnel or the edge of the
  lattice is sealed for the whole level), **two tunnels aiming at the same release slot**, and a
  **locked box standing in the doorway**. All are read off the finished layout, and a layer with any of
  them is **never shipped** (the mouth case used to go out with only a warning). Small grids are where
  it bites: three tunnels on a three-box grid have nothing to point at. Such a layer is dropped, a
  gentler form is tried, and if every form is unplayable the certified **base grid ships instead** — a
  level with no mechanics beats a broken one, and the report says so. The one exception is a layer the
  two **progress locks** broke: those are swapped out for other mechanics rather than given up on, see
  [Swapping a lock that breaks the level](#swapping-a-lock-that-breaks-the-level).

**The placement avoids the sealed mouth rather than discovering it.** `_tunnel_slots` used to check only
that a tunnel does not seal a *box* away; it would fill the back row with tunnels and then put the next
one in the row in front — which is the one slot the tunnel behind it was pointing at. That tunnel then
had nothing but tunnels on every side, and because the fault lands on the **base grid** there was
nothing left to fall back to: **81 boxes on a 64-slot lattice refused the level outright**, telling the
designer to raise the slot limit or shrink a picture that fitted perfectly well. `tunnels_can_release`
now asks of every candidate whether each tunnel still has a neighbour **of its own** that can hold a box
— a matching rather than a count, because two tunnels can each have a free neighbour and it can be the
same one — which makes the back rows fill in **alternating** order once one of them is solid — a full row of tunnels needs the
row in front of it to stay boxes, so the next tunnel goes one row further in. A picture of 576 boxes now
lays out on the same 64-slot lattice, 29 on the surface and 547 in 35 tunnels, every mouth facing a box.
It is a **preference, not a veto**: a lattice too cramped to give every tunnel a box seats them anyway
and lets the fault-and-relief path above handle it, which is what keeps a three-slot grid from failing
the run outright.

### Difficulty

The conveyor is the level's own `piece x 9` at every difficulty, so the bite comes from the obstacles
rather than from the belt. The main dial is `Hidden`: a hidden box shows no color, so the player cannot
tell whether tapping it wastes belt room.

#### Reading it off the picture

**Lấy độ khó từ ảnh** reads the difficulty off the picture instead, and it is **two readings, not
one** — they have different widths, so they cannot be the same number:

1. **What the artwork is**, on the three-wide scale somebody says out loud: `dễ` under four colors,
   `vừa` up to eight, `khó` from nine. This is a statement about the picture.
2. **Which tier to build for it**, on the four-wide scale the generator uses. This is a decision.

| Colors | Picture reads as | Tier to build |
| --- | --- | --- |
| 1–3 | dễ | Easy |
| 4–8 | vừa | Medium |
| 9–12 | khó | Hard |
| 13+ | khó | SuperHard |

The build scale is one step wider on purpose: past twelve colors a picture is beyond what a three-word
scale was drawn to describe, so it goes to SuperHard rather than being clamped into Hard and pretending
it is the same thing. A ten-color picture and a twenty-color one look equally hard; only one asks for
SuperHard.

A picture whose colors are broken into many small runs along the play order is pushed **up one tier**,
because it forces the player to keep more colors on the belt at once. That push lands on the *tier*,
not on the band — it is about how the picture plays, not what it looks like. It is never pushed down:
twelve colors in neat bands are still twelve colors to read. The dialog prints the whole reading beside
the tick box (`7 màu → tranh vừa → Medium, độ vụn 32% chưa tới ngưỡng nâng nấc`), and the report prints
it whether or not the tick box decided the tier — a designer overruling the picture still wants to know
what it would have said.

#### The difficulty a level adds up to

The tier is the **target**. What the level came out at is measured separately, after every obstacle is
on it, and reported on the same 0–3 line:

```
Độ khó tổng hợp của level dựng ra: 1.91/3 = Hard (mục tiêu 2.00 = Hard)
  cộng từ: Hidden 2.14, xáo trộn lưới 2.00, Tunnel 0.00, Wall 2.00, ArrowLock 1.80,
           LinkedContainer 0.67, Frozen 1.50, LargeBlock 2.00, độ trễ mở khoá 2.00
  thang điểm neo vào chính 4 dòng độ khó: Easy 0.0 < Medium 5.8 < Hard 18.8 < SuperHard 28.5
```

Two things about that number matter. It is a **sum**: "this picture is Hard" is a statement about the
whole level — the buried boxes *and* the obstacles together — so a shortfall in one mechanic can be
paid for by another, and no mechanic is checked against the tier on its own. Burial (`Hidden`, the
scramble, tunnel digging) is 4.5 of the 10 and the six obstacles the other 5.5: a picture is made hard
mostly by what the player cannot see, and the rest by what is in the way.

And there is **not one hand-picked threshold in it**. The four rows of `DIFFICULTY_PROFILES` *are* the
scale: each dial is read against the ladder those four rows write for it, and the four totals become
the 0/1/2/3 marks the level's own total is interpolated between. Edit a profile and the scale moves
with it, so it cannot drift away from what a tier means. A tier's dials spent in full score exactly
that tier, by construction.

When the sum falls short, step 12b climbs it. When it cannot be closed, the shortfall is said in the
report banner, in the report body and — for a folder run, where nobody opens a hundred reports — in the
**Đo được** column of the batch table, marked with a `!`:

```
CHỈ ĐẠT Hard (2.43/3) so với mức SuperHard mà tranh đọc ra — thiếu 0.57 nấc,
đã siết 6 loại obstacle mà vẫn không tới. Level vẫn chơi được — xem phần dưới.
```

That is a third verdict beside "does it win" and "does it load", and the only one of the three about
the *design* rather than about correctness — which is why it is a warning and not an error. The level
works; it is just not the level the picture asked for.

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

Relief on its own can overshoot, and that is what **Tự tăng obstacle cho tới khi đủ độ khó của tranh**
(beside it, also on by default) is the mirror of. Relief steps *every* dial down a whole tier at a time
because one mechanic was refused, so a Hard picture relieved two tiers ships carrying every mechanic
Hard bought, set the way Easy would set them, with a Hard label on it — and on level 10 at Medium, the
level scored a flat `0.00` (Easy) while shipping as Medium. The climb reads the
[sum](#the-difficulty-a-level-adds-up-to) and takes the overpayment back one mechanic at a time,
cheapest on the belt first, keeping only rungs that are playable and that actually raise the total. The
two work as a pair: relief finds a form the picture can pay for, the climb spends what the picture had
left over. Neither can overrule a knob the designer set — a mechanic switched off, a typed count, or
**Hạ độ khó obstacle** all cap the climb rather than being compensated for.

### The picture that cannot be won at all

Relief above reacts to what the belt **refuses**, and there is one case where the belt refuses nothing
and the reaction never comes: the picture does not win on the conveyor the level ships with at all —
the red `KHÔNG THỂ THẮNG với piece hiện tại` line at the top of the dialog, read after the repair has
had its go, so a picture the repair saves is not covered by it. Two things put that case out of relief's
reach. The obstacles are certified against the belt the picture *needs* rather than the one it has, on
purpose — certifying against a belt nothing wins on would only strip the level bare and every check
would fail for the same single reason — so the belt says no to nothing. And `Hidden` never costs a ball,
so it is not something a belt check could cut in the first place. The result was the worst combination
the tool could ship: a level the player runs dry, with 60% of the surface hidden and the box they need
next scattered anywhere on the grid.

**Hạ chôn box về Easy khi tranh không thắng được** (on by default, under the relief tick) splits the
level the way the [difficulty sum](#the-difficulty-a-level-adds-up-to) already splits it — what the
player cannot see, against what is in the way — and moves only the first half:

| | On a jammed picture | |
| --- | --- | --- |
| **Burial** — `Hidden`, the grid scramble, the tunnel dig window | **floored at Easy** | 8% hidden instead of 60%, boxes in solution order instead of anywhere on the grid, each one handed over exactly when the picture asks for it |
| **Obstacles on top** — wall, arrow, link, frozen, LargeBlock | **kept at the tier's form**, and still climbed | the level is not shipped bare; the score the floor gives up is made back out of these |

The floor is applied **last**, after the form ladder and after every climb rung, so nothing can bury the
level again — and the three burial rungs are skipped rather than attempted, since a rebuild that gets
overwritten can only score the same. What the [climb](#the-difficulty-a-level-adds-up-to) does instead
is pay for the missing burial out of the top half: on level 10 at Hard it buys back the lock timing and
a fourth arrow, so the level keeps its content and only stops being unreadable.

**What it does not do is make the picture winnable** — and no knob in the tool does. `winnable` is the
picture measured against the belt its own `piece` buys, before a single box exists: level 10's bare
walkthrough needs 40 balls, so on a 36-ball belt every tier and every form loses, base grid included.
Only raising `piece` to the number in the warning, or repainting, clears it. `difficulty`, `themeId` and
the mechanic count all stand, so the level is still the tier that was asked for, and raising `piece` and
generating again hands the tier's own burial straight back. Untick it to bury a stuck level at its tier's
form the way the tool used to.

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
| **Hạ chôn box về Easy khi tranh không thắng được** | On a picture that [cannot be won on the level's own belt](#the-picture-that-cannot-be-won-at-all), floor the *burial* — `Hidden`, the scramble, the dig window — at Easy's settings and leave every obstacle on top at its tier's form, still climbed. The one case relief cannot see: the belt refuses nothing there, and `Hidden` costs no ball for it to refuse. It does not make the picture winnable — nothing does but raising `piece` — it makes the level readable until you do. |
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
no need to generate it again. The one thing that *is* held back on a picture like that is how deep the boxes
are buried — see [the picture that cannot be won at all](#the-picture-that-cannot-be-won-at-all), which is the
exception this certification would otherwise create: the belt it certifies against is wide enough to pay for
a burial the shipped belt never could.

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

**The release slot holds one box at a time.** The box in it clears, the tunnel behind pushes the next one
in, and that one has to clear before anything else moves — so the whole queue comes out through that single
square. Two consequences, and both used to go out in shipped levels:

* **No two tunnels share a door.** A slot two tunnels aim at is two queues waiting on the same square, and
  nothing in the level file says who goes first. Tunnels claim their facings in turn — the one with the
  fewest box sides picking first, so a cornered tunnel keeps its only door — and a slot already claimed
  ranks below a free one. A clash that survives that is a fault, but only when a distinct-door assignment
  exists to be found: a picture that overflows the lattice badly enough parks tunnels along two rows with a
  single row of boxes between them, and there genuinely are more queues than doors.
* **Nothing is locked onto the doorway.** A `Frozen` box, a box under a `LargeBlock` and a box behind an
  `ArrowLock` all wait on something before they can go, and while they wait the tunnel behind them cannot
  hand out anything. So the three planners are handed the doorway boxes and keep off them. `Hidden` is not
  in that list: a hidden box does not say its colour, but it taps like any other.

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

**The colour read comes first.** Before either lock is placed, `read_color_supply` reads the picture
one colour at a time: every pixel number at which the frontier asks for that colour, and how many
balls of it the grid holds. Only the frontier colour can be spent, so this is what says whether a box
can clear anything at all at the moment a lock would be holding it shut — and unlike `tap_progress`
it is a fact about the *picture*, true for every order the player might tap in. Placement is chosen
from it, and only then is a number written.

**The deadlock rule.** The picture is cleared by a single frontier. If the colour the frontier wants
has only one box left and that box is frozen, nothing clears — and because the lock opens on progress,
nothing clearing means the lock **never opens**. That is not a hard level, it is a dead file. So a lock
only ever goes on a colour that still has another box to serve the frontier while it is shut, and
"another box" means one that is **actually still tappable**: a spare already sitting under a slab, or
frozen by an earlier round of the same pass, is not a spare, so the count is taken against what is
free rather than against a head count of the colour. The hand-made level 59 does exactly this by hand:
all four of its Frozen boxes are Red or White, its two most common colours.

**Two ceilings, and the tighter one wins.** `tap_progress` bounds a count by the one order the run
certified. `lock_reach` bounds it by the picture: the `n`-th pixel of a colour cannot clear until `n`
balls of it have been poured, so holding some back behind a counter stops the picture at the first
pixel it can no longer pay for, and the count may not exceed that pixel. The second bound holds for
**every** tap order, not only the certified one, which matters because the player does not know the
certified one. `locks_open` then asks the finished layout the same question as a fault and again as an
internal check, the way `locks_hold` does for the certified line — a set of counters that starves a
colour wins in the simulator and stalls for the player. On the pictures measured so far the certified
bound is the tighter of the two every time, so this changes no number; it is what stops one from being
written when a picture makes the two disagree.

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

**The window binds the count, not just the pick.** When the search has widened — no box on the grid
falls inside the window — honouring the tier's share alone writes a lock that is legal and useless: a
Frozen 29 on a box the winning line does not want until 126 has been cleared long before it could cost
anybody anything. Measured on level 10, 73% of Hard and SuperHard locks came out that way. So the
share reads as a **floor** and `lock_count` lifts the number toward the ceiling until the gap *is* the
window; the ceiling is still never crossed and the value is still rounded down, so the safety of the
number is untouched. Every lock now opens within one pixel of its window (the odd-rounding step), at
the price of the count leaving the band on grids whose boxes do not fall where the band wanted them.

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

**The size steps down rather than shipping nothing.** A slab needs a *solid* rectangle of the lattice,
and walls and tunnel mouths cut the lattice into pieces: measured on a 24×24 picture, SuperHard found
no 2×2 of real boxes anywhere in 13 of 15 seeds, so the run bought `LargeBlock` and laid none — a
mechanic *removed*, which is the budget's decision to make and not the geometry's. `block_span_ladder`
therefore tries the sized slab first and steps down through `2×2` to a **pair** (`2×1` or `1×2`),
which is still the thing a slab is and a Frozen box is not: two boxes behind one counter, opaque until
it lifts, lifting together. Never a single box — that is a Frozen, and it has its own planner. With the
ladder in place the slab dose now ships in full on every picture measured, where it previously shipped
nothing on two of three.

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
makes both halves of a pair carry identical effects, and the two halves have different ceilings). And
neither is ever laid on the box standing in front of a **tunnel's release slot**: that box has to leave
before the tunnel behind it can hand out a single one of its own, so a counter there is a counter on
the whole queue — a failure the replay cannot see at all, since it pops queues by index and never asks
whether the door is open. `ArrowLock` keeps off the same box for the same reason; `Hidden` does not
have to, because a hidden box still taps like any other.

#### Swapping a lock that breaks the level

The relief ladder answers "too hard" by rebuilding the same mechanics a tier gentler, and for five of
the seven that is the right answer: a shallower tunnel, a nearer arrow, a smaller wall count. It is the
**wrong answer for the two locks**. A `Frozen` box and a `LargeBlock` do not get milder as the form
steps down — they get a smaller number written on them — so a level they make unwinnable is unwinnable
because of *where they landed*, not how hard they bit. Stepping the form down four times and then
shipping a bare grid is what that used to cost.

So a level the locks broke **swaps them out**. Every fault is attributed to a mechanic as it is raised,
and when the ladder runs out with a lock to blame the run drops the blamed locks and draws the same
number of mechanics at random from whatever the picture can still pay for and the designer has not
switched off — never the other lock, which would be answering "the locks broke this level" with a lock.
The level keeps the mechanic **count** its tier rolled; only the mix changes. A designer who typed a
`Frozen` count loses it here too, and the report says why:

```
  đã đổi khoá: LargeBlock/Frozen làm level không thắng được ở mọi dạng, thay bằng Wall/LinkedContainer
```

The bare base grid is still the floor underneath it: a swap that finds nothing to draw, or one that
faults in its turn, leaves the original reading in place and the certified grid goes out plain.

The report states what is shut away, for how long, and the colour read the placement came from — the
last line is the check by eye: a colour whose picture demand is not covered by the boxes still tappable
is one whose lock has to open before the frontier reaches it, and the count says whether it does.

```
Khoá theo tiến độ: giữ 63/270 bóng (23% bức tranh)
  Frozen: 3/3 box (mục tiêu 15% box mặt ngoài, mở ở 10%-20% bức tranh)
  slot (x, y) → count, còn dư trước lúc cần: (3, 4) → 29 dư 97, (3, 3) → 37 dư 35
  LargeBlock: 1/1 slab (mục tiêu mở ở 30%, 45% bức tranh)
  ô lưới (x, y, w, h) → count, che, còn dư: (0, 12, 6, 6) → 49 che 4 box dư 41
  màu bị khoá → pixel tranh cần / bóng trên lưới, box còn tap được: 3: 81/81, 6 box,
  7: 108/108, 9 box, 12: 18/18, 1 box
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

### Auto Gen Folder (whole folder at once)

**Auto Gen Folder**, beside **Auto Gen Box** under the Box Ball Grid, runs the same generator over every
picture in one folder instead of the level in hand. The source folder holds one of two things, and both
are read the same way:

- **A folder of art** (`*.png`, `*.jpg`, `*.jpeg`, `*.bmp`, `*.tga`, `*.gif`, `*.webp`). Each image is
  sampled into a Pixel Grid exactly the way **Import Image** does, at the alpha threshold set in the
  dialog, and becomes a brand-new level file.

  **The grid size comes off each picture**, not off one number typed for the whole folder — *Lấy kích
  thước từ chính ảnh*, on by default. A folder of art is a folder of *different* pictures, and one size
  forced onto all of them is wrong for the commonest case: art that already **is** a grid. A 20×12 piece
  pushed through a 16×16 grid loses four columns and two rows and comes back square. With the option on,
  the two spin boxes become a **cap** instead of the size: a picture inside the cap keeps its own
  dimensions exactly and nothing is resampled — the grid is the art, cell for cell — while a larger one
  is scaled by the tighter of the two ratios, so a 400×100 banner under a 32×32 cap becomes 32×8 rather
  than a squashed square. The cap is what stops a 4000×3000 photograph asking for a twelve-million-cell
  grid. Untick it and every image is forced to the typed numbers, which is what a folder of photographs
  wants. The size line under the preview always names what the run will actually use, and follows both
  knobs as they move.
- **A folder of level files** (`*.json`). The picture is read off the level already in the file, so a
  folder of hand-painted levels can be (re)generated in one pass. `genlv*.json` presets sitting in the
  same folder are never mistaken for levels.
- **A folder of the game's own exports** (`*.json` again, but not in this editor's format). These write
  their picture under `pixelGrid.colors` rather than `colorIds`, or under the older `pixelBoard`/`map`
  shapes, with colour ids past the end of `ItemColor` and a `gridBoard` of box capacities this editor does
  not build. When the current reader refuses such a file, the picture is read the way **Import Old JSON**
  reads it — same importer, so the same palette folding onto free colour ids — and handed back to the
  current reader inside its own document, so the level's *own* `level`, `time`, `piece`, tier and theme are
  still parsed by the reader that knows those fields. The old boxes are deliberately dropped: Auto Gen Box
  is about to lay a fresh box grid anyway. The row says `đọc theo định dạng cũ`, because the palette does
  not survive whole.

Both kinds may sit in the same folder; sub-folders are left alone.

**Which level each file becomes.** The number in the file name: `7.png` and `7.json` both build level 7,
`7.2.png` its category variant, and `4.3mau.json` level 4 — a name that *opens* with a number keeps it
however it goes on to describe itself, so an exporter's label (`3mau` = three colours) is read and dropped
rather than mistaken for a category. A name with no number at all (`cat.png`, and `2024art.png`, where the
digits run straight into the word) takes the next free number from **Level bắt đầu**, skipping every number
the folder already claims. A *level file* is the exception — it
carries its own `level`/`category` inside, and that is what the output file is named after, whatever the
file on disk is called. Two sources landing on the same level: the first wins, the second is reported as
`bỏ qua` rather than silently overwriting it.

**Which knobs each level gets**, in order:

1. `genlv{level}.json` in the config folder, when **Ưu tiên cấu hình** is ticked and that level has one.
   A preset is taken whole — it is the exact set of knobs that level was tuned with, seed included, so
   the file it rebuilds is the file it built last time.
2. Otherwise the parameters from **Tham số Auto Gen Box…**, which opens the very dialog the single-level
   action uses. With **Dùng độ khó ghi trong từng file level** ticked, a level file's own difficulty
   replaces the dialog's tier so a mixed folder keeps its easy/hard spread.
3. Over the top of either: the two run-wide knobs on the folder form — the tier read off each picture
   and the roll count — which are described [below](#the-workbench-window) and are the only things that
   outrank a preset.

With **Lưu cấu hình** ticked, every generated level writes its preset back — including the seed the run
actually settled on, which is the only part of a run the dialog does not hold. That is what makes a
folder reproducible: run it again and the same files come out.

#### The workbench window

**Auto Gen Folder** opens a window of its own, because a folder run is work a designer sits with rather
than a question to answer once:

- **Nguồn trong folder** lists every source with the level it will become (`(tự đánh)` marks a number
  the run assigned), the toolbar's ◀ ▶ walk the list, and **Làm mới** re-reads the folder after files
  change on disk.
- **Bức tranh của dòng đang chọn** draws that source's picture — a level file's own Pixel Grid, or an
  image sampled at the width, height and alpha the settings ask for, so a bad sampling size is visible
  before anything is generated. Under it: size, painted pixels and colour count.
- **Chỉ sinh các dòng đang chọn** runs only the highlighted rows, for regenerating two levels without
  touching the other fifty.
- The run happens on a **worker thread**: the progress bar and label say `(k/n) đang sinh <file>`, the
  window stays usable, and the toolbar button turns into **⏹ Dừng**. Closing the window mid-run asks
  first, then stops and waits for the thread.
- **Kết quả** is the log: one row per source, coloured by outcome, with the source rows marked as each
  finishes. **Xoá log** clears it, **Xuất CSV** writes it out, and double-clicking a row opens that
  generated level in the editor (with the usual unsaved-changes prompt).

**Gen Folder (nhanh)** on the main toolbar is the same run without the workbench: one dialog, one
progress bar, one report table.

**While it runs** a progress dialog names the file being generated; **Cancel** stops between levels and
keeps everything generated so far. Afterwards a report table lists every source file with its level,
result, difficulty, box/hidden/tunnel/wall counts, the two progress locks (**Frozen** and **Slab**), the
belt it needs against the belt it has, its seed and the output file, plus the balancing or jam note for
that level. A jam does not withhold the file — the single-level action ships an unwinnable grid too — it
is flagged `KẸT` in orange so it can be found and fixed. **Xuất CSV** writes the table out (UTF-8 with
BOM, so Excel opens the Vietnamese columns correctly).

#### What a folder run says about the obstacles

A folder run is the single-level generator called once per file, so every rule the single-level action
is held to holds here as well: the picture is read per colour before a lock is placed, a lock's number
is bounded by both the certified line and the picture, the box grid is certified with no mechanics on it
before any are laid, and a mechanic layer that would cost the level its proof is stepped down or dropped
rather than shipped. There is nothing to switch on.

What a folder run adds is **scale**, and with it the one thing the single-level report never had to
worry about: nobody opens a hundred reports. So the three outcomes that make a level quietly different
from the tier that was asked for are on the row and in the headline:

- **`obs hạ N bậc xuống mức X để level còn qua được`** — the relief ladder stepped the obstacle forms
  down. The level is still the tier it says it is, but its mechanics bite at gentler settings. Counted
  as `N hạ bậc obs` in the headline. This is common on small pictures: six 9×9 pictures asked for at
  SuperHard all shipped Easy-form obstacles and no locks at all, which used to be invisible.
- **`obs không đặt được cái nào, ship lưới base trần`** — every form faulted, so the certified base grid
  went out with no mechanics on it. Counted as `N không có obs`. This is the loudest thing a row can
  say, and before it was on the report a folder of these looked like a folder of clean runs.
- **`chôn box hạ về Easy (box ẩn N) vì tranh chưa thắng được — nâng piece lên P là trả lại mức X`** —
  the picture [cannot be won on the belt its level ships with](#the-picture-that-cannot-be-won-at-all),
  so its burial was floored while every obstacle on top kept its tier's form. Counted as
  `N hạ chôn box về Easy (nâng piece)`, and always a subset of the `N kẹt` beside it — the actionable
  subset: each of these rows is a picture whose `piece` is too small, and the row names the number that
  fixes it. This is *the* folder-scale case, because a hundred pictures scaled off one template all
  inherit that template's `piece`, and one wrong number there buries the whole batch at its tier's depth.

The **Ẩn** column carries a `↓` on exactly those rows, so a batch can be scanned rather than read: a `2 ↓`
beside a SuperHard label is a picture that needs a wider `piece`, not a level that was built wrong. The
**Frozen** and **Slab** columns are the same signal at the mechanic level: a `0` where the tier bought one
means that lock found nowhere to land on that picture.

The generator's knobs are not duplicated in the folder form — **Tham số Auto Gen Box…** opens the very
dialog the single-level action uses, so every tick above is available per batch and round-trips through
`genlv{level}.json` like the rest. Two of them are called out in the summary line beside the button when
they are **off**, because nothing else in the report would show it: `KHÔNG tự tăng độ khó` and
`KHÔNG hạ chôn box khi tranh kẹt`.

Two knobs are lifted out of that dialog and onto the folder form itself, because they are the two the
folder run has to answer *per level* and nobody is going to open the params dialog a hundred times to do
it. Both are on by default, so **Sinh cả folder** is the whole operation: press it and every picture gets
its own tier and ten rolls.

**Lấy độ khó thẳng từ ảnh cho MỌI level trong folder** is the tier, read off each picture the way the
params dialog's own *Lấy độ khó từ ảnh* does for a single level — colour count first, a notch up for a
fragmented picture — so one folder of art comes out as a spread of Easy/Medium/Hard/SuperHard rather than
a hundred levels wearing one number somebody typed once. Ticked, it **outranks `genlv{level}.json` and
the level file's own difficulty** both: a designer who says "take the tier off the picture, for every
level" is not asking to be overruled by a number an earlier run wrote back. The rest of the preset still
stands — only the tier moves, and the doses left on Auto follow it there — and the preset written back
records *that the tier came from the picture*, so the next run over the same folder rebuilds the same
level. Untick it and the tier falls back to the old order: the level's preset, then the difficulty
written in the level file, then the number in the params dialog.

**Xóc lại cho cả folder** is the roll count, and it defaults to **10 lần**: rolling is what makes an
unattended run worth trusting, and a folder run is the one place nobody is watching each level to re-roll
it by hand. `Theo tham số` (0) hands the count back to each level's preset or the params dialog; any
number applies to **every level in the run** and, like the tier box above, **outranks a per-level
preset**. Why it is allowed to: it is the run's *cost* dial — N rolls times a hundred levels is the whole
wall-clock of a batch — so it belongs to the run rather than to any one picture; and unlike the obstacle
doses it changes nothing about what a level *is*, because every roll is a complete certified level and
the shuffle only picks between them, so forcing it cannot produce a grid nobody chose. It matters because
`write_presets` is on by default: after one batch run every level has a preset carrying that run's count,
so a dial that deferred to presets would be dead in the workflow it exists for. The preset written back
records the count the run used and the seed of the roll that won.

The source, output and config folders are remembered in `settings.json` (`autogen_batch_source_dir`,
`autogen_batch_output_dir`, `autogen_config_dir`). Generating into the folder of the level currently
open reloads it on screen when it has no unsaved edits, and warns instead of discarding them when it has.

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
| 17 | Color 17 | `#94F8FF` |
| 18 | Color 18 | `#FF6A63` |
| 19 | Color 19 | `#AEC6F7` |
| 20 | Color 20 | `#C37035` |
| 21 | Color 21 | `#9D4B2F` |
| 22 | Color 22 | `#0A782F` |
| 23 | Color 23 | `#F9E2AB` |
| 24 | Color 24 | `#FFBDBD` |
| 25 | Color 25 | `#F2235E` |
| 26 | Color 26 | `#4C4DA8` |
| 27 | Color 27 | `#E0FDFF` |
| 28 | Color 28 | `#B71F2E` |

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
