# Auto Gen Box — cơ chế Tunnel

> Ghi chép phiên làm việc **2026-07-31**. Mục đích: lần sau mở lại là tiếp tục sửa được ngay,
> không phải đọc lại toàn bộ code.

---

## 1. Bối cảnh & yêu cầu

Level 20 là một level hand-made có `Tunnel`. Rule tunnel do designer xác nhận:

- Tunnel là **hàng đợi** chứa box, box được lấy ra **lần lượt** — chỉ lấy được box ở đầu hàng.
- Có tunnel thì dù pixel grid nhiều pixel vượt quá giới hạn lưới box **8x8 slot** vẫn đẩy được
  phần dư vào tunnel.
- Lấy hết box trong tunnel thì **tunnel không biến mất**, vẫn nằm đó như một **wall chặn đường**.

Yêu cầu: auto gen box phải biết sinh cả tunnel, và độ khó của tunnel **chia theo mức như các
phần khác**, theo nguyên tắc:

- **Mức dễ**: box được lấy ra khỏi tunnel **vừa đúng lúc** bên pixel cần màu đó → tunnel không
  gây khó chịu.
- **Mức khó**: lấy mãi không tới màu cần, vì màu cần **bị giấu ở phía sau** → tạo cảm giác phải
  đào, phải lôi ra.

Quan trọng: **khó chịu nhưng không được bất công** — màn vẫn phải giải được với `piece` đã chọn.

---

## 2. File đã thay đổi

| File | Nội dung |
| --- | --- |
| `src/pixel_level_tool/services/pixel_gameplay.py` | Thêm mô hình tunnel vào phần giả lập |
| `src/pixel_level_tool/services/box_autogen.py` | Toàn bộ logic sinh + xếp + chôn + kiểm chứng tunnel |
| `src/pixel_level_tool/ui/dialogs/auto_gen_box_dialog.py` | 3 tuỳ chọn tunnel mới |
| `tests/test_box_autogen.py` | ~20 test mới cho tunnel |
| `tests/test_auto_gen_box_ui.py` | Test cho các ô chọn tunnel trong dialog |
| `README.md` | Mục **Tunnels**, cập nhật pipeline + bảng độ khó |

Chạy test: `.\.venv\Scripts\python.exe -m pytest tests/ -q` → **220 passed**.

---

## 3. Pipeline hiện tại (6 stage)

Docstring đầu file `box_autogen.py` là bản mô tả chuẩn. Tóm lại:

1. **Balance** — mỗi box chứa đúng 9 ball, nên mọi màu phải có số pixel chia hết 9; pixel dư bị xoá
   (từ dưới lên, ưu tiên cột ngoài).
2. **Walkthrough** — histogram pixel quyết định luôn tập box, chỉ còn **thứ tự pick** là tự do;
   `solve_order` tìm thứ tự thắng được ở `piece` mục tiêu.
3. **Layout** — box lấp vào lưới slot 3x3 nhỏ nhất đủ chứa. Tràn thì đổ vào tunnel; hoặc bật
   `tunnel_mode="mechanic"` để có tunnel dù không tràn.
4. **Queue** ← *mới* — mỗi tunnel nhận một **khối liền mạch** của walkthrough, rồi bị **chôn** theo
   độ khó.
5. **Hide** — một tỷ lệ box mang effect `Hidden`, ưu tiên màu hiếm, không bao giờ ở hàng trước.
6. **Certify** — chạy lại màn **hai lần**: theo thứ tự walkthrough lý tưởng, **và** theo thứ tự mà
   tunnel bắt buộc. Rồi so histogram và đo độ khó.

---

## 4. API mới

### `pixel_gameplay.py`

```python
@dataclass
class TunnelRelease:
    sequence: list[int]   # index walkthrough, theo đúng thứ tự người chơi thực sự pop
    digs: list[int]       # mỗi box tunnel cần dùng: phải lôi mấy box rác ra trước nó
    # properties: max_dig, total_dig, mean_dig

def resolve_pick_sequence(box_count: int, tunnel_queues: list[list[int]]) -> TunnelRelease
```

`resolve_pick_sequence` là trái tim của cơ chế: walkthrough nói **cần box nào tiếp**, tunnel nói
**khi nào lấy được**. Cần một box nằm thứ 3 trong tunnel ⇒ phải pop 2 box trước nó, và 2 box đó vào
khay **sớm** thay vì vào ở bước của chính chúng. Box đã bị lôi ra trong lần đào trước thì lúc đến
lượt nó chỉ bị bỏ qua, **không tính dig thêm** (nên `digs` chỉ có một entry cho mỗi lần thật sự
phải đào).

### `box_autogen.py`

```python
plan_tunnels(box_count, capacity, options, profile) -> (số_tunnel, số_box_bị_nhét_vào)
tunnel_blocks(box_count, per_tunnel)  -> list các khối index liền mạch, rải đều walkthrough
bury_queue(block, window)             -> hàng đợi đã bị chôn
plan_queues(board, order, blocks, window, rules) -> (queues, windows, TunnelRelease)
_tunnel_slots(slots, count)           -> chọn slot đặt tunnel
```

`AutoGenOptions` thêm: `tunnel_mode` (`"overflow"` | `"mechanic"`), `tunnel_depth` (0 = auto),
`dig_window` (None = auto).

`AutoGenResult` thêm: `dig_windows: list[int]`, `release: TunnelRelease`,
`tunnel_queues: list[list[int]]`, property `dig_window` (= max), `play_order` (thứ tự pick thật),
`surface_hidden_ratio`.

`DifficultyProfile` thêm: `tunnels`, `tunnel_depth`, `dig_window`.

---

## 5. Bảng độ khó

| Difficulty | Hidden | Layout | Tunnel | Độ đào |
| --- | --- | --- | --- | --- |
| Easy | 0% | đúng thứ tự giải | 1 × 3 box | **0** — nhả đúng lúc cần |
| Medium | 15% | đúng thứ tự giải | 1 × 4 box | 1 box chắn |
| Hard | 40% | box cần trong 4 box tính từ hàng trước | 2 × 4 box | 2 box chắn |
| SuperHard | 60% | box cần ở bất kỳ đâu | 2 × 5 box | 3 box chắn |

Sửa ở dict `DIFFICULTY_PROFILES` trong `box_autogen.py`.

Kết quả đo thực tế trên level 10 (`tunnel_mode="mechanic"`): `max_dig` = 0 / 1 / 2 / 3 theo 4 mức,
Hidden khớp đúng target 0% / 15% / 41% / 60%.

---

## 6. Các quyết định thiết kế & lý do

Đây là phần quan trọng nhất nếu sau này muốn sửa — đừng phá mấy chỗ này mà không đọc lý do.

### Chôn box bằng **đảo ngược**, không phải xáo trộn ngẫu nhiên

`bury_queue` đảo ngược từng cửa sổ `window` box, nên box cần sớm nhất bị đẩy xuống **cuối** cửa sổ.
Lý do: đảo ngược cho độ đào **đúng bằng `window - 1`** — một con số xác định, nên kiểm tra được với
số slot khay. Xáo trộn ngẫu nhiên thì độ đào không đoán được và không kiểm chứng được.

### Mỗi tunnel một **khối liền mạch** của walkthrough

Đây là thứ giữ cho việc đào **công bằng**: mấy box bị đào ra dù sao cũng cần dùng trong vài bước
tới, nên khay chỉ bị ép trong một lát, chứ không phải giữ box chết suốt màn.

### Nới độ đào **từng tunnel một**, không phải toàn cục

`plan_queues` bắt đầu ở `window = 1` (luôn thắng, vì lúc đó thứ tự pick **chính là** walkthrough đã
được kiểm chứng), rồi nới từng tunnel, chỉ giữ mức nới nào mà màn vẫn thắng.

Ban đầu mình làm toàn cục (thu hẹp cả loạt) → Hard trên level 10 bị tụt hết về window 1 chỉ vì
**một** tunnel rơi vào đoạn khay đang chật. Làm từng tunnel thì Hard đạt `3/1`, SuperHard đạt `4/3`.

Vì `window = 1` luôn thắng nên hàm này **không thể fail** — luôn có đường lùi an toàn.

### Tunnel **trả giá hai lần**

Tunnel vừa chứa box, vừa chiếm một slot **vĩnh viễn** làm tường (hết box vẫn ở đó). Nên một ảnh
tràn lưới `N` slot cần chỗ cho `số_box - (N - số_tunnel)` box, **không phải** `số_box - N`.

Code cũ dùng heuristic `ceil(overflow / 16)` tính thiếu đúng chỗ này.

### Đặt tunnel ở **hàng sau, cột ngoài cùng trước**

Giống level 20 (2 tunnel ở hai biên). Tường thì đặt ở biên đỡ cản nhất, và cột ngoài giữ cho phần
giữa lưới dễ đọc. Lưới hẹp thì đi tiếp sang hàng trước đó, chứ không hết slot.

### `Hidden` không bao giờ dùng cho box trong tunnel

Tunnel bản thân đã che hết mọi thứ phía sau đầu hàng đợi rồi. Nên `Hidden` chỉ tiêu trên box mặt
ngoài, và report tính % theo **số box mặt ngoài** (`surface_hidden_ratio`) — nếu chia cho tổng số
box thì Hard hiện 30% trong khi target 40%, gây hiểu nhầm là bug.

### `direction` của tunnel là **hướng nhả box**, luôn chỉ vào một box thật

*(bổ sung 2026-08-05 — trước đó luôn là `Direction.Up`, xem mục 9.2 cũ)*

`tunnel_directions(tunnel_slots, box_slots, wall_slots, cols, rows)` chọn hướng cho từng tunnel.
Slot nằm **trước miệng tunnel** quyết định hàng đợi có lấy được hay không, nên xếp hạng theo 3 tier:

| Tier | Slot phía trước | Lý do |
| --- | --- | --- |
| 0 ✅ | có **box thật** | box sẽ được lấy đi ⇒ miệng tunnel chắc chắn thông ra |
| 1 | trong lưới nhưng trống | ít nhất còn hướng vào trong lưới |
| 2 ❌ | **wall** hoặc **tunnel khác** | cả hai đều vĩnh viễn ⇒ miệng bị bịt suốt màn |
| 3 ❌ | **ra ngoài lưới** (góc lưới có **2** cạnh như vậy) | nhả box vào chỗ không có gì |

Cùng tier thì theo `TUNNEL_FACING_ORDER = (Down, Left, Right, Up)` — `Down` trước vì tunnel nằm ở
hàng sau, quay về **hàng trước** là quay về phần lưới người chơi rút cạn đầu tiên (giống level
hand-made: tunnel ở biên đều nhìn vào trong).

Lưu ý `DIRECTION_STEPS`: `gridY` tăng theo chiều **xa hàng trước**, nên `Up = +1`, `Down = -1`.
Dict này đã được chuyển lên khối constant đầu file vì giờ cả ArrowLock và tunnel đều dùng.

Hướng được tính **cuối cùng trong `_layout`**, sau khi đã biết slot nào là wall và slot nào thật sự
có box — tính sớm hơn thì chưa đủ dữ liệu.

Không có hướng nào đạt tier 0 (lưới quá nhỏ / quá nhiều wall) thì **không raise**: layout đã được
`layout_is_open` chứng minh là chơi được rồi, nên chỉ giữ hướng tốt nhất còn lại và ghi **warning**
`"Không tìm được hướng nhả box hợp lệ cho tunnel ..."`.

`AutoGenResult.tunnel_mouths: list[(slot, Direction)]` (chỉ các tunnel thật sự có box) và report có
dòng `hướng nhả box (slot → hướng)`.

Đo thực tế trên level 10 (`tunnel_mode="mechanic"`): Easy/Medium/Hard đều `Down`; SuperHard thì
tunnel `(0, 6)` chuyển sang `Right` vì `(0, 5)` là wall — đúng ý đồ.

### Tunnel hiện màu của **box đầu hàng đợi**

Là box duy nhất nó đang chào. Khớp với level 20 (tunnel White, storedCell đầu là White).

---

## 7. Bug đã bắt được

Test fuzz (chạy trên nhiều ảnh random × 4 độ khó) bắt được một bug thật lúc đang viết:

> Lưới hẹp ⇒ số slot biên ở hàng sau **ít hơn** số tunnel ⇒ `zip(tunnel_slots, queues)` âm thầm
> làm mất cả một hàng đợi box ⇒ `AutoGenError: some generated boxes were dropped during layout`.

Sửa: `_tunnel_slots` đi tiếp sang các hàng trước đó thay vì chỉ lấy hàng cuối; và chỗ `zip` giờ dùng
`strict=True` để lỗi kiểu này **không thể im lặng** nữa.

---

## 8. Test đã có

Trong `tests/test_box_autogen.py`, mục `# Tunnels`:

- `plan_tunnels`: tunnel trả giá hai lần; overflow mode không tạo tunnel khi ảnh vừa; mechanic mode
  tạo đúng số tunnel của độ khó.
- `tunnel_blocks`: liền mạch, không giao nhau, rải đều, không chiếm bước 0.
- `bury_queue`: window 1 = identity; window 3 đảo đúng; chôn chỉ đổi thứ tự.
- `resolve_pick_sequence`: box bị chôn buộc phải đào; hàng đợi không chôn = thứ tự walkthrough;
  một box không được nằm ở 2 tunnel.
- Mỗi độ khó: level valid + đủ box + `play_order` thắng được với `piece`.
- Easy: `play_order == solution.order` (tunnel không cản đường).
- Độ đào tăng dần theo độ khó, Easy = 0.
- Tunnel hiện màu đầu hàng đợi; nằm ở biên hàng sau; không chồng lấn box nào.
- Độ đào bị thu hẹp khi `piece` chật (kèm warning).
- Overflow tunnel cũng bị chôn theo độ khó.
- Override `max_tunnels` / `tunnel_depth` / `dig_window`; option sai bị reject.
- **Fuzz**: 5 seed × 4 độ khó trên ảnh random 12x12 — `play_order` luôn thắng, invariant luôn đúng.

---

## 9. Điểm còn mở / TODO cho lần sau

1. **Mặc định vẫn là `tunnel_mode="overflow"`** (chỉ tạo tunnel khi tràn), để hành vi cũ và test
   regression của level 10 không đổi. Muốn Hard/SuperHard **luôn** có tunnel thì sửa mặc định của
   `AutoGenOptions.tunnel_mode` hoặc cho `_DIFFICULTY` quyết định — **1 dòng**, nhưng sẽ phải sửa
   `test_regenerating_level_10_reproduces_its_structure` (đang assert `tunnel_count == 0`).

2. ~~**`direction` của tunnel sinh ra luôn là `Up`.**~~ **Đã làm 2026-08-05**: `direction` giờ là
   hướng nhả box, luôn chỉ vào slot có box thật, không bao giờ vào wall / tunnel khác / ra ngoài
   lưới. Xem mục 6. Còn mở: nếu runtime nhả box **ra đúng ô đó** (chứ chỉ là hướng gợi ý) thì cần
   thêm rule "ô đó phải trống ở thời điểm nhả" — hiện chỉ đảm bảo ô đó là box sẽ được lấy đi.

3. **Hard trên level 10 có tunnel thứ 2 bị kẹt ở window 1** vì `piece=5` chật ở đoạn đó. Muốn đào
   sâu hơn thì nâng `piece` hoặc rút ngắn tunnel. Report đã ghi rõ warning này.

4. **Chưa thử trên file level 20 thật** — `level/` trong repo chỉ có `1.json`, và mình không tự
   chép tay 306 số colorIds vì chép sai thì kiểm chứng thành vô nghĩa. Thay vào đó dùng fuzz test
   trên ảnh random (bằng chứng mạnh hơn một grid chép tay). **Nếu bỏ được file 20.json vào `level/`
   thì nên chạy lại một lần cho chắc.**

5. **Hướng mở rộng chưa làm**: đặt `Hidden` lên `storedCells` trong tunnel (hiện để `None`) — cộng
   dồn hai cơ chế che thông tin. Chưa làm vì yêu cầu ban đầu là "giấu bằng vị trí trong hàng đợi",
   không phải bằng effect.

---

## 10. Miệng tunnel — bổ sung 2026-09-08

Mục 9.2 để mở câu hỏi *"nếu runtime nhả box ra đúng ô đó thì cần thêm rule ô đó phải trống"*.
Câu trả lời là **có**, và nó gây ra hai bug thật trên level đã ship.

### 10.1 Một slot nhả, một tunnel

Slot trước miệng tunnel chứa **một box tại một thời điểm**: box trong đó bị ăn ⇒ tunnel phía sau
đẩy box tiếp theo vào ⇒ box đó lại phải được ăn thì mới có box tiếp. Nên **cả hàng đợi đi qua đúng
một ô vuông đó**.

Hai tunnel cùng chỉ vào một slot = hai hàng đợi xếp hàng trước một cái cửa, và file level **không
nói ai đi trước**. Level 25 sinh ra đúng thế: tunnel `(0, 0)→Up` và tunnel `(0, 2)→Down` đều nhả
vào slot `(0, 1)`, 8 box chung một cửa; tương tự ở `(7, 1)`.

Nguyên nhân: `tunnels_can_release` chỉ hỏi *"mỗi tunnel còn **một** hàng xóm không phải tunnel
không?"* — hai tunnel đều trả lời có, và đó **cùng là một hàng xóm**.

Sửa ở 3 chỗ:

| Hàm | Thay đổi |
| --- | --- |
| `distinct_doors` *(mới)* | ghép cặp tunnel → cửa riêng (augmenting path). Nhỏ xíu: ≤ 4 cửa/tunnel |
| `tunnels_can_release` | dùng `distinct_doors` thay cho `any(...)` ⇒ lúc **đặt slot** đã tránh |
| `tunnel_directions` | chọn hướng **tuần tự**, slot đã có tunnel khác nhắm vào bị tụt tier; tunnel **ít cửa nhất chọn trước** (tunnel góc kẹt giữ lấy cửa duy nhất của nó) |

`shared_tunnel_mouths` là fault cuối cùng — nhưng **chỉ khi lưới còn cách xếp khác**
(`distinct_doors` tìm được ghép cặp). Ảnh tràn lưới nặng thì hai hàng tunnel kẹp một hàng box là
tình huống *không có* cách nào tốt hơn, từ chối level ở đó không sửa được gì.

### 10.2 Không khoá gì lên box trước miệng tunnel

Box đứng trước miệng phải rời đi thì tunnel mới nhúc nhích. Đặt `Frozen` / `LargeBlock` /
`ArrowLock` lên đúng box đó = khoá **cả hàng đợi**, và `resolve_pick_sequence` pop theo index nên
**không nhìn thấy gì cả** — replay vẫn báo thắng, runtime thì kẹt.

Đo trên `level_gen/`: **39/89 file** đang dính, gồm level 10 (`tunnel 301 → box 309 ArrowLock`) và
level 83 (`mouth nằm dưới LargeBlock count=355`).

Sửa: `build_obstacle_layer` tính `mouths` **sớm** (ngay sau `plan_queues`, thay vì ở cuối), lấy
`doorways = mouth_boxes(...)` rồi truyền vào cả 3 planner làm danh sách cấm:

- `plan_arrow_locks(..., hidden | linked_indices | set(doorways), ...)`
- `plan_slabs(..., banned=set(doorways), ...)`
- `plan_frozen(..., linked_indices | slab_covered | set(doorways), ...)`

`gated_tunnel_mouths` kiểm lại layout đã xong, phòng khi vẫn lọt. **`Hidden` không nằm trong danh
sách cấm**: box ẩn vẫn tap được bình thường, chỉ là không biết màu.

### 10.3 Còn mở

Box trước miệng tunnel phải được tap **trước** khi hàng đợi cần ra — hiện chưa mô hình hoá, chỉ
đảm bảo nó không bị khoá. `tunnel_blocks` rải khối theo walkthrough và không bao giờ bắt đầu ở
bước 0, nên thực tế box mặt ngoài luôn có đường tap trước, nhưng đó là *quan sát* chứ chưa phải
*chứng minh*.
