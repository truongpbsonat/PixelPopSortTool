from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from pixel_level_tool.domain.enums import LevelDifficulty
from pixel_level_tool.services.box_autogen import (
    DEFAULT_PIECE,
    DIFFICULTY_PROFILES,
    MAX_BOX_SLOTS,
    LOCK_BUDGET,
    OBSTACLE_BUDGET,
    OBSTACLE_KIND_LABELS,
    SLOT,
    AutoGenOptions,
    format_scan,
)
from pixel_level_tool.services.picture_scan import (
    PictureScan,
    suggest_difficulty,
)


class AutoGenBoxDialog(QDialog):
    """Difficulty and layout options for the Auto Gen Box action."""

    _ACTIVE_POLICIES = (
        ("Không box nào (giống các file level)", "none"),
        ("Chỉ hàng trước (slot hàng 0)", "row0"),
        ("Mọi box", "all"),
    )
    _TUNNEL_MODES = (
        ("Theo độ khó", "auto"),
        ("Chỉ khi số box vượt giới hạn slot", "overflow"),
        ("Luôn luôn, như một cơ chế", "mechanic"),
    )
    _TUNNEL_PLACEMENTS = (
        ("Theo độ khó", "auto"),
        ("Hàng sau cùng — như các file level", "back"),
        ("Hàng trước — chặn ngay lối vào đầu game", "front"),
        ("Ngẫu nhiên trong lưới — có thể rơi vào giữa", "random"),
    )
    _LINKED_MODES = (
        ("Theo độ khó", "auto"),
        ("Dễ — hai box đều là màu đang cần", "sync"),
        ("Khó — box đi kèm là màu chưa cần", "stall"),
    )
    _LOCK_ROUNDINGS = (
        ("Số lẻ — 19, 33, 99", "odd"),
        ("Bội 5 — 20, 35, 100", "five"),
        ("Bội 10 — 20, 30, 100", "ten"),
        ("Không làm tròn", "none"),
    )
    # Kiểu xếp layout của từng độ khó, dịch từ DifficultyProfile.scramble.
    _SCRAMBLE_LABELS = {
        "ordered": "xếp đúng thứ tự giải",
        "local": "box cần nằm gần hàng trước",
        "global": "box cần nằm bất kỳ đâu",
    }

    def __init__(
        self,
        difficulty: int,
        parent=None,
        options: AutoGenOptions | None = None,
        scan: PictureScan | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Auto Gen Box")
        self.scan = scan
        # Everything except the buttons lives on this page, and the page lives in
        # a scroll area: the form is long and a designer's screen is not, so the
        # window is sized to the screen and scrolls rather than growing past it.
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)
        outer.addWidget(
            QLabel(
                "Dựng toàn bộ lưới box Square_3x3 từ Pixel Grid hiện tại. Mỗi màu cần số"
                " pixel chia hết cho 9 — tool tự thêm pixel vào chỗ trống hoặc đổi màu"
                " cho nhau, chỉ xoá khi hết cách."
            )
        )

        # The scan is read off the picture the moment the dialog opens, because
        # every knob below is a guess until the designer can see what the picture
        # actually costs: how many colours have to wait on the belt at once, and
        # whether the picture can be won at all. It spans both columns because it
        # is the one thing here that describes the *picture* rather than a knob.
        self.scan_label = QLabel(format_scan(scan) if scan is not None else "")
        self.scan_label.setWordWrap(True)
        if scan is not None:
            self.scan_label.setStyleSheet(
                "color: #b00020;"
                if not scan.demand.wins(scan.belt_slots)
                else "color: #444;"
            )
            scan_group = QGroupBox("Quét ảnh")
            scan_layout = QVBoxLayout(scan_group)
            scan_layout.setContentsMargins(8, 4, 8, 6)
            scan_layout.addWidget(self.scan_label)
            outer.addWidget(scan_group)

        self.difficulty = QComboBox()
        for member in LevelDifficulty:
            profile = DIFFICULTY_PROFILES[int(member)]
            scramble = self._SCRAMBLE_LABELS.get(profile.scramble, profile.scramble)
            self.difficulty.addItem(
                f"{int(member)}  {profile.label}"
                f"  ({profile.hidden_ratio:.0%} box ẩn, {scramble},"
                f" độ chôn {profile.dig_window}"
                + (f", {profile.walls} wall" if profile.walls else "")
                + ")",
                int(member),
            )
        index = self.difficulty.findData(difficulty)
        self.difficulty.setCurrentIndex(index if index != -1 else 0)

        self.auto_difficulty = QCheckBox("Lấy độ khó từ ảnh")
        self.auto_difficulty.setToolTip(
            "Đọc độ khó từ chính bức ảnh thay vì từ ô bên trên:\n"
            "  dưới 4 màu = Easy, 4-8 màu = Medium, 9-12 màu = Hard, trên 12 = SuperHard.\n"
            "Ảnh vụn (mỗi màu bị cắt thành nhiều mảnh nhỏ theo thứ tự ăn) được nâng thêm\n"
            "một nấc, vì nó bắt người chơi giữ nhiều màu trên băng cùng lúc."
        )
        self.auto_difficulty.toggled.connect(self._update_enabled)
        if scan is not None:
            self.auto_difficulty.toggled.connect(self._apply_scanned_difficulty)
        self.difficulty.setToolTip(
            "Easy hiện mọi box và xếp chúng theo đúng thứ tự giải.\n"
            "Medium ẩn một vài box. Hard ẩn ~40% và giữ box cần tiếp theo gần hàng trước.\n"
            "SuperHard ẩn ~60% và đặt box cần tiếp theo ở bất kỳ đâu trên lưới.\n"
            "Độ chôn cũng cùng một nấc chỉnh đó cho tunnel: Easy nhả box ra đúng lúc pixel grid\n"
            "cần, còn SuperHard chôn nó sau ba box khác.\n"
            "Riêng Hard và SuperHard còn chừa sẵn vài slot làm wall để kẹp box lại.\n"
            "Độ khó cũng quyết định level này dùng bao nhiêu LOẠI obstacle: Easy tối đa 2,\n"
            "Medium 3-4, Hard và SuperHard 4-6 trong 5 loại — xem dòng đầu cột Obstacle."
        )

        self.slot_cols = QSpinBox()
        self.slot_cols.setRange(1, MAX_BOX_SLOTS)
        self.slot_cols.setValue(MAX_BOX_SLOTS)
        self.slot_rows = QSpinBox()
        self.slot_rows.setRange(1, MAX_BOX_SLOTS)
        self.slot_rows.setValue(MAX_BOX_SLOTS)
        for spin in (self.slot_cols, self.slot_rows):
            spin.setToolTip(
                f"Giới hạn trên tính theo slot box 3x3. {MAX_BOX_SLOTS}x{MAX_BOX_SLOTS} slot nghĩa "
                f"là gridCols/gridRows tối đa {MAX_BOX_SLOTS * SLOT} và "
                f"{MAX_BOX_SLOTS * MAX_BOX_SLOTS * 9} ball; dư ra bao nhiêu sẽ vào tunnel."
            )
            spin.valueChanged.connect(self._update_capacity)

        self.capacity_label = QLabel()

        # The obstacle budget is the one rule in this column that applies to every
        # row below it, so it is stated once at the top and re-read whenever the
        # tier changes - a designer switching Easy to Hard should see the ceiling
        # move before they start typing counts underneath it.
        self.obstacle_budget_label = QLabel()
        self.obstacle_budget_label.setWordWrap(True)
        self.obstacle_budget_label.setStyleSheet("color: #444;")

        self.ease_obstacles = QSpinBox()
        self.ease_obstacles.setRange(0, 3)
        self.ease_obstacles.setValue(0)
        self.ease_obstacles.setSuffix(" nấc")
        self.ease_obstacles.setSpecialValueText("Đúng mức")
        self.ease_obstacles.setToolTip(
            "Dựng obstacle ở dạng của mức thấp hơn, bao nhiêu nấc thì tuỳ ô này.\n"
            "1 nấc: obstacle của level Hard được dựng theo kiểu Medium — link rút cạn ngay thay\n"
            "vì ngồi chiếm khay, mũi tên chỉ vào box vừa mở, chôn nông hơn, ít wall hơn.\n"
            "Level vẫn là mức Hard: difficulty và theme không đổi, số loại obstacle không đổi.\n"
            "Khác với ô tự hạ bên dưới: ô này là bạn quyết, ô kia chỉ hạ khi băng không trả nổi."
        )

        self.obstacle_relief = QCheckBox("Tự hạ độ khó obstacle khi tranh đã khó")
        self.obstacle_relief.setChecked(True)
        self.obstacle_relief.setToolTip(
            "Tranh khó và obstacle khó là hai cái khó cộng vào nhau ở cùng một chỗ: băng chuyền.\n"
            "Bật ô này thì phần băng còn dư sau lời giải được đo ra, và obstacle chỉ chạy ở dạng\n"
            "của mức nào mà chỗ dư đó trả được — Hard có thể tụt xuống Medium hoặc Easy.\n"
            "Vẫn giữ đủ số loại obstacle của mức, chỉ nhẹ tay hơn: link rút cạn ngay thay vì\n"
            "ngồi chiếm khay, mũi tên chỉ vào box vừa mở, chôn box nông hơn, ít wall hơn.\n"
            "Tắt thì mỗi mức luôn dùng đúng dạng của nó, kể cả khi băng không còn chỗ."
        )

        self.hidden_ratio = QSpinBox()
        self.hidden_ratio.setRange(-1, 100)
        self.hidden_ratio.setValue(-1)
        self.hidden_ratio.setSpecialValueText("Auto")
        self.hidden_ratio.setSuffix(" %")
        self.hidden_ratio.setToolTip(
            "Tỷ lệ box mang effect Hidden. Auto lấy theo giá trị của độ khó.\n"
            "Việc ẩn được ưu tiên tiêu cho màu hiếm trước, vì ẩn một trong cả tá box giống nhau\n"
            "thì chẳng giấu được gì. Hàng slot trước không bao giờ bị ẩn."
        )

        self.hidden_boxes = QSpinBox()
        self.hidden_boxes.setRange(-1, MAX_BOX_SLOTS * MAX_BOX_SLOTS)
        self.hidden_boxes.setValue(-1)
        self.hidden_boxes.setSpecialValueText("Auto")
        self.hidden_boxes.setToolTip(
            "Số box ẩn tính bằng con số cụ thể, thay vì theo tỷ lệ. Đặt số ở đây thì ô tỷ lệ %\n"
            "bên trên bị vô hiệu hoá — số cụ thể luôn thắng.\n"
            "Xin nhiều hơn số box nằm ngoài hàng trước thì chỉ ẩn được chừng đó, và report nói rõ."
        )

        self.belt_slots = QSpinBox()
        self.belt_slots.setRange(0, 90)
        self.belt_slots.setSingleStep(9)
        self.belt_slots.setSpecialValueText("Auto")
        self.belt_slots.setToolTip(
            "Sức chứa băng truyền, tính bằng BÓNG. Auto = piece của level x 9\n"
            f"(piece {DEFAULT_PIECE} -> {DEFAULT_PIECE * 9} bóng, giống các file level).\n"
            "Mỗi lần tap đổ nguyên một box 9 bóng, nên chỉ tap được khi còn ít nhất 9 ô trống.\n"
            "Thua = không tap được box nào mà băng cũng không rót được bóng nào xuống tranh.\n"
            "Đây là ngưỡng để kiểm chứng việc chôn box trong tunnel và nối link: những box bị "
            "đào ra sớm phải nằm trên băng, và tổng không được vượt con số này."
        )

        self.active_policy = QComboBox()
        for label, value in self._ACTIVE_POLICIES:
            self.active_policy.addItem(label, value)
        self.active_policy.setToolTip(
            "Những box nào được ghi với isActive = true. Các file level không dùng box nào, và "
            "box Hidden luôn được ghi inactive vì validator bắt buộc như vậy."
        )

        self.tunnel_count = QSpinBox()
        self.tunnel_count.setRange(-1, 8)
        self.tunnel_count.setValue(-1)
        self.tunnel_count.setSpecialValueText("Auto")
        self.tunnel_count.setToolTip(
            "Số tunnel muốn dựng, tính bằng con số cụ thể. Đặt số ở đây thì tunnel được cắm đủ\n"
            "chừng đó dù bức ảnh có vừa lưới hay không, và ô 'Số tunnel tối đa' bị vô hiệu hoá.\n"
            "Đây là mức sàn chứ không phải trần: ảnh tràn slot vẫn được thêm tunnel để chứa box,\n"
            "và report nói rõ khi số thực tế khác số đã xin."
        )

        self.max_tunnels = QSpinBox()
        self.max_tunnels.setRange(0, 32)
        self.max_tunnels.setValue(0)
        self.max_tunnels.setSpecialValueText("Auto")
        self.max_tunnels.setToolTip(
            "Trần số tunnel. Auto = đo từ bức tranh, giống các obstacle còn lại:\n"
            "1 tunnel cho mỗi 8 box, và không quá 1/3 số slot của lưới.\n"
            "Ảnh tràn slot luôn được cấp thêm tunnel vượt trần này — ảnh càng lớn thì\n"
            "tunnel càng nhiều và càng nông, để lưới không phải nới rộng quá giới hạn slot.\n"
            "Đặt một con số cụ thể nếu muốn khoá trần cho riêng level này."
        )
        self.allow_tunnels = QCheckBox("Cất box tràn vào tunnel")
        self.allow_tunnels.setChecked(True)
        self.allow_tunnels.setToolTip(
            "Chỉ cần khi bức ảnh có nhiều box hơn sức chứa của giới hạn slot. "
            "Nếu tắt, việc sinh box sẽ báo lỗi thay vì tạo tunnel."
        )

        self.tunnel_mode = QComboBox()
        for label, value in self._TUNNEL_MODES:
            self.tunnel_mode.addItem(label, value)
        self.tunnel_mode.setToolTip(
            "Tunnel là một hàng đợi: chỉ lấy được box ở đầu hàng, và tunnel hết box vẫn nằm lại\n"
            "trên lưới như một bức tường.\n"
            "Theo độ khó: tunnel chỉ được cắm khi ngân sách obstacle của mức đó còn chỗ cho nó\n"
            "(Easy 2 loại nên thường không tới lượt tunnel; Hard 4-6 loại thì có).\n"
            "Chỉ khi vượt slot: chỉ dựng tunnel khi ảnh quá lớn so với giới hạn slot.\n"
            "Luôn luôn: cắm đủ số tunnel của độ khó ngay cả khi mọi thứ vừa lưới.\n"
            "Ảnh tràn slot thì tunnel luôn được dựng, dù chọn kiểu nào."
        )

        self.tunnel_placement = QComboBox()
        for label, value in self._TUNNEL_PLACEMENTS:
            self.tunnel_placement.addItem(label, value)
        self.tunnel_placement.setToolTip(
            "Tunnel nằm ở đâu trên lưới. Tunnel là một lỗ vĩnh viễn — hết box vẫn nằm lại như\n"
            "wall — nên càng xa hàng sau thì càng bắt người chơi phải đi vòng nhiều.\n"
            "Hàng sau gần như không tốn gì; hàng trước chặn ngay lối vào từ nước đi đầu tiên;\n"
            "ngẫu nhiên có thể rơi vào giữa lưới, mới lạ nhất nhưng cũng khó đoán nhất.\n"
            "Vị trí nào làm một box không còn đường vào sẽ bị loại, nên level luôn chơi được.\n"
            "Theo độ khó: Easy/Medium hàng sau, Hard hàng trước, SuperHard ngẫu nhiên."
        )

        self.tunnel_depth = QSpinBox()
        self.tunnel_depth.setRange(0, 16)
        self.tunnel_depth.setSpecialValueText("Auto")
        self.tunnel_depth.setToolTip(
            "Số box cất trong mỗi tunnel. Auto lấy theo độ sâu của độ khó, và tự được nâng lên "
            "mỗi khi bức ảnh vượt giới hạn slot."
        )

        self.dig_window = QSpinBox()
        self.dig_window.setRange(0, 8)
        self.dig_window.setSpecialValueText("Auto")
        self.dig_window.setToolTip(
            "Màu mà pixel grid cần tiếp theo bị chôn sâu bao nhiêu trong tunnel.\n"
            "1 là nhả mọi box ra đúng lúc cần, nên tunnel không gây khó chịu.\n"
            "4 nghĩa là người chơi phải lôi ra ba box thừa mới tới được box mình cần.\n"
            "Sẽ tự thu hẹp lại khi đào sâu như vậy sẽ làm tràn khay."
        )
        self.walls = QSpinBox()
        self.walls.setRange(-1, 16)
        self.walls.setValue(-1)
        self.walls.setSpecialValueText("Auto")
        self.walls.setToolTip(
            "Số slot cố ý bỏ trống. Slot trống chính là wall: nó chặn đường vào các box bên\n"
            "cạnh và không bao giờ mở ra, nên hai wall kẹp hai bên một box sẽ ép người chơi\n"
            "đi vòng vào cạnh còn lại. Auto lấy theo độ khó (Easy/Medium 0, Hard 2,\n"
            "SuperHard 4) và bị giới hạn tối đa 1 wall trên mỗi 4 box. Đặt 0 để tắt hẳn.\n"
            "Wall vừa ăn một slot vừa làm level khó hơn hẳn nên dùng dè."
        )

        # Cả năm obstacle giờ được đọc từ level theo cùng một cách, nên hai ô này
        # mặc định để mờ = giao cho độ khó quyết định, đúng như Hidden và Wall vẫn
        # làm. Tích là bắt buộc có, bỏ tích là level này không bao giờ có.
        self.use_arrow_lock = QCheckBox("ArrowLock — để mờ là theo độ khó")
        self.use_arrow_lock.setTristate(True)
        self.use_arrow_lock.setCheckState(Qt.CheckState.PartiallyChecked)
        self.use_arrow_lock.setToolTip(
            "Box mang ArrowLock hiện một mũi tên và chỉ mở được sau khi người chơi đã mở một box\n"
            "nằm ở hướng mũi tên đó. Mũi tên luôn được chỉ vào một box thật nằm sát bên và box đó\n"
            "chắc chắn được mở trước trong lời giải, nên khoá luôn có chìa — không bao giờ chỉ vào\n"
            "wall, vào tunnel hay ra ngoài lưới, vì như vậy box sẽ không bao giờ mở được.\n"
            "Riêng ArrowLock đã khá khó, nên số box bị khoá được giữ ở mức thấp.\n"
            "Ba trạng thái: để mờ = độ khó tự chọn (chỉ dùng khi ngân sách obstacle còn chỗ),\n"
            "tích = level này bắt buộc có, bỏ tích = level này không bao giờ có."
        )
        self.arrow_ratio = QSpinBox()
        self.arrow_ratio.setRange(-1, 100)
        self.arrow_ratio.setValue(-1)
        self.arrow_ratio.setSpecialValueText("Auto")
        self.arrow_ratio.setSuffix(" %")
        self.arrow_ratio.setToolTip(
            "Tỷ lệ box mặt ngoài mang ArrowLock. Auto lấy theo độ khó (Easy 8%, Medium 15%,\n"
            "Hard 25%, SuperHard 33%) và bị giới hạn tối đa 1 box khoá trên mỗi 3 box, để lưới\n"
            "không bao giờ rơi vào cảnh không còn box nào bấm được.\n"
            "Auto còn hạ theo độ vụn của ảnh: ảnh càng vụn thì thứ tự lấy box càng bị ép cứng,\n"
            "nên mỗi ô khoá càng đắt — ảnh vụn 50% chỉ còn một nửa số khoá.\n"
            "Box ẩn và box đã bị link sẽ không nhận ArrowLock."
        )

        self.arrow_boxes = QSpinBox()
        self.arrow_boxes.setRange(-1, MAX_BOX_SLOTS * MAX_BOX_SLOTS)
        self.arrow_boxes.setValue(-1)
        self.arrow_boxes.setSpecialValueText("Auto")
        self.arrow_boxes.setToolTip(
            "Số box mang ArrowLock tính bằng con số cụ thể, thay vì theo tỷ lệ. Đặt số ở đây thì\n"
            "ô tỷ lệ % bên trên bị vô hiệu hoá.\n"
            "Vẫn bị chặn ở mức tối đa 1 box khoá trên mỗi 3 box, và số box thực sự khoá được còn\n"
            "phụ thuộc có tìm ra chìa hợp lệ hay không — report nói rõ khi thiếu."
        )

        self.use_linked_container = QCheckBox("LinkedContainer — để mờ là theo độ khó")
        self.use_linked_container.setTristate(True)
        self.use_linked_container.setCheckState(Qt.CheckState.PartiallyChecked)
        self.use_linked_container.setToolTip(
            "LinkedContainer nối hai box nằm sát nhau: bấm một box thì cả hai cùng xuống băng\n"
            "chuyền, nên một lần bấm tốn hai ô khay cùng lúc.\n"
            "Dễ: cả hai box đều là màu bên dưới đang cần, khay rút cạn ngay.\n"
            "Khó: cố tình nối một box đang cần với một box màu chưa cần, box kia ngồi chiếm ô khay\n"
            "và làm băng chuyền đầy lên — dùng cẩn thận.\n"
            "Mọi cặp đều được chơi thử lại, cặp nào làm tràn khay thì bị bỏ.\n"
            "Kiểu khó còn bị chặn theo chỗ trống thật của băng: mỗi cặp stall đậu một box lên\n"
            "băng, nên số cặp không vượt quá số box băng còn chứa được ở đoạn chật nhất.\n"
            "Ba trạng thái: để mờ = độ khó tự chọn, tích = bắt buộc có, bỏ tích = không có."
        )
        self.linked_pairs = QSpinBox()
        self.linked_pairs.setRange(-1, 16)
        self.linked_pairs.setValue(-1)
        self.linked_pairs.setSpecialValueText("Auto")
        self.linked_pairs.setToolTip(
            "Số cặp box được nối. Auto lấy theo độ khó (Easy 2, Medium 3, Hard 3, SuperHard 4)\n"
            "và bị giới hạn tối đa 1 cặp trên mỗi 4 box."
        )
        self.linked_mode = QComboBox()
        for label, value in self._LINKED_MODES:
            self.linked_mode.addItem(label, value)
        self.linked_mode.setToolTip(
            "Easy/Medium nối hai box mà bên dưới đang cần gần như cùng lúc, nên link gần như miễn "
            "phí.\nHard/SuperHard cố tình nối một box đang cần với một box còn lâu mới cần."
        )

        self.frozen_boxes = QSpinBox()
        self.frozen_boxes.setRange(-1, 32)
        self.frozen_boxes.setValue(-1)
        self.frozen_boxes.setSpecialValueText("Auto")
        self.frozen_boxes.setToolTip(
            "Số box mang khoá Frozen. Auto lấy theo độ khó (Easy 5%, Medium 10%, Hard 15%,\n"
            "SuperHard 20% số box mặt ngoài).\n"
            "\n"
            "Frozen mở theo tiến độ chứ không theo một box khác: nó mở khi bức tranh đã tan đủ\n"
            "số pixel ghi trên box. Con số đó tính ngược từ đường thắng đã chứng minh, nên khoá\n"
            "luôn mở trước lúc đường thắng cần đến box — cái nó lấy đi là quyền tap sớm.\n"
            "\n"
            "Khoá chỉ đặt lên màu còn box khác phục vụ được: nếu màu dưới frontier chỉ còn đúng\n"
            "một box mà box đó bị khoá thì không clear được pixel nào, bộ đếm đứng yên và khoá\n"
            "không bao giờ mở — level chết hẳn chứ không phải khó."
        )
        self.blocks = QSpinBox()
        self.blocks.setRange(-1, 8)
        self.blocks.setValue(-1)
        self.blocks.setSpecialValueText("Auto")
        self.blocks.setToolTip(
            "Số slab LargeBlock. Auto lấy theo độ khó (Easy 0, Medium 2, Hard 2, SuperHard 3).\n"
            "\n"
            "Một slab là Frozen áp cho cả vùng, chung một bộ đếm, VÀ nó che luôn màu của các box\n"
            "bên dưới cho tới lúc vỡ. Số của nó bị chặn bởi box được cần SỚM NHẤT trong vùng, nên\n"
            "slab luôn được đặt vào vùng mà đường thắng lâu mới đụng tới.\n"
            "\n"
            "Kích thước và mốc vỡ đều lấy từ BIÊN ĐO ĐƯỢC của level — số box băng chuyền còn dư ở\n"
            "đoạn chật nhất của tranh:\n"
            "  • dư từ 3 box trở lên → slab 3x3 box, vỡ đúng mốc của tier\n"
            "  • dư ít hơn           → slab 2x2 box, vỡ sớm hơn (thấp nhất 60% mốc tier)\n"
            "Tranh đã chật thì không nên có thêm một phần chín lưới tối om suốt nửa level.\n"
            "\n"
            "Lúc còn đóng, slab được tính như wall: một slab làm kẹt box khác hoặc bịt miệng tunnel\n"
            "sẽ bị loại. Slab cũng không bao giờ đè lên một nửa cặp LinkedContainer — tap nửa này là\n"
            "lấy cả cặp, nên một nửa nằm dưới slab sẽ khoá cứng cả cặp."
        )
        self.lock_margin = QSpinBox()
        self.lock_margin.setRange(0, 90)
        self.lock_margin.setValue(9)
        self.lock_margin.setSuffix(" bóng")
        self.lock_margin.setToolTip(
            "Khoảng an toàn giữa lúc khoá mở và lúc đường thắng cần box đằng sau nó. 9 = một box.\n"
            "\n"
            "Đặt 45 (một băng ở piece 5) nếu runtime thực ra đếm bóng ĐÃ ĐỔ LÊN BĂNG thay vì bóng\n"
            "đã tan khỏi tranh: hai cách đếm chênh nhau tối đa đúng một băng."
        )
        self.lock_rounding = QComboBox()
        for label, value in self._LOCK_ROUNDINGS:
            self.lock_rounding.addItem(label, value)
        self.lock_rounding.setToolTip(
            "Cách viết con số trên khoá. Luôn làm tròn XUỐNG, vì con số bị chặn trên bởi giới hạn\n"
            "an toàn — làm tròn lên là bước qua giới hạn đó."
        )
        self.shuffle_obstacles = QCheckBox("Xóc ngẫu nhiên mix obstacle ở mức Dễ/Vừa")
        self.shuffle_obstacles.setChecked(True)
        self.shuffle_obstacles.setToolTip(
            "Mức Dễ và Vừa chỉ tiêu 1-4 loại obstacle, nên nếu đọc bảng ưu tiên từ trên xuống thì\n"
            "level nào cũng ra đúng mấy loại đầu bảng. Bật cái này để rút ngẫu nhiên trong cả 7\n"
            "loại cho đa dạng — cái giữ cho level dễ vẫn dễ là liều lượng và dạng của obstacle,\n"
            "không phải việc nó là loại nào.\n"
            "\n"
            "Mức Khó/Rất khó không xóc: ở đó thứ tự ưu tiên chính là bản chất của mức — một level\n"
            "Khó thiếu wall và tunnel thì không còn khó nữa.\n"
            "\n"
            "Tắt để mọi mức đều lấy đúng mix chuẩn của bảng."
        )

        # Cùng một seed thì cùng một lưới. Cấu hình đã lưu của level mang theo seed
        # của lần gen đó, nên mở lại và bấm Sinh box sẽ ra đúng lưới cũ; đổi số hoặc
        # về Auto để xóc lại.
        self.seed = QSpinBox()
        self.seed.setRange(-1, 2_147_483_647)
        self.seed.setValue(-1)
        self.seed.setSpecialValueText("Auto")
        self.seed.setToolTip(
            "Số gieo cho mọi lựa chọn ngẫu nhiên: chỗ đặt box, box nào bị ẩn, wall, arrow, link.\n"
            "Cùng một seed trên cùng một bức ảnh luôn cho ra cùng một lưới.\n"
            "Auto tự tính seed từ số level và độ khó. Cấu hình Auto Gen đã lưu của level sẽ điền\n"
            "lại đúng seed của lần gen đó; sửa số này để xóc ra một lưới khác."
        )

        self.apply_theme = QCheckBox("Áp dụng theme Hard / Super Hard")
        self.apply_theme.setChecked(True)

        self.repair_picture = QCheckBox("Sửa tranh cho chơi được")
        self.repair_picture.setChecked(True)
        self.repair_picture.setToolTip(
            "Chỉ chạy khi bức tranh không thắng được trên băng của chính level.\n"
            "Nguyên nhân luôn là màu bị rắc thành đốm lẻ: mỗi tap đổ 9 bóng, một đốm 4 pixel\n"
            "chỉ tiêu 4 bóng, 5 bóng còn lại nằm chờ trên băng tới lúc tranh đòi màu đó lần nữa.\n"
            "Việc sửa là nhập đốm lẻ vào màu bên cạnh, rồi trả lại đúng số pixel đó ngay cạnh\n"
            "mảng lớn của chính màu đấy — nên số pixel từng màu KHÔNG đổi, số box sinh ra y nguyên,\n"
            "chỉ thứ tự tranh đòi màu là đổi. Report liệt kê từng nước đã sửa và ô nào bị đổi."
        )

        self.ease_difficulty = QSpinBox()
        self.ease_difficulty.setRange(0, 3)
        self.ease_difficulty.setValue(0)
        self.ease_difficulty.setSuffix(" nấc")
        self.ease_difficulty.setSpecialValueText("Giữ nguyên")
        self.ease_difficulty.setToolTip(
            "Hạ độ khó của level xuống mấy nấc so với con số ở trên (hoặc so với mức đọc\n"
            "được từ tranh khi bật 'Lấy độ khó từ ảnh').\n"
            "1 nấc: tranh đọc ra Hard thì dựng thành level Medium — difficulty, theme, ngân sách\n"
            "obstacle và mọi liều lượng đều theo Medium. Easy là sàn."
        )

        self.shuffle_attempts = QSpinBox()
        self.shuffle_attempts.setRange(1, 24)
        self.shuffle_attempts.setValue(1)
        self.shuffle_attempts.setSuffix(" lần")
        self.shuffle_attempts.setToolTip(
            "Xóc lại cả lượt gen bấy nhiêu lần trên các seed liên tiếp rồi giữ bản tốt nhất.\n"
            "Thứ tự ưu tiên: thắng được → còn obstacle → nhiều loại obstacle hơn →\n"
            "dạng obstacle cứng hơn → còn nhiều băng dư hơn.\n"
            "Mỗi lần xóc là một level hoàn chỉnh đã kiểm chứng, xóc chỉ chọn giữa chúng.\n"
            "Report nói seed của bản được giữ, điền seed đó và đặt về 1 lần để dựng lại y nguyên."
        )

        # Two columns, split by what the knob decides rather than by widget type.
        # Left is the level itself: how big the grid is, how the boxes are ordered
        # on it, and the queue they come out of. Right is every mechanic laid on
        # top of that. The split matters because the two are tuned at different
        # moments - the grid is settled once per picture, the obstacles are what a
        # designer keeps coming back to.
        board = QFormLayout()
        board.setVerticalSpacing(3)
        board.setContentsMargins(8, 4, 8, 4)
        board.addRow("Độ khó", self.difficulty)
        board.addRow("", self.auto_difficulty)
        board.addRow("Hạ độ khó", self.ease_difficulty)
        board.addRow("Xóc lại", self.shuffle_attempts)
        board.addRow("", self.repair_picture)
        board.addRow("Số slot box tối đa theo chiều ngang", self.slot_cols)
        board.addRow("Số slot box tối đa theo chiều dọc", self.slot_rows)
        board.addRow("", self.capacity_label)
        board.addRow("Băng truyền (số bóng)", self.belt_slots)
        board.addRow("isActive", self.active_policy)
        board.addRow("Seed", self.seed)
        board.addRow("", self.apply_theme)
        board.addRow(self._section("Hàng đợi box (Tunnel)"))
        board.addRow("Tunnel", self.tunnel_mode)
        board.addRow("Vị trí tunnel", self.tunnel_placement)
        board.addRow("Số tunnel", self.tunnel_count)
        board.addRow("Số tunnel tối đa", self.max_tunnels)  # Auto = đo từ tranh
        board.addRow("Số box mỗi tunnel", self.tunnel_depth)
        board.addRow("Độ chôn trong tunnel", self.dig_window)
        board.addRow("", self.allow_tunnels)

        obstacles = QFormLayout()
        obstacles.setVerticalSpacing(3)
        obstacles.setContentsMargins(8, 4, 8, 4)
        obstacles.addRow(self.obstacle_budget_label)
        obstacles.addRow("Dạng obstacle nhẹ đi", self.ease_obstacles)
        obstacles.addRow("", self.obstacle_relief)
        obstacles.addRow(self._section("Hidden — box ẩn màu"))
        obstacles.addRow("Tỷ lệ box ẩn", self.hidden_ratio)
        obstacles.addRow("Số box ẩn", self.hidden_boxes)
        obstacles.addRow(self._section("Wall — slot chặn đường"))
        obstacles.addRow("Số wall", self.walls)
        obstacles.addRow(self._section("ArrowLock — khoá theo thứ tự"))
        obstacles.addRow("", self.use_arrow_lock)
        obstacles.addRow("Tỷ lệ box ArrowLock", self.arrow_ratio)
        obstacles.addRow("Số box ArrowLock", self.arrow_boxes)
        obstacles.addRow(self._section("LinkedContainer — nối 2 box"))
        obstacles.addRow("", self.use_linked_container)
        obstacles.addRow("Số cặp", self.linked_pairs)
        obstacles.addRow("Kiểu", self.linked_mode)
        obstacles.addRow(self._section("Frozen — khoá 1 box theo tiến độ"))
        obstacles.addRow("Số box Frozen", self.frozen_boxes)
        obstacles.addRow(self._section("LargeBlock — khoá cả vùng theo tiến độ"))
        obstacles.addRow("Số slab", self.blocks)
        obstacles.addRow(self._section("Chung cho hai loại khoá"))
        obstacles.addRow("Biên an toàn", self.lock_margin)
        obstacles.addRow("Làm tròn số khoá", self.lock_rounding)
        obstacles.addRow("", self.shuffle_obstacles)

        board_group = QGroupBox("Lưới box, hàng đợi và độ khó")
        board_group.setLayout(board)
        obstacle_group = QGroupBox("Obstacle")
        obstacle_group.setLayout(obstacles)
        # The obstacle column is the shorter of the two, so it is pinned to the
        # top instead of being spread out to match the other one's height.
        obstacle_column = QVBoxLayout()
        obstacle_column.addWidget(obstacle_group)
        obstacle_column.addStretch(1)

        columns = QHBoxLayout()
        columns.setSpacing(8)
        columns.addWidget(board_group, 1, Qt.AlignmentFlag.AlignTop)
        columns.addLayout(obstacle_column, 1)
        outer.addLayout(columns)

        scroll = QScrollArea(self)
        scroll.setWidget(page)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        # Horizontal scrolling would mean a column is cut off, which is worse than
        # a narrower one: the two columns wrap their labels instead.
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Sinh box")
        buttons.button(QDialogButtonBox.Cancel).setText("Huỷ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        # The buttons sit outside the scroll area: "Sinh box" is the one control
        # that must never be the thing the designer has to scroll to find.
        frame = QVBoxLayout(self)
        frame.setContentsMargins(0, 0, 0, 8)
        frame.addWidget(scroll)
        frame.addWidget(buttons)

        self.allow_tunnels.toggled.connect(self._update_enabled)
        # stateChanged, not toggled: a tri-state box passing through the middle
        # state does not always emit toggled, and the middle state is the default.
        for toggle in (self.use_arrow_lock, self.use_linked_container):
            toggle.stateChanged.connect(self._update_enabled)
        for spin in (self.hidden_boxes, self.tunnel_count, self.arrow_boxes):
            spin.valueChanged.connect(self._update_enabled)
        self.difficulty.currentIndexChanged.connect(self._update_budget)
        self.auto_difficulty.toggled.connect(self._update_budget)
        self._update_capacity()
        self._update_budget()
        self._update_enabled()
        # Last, so the saved preset wins over every default above and lands after
        # the toggles that enable the obstacle knobs are wired up.
        if options is not None:
            self.set_options(options)
        self._fit_to_screen(page)

    def _fit_to_screen(self, page: QWidget) -> None:
        """Open at the size the form wants, or the size the screen has - whichever is smaller.

        Qt would otherwise open a dialog as tall as its contents, which for this
        form is taller than a laptop screen: the buttons end up under the taskbar
        and there is no way to reach them. Inside a scroll area the same form is
        merely long.
        """
        screen = self.screen()
        wanted = page.sizeHint()
        if screen is None:  # pragma: no cover - only when there is no display
            self.resize(wanted)
            return
        available = screen.availableGeometry()
        self.resize(
            min(wanted.width() + 24, int(available.width() * 0.95)),
            min(wanted.height() + 56, int(available.height() * 0.9)),
        )

    def _apply_scanned_difficulty(self, on: bool) -> None:
        """Show the tier the scan reads, so the combo never contradicts the label."""
        if on and self.scan is not None and self.scan.painted:
            self._select(self.difficulty, suggest_difficulty(self.scan))

    def _update_enabled(self) -> None:
        self.difficulty.setEnabled(not self.auto_difficulty.isChecked())
        """One place decides what is greyed out, because several knobs gate each other.

        A knob that cannot affect the run is disabled rather than quietly ignored:
        an exact count always beats the share or ceiling beside it, so that
        neighbour goes grey the moment a number is typed.
        """
        self.hidden_ratio.setEnabled(self.hidden_boxes.value() < 0)

        tunnels_on = self.allow_tunnels.isChecked()
        for widget in (
            self.tunnel_mode,
            self.tunnel_placement,
            self.tunnel_count,
            self.tunnel_depth,
            self.dig_window,
        ):
            widget.setEnabled(tunnels_on)
        self.max_tunnels.setEnabled(tunnels_on and self.tunnel_count.value() < 0)

        # Only an explicitly unticked box greys its knobs out: the middle state
        # means the tier may still spend the mechanic, so its dose still matters.
        arrow_on = self.use_arrow_lock.checkState() != Qt.CheckState.Unchecked
        self.arrow_boxes.setEnabled(arrow_on)
        self.arrow_ratio.setEnabled(arrow_on and self.arrow_boxes.value() < 0)

        link_on = self.use_linked_container.checkState() != Qt.CheckState.Unchecked
        for widget in (self.linked_pairs, self.linked_mode):
            widget.setEnabled(link_on)

    def _update_budget(self) -> None:
        """Restate the tier's obstacle ceiling, in the tier's own priority order."""
        difficulty = int(self.difficulty.currentData())
        profile = DIFFICULTY_PROFILES[difficulty]
        low, high = OBSTACLE_BUDGET[difficulty]
        lock_low, lock_high = LOCK_BUDGET[difficulty]
        order = " > ".join(OBSTACLE_KIND_LABELS[kind] for kind in profile.kinds)
        locks = " > ".join(OBSTACLE_KIND_LABELS[kind] for kind in profile.lock_kinds)
        # Two budgets, two sentences. A lock spends no băng and no slot, so it is
        # never the reason a mechanic got dropped, and saying so here is the only
        # place the designer sees why the two counts do not add up.
        pick = "rút ngẫu nhiên" if profile.shuffle_kinds else "theo thứ tự ưu tiên"
        self.obstacle_budget_label.setText(
            f"Mức {profile.label} dùng {low}-{high} loại obstacle trong 5 loại"
            f" ({pick}: {order})."
            f" Riêng khoá theo tiến độ tính ngân sách riêng: {lock_low}-{lock_high}"
            f" trong {locks} — khoá không tốn băng cũng không chiếm slot."
            " Số cụ thể bạn nhập luôn được giữ, kể cả khi vượt ngân sách."
        )

    def _update_capacity(self) -> None:
        cols, rows = self.slot_cols.value(), self.slot_rows.value()
        self.capacity_label.setText(
            f"= lưới box tối đa {cols * SLOT} x {rows * SLOT} ô,"
            f" {cols * rows} box, {cols * rows * 9} ball"
        )

    @staticmethod
    def _section(text: str) -> QLabel:
        """A bold heading inside a column, spanning both of its form fields."""
        label = QLabel(text)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        return label

    @staticmethod
    def _select(combo: QComboBox, value) -> None:
        index = combo.findData(value)
        if index != -1:
            combo.setCurrentIndex(index)

    @staticmethod
    def _percent(ratio: float | None) -> int:
        return -1 if ratio is None else round(ratio * 100)

    @staticmethod
    def _count(value: int | None) -> int:
        """None is Auto, which every one of these spin boxes spells -1."""
        return -1 if value is None else value

    def set_options(self, options: AutoGenOptions) -> None:
        """Fill every widget from a saved preset — the inverse of :meth:`options`.

        A value the widget cannot show (a combo entry that no longer exists) leaves
        that one widget on its default rather than failing the whole load.
        """
        self._select(self.difficulty, options.difficulty)
        self.auto_difficulty.setChecked(options.auto_difficulty)
        self.slot_cols.setValue(options.max_slot_cols)
        self.slot_rows.setValue(options.max_slot_rows)
        self.hidden_ratio.setValue(self._percent(options.hidden_ratio))
        self.hidden_boxes.setValue(self._count(options.hidden_boxes))
        self.belt_slots.setValue(options.belt_slots)
        self._select(self.active_policy, options.active_policy)
        self.allow_tunnels.setChecked(options.allow_tunnels)
        self.max_tunnels.setValue(options.max_tunnels)
        self.tunnel_count.setValue(self._count(options.tunnel_count))
        self._select(self.tunnel_mode, options.tunnel_mode)
        self._select(self.tunnel_placement, options.tunnel_placement)
        self.tunnel_depth.setValue(options.tunnel_depth)
        self.dig_window.setValue(0 if options.dig_window is None else options.dig_window)
        self.walls.setValue(self._count(options.walls))
        self.use_arrow_lock.setCheckState(self._tristate(options.use_arrow_lock))
        self.arrow_ratio.setValue(self._percent(options.arrow_ratio))
        self.arrow_boxes.setValue(self._count(options.arrow_boxes))
        self.use_linked_container.setCheckState(self._tristate(options.use_linked_container))
        self.linked_pairs.setValue(self._count(options.linked_pairs))
        self._select(self.linked_mode, options.linked_mode)
        self.frozen_boxes.setValue(self._count(options.frozen_boxes))
        self.blocks.setValue(self._count(options.blocks))
        self.lock_margin.setValue(max(0, options.lock_margin))
        self._select(self.lock_rounding, options.lock_rounding)
        self.shuffle_obstacles.setChecked(options.shuffle_obstacles)
        self.obstacle_relief.setChecked(options.obstacle_relief)
        self.repair_picture.setChecked(options.repair_picture)
        self.ease_difficulty.setValue(max(0, options.ease_difficulty))
        self.ease_obstacles.setValue(max(0, options.ease_obstacles))
        self.shuffle_attempts.setValue(max(1, options.shuffle_attempts))
        self.apply_theme.setChecked(options.apply_theme)
        self.seed.setValue(self._count(options.seed))
        self._update_enabled()

    @staticmethod
    def _tristate(value: bool | None) -> Qt.CheckState:
        """None is the middle state, which means "the difficulty decides"."""
        if value is None:
            return Qt.CheckState.PartiallyChecked
        return Qt.CheckState.Checked if value else Qt.CheckState.Unchecked

    @staticmethod
    def _from_tristate(box: QCheckBox) -> bool | None:
        state = box.checkState()
        if state == Qt.CheckState.PartiallyChecked:
            return None
        return state == Qt.CheckState.Checked

    @staticmethod
    def _optional(value: int) -> int | None:
        """-1 is the Auto entry of a count spin box, and Auto means "no opinion"."""
        return None if value < 0 else value

    def options(self) -> AutoGenOptions:
        hidden = self.hidden_ratio.value()
        dig = self.dig_window.value()
        arrow = self.arrow_ratio.value()
        return AutoGenOptions(
            use_arrow_lock=self._from_tristate(self.use_arrow_lock),
            arrow_ratio=None if arrow < 0 else arrow / 100.0,
            arrow_boxes=self._optional(self.arrow_boxes.value()),
            use_linked_container=self._from_tristate(self.use_linked_container),
            linked_pairs=self._optional(self.linked_pairs.value()),
            linked_mode=str(self.linked_mode.currentData()),
            frozen_boxes=self._optional(self.frozen_boxes.value()),
            blocks=self._optional(self.blocks.value()),
            lock_margin=self.lock_margin.value(),
            lock_rounding=str(self.lock_rounding.currentData()),
            shuffle_obstacles=self.shuffle_obstacles.isChecked(),
            obstacle_relief=self.obstacle_relief.isChecked(),
            repair_picture=self.repair_picture.isChecked(),
            ease_difficulty=self.ease_difficulty.value(),
            ease_obstacles=self.ease_obstacles.value(),
            shuffle_attempts=self.shuffle_attempts.value(),
            walls=self._optional(self.walls.value()),
            tunnel_mode=str(self.tunnel_mode.currentData()),
            tunnel_placement=str(self.tunnel_placement.currentData()),
            tunnel_count=self._optional(self.tunnel_count.value()),
            tunnel_depth=self.tunnel_depth.value(),
            dig_window=None if dig <= 0 else dig,
            difficulty=int(self.difficulty.currentData()),
            auto_difficulty=self.auto_difficulty.isChecked(),
            max_slot_cols=self.slot_cols.value(),
            max_slot_rows=self.slot_rows.value(),
            hidden_ratio=None if hidden < 0 else hidden / 100.0,
            hidden_boxes=self._optional(self.hidden_boxes.value()),
            belt_slots=self.belt_slots.value(),
            active_policy=str(self.active_policy.currentData()),
            allow_tunnels=self.allow_tunnels.isChecked(),
            max_tunnels=self.max_tunnels.value(),
            apply_theme=self.apply_theme.isChecked(),
            seed=self._optional(self.seed.value()),
        )
