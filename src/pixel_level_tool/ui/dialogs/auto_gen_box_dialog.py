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
            "Riêng Hard và SuperHard còn chừa sẵn vài slot làm wall để kẹp box lại."
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
        layout.addRow("", self.apply_theme)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Sinh box")
        buttons.button(QDialogButtonBox.Cancel).setText("Huỷ")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        for widget in (self.max_tunnels, self.tunnel_depth, self.dig_window, self.tunnel_mode):
            self.allow_tunnels.toggled.connect(widget.setEnabled)
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
        return AutoGenOptions(
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
