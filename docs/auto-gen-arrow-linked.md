# Auto Gen Box — cơ chế ArrowLock & LinkedContainer

> Ghi chép phiên làm việc **2026-08-04**. Mục đích: lần sau mở lại là tiếp tục sửa được ngay,
> không phải đọc lại toàn bộ code.

---

## 1. Bối cảnh & yêu cầu

Level 44 là level hand-made có cả `ArrowLock` và `LinkedContainer`. Rule do designer xác nhận:

**ArrowLock**

- Box mang obs này hiển thị **một mũi tên chỉ hướng**. Muốn mở được box đó thì phải **mở một box ở
  đúng hướng mũi tên đang chỉ** trước.
- Độ khó của arrow **khá là khó**, nên dùng liều lượng thấp.
- **Tránh không đặt hướng mũi tên vào wall hoặc vào nơi không có box** — vì điều kiện mở arrow box là
  cần mở một box ở hướng mà nó chỉ tới. Chỉ vào chỗ trống ⇒ box **không bao giờ mở được**.

**LinkedContainer**

- Nối **hai box nằm gần nhau**. Active thì active cả hai; chọn một box thì **cả hai cùng xuống băng
  chuyền**.
- **Dễ**: nếu đúng màu và số lượng pixel bên dưới đang cần thì khay rút cạn ngay.
- **Khó**: cố tình để hai box **không phải màu có thể ăn được luôn** ở phía dưới ⇒ **băng chuyền ở dưới
  full**. Dùng cẩn thận.

Yêu cầu chung: **thêm phần chọn trước khi auto gen box** để quyết định level đấy có obs này hay không —
tức là hai obs này là **tuỳ chọn của từng level**, không phải hệ quả của độ khó.

---

## 2. File đã thay đổi

| File | Nội dung |
| --- | --- |
| `src/pixel_level_tool/services/pixel_gameplay.py` | `simulate_groups`, `resolve_link_groups`; `simulate_order` gọi lại `simulate_groups` |
| `src/pixel_level_tool/services/box_autogen.py` | Toàn bộ logic plan + đặt + kiểm chứng arrow/link, stage 6 & 7 |
| `src/pixel_level_tool/ui/dialogs/auto_gen_box_dialog.py` | 2 ô tick + 3 knob mới |
| `tests/test_box_autogen_obstacles.py` | File mới, 33 test |
| `tests/test_auto_gen_box_ui.py` | 4 test cho ô tick & knob mới |
| `README.md` | Mục **Arrow locks**, **Linked containers**, cập nhật rule runtime + pipeline + bảng độ khó |

Chạy test: `.\.venv\Scripts\python.exe -m pytest tests/ -q` → **291 passed**.

---

## 3. API mới

`pixel_gameplay.py`:

```python
simulate_groups(board, groups, rules)      -> bool; mỗi group là các box vào khay CÙNG LÚC
resolve_link_groups(sequence, links)       -> list[list[int]]; gộp cặp link vào một lần bấm
```

`box_autogen.py`:

```python
plan_link_count(surface_boxes, options, profile)  -> số cặp muốn nối
link_candidates(placements, hidden, position, mode, rng) -> [(left, right, gap)], tốt nhất trước
plan_links(board, order, sequence, placements, hidden, count, mode, rules, rng)
                                                  -> (cặp đã chọn, play_groups)
plan_arrow_count(surface_boxes, options, profile) -> số box muốn khoá
arrow_candidates(placements, position, blocked)    -> [(box, direction, key)]
plan_arrow_locks(placements, position, blocked, count, rng) -> {order_index: (direction, key)}
arrow_order_holds(arrows, position)                -> bool, invariant chính của arrow
DIRECTION_STEPS                                    -> dict[Direction, (dx, dy)]
```

`DifficultyProfile` thêm `arrow_ratio`, `linked_pairs`, `linked_mode`.
`AutoGenOptions` thêm `use_arrow_lock`, `arrow_ratio`, `use_linked_container`, `linked_pairs`,
`linked_mode`.
`AutoGenResult` thêm `arrow_locks`, `linked_pairs`, `linked_mode`, `play_groups`, các property
`arrow_count` / `link_count` / `max_link_gap` / `max_arrow_wait` / `play_groups_specs`.
Hằng số: `ARROW_BOX_BUDGET = 3`, `LINK_BOX_BUDGET = 4`, `MAX_SYNC_GAP = 2`, `MIN_STALL_GAP = 3`.

---

## 4. Bảng độ khó

Chỉ áp dụng **khi ô tick được bật**. Mặc định tắt hẳn.

| Difficulty | ArrowLock | Cặp link | Kiểu link |
| --- | --- | --- | --- |
| Easy | 8% | 2 | sync |
| Medium | 15% | 3 | sync |
| Hard | 25% | 3 | stall |
| SuperHard | 33% | 4 | stall |

Sửa ở dict `DIFFICULTY_PROFILES`.

---

## 5. Các quyết định thiết kế & lý do

### Arrow chỉ nhắm **slot kề cạnh**, không phải cả tia

`LevelValidator._has_arrow_blocker_for_cell` quét **cả tia** theo hướng mũi tên, nên chỉ cần có box nào
đó trên tia là validator cho qua. Generator chặt hơn: **bắt buộc slot ngay kề** phải là một box thật
trên mặt lưới.

Lý do: không biết chắc runtime tính "box ở hướng đó" là **box gần nhất** hay **bất kỳ box nào trên
tia**. Nhắm slot kề cạnh thì **hai cách hiểu trùng nhau**, nên đúng trong cả hai trường hợp. Đây cũng
là cách duy nhất tự động thoả yêu cầu "tránh chỉ vào wall": wall là slot trống ⇒ không có placement ⇒
ứng viên bị loại ngay.

Tunnel cũng bị loại làm chìa, dù nó có box: tunnel là hàng đợi, lấy hết vẫn nằm lại như wall, nên
không coi nó là "mở được một box ở hướng đó".

### Arrow là ràng buộc **thứ tự**, không sửa gì trong mô hình khay

Chìa phải được mở **trước** box bị khoá trong thứ tự đã được chứng minh thắng. Nhờ đó `solve_order`,
`plan_queues`, `simulate_*` **không phải sửa một dòng nào** cho arrow — chỉ cần một invariant tĩnh
`arrow_order_holds` so trên thứ tự chơi thật.

Mỗi box chọn hướng có chìa **mở muộn nhất mà vẫn hợp lệ**, để khoá đóng lâu nhất có thể thay vì chỉ vào
box bị dọn trong vài lượt đầu.

### Không cho arrow **xếp chuỗi**

`plan_arrow_locks` giữ hai set `chosen` và `keys`, loại ứng viên nếu chìa của nó cũng đang bị khoá,
hoặc nếu chính nó đã là chìa của một khoá khác. Chuỗi khoá đọc như bug hơn là như độ khó.

Cũng loại box `Hidden` (box không hiện màu mà lại còn khoá thì không đọc được gì) và box đã bị link
(validator cấm `LinkedContainer` nhắm vào box `ArrowLock`).

### Link phải **charge hai ô khay cùng một lúc** — vì thế mới cần `simulate_groups`

`simulate_order` cũ drain trước mỗi lần append, nên nếu chỉ nối thứ tự phẳng thì box thứ hai có thể
"lách" vào ô mà box thứ nhất vừa rút cạn — người chơi **không bao giờ có khoảng nghỉ đó**.
`simulate_groups` kiểm `len(tray) + len(group) > tray_slots` **trước khi** thả cả nhóm. Test
`test_a_group_of_two_needs_two_free_tray_slots_at_once` ghim đúng chỗ khác biệt này:
`simulate_order` thắng với `piece=1`, `simulate_groups` thì không.

`simulate_order` giờ chỉ là `simulate_groups` với mọi group cỡ 1, nên không có hai đường code song song.

### Link chỉ **kéo partner lên trước**, không bao giờ đẩy lùi

`resolve_link_groups` gộp cặp tại **lần xuất hiện sớm nhất** của một trong hai nửa. Nhờ tính chất
"chỉ kéo lên trước" này mà mọi ràng buộc thứ tự khác của level vẫn còn đúng sau khi nối: chìa của arrow
có thể được mở sớm hơn (càng tốt), không bao giờ muộn hơn. Đó là lý do **plan link trước, plan arrow
sau**, và `position` của arrow được tính trên `play_groups` cuối cùng.

### Độ khó của link là **khoảng cách trong thứ tự lấy**, và được lọc bằng replay

`gap` = hai nửa cách nhau bao nhiêu lượt. `sync` lấy gap nhỏ nhất (`<= MAX_SYNC_GAP`), `stall` lấy gap
lớn nhất (`>= MIN_STALL_GAP`). Đúng như designer nói: stall nghĩa là partner là màu bên dưới **chưa
cần**, nên nó ngồi chiếm ô khay ⇒ băng chuyền full.

Không cố chứng minh trước cặp nào an toàn — **thử replay từng cặp một, cặp nào làm tràn khay thì bỏ**,
và report nói rõ bỏ mấy cặp. Nhờ vậy xin 4 cặp trên một bức ảnh chật thì nhận được 2 cặp chơi được,
chứ không phải một level không giải được.

### Hai obs là **tuỳ chọn của level**, không phải của độ khó

`use_arrow_lock` / `use_linked_container` mặc định `False`, và `plan_*_count` trả 0 ngay nếu chưa bật —
kể cả khi `arrow_ratio` / `linked_pairs` đã được set. Có test ghim đúng điều này
(`test_neither_obstacle_appears_unless_it_is_asked_for`), vì đây là yêu cầu trực tiếp của designer.

Trong dialog, knob của obs nào **bị disable** khi ô tick của obs đó chưa bật, để không ai tưởng mình đã
bật cơ chế chỉ vì đã sửa con số.

---

## 6. Điểm còn mở / TODO

1. **Chưa xác nhận runtime tính "box ở hướng mũi tên" thế nào.** Đang nhắm slot kề cạnh nên đúng cả
   hai cách hiểu. Nếu designer xác nhận là **cả tia** thì có thể nới ra để có thêm ứng viên trên lưới
   nhiều wall — hiện SuperHard hay chỉ khoá được ~60% số box nó muốn.

2. **`sync` gap luôn bằng 1 trên lưới xếp đúng thứ tự.** Hai slot kề nhau ở layout `ordered` gần như
   luôn là hai bước liền nhau, nên `MAX_SYNC_GAP = 2` gần như không bao giờ chạm tới. Không sai, chỉ là
   knob đó hiện chưa có việc gì làm.

3. **Link chưa xét màu.** `stall` chỉ dựa vào gap, chưa bắt buộc hai nửa **khác màu**. Gap lớn thường
   đã kéo theo khác màu, nhưng chưa ghim.

4. **Arrow chưa tương tác với wall/pinch.** Một box vừa bị hai wall kẹp vừa bị arrow khoá là hai lớp
   chặn cộng dồn — có thể quá tay, chưa thử đo.

5. **Chưa có link nào nối vào tunnel.** Chỉ nối box trên mặt lưới. Level 44 hand-made cũng vậy, nên
   chưa cần, nhưng nếu designer muốn thì phải mở rộng cả `resolve_link_groups`.
