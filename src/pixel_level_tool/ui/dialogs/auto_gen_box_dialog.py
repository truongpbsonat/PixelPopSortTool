from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
)

from pixel_level_tool.domain.enums import LevelDifficulty
from pixel_level_tool.services.box_autogen import (
    DIFFICULTY_PROFILES,
    MAX_BOX_SLOTS,
    SLOT,
    AutoGenOptions,
)


class AutoGenBoxDialog(QDialog):
    """Difficulty and layout options for the Auto Gen Box action."""

    _ACTIVE_POLICIES = (
        ("Không box nào (giống các file level)", "none"),
        ("Chỉ hàng trước (slot hàng 0)", "row0"),
        ("Mọi box", "all"),
    )
    _TUNNEL_MODES = (
        ("Chỉ khi số box vượt giới hạn slot", "overflow"),
        ("Luôn luôn, như một cơ chế", "mechanic"),
    )
    _LINKED_MODES = (
        ("Theo độ khó", "auto"),
        ("Dễ — hai box đều là màu đang cần", "sync"),
        ("Khó — box đi kèm là màu chưa cần", "stall"),
    )
    # Kiểu xếp layout của từng độ khó, dịch từ DifficultyProfile.scramble.
    _SCRAMBLE_LABELS = {
        "ordered": "xếp đúng thứ tự giải",
        "local": "box cần nằm gần hàng trước",
        "global": "box cần nằm bất kỳ đâu",
    }

    def __init__(self, difficulty: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Auto Gen Box")
        layout = QFormLayout(self)
        layout.addRow(
            QLabel(
                "Dựng toàn bộ lưới box Square_3x3 từ Pixel Grid hiện tại.\n"
                "Mỗi màu cần số pixel chia hết cho 9; pixel dư sẽ bị xoá.\n"
                "Độ khó đến từ việc bao nhiêu box được đặt Hidden."
            )
        )

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
        self.difficulty.setToolTip(
            "Easy hiện mọi box và xếp chúng theo đúng thứ tự giải.\n"
            "Medium ẩn một vài box. Hard ẩn ~40% và giữ box cần tiếp theo gần hàng trước.\n"
            "SuperHard ẩn ~60% và đặt box cần tiếp theo ở bất kỳ đâu trên lưới.\n"
            "Độ chôn cũng cùng một nấc chỉnh đó cho tunnel: Easy nhả box ra đúng lúc pixel grid\n"
            "cần, còn SuperHard chôn nó sau ba box khác.\n"
            "Riêng Hard và SuperHard còn chừa sẵn vài slot làm wall để kẹp box lại.\n"
            "ArrowLock và LinkedContainer là tuỳ chọn riêng bên dưới; khi bật, độ khó quyết định\n"
            "số box bị khoá và số cặp được nối, và Hard/SuperHard nối link theo kiểu khó."
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

        self.tray_slots = QSpinBox()
        self.tray_slots.setRange(0, 8)
        self.tray_slots.setSpecialValueText("Auto")
        self.tray_slots.setToolTip(
            "piece, tức số ô khay. Auto dùng 5 giống các file level, và chỉ được nâng lên khi "
            "bức ảnh không chơi được với chừng đó ô."
        )

        self.active_policy = QComboBox()
        for label, value in self._ACTIVE_POLICIES:
            self.active_policy.addItem(label, value)
        self.active_policy.setToolTip(
            "Những box nào được ghi với isActive = true. Các file level không dùng box nào, và "
            "box Hidden luôn được ghi inactive vì validator bắt buộc như vậy."
        )

        self.max_tunnels = QSpinBox()
        self.max_tunnels.setRange(1, 8)
        self.max_tunnels.setValue(4)
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
            "trên lưới như một bức tường. Chế độ tràn chỉ dựng tunnel khi ảnh quá lớn so với giới\n"
            "hạn slot; chế độ cơ chế cắm đủ số tunnel của độ khó ngay cả khi mọi thứ vừa lưới."
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

        # Hai obstacle dưới đây là tuỳ chọn của từng level: mặc định tắt, bật lên
        # thì độ khó mới quyết định liều lượng.
        self.use_arrow_lock = QCheckBox("Có ArrowLock trong level này")
        self.use_arrow_lock.setToolTip(
            "Box mang ArrowLock hiện một mũi tên và chỉ mở được sau khi người chơi đã mở một box\n"
            "nằm ở hướng mũi tên đó. Mũi tên luôn được chỉ vào một box thật nằm sát bên và box đó\n"
            "chắc chắn được mở trước trong lời giải, nên khoá luôn có chìa — không bao giờ chỉ vào\n"
            "wall, vào tunnel hay ra ngoài lưới, vì như vậy box sẽ không bao giờ mở được.\n"
            "Riêng ArrowLock đã khá khó, nên số box bị khoá được giữ ở mức thấp."
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
            "Box ẩn và box đã bị link sẽ không nhận ArrowLock."
        )

        self.use_linked_container = QCheckBox("Có LinkedContainer trong level này")
        self.use_linked_container.setToolTip(
            "LinkedContainer nối hai box nằm sát nhau: bấm một box thì cả hai cùng xuống băng\n"
            "chuyền, nên một lần bấm tốn hai ô khay cùng lúc.\n"
            "Dễ: cả hai box đều là màu bên dưới đang cần, khay rút cạn ngay.\n"
            "Khó: cố tình nối một box đang cần với một box màu chưa cần, box kia ngồi chiếm ô khay\n"
            "và làm băng chuyền đầy lên — dùng cẩn thận.\n"
            "Mọi cặp đều được chơi thử lại, cặp nào làm tràn khay thì bị bỏ."
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

        self.apply_theme = QCheckBox("Áp dụng theme Hard / Super Hard")
        self.apply_theme.setChecked(True)

        layout.addRow("Độ khó", self.difficulty)
        layout.addRow("Box ẩn", self.hidden_ratio)
        layout.addRow("Số slot box tối đa theo chiều ngang", self.slot_cols)
        layout.addRow("Số slot box tối đa theo chiều dọc", self.slot_rows)
        layout.addRow("", self.capacity_label)
        layout.addRow("Wall (slot bỏ trống)", self.walls)
        layout.addRow("piece (số ô khay)", self.tray_slots)
        layout.addRow("isActive", self.active_policy)
        layout.addRow("Tunnel", self.tunnel_mode)
        layout.addRow("Số tunnel tối đa", self.max_tunnels)
        layout.addRow("Số box mỗi tunnel", self.tunnel_depth)
        layout.addRow("Độ chôn trong tunnel", self.dig_window)
        layout.addRow("", self.allow_tunnels)
        layout.addRow("", self.use_arrow_lock)
        layout.addRow("Tỷ lệ box ArrowLock", self.arrow_ratio)
        layout.addRow("", self.use_linked_container)
        layout.addRow("Số cặp LinkedContainer", self.linked_pairs)
        layout.addRow("Kiểu LinkedContainer", self.linked_mode)
        layout.addRow("", self.apply_theme)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Sinh box")
        buttons.button(QDialogButtonBox.Cancel).setText("Huỷ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        for widget in (self.max_tunnels, self.tunnel_depth, self.dig_window, self.tunnel_mode):
            self.allow_tunnels.toggled.connect(widget.setEnabled)
        self.use_arrow_lock.toggled.connect(self.arrow_ratio.setEnabled)
        self.arrow_ratio.setEnabled(False)
        for widget in (self.linked_pairs, self.linked_mode):
            self.use_linked_container.toggled.connect(widget.setEnabled)
            widget.setEnabled(False)
        self._update_capacity()

    def _update_capacity(self) -> None:
        cols, rows = self.slot_cols.value(), self.slot_rows.value()
        self.capacity_label.setText(
            f"= lưới box tối đa {cols * SLOT} x {rows * SLOT} ô,"
            f" {cols * rows} box, {cols * rows * 9} ball"
        )

    def options(self) -> AutoGenOptions:
        hidden = self.hidden_ratio.value()
        dig = self.dig_window.value()
        walls = self.walls.value()
        arrow = self.arrow_ratio.value()
        pairs = self.linked_pairs.value()
        return AutoGenOptions(
            use_arrow_lock=self.use_arrow_lock.isChecked(),
            arrow_ratio=None if arrow < 0 else arrow / 100.0,
            use_linked_container=self.use_linked_container.isChecked(),
            linked_pairs=None if pairs < 0 else pairs,
            linked_mode=str(self.linked_mode.currentData()),
            walls=None if walls < 0 else walls,
            tunnel_mode=str(self.tunnel_mode.currentData()),
            tunnel_depth=self.tunnel_depth.value(),
            dig_window=None if dig <= 0 else dig,
            difficulty=int(self.difficulty.currentData()),
            max_slot_cols=self.slot_cols.value(),
            max_slot_rows=self.slot_rows.value(),
            hidden_ratio=None if hidden < 0 else hidden / 100.0,
            tray_slots=self.tray_slots.value(),
            active_policy=str(self.active_policy.currentData()),
            allow_tunnels=self.allow_tunnels.isChecked(),
            max_tunnels=self.max_tunnels.value(),
            apply_theme=self.apply_theme.isChecked(),
        )
