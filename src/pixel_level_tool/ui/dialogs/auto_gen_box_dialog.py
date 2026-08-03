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
        ("No box (matches the level files)", "none"),
        ("Front row only (slot row 0)", "row0"),
        ("Every box", "all"),
    )
    _TUNNEL_MODES = (
        ("Only when the boxes overflow the slot limit", "overflow"),
        ("Always, as a mechanic", "mechanic"),
    )

    def __init__(self, difficulty: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Auto Gen Box")
        layout = QFormLayout(self)
        layout.addRow(
            QLabel(
                "Builds a full lattice of Square_3x3 boxes from the current Pixel Grid.\n"
                "Every color needs a pixel count divisible by 9; surplus pixels are deleted.\n"
                "Difficulty comes from how many boxes are Hidden."
            )
        )

        self.difficulty = QComboBox()
        for member in LevelDifficulty:
            profile = DIFFICULTY_PROFILES[int(member)]
            self.difficulty.addItem(
                f"{int(member)}  {profile.label}"
                f"  ({profile.hidden_ratio:.0%} hidden, {profile.scramble} layout,"
                f" dig {profile.dig_window})",
                int(member),
            )
        index = self.difficulty.findData(difficulty)
        self.difficulty.setCurrentIndex(index if index != -1 else 0)
        self.difficulty.setToolTip(
            "Easy shows every box and lays them out in solution order.\n"
            "Medium hides a few. Hard hides ~40% and keeps the next box near the front row.\n"
            "SuperHard hides ~60% and puts the next box anywhere on the grid.\n"
            "The dig depth is the same dial for tunnels: Easy hands a stored box over exactly\n"
            "when the pixel grid needs it, SuperHard buries it behind three others."
        )

        self.slot_cols = QSpinBox()
        self.slot_cols.setRange(1, MAX_BOX_SLOTS)
        self.slot_cols.setValue(MAX_BOX_SLOTS)
        self.slot_rows = QSpinBox()
        self.slot_rows.setRange(1, MAX_BOX_SLOTS)
        self.slot_rows.setValue(MAX_BOX_SLOTS)
        for spin in (self.slot_cols, self.slot_rows):
            spin.setToolTip(
                f"Upper bound in 3x3 box slots. {MAX_BOX_SLOTS}x{MAX_BOX_SLOTS} slots means "
                f"gridCols/gridRows up to {MAX_BOX_SLOTS * SLOT} and "
                f"{MAX_BOX_SLOTS * MAX_BOX_SLOTS * 9} balls; anything more goes into tunnels."
            )
            spin.valueChanged.connect(self._update_capacity)

        self.capacity_label = QLabel()

        self.hidden_ratio = QSpinBox()
        self.hidden_ratio.setRange(-1, 100)
        self.hidden_ratio.setValue(-1)
        self.hidden_ratio.setSpecialValueText("Auto")
        self.hidden_ratio.setSuffix(" %")
        self.hidden_ratio.setToolTip(
            "Share of boxes carrying the Hidden effect. Auto uses the difficulty's value.\n"
            "Hiding is spent on the rarest colors first, because hiding one of a dozen identical\n"
            "boxes hides nothing. The front slot row is never hidden."
        )

        self.tray_slots = QSpinBox()
        self.tray_slots.setRange(0, 8)
        self.tray_slots.setSpecialValueText("Auto")
        self.tray_slots.setToolTip(
            "piece, the number of tray slots. Auto uses 5, like the level files, and is only "
            "raised when the picture cannot be played with that many."
        )

        self.active_policy = QComboBox()
        for label, value in self._ACTIVE_POLICIES:
            self.active_policy.addItem(label, value)
        self.active_policy.setToolTip(
            "Which boxes are written with isActive = true. The level files use none, and a "
            "Hidden box is always written inactive because the validator requires it."
        )

        self.max_tunnels = QSpinBox()
        self.max_tunnels.setRange(1, 8)
        self.max_tunnels.setValue(4)
        self.allow_tunnels = QCheckBox("Store overflow boxes in tunnels")
        self.allow_tunnels.setChecked(True)
        self.allow_tunnels.setToolTip(
            "Only needed when the picture has more boxes than the slot limit holds. "
            "When off, generation fails instead of creating tunnels."
        )

        self.tunnel_mode = QComboBox()
        for label, value in self._TUNNEL_MODES:
            self.tunnel_mode.addItem(label, value)
        self.tunnel_mode.setToolTip(
            "A tunnel is a queue: only its head can be taken, and an emptied tunnel stays on the\n"
            "grid as a wall. Overflow only builds them when the picture is too big for the slot\n"
            "limit; as a mechanic plants the difficulty's tunnels even when everything fits."
        )

        self.tunnel_depth = QSpinBox()
        self.tunnel_depth.setRange(0, 16)
        self.tunnel_depth.setSpecialValueText("Auto")
        self.tunnel_depth.setToolTip(
            "Boxes stored per tunnel. Auto uses the difficulty's depth, and it is raised on its "
            "own whenever the picture overflows the slot limit."
        )

        self.dig_window = QSpinBox()
        self.dig_window.setRange(0, 8)
        self.dig_window.setSpecialValueText("Auto")
        self.dig_window.setToolTip(
            "How deep the color the pixel grid wants next is buried in the tunnel.\n"
            "1 releases every box exactly when it is needed, so the tunnel never annoys.\n"
            "4 means the player pops three unwanted boxes before reaching the one they want.\n"
            "Narrowed automatically when digging that deep would overflow the tray."
        )
        self.apply_theme = QCheckBox("Apply the Hard / Super Hard theme")
        self.apply_theme.setChecked(True)

        layout.addRow("Difficulty", self.difficulty)
        layout.addRow("Hidden boxes", self.hidden_ratio)
        layout.addRow("Max box slots across", self.slot_cols)
        layout.addRow("Max box slots deep", self.slot_rows)
        layout.addRow("", self.capacity_label)
        layout.addRow("piece (tray slots)", self.tray_slots)
        layout.addRow("isActive", self.active_policy)
        layout.addRow("Tunnels", self.tunnel_mode)
        layout.addRow("Max tunnels", self.max_tunnels)
        layout.addRow("Boxes per tunnel", self.tunnel_depth)
        layout.addRow("Tunnel dig depth", self.dig_window)
        layout.addRow("", self.allow_tunnels)
        layout.addRow("", self.apply_theme)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Generate")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        for widget in (self.max_tunnels, self.tunnel_depth, self.dig_window, self.tunnel_mode):
            self.allow_tunnels.toggled.connect(widget.setEnabled)
        self._update_capacity()

    def _update_capacity(self) -> None:
        cols, rows = self.slot_cols.value(), self.slot_rows.value()
        self.capacity_label.setText(
            f"= box grid up to {cols * SLOT} x {rows * SLOT} cells,"
            f" {cols * rows} boxes, {cols * rows * 9} balls"
        )

    def options(self) -> AutoGenOptions:
        hidden = self.hidden_ratio.value()
        dig = self.dig_window.value()
        return AutoGenOptions(
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
