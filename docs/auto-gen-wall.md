# Auto Gen Box — cơ chế Wall

> Ghi chép phiên làm việc **2026-08-03**. Đọc kèm [auto-gen-tunnel.md](auto-gen-tunnel.md).

---

## 1. Luật wall (designer xác nhận)

- **Một slot trống trong box grid chính là một wall.** Không có cell type riêng, không có obstacle
  riêng — chỗ nào không có box thì chỗ đó là tường.
- Wall **chặn đường active** vào box nằm cạnh nó và **không bao giờ mở ra**.
- Kẹp wall vào **hai cạnh** của một box thì chỉ còn cách **đi vòng vào cạnh còn lại** để lấy box đó.
- Suy ra điều duy nhất bị cấm: **bịt cả bốn cạnh** ⇒ box kẹt vĩnh viễn ⇒ level không giải được.

Box **không** chặn nhau — dòng designer-confirmed trong `pixel_gameplay.py` vẫn đúng: *"Every box on
the grid can be picked"*. Nên khi tính đường đi thì đi xuyên qua box, chỉ wall và tunnel mới cản.

Yêu cầu: thêm wall vào auto gen cho **Hard và SuperHard** để tạo cảm giác "chỉ có một đường để win",
nhưng **dùng dè** vì wall vừa cản đường vừa ăn mất một slot.

## 2. Nguồn tham khảo

`D:\Marble Flow\bolevel_fixmau` — 56 level hand-made. Quan sát rút ra:

- Wall xuất hiện ở **rất nhiều level**, kể cả Easy (nhiều nhất là `18.json` với 11 wall trên lưới 7x6).
  Nghĩa là data hand-made **không** gắn wall với độ khó — đó là lever mình mới thêm.
- Wall luôn **đối xứng trái–phải** quanh cột giữa.
- Chủ yếu nằm ở **góc và rìa** để tạo dáng cho lưới, thỉnh thoảng có **hõm ở giữa**.
- `18.json` là ví dụ mẫu của cơ chế: box ở slot `(3,1)` bị wall bịt trái, phải và dưới — chỉ vào được
  từ phía trên.
- **Không level nào ship `isActive: true`** — runtime tự tính activation từ hình học wall. Đây là bằng
  chứng mạnh nhất cho việc wall quyết định reachability.

## 3. File đã thay đổi

| File | Nội dung |
| --- | --- |
| `src/pixel_level_tool/services/box_autogen.py` | Toàn bộ logic wall |
| `src/pixel_level_tool/ui/dialogs/auto_gen_box_dialog.py` | Ô **Wall (slot bỏ trống)** |
| `src/pixel_level_tool/ui/main_window.py` | Status bar báo số wall |
| `tests/test_box_autogen.py` | Mục `# Walls`, ~11 test |
| `tests/test_auto_gen_box_ui.py` | Test ô chọn wall |
| `README.md` | Mục **Walls**, cập nhật bảng độ khó |

Chạy test: `.\.venv\Scripts\python.exe -m pytest tests/ -q` → **254 passed**.

## 4. API mới trong `box_autogen.py`

```python
slot_neighbours(slot, cols, rows)          -> 4 slot kề cạnh, đã cắt theo biên lưới
reachable_slots(cols, rows, blocked)       -> flood fill từ ngoài lưới vào
layout_is_open(cols, rows, walls, tunnels) -> bool, invariant chính
plan_walls(surface_boxes, options, profile)-> số wall muốn đặt trước
_wall_groups(cols, rows)                   -> generator (group, pinch, strict), tốt nhất trước
_wall_slots(cols, rows, tunnel_slots, count) -> (wall_slots, pinched_slots)
```

`DifficultyProfile` thêm `walls`; `AutoGenOptions` thêm `walls: int | None` (None = auto).
`AutoGenResult` thêm `wall_slots`, `pinched_slots`, property `wall_count`.
Hằng số `WALL_BOX_BUDGET = 4` (tối đa 1 wall / 4 box).

## 5. Bảng độ khó

| Difficulty | Walls | Ý nghĩa |
| --- | --- | --- |
| Easy | 0 | lưới đặc |
| Medium | 0 | lưới đặc |
| Hard | 2 | một box bị kẹp |
| SuperHard | 4 | hai box bị kẹp |

Sửa ở dict `DIFFICULTY_PROFILES`.

## 6. Các quyết định thiết kế & lý do

### Reachability: box trong suốt, chỉ wall và tunnel mới chặn

`layout_is_open` flood fill từ **ngoài biên lưới** vào, đi xuyên box, không đi xuyên wall/tunnel. Yêu
cầu: mọi slot không-bị-chặn phải reachable, và mỗi tunnel phải nằm ở biên hoặc kề một slot reachable.

Lý do đi xuyên box: nếu box cũng chặn thì trong một lưới đặc 5x6, **12 box ở giữa sẽ không lấy được ở
bước đầu** — level 10 hand-made sẽ thành không hợp lệ. Mâu thuẫn với chính data đang ship, nên box
phải trong suốt.

Hệ quả quan trọng: **reachability không ràng buộc thứ tự pick**, nó là tính chất tĩnh của layout. Nhờ
vậy `solve_order`, `plan_queues`, `simulate_order` **không phải sửa một dòng nào**.

### Wall đặt theo **cặp đối xứng kẹp một box**, không rải lẻ

`_wall_groups` ưu tiên "pinch": tâm là một slot bên trong, hai wall là `(cx-1, cy)` và `(cx+1, cy)`.
Đối xứng có sẵn theo cấu trúc. Ưu tiên hàng giữa trước vì pinch ở biên chỉ bỏ đi một hướng vào mà
ngoài lưới vốn đã cho sẵn.

### Cấm hai pinch ở hàng kề nhau

Bản đầu tiên không có luật này và bị đúng hai bug thật:

1. Pinch thứ hai lấy **tâm của pinch thứ nhất** làm wall ⇒ "box bị kẹp" báo trong report thật ra lại
   là một cái wall.
2. Các cặp dính nhau thành **một dải wall liền** cắt đôi lưới (`# # # #` chắn ngang lưới 4 cột).

Sửa: `pinched_rows` cấm tâm pinch mới nằm ở hàng cách ≤ 1; wall không bao giờ được đặt lên một slot
đã ghi là pinch; và cờ `strict` cấm group mới kề cạnh wall đã đặt.

### Slot thừa cũng là wall, nên cũng phải đặt có chủ đích

Trước đây slot thừa rơi đâu thì rơi (chỗ nào `zip` hết chỗ). Giờ mọi slot trống đều là wall nên
`_wall_slots` đặt cả phần thừa, đi theo cùng thứ tự ưu tiên. Warning cũ *"boxes do not form a full
rectangle"* được viết lại thành warning về wall.

### Đặt trước wall làm **lưới to ra**

Box vẫn cần đủ slot của nó, nên lưới phải được chọn cho `box + tunnel + wall`. Level 10 có 30 box vừa
khít 5x6, nhưng Hard đặt trước 2 wall ⇒ 32 slot ⇒ **4x8**. Đây là hệ quả của chính sách "ưu tiên khít
tuyệt đối" có sẵn trong `choose_lattice`.

Đã cân nhắc đổi sang ưu tiên lưới vuông: 6x6 sẽ đẹp hơn nhưng để thừa **6 wall** thay vì 2 — trái với
yêu cầu "hạn chế dùng". Chọn giữ ít wall, chấp nhận lưới cao.

### Test parity của level 10 phải ghim `walls=0`

Ba test tái tạo level 10 hand-made giờ truyền `walls=0`, vì level 10 hand-made **không có wall**. Đó
mới là so sánh đúng, chứ không phải nới lỏng assert.

## 7. Điểm còn mở / TODO

1. **Chưa xác nhận được luật runtime chính xác.** Mình suy luận từ mô tả của designer + 56 level tham
   khảo + việc không level nào ship `isActive`. Nếu runtime thực ra **cũng** để box chặn nhau (kiểu
   bãi đỗ xe) thì `layout_is_open` phải chặt hơn nhiều và `solve_order` sẽ phải xét cả reachability
   theo từng bước. **Nên hỏi lại designer một câu: box có chặn nhau không, hay chỉ wall mới chặn?**

2. **Pinch chưa gắn với box cụ thể nào.** Hiện chọn tâm pinch thuần theo hình học. Có thể chọn box mà
   walkthrough cần muộn, hoặc box `Hidden`, để cảm giác "chỉ một đường" mạnh hơn. Chưa làm vì với mô
   hình box-trong-suốt thì pinch không đổi thứ tự pick, giá trị của nó là hình ảnh/UX.

3. **Wall chưa tương tác với `Hidden`.** Một box vừa bị kẹp vừa `Hidden` là hai lớp che thông tin cộng
   dồn — có thể là quá tay, chưa thử đo.

4. **`choose_lattice` chưa có ràng buộc tỷ lệ khung.** 4x8 (12x24 cell) hợp lệ nhưng không level
   hand-made nào cao/hẹp như vậy — level tham khảo đều quanh 6x6, 7x7. Nếu thấy xấu thì thêm penalty
   tỷ lệ khung vào `choose_lattice`, nhưng nhớ là nó sẽ đổi hành vi của **cả** đường không-wall.
