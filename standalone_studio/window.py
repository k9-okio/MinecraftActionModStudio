from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QVBoxLayout,
    QWidget,
)

from .core import (
    Animation,
    Bone,
    Project,
    _safe_name,
    make_basis,
    quat_from_axis_deg,
    quat_from_euler_deg,
    quat_matrix,
    quat_multiply,
    quat_to_euler_deg,
    rest_matrix_from_basis,
)
from .exporter import export_mod
from .importers import import_blend
from .viewport import ModelViewport


class ExportDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导出动作 Mod")
        layout = QVBoxLayout(self)
        self.name = QLineEdit("player_actions")
        self.output = QLineEdit(
            str(Path.home() / "Documents" / "Minecraft Action Mods")
        )
        browse = QPushButton("选择…")
        browse.clicked.connect(self.pick_directory)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output)
        output_row.addWidget(browse)
        self.install = QCheckBox("构建后安装到 D:\\mc 当前 Forge 实例")
        self.install.setChecked(True)
        form = QFormLayout()
        form.addRow("Mod 文件名", self.name)
        form.addRow("导出目录", output_row)
        layout.addLayout(form)
        layout.addWidget(self.install)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def pick_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self, "选择导出目录", self.output.text()
        )
        if directory:
            self.output.setText(directory)


class BbmodelImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导入 Blockbench 选项")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        info = QLabel(
            "只导入模型时，不会带进模型自带的骨骼和动作，所有网格块保持未绑定；"
            "之后可在左侧“模型部件”里选择部件，用右侧“骨骼编辑”新建骨骼并绑定。"
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        self.import_bones = QCheckBox("导入模型自带的骨骼层级")
        self.import_bones.setChecked(False)
        self.import_animations = QCheckBox("导入模型自带的动作")
        self.import_animations.setChecked(False)
        self.import_animations.setEnabled(False)
        self.import_bones.toggled.connect(self.on_bones_toggled)
        layout.addWidget(self.import_bones)
        layout.addWidget(self.import_animations)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("导入")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def on_bones_toggled(self, enabled):
        self.import_animations.setEnabled(bool(enabled))
        self.import_animations.setChecked(bool(enabled))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Minecraft Action Mod Studio 0.6")
        self.setWindowIcon(make_icon())
        self.resize(1500, 940)
        self.project: Project | None = None
        self.current_animation: Animation | None = None
        self.selected_bone: str | None = None
        self.selected_parts: set[int] = set()
        self.current_frame = 1
        self.updating = False
        self.settings = QSettings("Codex", "MinecraftActionStudio")

        self.play_timer = QTimer(self)
        self.play_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.play_timer.timeout.connect(self.advance_playback)
        self.playing = False

        self.viewport = ModelViewport()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["骨骼层级"])
        self.tree.itemSelectionChanged.connect(self.on_bone_selected)

        self.part_list = QListWidget()
        self.part_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.part_list.itemSelectionChanged.connect(self.on_parts_selected)
        parts_box = QGroupBox("模型部件（可按住 Ctrl 多选）")
        parts_layout = QVBoxLayout(parts_box)
        parts_layout.addWidget(self.part_list)
        bind_row = QHBoxLayout()
        self.bind_parts_button = QPushButton("绑定到当前骨骼")
        self.bind_parts_button.clicked.connect(self.bind_selected_parts)
        self.unbind_parts_button = QPushButton("解除绑定")
        self.unbind_parts_button.clicked.connect(self.unbind_selected_parts)
        bind_row.addWidget(self.bind_parts_button)
        bind_row.addWidget(self.unbind_parts_button)
        parts_layout.addLayout(bind_row)
        self.auto_bind_button = QPushButton("自动绑定到最近骨骼")
        self.auto_bind_button.clicked.connect(self.auto_bind_parts)
        parts_layout.addWidget(self.auto_bind_button)

        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_splitter.addWidget(self.tree)
        left_splitter.addWidget(parts_box)
        left_splitter.setSizes([430, 330])
        self.left_panel = left_splitter

        self.rotate_x = self.make_rotation_spin()
        self.rotate_y = self.make_rotation_spin()
        self.rotate_z = self.make_rotation_spin()
        for spin in (self.rotate_x, self.rotate_y, self.rotate_z):
            spin.valueChanged.connect(self.on_rotation_changed)
        self.location_x = self.make_location_spin()
        self.location_y = self.make_location_spin()
        self.location_z = self.make_location_spin()
        for spin in (self.location_x, self.location_y, self.location_z):
            spin.valueChanged.connect(self.on_location_changed)
        self.auto_key = QCheckBox("修改参数时自动记录关键帧")
        self.auto_key.setChecked(True)
        self.lock_bone = QPushButton("锁定当前骨骼")
        self.lock_bone.setCheckable(True)
        self.lock_bone.setToolTip("锁定后，点击其他骨骼或方块不会切换当前骨骼")
        self.lock_bone.toggled.connect(self.on_lock_bone_changed)
        self.direct_edit = QCheckBox("视口内直接拖动骨骼")
        self.direct_edit.setChecked(True)
        self.whole_model_mode = QCheckBox("整个人物模式")
        self.whole_model_mode.toggled.connect(self.on_whole_model_mode)
        self.transform_mode = QComboBox()
        self.transform_mode.addItem("旋转 (R)", "rotate")
        self.transform_mode.addItem("移动 (V)", "move")
        self.direct_edit.toggled.connect(self.on_direct_edit_changed)
        self.transform_mode.currentIndexChanged.connect(self.on_direct_edit_changed)
        self.record_button = QPushButton("记录当前旋转")
        self.record_button.clicked.connect(self.record_key)
        self.remove_key_button = QPushButton("删除当前帧关键帧")
        self.remove_key_button.clicked.connect(self.delete_key)

        self.bone_info = QLabel("尚未选择骨骼")
        self.bone_info.setWordWrap(True)
        inspector = QWidget()
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.addWidget(self.bone_info)

        self.bone_name_edit = QLineEdit()
        self.bone_name_edit.setPlaceholderText("骨骼名称，如 spine / chest / head")
        self.bone_name_edit.setToolTip(
            "导出动作只识别这些骨骼名：spine、chest、head、"
            "upper_arm.L、forearm.L、upper_arm.R、forearm.R、"
            "thigh.L、shin.L、thigh.R、shin.R"
        )
        self.parent_combo = QComboBox()
        self.head_x = self.make_location_spin()
        self.head_y = self.make_location_spin()
        self.head_z = self.make_location_spin()
        self.tail_x = self.make_location_spin()
        self.tail_y = self.make_location_spin()
        self.tail_z = self.make_location_spin()
        bone_group = QGroupBox("骨骼编辑 / 绑定")
        bone_layout = QFormLayout(bone_group)
        bone_layout.addRow("名称", self.bone_name_edit)
        bone_layout.addRow("父骨骼", self.parent_combo)
        head_row = QHBoxLayout()
        for spin in (self.head_x, self.head_y, self.head_z):
            head_row.addWidget(spin)
        bone_layout.addRow("关节 Head", head_row)
        tail_row = QHBoxLayout()
        for spin in (self.tail_x, self.tail_y, self.tail_z):
            tail_row.addWidget(spin)
        bone_layout.addRow("末端 Tail", tail_row)
        self.apply_bone_button = QPushButton("应用修改")
        self.apply_bone_button.clicked.connect(self.apply_bone_edit)
        self.new_bone_button = QPushButton("新建骨骼")
        self.new_bone_button.clicked.connect(lambda: self.new_bone(False))
        self.new_child_bone_button = QPushButton("新建子骨骼")
        self.new_child_bone_button.clicked.connect(lambda: self.new_bone(True))
        self.delete_bone_button = QPushButton("删除骨骼")
        self.delete_bone_button.clicked.connect(self.delete_bone)
        bone_layout.addRow(self.apply_bone_button)
        bone_buttons = QHBoxLayout()
        bone_buttons.addWidget(self.new_bone_button)
        bone_buttons.addWidget(self.new_child_bone_button)
        bone_buttons.addWidget(self.delete_bone_button)
        bone_layout.addRow(bone_buttons)
        inspector_layout.addWidget(bone_group)

        rotation_group = QGroupBox("局部旋转")
        rotation_layout = QFormLayout(rotation_group)
        rotation_layout.addRow("X", self.rotate_x)
        rotation_layout.addRow("Y", self.rotate_y)
        rotation_layout.addRow("Z", self.rotate_z)
        inspector_layout.addWidget(rotation_group)
        location_group = QGroupBox("局部位移")
        location_layout = QFormLayout(location_group)
        location_layout.addRow("X", self.location_x)
        location_layout.addRow("Y", self.location_y)
        location_layout.addRow("Z", self.location_z)
        inspector_layout.addWidget(location_group)
        pivot_group = QGroupBox("旋转中心")
        pivot_layout = QFormLayout(pivot_group)
        self.pivot_mode = QComboBox()
        self.pivot_mode.addItem("骨骼关节", "head")
        self.pivot_mode.addItem("整个人物中心", "center")
        self.pivot_mode.addItem("自定义坐标", "custom")
        self.pivot_x = self.make_location_spin()
        self.pivot_y = self.make_location_spin()
        self.pivot_z = self.make_location_spin()
        pivot_layout.addRow("模式", self.pivot_mode)
        pivot_layout.addRow("中心 X", self.pivot_x)
        pivot_layout.addRow("中心 Y", self.pivot_y)
        pivot_layout.addRow("中心 Z", self.pivot_z)
        self.apply_pivot_button = QPushButton("把这个点设为旋转中心")
        self.apply_pivot_button.clicked.connect(self.apply_pivot)
        pivot_layout.addWidget(self.apply_pivot_button)
        inspector_layout.addWidget(pivot_group)
        inspector_layout.addWidget(self.lock_bone)
        inspector_layout.addWidget(self.auto_key)
        direct_row = QHBoxLayout()
        direct_row.addWidget(self.direct_edit)
        direct_row.addWidget(self.transform_mode)
        inspector_layout.addLayout(direct_row)
        inspector_layout.addWidget(self.whole_model_mode)
        hint = QLabel(
            "直接拖动时：左右旋转 Y，上下旋转 X，按住 Shift 旋转 Z。移动模式使用左右/上下拖动。\n"
            "快捷键：在视口里按 R 切到旋转（三色圆环），按 V 切到移动（三色箭头）。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8fa7bd;")
        inspector_layout.addWidget(hint)
        inspector_layout.addWidget(self.record_button)
        inspector_layout.addWidget(self.remove_key_button)
        inspector_layout.addStretch()
        inspector_scroll = QScrollArea()
        inspector_scroll.setWidgetResizable(True)
        inspector_scroll.setFrameShape(QFrame.Shape.NoFrame)
        inspector_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        inspector_scroll.setWidget(inspector)

        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.addWidget(self.left_panel)
        top_splitter.addWidget(self.viewport)
        top_splitter.addWidget(inspector_scroll)
        top_splitter.setSizes([270, 930, 330])
        top_splitter.setStretchFactor(1, 1)

        timeline = self.build_timeline()
        self.timeline_panel = timeline
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.addWidget(top_splitter)
        main_splitter.addWidget(timeline)
        main_splitter.setSizes([700, 220])
        self.setCentralWidget(main_splitter)

        self.make_actions_and_toolbar()
        self.setAcceptDrops(True)
        self.viewport.transform_callback = self.viewport_transform
        self.viewport.pick_callback = self.on_viewport_pick
        self.viewport.gizmo_callback = self.on_gizmo
        self.viewport.mode_callback = self.set_transform_mode
        self.left_panel.hide()
        self.selection_label = QLabel("未选择", self.viewport)
        self.selection_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.selection_label.setStyleSheet(
            "background: rgba(20, 24, 31, 170); color: white; "
            "padding: 5px 9px; border-radius: 4px;"
        )
        self.selection_label.move(14, 12)
        self.selection_label.show()
        self.on_direct_edit_changed()
        self.statusBar().showMessage("就绪")
        self.update_controls()

    def make_rotation_spin(self):
        spin = QDoubleSpinBox()
        spin.setRange(-3600, 3600)
        spin.setDecimals(2)
        spin.setSingleStep(1.0)
        spin.setSuffix("°")
        return spin

    def make_location_spin(self):
        spin = QDoubleSpinBox()
        spin.setRange(-1000, 1000)
        spin.setDecimals(3)
        spin.setSingleStep(0.05)
        spin.setMinimumWidth(42)
        spin.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        return spin

    def build_timeline(self):
        panel = QWidget()
        outer = QVBoxLayout(panel)
        header = QHBoxLayout()
        header.addWidget(QLabel("动作与时间轴"))
        header.addStretch()
        close_button = QPushButton("×")
        close_button.setFixedSize(32, 24)
        close_button.setStyleSheet(
            "QPushButton { color: #ffffff; background: #5b2431; "
            "font-size: 14pt; font-weight: bold; padding: 0; }"
        )
        close_button.setToolTip("关闭时间轴；需要时从工具栏重新打开")
        close_button.clicked.connect(self.hide_timeline)
        header.addWidget(close_button)
        outer.addLayout(header)
        content = QWidget()
        layout = QHBoxLayout(content)

        animation_box = QGroupBox("动作 / 导出选择")
        animation_layout = QVBoxLayout(animation_box)
        self.animation_list = QListWidget()
        self.animation_list.itemClicked.connect(self.on_animation_selected)
        self.animation_list.itemChanged.connect(self.on_animation_check_changed)
        animation_layout.addWidget(self.animation_list)
        row = QHBoxLayout()
        for label, callback in (
            ("新建", self.new_animation),
            ("复制", self.duplicate_animation),
            ("删除", self.delete_animation),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        animation_layout.addLayout(row)
        layout.addWidget(animation_box, 2)

        timeline_box = QGroupBox("时间轴")
        timeline_layout = QVBoxLayout(timeline_box)
        controls = QHBoxLayout()
        self.play_button = QPushButton("▶ 播放")
        self.play_button.clicked.connect(self.toggle_play)
        controls.addWidget(self.play_button)
        self.rest_button = QPushButton("静置姿势")
        self.rest_button.clicked.connect(self.return_to_rest)
        controls.addWidget(self.rest_button)
        controls.addWidget(QLabel("帧"))
        self.frame_spin = QSpinBox()
        self.frame_spin.setRange(1, 10000)
        self.frame_spin.valueChanged.connect(self.set_frame)
        controls.addWidget(self.frame_spin)
        controls.addWidget(QLabel("FPS"))
        self.fps_spin = QDoubleSpinBox()
        self.fps_spin.setRange(1, 240)
        self.fps_spin.setValue(24)
        self.fps_spin.valueChanged.connect(self.on_fps_changed)
        controls.addWidget(self.fps_spin)
        controls.addWidget(QLabel("结束帧"))
        self.end_spin = QSpinBox()
        self.end_spin.setRange(2, 10000)
        self.end_spin.setValue(24)
        self.end_spin.valueChanged.connect(self.on_end_changed)
        controls.addWidget(self.end_spin)
        self.loop_check = QCheckBox("循环")
        self.loop_check.setChecked(True)
        self.loop_check.toggled.connect(self.on_loop_changed)
        controls.addWidget(self.loop_check)
        controls.addStretch()
        timeline_layout.addLayout(controls)

        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setRange(1, 24)
        self.frame_slider.valueChanged.connect(self.set_frame)
        timeline_layout.addWidget(self.frame_slider)
        self.key_info = QLabel("关键帧: -")
        self.key_info.setStyleSheet("color: #9fb4c9;")
        timeline_layout.addWidget(self.key_info)
        timeline_layout.addStretch()
        layout.addWidget(timeline_box, 5)
        outer.addWidget(content)
        return panel

    def make_actions_and_toolbar(self):
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        open_action = QAction("打开工程", self)
        open_action.triggered.connect(self.open_project)
        save_action = QAction("保存工程", self)
        save_action.triggered.connect(self.save_project)
        blend_action = QAction("导入 Blend", self)
        blend_action.triggered.connect(self.open_blend)
        bb_action = QAction("导入 BBModel", self)
        bb_action.triggered.connect(self.open_bbmodel)
        export_action = QAction("导出动作 Mod", self)
        export_action.triggered.connect(self.open_export)
        tree_action = QAction("骨骼/部件", self)
        tree_action.setCheckable(True)
        tree_action.toggled.connect(self.left_panel.setVisible)
        self.tree_action = tree_action
        toolbar.addAction(tree_action)
        toolbar.addSeparator()
        self.timeline_action = QAction("时间轴", self)
        self.timeline_action.setCheckable(True)
        self.timeline_action.setChecked(True)
        self.timeline_action.toggled.connect(self.set_timeline_visible)
        toolbar.addAction(self.timeline_action)
        toolbar.addSeparator()
        for action in (open_action, save_action, blend_action, bb_action, export_action):
            toolbar.addAction(action)
            if action in (save_action, bb_action, export_action):
                toolbar.addSeparator()

        menu = self.menuBar().addMenu("文件")
        menu.addAction(open_action)
        menu.addAction(save_action)
        menu.addSeparator()
        menu.addAction(blend_action)
        menu.addAction(bb_action)
        menu.addSeparator()
        menu.addAction(export_action)
        menu.addSeparator()
        menu.addAction("退出", self.close, QKeySequence.StandardKey.Quit)

    def load_project(self, project: Project, source_path: str | None = None):
        self.stop_playback()
        self.project = project
        self.current_animation = None
        self.selected_bone = None
        self.selected_parts = set()
        self.viewport.set_project(project)
        self.viewport.set_selected_parts(set())
        self.populate_tree()
        self.populate_parts()
        self.populate_animations()
        if not project.bones and hasattr(self, "tree_action"):
            self.tree_action.setChecked(True)
        self.current_frame = 1
        self.sync_frame_controls()
        self.update_viewport()
        self.update_controls()
        if source_path:
            self.setWindowTitle(f"Minecraft Action Mod Studio 0.6 — {Path(source_path).name}")
        else:
            self.setWindowTitle(f"Minecraft Action Mod Studio 0.6 — {project.name}")
        self.statusBar().showMessage(
            f"{len(project.bones)} 根骨骼，{len(project.parts)} 个网格块，{len(project.animations)} 个动作"
        )

    def populate_tree(self):
        self.updating = True
        self.tree.clear()
        if self.project:
            placed = {}
            pending = dict(self.project.bones)
            while pending:
                progressed = False
                for name, bone in list(pending.items()):
                    if bone.parent in pending:
                        continue
                    item = QTreeWidgetItem([name])
                    item.setData(0, Qt.ItemDataRole.UserRole, name)
                    if bone.parent in placed:
                        placed[bone.parent].addChild(item)
                    else:
                        self.tree.addTopLevelItem(item)
                    placed[name] = item
                    pending.pop(name)
                    progressed = True
                if not progressed:
                    for name in pending:
                        item = QTreeWidgetItem([name])
                        item.setData(0, Qt.ItemDataRole.UserRole, name)
                        self.tree.addTopLevelItem(item)
                        placed[name] = item
                    pending.clear()
            self.tree.expandAll()
            if self.selected_bone in placed:
                self.tree.setCurrentItem(placed[self.selected_bone])
        self.updating = False

    def populate_parts(self):
        if not hasattr(self, "part_list"):
            return
        self.updating = True
        self.part_list.blockSignals(True)
        self.part_list.clear()
        if self.project:
            for index, part in enumerate(self.project.parts):
                if part.bone:
                    label = f"{part.name}  →  {part.bone}"
                else:
                    label = f"{part.name}  （未绑定）"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, index)
                self.part_list.addItem(item)
                if index in self.selected_parts:
                    item.setSelected(True)
        self.part_list.blockSignals(False)
        self.updating = False

    def populate_parent_combo(self, current=None):
        if not hasattr(self, "parent_combo"):
            return
        self.parent_combo.blockSignals(True)
        self.parent_combo.clear()
        self.parent_combo.addItem("无（根骨骼）", None)
        blocked = set()
        if self.project and self.selected_bone in self.project.bones:
            walk = self.selected_bone
            while walk in self.project.bones and walk not in blocked:
                blocked.add(walk)
                walk = self.project.bones[walk].parent
        if self.project:
            for name in self.project.bones:
                if name in blocked:
                    continue
                self.parent_combo.addItem(name, name)
        if current is not None:
            index = self.parent_combo.findData(current)
            if index >= 0:
                self.parent_combo.setCurrentIndex(index)
        self.parent_combo.blockSignals(False)

    def on_parts_selected(self):
        if self.updating or not self.project:
            return
        self.selected_parts = {
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.part_list.selectedItems()
        }
        self.viewport.set_selected_parts(self.selected_parts)

    def select_part(self, index):
        if not self.project or index is None:
            return
        if not 0 <= int(index) < len(self.project.parts):
            return
        self.selected_parts = {int(index)}
        self.populate_parts()
        self.viewport.set_selected_parts(self.selected_parts)

    def bind_selected_parts(self):
        if not self.project:
            return
        if not self.selected_bone:
            self.statusBar().showMessage("请先在骨骼列表里选中一根骨骼", 5000)
            return
        if not self.selected_parts:
            self.statusBar().showMessage(
                "请先在左侧“模型部件”里选择部件，按住 Ctrl 可多选", 6000
            )
            return
        count = 0
        for index in sorted(self.selected_parts):
            if 0 <= index < len(self.project.parts):
                part = self.project.parts[index]
                part.bone = self.selected_bone
                part.weights = {}
                count += 1
        self.populate_parts()
        self.update_viewport()
        self.statusBar().showMessage(
            f"已把 {count} 个部件绑定到骨骼 {self.selected_bone}", 5000
        )

    def unbind_selected_parts(self):
        if not self.project or not self.selected_parts:
            return
        count = 0
        for index in sorted(self.selected_parts):
            if 0 <= index < len(self.project.parts):
                part = self.project.parts[index]
                if part.bone or part.weights:
                    count += 1
                part.bone = ""
                part.weights = {}
        self.populate_parts()
        self.update_viewport()
        self.statusBar().showMessage(f"已解除 {count} 个部件的绑定", 5000)

    def auto_bind_parts(self):
        if not self.project or not self.project.bones:
            self.statusBar().showMessage("当前没有骨骼，请先在右侧新建骨骼", 5000)
            return
        bones = [
            (name, np.asarray(bone.head, dtype=float), np.asarray(bone.tail, dtype=float))
            for name, bone in self.project.bones.items()
        ]
        count = 0
        for part in self.project.parts:
            vertices = np.asarray(part.vertices, dtype=float)
            if not len(vertices):
                continue
            center = (vertices.min(axis=0) + vertices.max(axis=0)) * 0.5
            best_name = None
            best_distance = float("inf")
            for name, head, tail in bones:
                distance = ModelViewport.point_segment_distance(center, head, tail)
                if distance < best_distance:
                    best_distance = distance
                    best_name = name
            if best_name:
                part.bone = best_name
                part.weights = {}
                count += 1
        self.populate_parts()
        self.update_viewport()
        self.statusBar().showMessage(
            f"已按最近骨骼自动绑定 {count} 个部件，可再手动微调", 6000
        )

    def new_bone(self, child=False):
        if not self.project:
            return
        base = self.bone_name_edit.text().strip() or "bone"
        name = _safe_name(base, set(self.project.bones))
        parent = (
            self.selected_bone
            if child and self.selected_bone in self.project.bones
            else None
        )
        if parent:
            head = np.asarray(self.project.bones[parent].tail, dtype=float).copy()
        elif self.project.parts:
            all_vertices = np.concatenate(
                [np.asarray(part.vertices, dtype=float) for part in self.project.parts],
                axis=0,
            )
            low = all_vertices.min(axis=0)
            high = all_vertices.max(axis=0)
            head = np.array(
                [(low[0] + high[0]) * 0.5, float(low[1]), (low[2] + high[2]) * 0.5]
            )
        else:
            head = np.zeros(3)
        tail = head + np.array([0.0, 0.5, 0.0])
        basis = make_basis(head, tail)
        self.project.bones[name] = Bone(
            name,
            parent,
            head,
            tail,
            basis,
            rest_matrix_from_basis(head, basis),
        )
        self.selected_bone = name
        self.refresh_rig()
        self.select_bone(name)
        self.statusBar().showMessage(
            f"已新建骨骼 {name}，可修改关节坐标并绑定部件", 6000
        )

    def apply_bone_edit(self):
        if not self.project or not self.selected_bone:
            return
        if self.selected_bone not in self.project.bones:
            return
        bone = self.project.bones[self.selected_bone]
        name = self.bone_name_edit.text().strip()
        target = self.selected_bone
        if name and name != target:
            if name in self.project.bones:
                QMessageBox.warning(self, "无法重命名", f"骨骼 {name} 已存在")
                return
            target = name
        parent = self.parent_combo.currentData()
        if parent == target:
            parent = bone.parent
        walk = parent
        while walk:
            if walk == target:
                QMessageBox.warning(self, "父骨骼无效", "父骨骼不能是自身或自身的子骨骼")
                return
            walk = self.project.bones[walk].parent if walk in self.project.bones else None
        head = np.array([self.head_x.value(), self.head_y.value(), self.head_z.value()])
        tail = np.array([self.tail_x.value(), self.tail_y.value(), self.tail_z.value()])
        if float(np.linalg.norm(tail - head)) < 1e-4:
            tail = head + np.array([0.0, 0.5, 0.0])
        if target != self.selected_bone:
            self.rename_bone(self.selected_bone, target)
        bone.head = head
        bone.tail = tail
        bone.basis = make_basis(head, tail)
        bone.rest_matrix = rest_matrix_from_basis(head, bone.basis)
        bone.parent = parent
        self.selected_bone = target
        self.refresh_rig()
        self.select_bone(target)
        self.statusBar().showMessage("骨骼已更新", 4000)

    def rename_bone(self, old, new):
        project = self.project
        bones = {}
        for name, bone in project.bones.items():
            key = new if name == old else name
            bone.name = key
            bones[key] = bone
        project.bones = bones
        for bone in project.bones.values():
            if bone.parent == old:
                bone.parent = new
        for part in project.parts:
            if part.bone == old:
                part.bone = new
            if old in part.weights:
                part.weights[new] = part.weights.pop(old)
        for animation in project.animations:
            for mapping in (
                animation.tracks,
                animation.locations,
                animation.pivots,
                animation.deform_tracks,
            ):
                if old in mapping:
                    mapping[new] = mapping.pop(old)

    def delete_bone(self):
        if not self.project or not self.selected_bone:
            return
        if self.selected_bone not in self.project.bones:
            return
        answer = QMessageBox.question(
            self,
            "删除骨骼",
            f"确定删除骨骼 {self.selected_bone} 吗？绑定的部件会变为未绑定。",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        name = self.selected_bone
        parent = self.project.bones[name].parent
        self.project.bones.pop(name, None)
        for bone in self.project.bones.values():
            if bone.parent == name:
                bone.parent = parent if parent in self.project.bones else None
        for part in self.project.parts:
            if part.bone == name:
                part.bone = ""
            part.weights.pop(name, None)
        for animation in self.project.animations:
            for mapping in (
                animation.tracks,
                animation.locations,
                animation.pivots,
                animation.deform_tracks,
            ):
                mapping.pop(name, None)
        self.selected_bone = parent if parent in self.project.bones else None
        self.selected_parts = set()
        self.refresh_rig()
        if self.selected_bone:
            self.select_bone(self.selected_bone)
        else:
            self.update_viewport()
            self.update_inspector()
            self.update_controls()

    def refresh_rig(self):
        if not self.project:
            return
        self.populate_tree()
        self.populate_parts()
        self.viewport.sync_bones()
        self.update_viewport()
        self.update_inspector()
        self.update_controls()

    def populate_animations(self):
        self.updating = True
        self.animation_list.clear()
        if self.project:
            for animation in self.project.animations:
                item = QListWidgetItem(animation.name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if animation.name in {"idle", "run"} else Qt.CheckState.Unchecked)
                item.setData(Qt.ItemDataRole.UserRole, animation.name)
                self.animation_list.addItem(item)
            if self.current_animation:
                matches = self.animation_list.findItems(
                    self.current_animation.name, Qt.MatchFlag.MatchExactly
                )
                if matches:
                    self.animation_list.setCurrentItem(matches[0])
        self.updating = False

    def on_bone_selected(self):
        if self.updating:
            return
        selected = self.tree.selectedItems()
        requested = (
            selected[0].data(0, Qt.ItemDataRole.UserRole) if selected else None
        )
        if (
            self.lock_bone.isChecked()
            and self.selected_bone
            and requested != self.selected_bone
        ):
            iterator = QTreeWidgetItemIterator(self.tree)
            while iterator.value():
                item = iterator.value()
                if item.data(0, Qt.ItemDataRole.UserRole) == self.selected_bone:
                    self.tree.setCurrentItem(item)
                    break
                iterator += 1
            return
        self.selected_bone = requested
        self.update_selection_label()
        self.update_inspector()
        self.update_viewport()
        self.update_controls()

    def update_inspector(self):
        self.updating = True
        if self.project and self.selected_bone:
            bone = self.project.bones[self.selected_bone]
            self.bone_info.setText(
                f"<b>{bone.name}</b><br>父骨骼: {bone.parent or '无'}<br>"
                f"Head: {np.round(bone.head, 3).tolist()}"
            )
            self.bone_name_edit.setText(bone.name)
            self.populate_parent_combo(bone.parent)
            for spin, value in zip((self.head_x, self.head_y, self.head_z), bone.head):
                spin.setValue(float(value))
            for spin, value in zip((self.tail_x, self.tail_y, self.tail_z), bone.tail):
                spin.setValue(float(value))
            q = (
                self.current_animation.rotation_at(self.selected_bone, self.current_frame)
                if self.current_animation
                else np.array([1.0, 0.0, 0.0, 0.0])
            )
            rotation = quat_to_euler_deg(q)
            self.rotate_x.setValue(rotation[0])
            self.rotate_y.setValue(rotation[1])
            self.rotate_z.setValue(rotation[2])
            location = (
                self.current_animation.location_at(self.selected_bone, self.current_frame)
                if self.current_animation
                else np.zeros(3)
            )
            world_location = bone.basis @ location
            self.location_x.setValue(float(world_location[0]))
            self.location_y.setValue(float(world_location[1]))
            self.location_z.setValue(float(world_location[2]))
            pivot = (
                self.current_animation.pivots.get(self.selected_bone, bone.head)
                if self.current_animation
                else bone.head
            )
            self.pivot_x.setValue(float(pivot[0]))
            self.pivot_y.setValue(float(pivot[1]))
            self.pivot_z.setValue(float(pivot[2]))
        else:
            self.bone_info.setText("尚未选择骨骼")
            self.bone_name_edit.clear()
            self.populate_parent_combo(None)
        self.updating = False

    def ensure_animation(self):
        if self.current_animation is not None:
            return self.current_animation
        if not self.project:
            return None
        if self.project.animations:
            animation = self.project.animations[0]
        else:
            animation = Animation("pose", self.fps_spin.value(), 1, 24, True)
            self.project.animations.append(animation)
        self.current_animation = animation
        self.current_frame = animation.start
        self.sync_frame_controls()
        self.populate_animations()
        self.statusBar().showMessage(
            f"没有选中动作，已自动切换到 {animation.name} 记录关键帧", 5000
        )
        return animation

    def on_rotation_changed(self):
        if self.updating or not self.project or not self.selected_bone:
            return
        if not self.ensure_animation():
            return
        quaternion = quat_from_euler_deg(
            (self.rotate_x.value(), self.rotate_y.value(), self.rotate_z.value())
        )
        if self.auto_key.isChecked():
            self.record_quaternion(quaternion)
        else:
            self.current_animation.set_key(
                self.selected_bone, self.current_frame, quaternion
            )
            self.update_viewport()
        self.update_key_info()

    def on_location_changed(self):
        if self.updating or not self.project or not self.selected_bone:
            return
        if not self.ensure_animation():
            return
        world_location = np.array(
            [self.location_x.value(), self.location_y.value(), self.location_z.value()]
        )
        local_location = self.project.bones[self.selected_bone].basis.T @ world_location
        if self.auto_key.isChecked():
            self.current_animation.set_location(
                self.selected_bone, self.current_frame, local_location
            )
        else:
            self.current_animation.set_location(
                self.selected_bone, self.current_frame, local_location
            )
        self.end_spin.setValue(max(self.end_spin.value(), self.current_frame))
        self.update_viewport()

    def set_transform_mode(self, mode):
        index = self.transform_mode.findData(mode)
        if index < 0:
            return
        self.transform_mode.setCurrentIndex(index)
        label = "旋转（三色圆环）" if mode == "rotate" else "移动（三色箭头）"
        self.statusBar().showMessage(f"已切换到{label}模式", 3000)

    def on_direct_edit_changed(self, *_args):
        if hasattr(self, "viewport") and hasattr(self, "direct_edit"):
            self.viewport.set_transform_controls(
                self.direct_edit.isChecked(),
                self.transform_mode.currentData(),
            )

    def viewport_transform(self, dx, dy, shift, mode):
        if not self.project or not self.selected_bone:
            return
        if not self.ensure_animation():
            return
        self.updating = True
        try:
            if mode == "rotate":
                self.rotate_y.setValue(self.rotate_y.value() + dx * 0.45)
                self.rotate_x.setValue(self.rotate_x.value() + dy * 0.45)
                if shift:
                    self.rotate_z.setValue(self.rotate_z.value() + dx * 0.45)
            else:
                bone = self.project.bones[self.selected_bone]
                world_location = np.array(
                    [
                        self.location_x.value(),
                        self.location_y.value(),
                        self.location_z.value(),
                    ]
                )
                world_location += np.array(
                    [dx * 0.006, dy * 0.006 if shift else 0.0, -dy * 0.006]
                )
                local_location = bone.basis.T @ world_location
                self.current_animation.set_location(
                    self.selected_bone, self.current_frame, local_location
                )
                self.location_x.setValue(float(world_location[0]))
                self.location_y.setValue(float(world_location[1]))
                self.location_z.setValue(float(world_location[2]))
        finally:
            self.updating = False
        if mode == "rotate":
            self.on_rotation_changed()
        else:
            self.end_spin.setValue(max(self.end_spin.value(), self.current_frame))
            self.update_viewport()

    def on_gizmo(self, kind, axis_index, value):
        if not self.project or not self.selected_bone:
            return
        bone = self.project.bones.get(self.selected_bone)
        if bone is None:
            return
        if not self.ensure_animation():
            return
        axes = (
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
            np.array([0.0, 0.0, 1.0]),
        )
        axis = axes[int(axis_index)]
        if kind == "move":
            world_location = np.array(
                [
                    self.location_x.value(),
                    self.location_y.value(),
                    self.location_z.value(),
                ]
            )
            world_location += axis * float(value)
            local_location = bone.basis.T @ world_location
            self.current_animation.set_location(
                self.selected_bone, self.current_frame, local_location
            )
            self.updating = True
            self.location_x.setValue(float(world_location[0]))
            self.location_y.setValue(float(world_location[1]))
            self.location_z.setValue(float(world_location[2]))
            self.updating = False
            self.end_spin.setValue(max(self.end_spin.value(), self.current_frame))
            self.update_viewport()
            return
        transforms = self.project.bone_transforms(
            self.current_animation, float(self.current_frame)
        )
        deform = transforms.get(self.selected_bone, np.eye(4))
        previous = self.current_animation.rotation_at(
            self.selected_bone, float(self.current_frame)
        )
        base_rotation = deform[:3, :3] @ bone.basis @ quat_matrix(previous).T
        local_axis = base_rotation.T @ axis
        quaternion = quat_multiply(
            quat_from_axis_deg(local_axis, float(value)), previous
        )
        self.current_animation.set_key(
            self.selected_bone, self.current_frame, quaternion
        )
        self.end_spin.setValue(max(self.end_spin.value(), self.current_frame))
        self.update_inspector()
        self.update_viewport()
        self.update_key_info()

    def apply_pivot(self):
        if not self.project or not self.selected_bone or not self.current_animation:
            return
        bone = self.project.bones[self.selected_bone]
        mode = self.pivot_mode.currentData()
        if mode == "head":
            self.current_animation.set_pivot(self.selected_bone, None)
            pivot = bone.head
        elif mode == "center":
            vertices = np.concatenate([part.vertices for part in self.project.parts], axis=0)
            pivot = (vertices.min(axis=0) + vertices.max(axis=0)) * 0.5
            self.current_animation.set_pivot(self.selected_bone, pivot)
        else:
            pivot = np.array(
                [self.pivot_x.value(), self.pivot_y.value(), self.pivot_z.value()]
            )
            self.current_animation.set_pivot(self.selected_bone, pivot)
        self.updating = True
        self.pivot_x.setValue(float(pivot[0]))
        self.pivot_y.setValue(float(pivot[1]))
        self.pivot_z.setValue(float(pivot[2]))
        self.updating = False
        self.update_viewport()

    def record_quaternion(self, quaternion):
        if not self.current_animation or not self.selected_bone:
            return
        self.current_animation.set_key(
            self.selected_bone, self.current_frame, quaternion
        )
        self.end_spin.setValue(max(self.end_spin.value(), self.current_frame))
        self.update_viewport()
        self.update_key_info()

    def record_key(self):
        if not self.project or not self.selected_bone or not self.current_animation:
            return
        self.record_quaternion(
            quat_from_euler_deg(
                (self.rotate_x.value(), self.rotate_y.value(), self.rotate_z.value())
            )
        )
        self.statusBar().showMessage(
            f"已记录 {self.selected_bone} @ {self.current_frame}", 2500
        )

    def delete_key(self):
        if not self.current_animation or not self.selected_bone:
            return
        self.current_animation.remove_key(self.selected_bone, self.current_frame)
        self.update_viewport()
        self.update_key_info()

    def update_key_info(self):
        if self.current_animation and self.selected_bone:
            frames = sorted(
                self.current_animation.tracks.get(self.selected_bone, {}).keys()
            )
            self.key_info.setText(
                "关键帧: " + (", ".join(map(str, frames)) if frames else "-")
            )
        else:
            self.key_info.setText("关键帧: -")

    def on_animation_selected(self, item, _column=0):
        if self.updating or not self.project:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        self.current_animation = self.project.animation(name)
        if self.current_animation:
            self.current_frame = self.current_animation.start
            self.sync_frame_controls()
            self.update_inspector()
            self.update_viewport()

    def return_to_rest(self):
        self.stop_playback()
        self.current_animation = None
        self.current_frame = 1
        self.animation_list.clearSelection()
        self.sync_frame_controls()
        self.update_inspector()
        self.update_viewport()

    def on_animation_check_changed(self, _item):
        if not self.updating:
            self.update_controls()

    def new_animation(self):
        name, accepted = self.text_prompt("新建动作", "动作名称", "new_action")
        if accepted and name and self.project:
            animation = Animation(name, self.fps_spin.value(), 1, 24, True)
            self.project.animations.append(animation)
            self.current_animation = animation
            self.populate_animations()
            self.set_frame(1)

    def duplicate_animation(self):
        if not self.current_animation or not self.project:
            return
        copy = Animation.from_dict(self.current_animation.to_dict())
        copy.name = f"{copy.name}_copy"
        self.project.animations.append(copy)
        self.current_animation = copy
        self.populate_animations()

    def delete_animation(self):
        if not self.current_animation or not self.project:
            return
        self.project.animations = [
            animation
            for animation in self.project.animations
            if animation is not self.current_animation
        ]
        self.current_animation = self.project.animations[0] if self.project.animations else None
        self.populate_animations()
        self.update_viewport()

    def text_prompt(self, title, label, default):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        layout = QVBoxLayout(dialog)
        edit = QLineEdit(default)
        layout.addWidget(QLabel(label))
        layout.addWidget(edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        return edit.text(), dialog.exec() == QDialog.DialogCode.Accepted

    def set_frame(self, value):
        if self.updating:
            return
        self.current_frame = int(value)
        self.updating = True
        self.frame_slider.setValue(self.current_frame)
        self.frame_spin.setValue(self.current_frame)
        self.updating = False
        self.update_inspector()
        self.update_viewport()

    def sync_frame_controls(self):
        self.updating = True
        if self.current_animation:
            start = max(1, self.current_animation.start)
            end = max(start + 1, self.current_animation.end)
            self.frame_spin.setRange(start, end)
            self.frame_slider.setRange(start, end)
            self.end_spin.setValue(end)
            self.fps_spin.setValue(self.current_animation.fps)
            self.loop_check.setChecked(self.current_animation.loop)
            self.current_frame = min(max(self.current_frame, start), end)
            self.frame_spin.setValue(self.current_frame)
            self.frame_slider.setValue(self.current_frame)
        self.updating = False

    def on_fps_changed(self, value):
        if self.updating or not self.current_animation:
            return
        self.current_animation.fps = float(value)
        if self.playing:
            self.start_playback()

    def on_end_changed(self, value):
        if self.updating or not self.current_animation:
            return
        self.current_animation.end = int(value)
        self.sync_frame_controls()

    def on_loop_changed(self, value):
        if self.updating or not self.current_animation:
            return
        self.current_animation.loop = bool(value)

    def update_viewport(self):
        pivot_marker = None
        if self.project and self.selected_bone:
            bone = self.project.bones[self.selected_bone]
            transforms = self.project.bone_transforms(
                self.current_animation, float(self.current_frame)
            )
            local = (
                self.current_animation.location_at(
                    self.selected_bone, float(self.current_frame)
                )
                if self.current_animation
                else np.zeros(3)
            )
            pivot = (
                self.current_animation.pivots.get(self.selected_bone, bone.head)
                if self.current_animation
                else bone.head
            ) + bone.basis @ local
            parent = transforms.get(bone.parent, np.eye(4)) if bone.parent else np.eye(4)
            pivot_marker = (
                parent @ np.append(pivot, 1.0)
            )[:3]
        self.viewport.update_pose(
            self.current_animation,
            float(self.current_frame),
            self.selected_bone,
            pivot_marker,
        )
        self.update_key_info()

    def toggle_play(self):
        if self.playing:
            self.stop_playback()
        else:
            self.start_playback()

    def start_playback(self):
        if not self.current_animation:
            return
        if hasattr(self, "timeline_panel"):
            self.timeline_panel.show()
        if hasattr(self, "timeline_action"):
            self.timeline_action.setChecked(True)
        self.playing = True
        self.play_button.setText("⏸ 暂停")
        self.play_timer.start(max(8, int(1000 / max(1, self.current_animation.fps))))

    def stop_playback(self):
        self.playing = False
        self.play_timer.stop()
        self.play_button.setText("▶ 播放")

    def advance_playback(self):
        if not self.current_animation:
            self.stop_playback()
            return
        next_frame = self.current_frame + 1
        if next_frame > self.current_animation.end:
            next_frame = self.current_animation.start if self.current_animation.loop else self.current_animation.end
            if not self.current_animation.loop:
                self.stop_playback()
        self.set_frame(next_frame)

    def selected_animations(self):
        if not self.project:
            return []
        names = []
        for index in range(self.animation_list.count()):
            item = self.animation_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                names.append(item.data(Qt.ItemDataRole.UserRole))
        return [self.project.animation(name) for name in names if self.project.animation(name)]

    def update_controls(self):
        ready = self.project is not None
        if not ready or self.selected_bone is None:
            if self.lock_bone.isChecked():
                self.lock_bone.setChecked(False)
            self.viewport.locked_bone = None
        for widget in (
            self.rotate_x,
            self.rotate_y,
            self.rotate_z,
            self.location_x,
            self.location_y,
            self.location_z,
            self.record_button,
            self.remove_key_button,
            self.apply_pivot_button,
            self.lock_bone,
        ):
            widget.setEnabled(ready and self.selected_bone is not None)
        bone_ready = ready and self.selected_bone is not None
        for widget in (
            self.bone_name_edit,
            self.parent_combo,
            self.head_x,
            self.head_y,
            self.head_z,
            self.tail_x,
            self.tail_y,
            self.tail_z,
            self.apply_bone_button,
            self.delete_bone_button,
            self.new_child_bone_button,
            self.bind_parts_button,
            self.unbind_parts_button,
        ):
            widget.setEnabled(bone_ready)
        self.new_bone_button.setEnabled(ready)
        self.auto_bind_button.setEnabled(ready)
        self.part_list.setEnabled(ready)
        selected = len(self.selected_animations())
        self.statusBar().showMessage(f"就绪 · 已选择 {selected} 个动作")

    def hide_timeline(self):
        if hasattr(self, "timeline_panel"):
            self.timeline_panel.hide()
        if hasattr(self, "timeline_action"):
            self.timeline_action.setChecked(False)

    def set_timeline_visible(self, visible):
        if hasattr(self, "timeline_panel"):
            self.timeline_panel.setVisible(bool(visible))

    def on_lock_bone_changed(self, enabled):
        if enabled and not self.selected_bone:
            self.lock_bone.setChecked(False)
            return
        self.viewport.locked_bone = self.selected_bone if enabled else None
        self.lock_bone.setText("解锁当前骨骼" if enabled else "锁定当前骨骼")
        self.update_selection_label()

    def update_selection_label(self):
        if not hasattr(self, "selection_label"):
            return
        prefix = "🔒 " if self.lock_bone.isChecked() else ""
        self.selection_label.setText(prefix + (self.selected_bone or "未选择"))

    def select_bone(self, name: str, sync_tree: bool = True):
        if not self.project or name not in self.project.bones:
            return
        if self.lock_bone.isChecked() and self.selected_bone and name != self.selected_bone:
            return
        self.selected_bone = name
        self.update_selection_label()
        if sync_tree:
            iterator = QTreeWidgetItemIterator(self.tree)
            while iterator.value():
                item = iterator.value()
                if item.data(0, Qt.ItemDataRole.UserRole) == name:
                    self.tree.setCurrentItem(item)
                    break
                iterator += 1
        self.update_inspector()
        self.update_viewport()
        self.update_controls()

    def on_viewport_pick(self, bone_name, _part_index):
        if _part_index is not None:
            self.select_part(_part_index)
        if not bone_name:
            if _part_index is not None and self.project:
                part = self.project.parts[_part_index]
                if not part.bone:
                    self.statusBar().showMessage(
                        f"方块 {part.name} 还没有绑定骨骼：先在左侧选中它，"
                        "再点『绑定到当前骨骼』，就能直接拖动/旋转",
                        7000,
                    )
            return
        if self.lock_bone.isChecked() and self.selected_bone:
            bone_name = self.selected_bone
        if self.whole_model_mode.isChecked() and self.viewport.whole_model_bone:
            bone_name = self.viewport.whole_model_bone
        self.select_bone(bone_name)

    def on_whole_model_mode(self, enabled):
        if not self.project:
            return
        root_name = next(
            (name for name, bone in self.project.bones.items() if bone.parent is None),
            next(iter(self.project.bones), None),
        )
        self.viewport.whole_model_mode = bool(enabled)
        self.viewport.whole_model_bone = root_name
        if enabled and root_name:
            if self.lock_bone.isChecked():
                self.lock_bone.setChecked(False)
            self.pivot_mode.setCurrentIndex(1)
            self.select_bone(root_name)
            self.apply_pivot()

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开动作工程", "", "Action Studio Project (*.mcasproj);;JSON (*.json)"
        )
        if path:
            try:
                self.load_project(Project.load(path), path)
            except Exception as exc:
                self.show_error("打开工程失败", exc)

    def save_project(self):
        if not self.project:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "保存动作工程", f"{self.project.name}.mcasproj", "Action Studio Project (*.mcasproj)"
        )
        if path:
            try:
                self.project.save(path)
                self.statusBar().showMessage(f"已保存 {path}", 3000)
            except Exception as exc:
                self.show_error("保存失败", exc)

    def open_blend(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入 Blend", "", "Blender (*.blend)")
        if not path:
            return
        self.busy("正在用 Blender 后台读取骨骼和动作…")
        try:
            project = import_blend(path)
            self.load_project(project, path)
        except Exception as exc:
            self.show_error("导入 Blend 失败", exc)
        finally:
            self.normal_cursor()

    def open_bbmodel(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入 Blockbench", "", "Blockbench (*.bbmodel)")
        if not path:
            return
        self.import_bbmodel_file(path)

    def import_bbmodel_file(self, path):
        dialog = BbmodelImportDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        import_bones = dialog.import_bones.isChecked()
        import_animations = dialog.import_animations.isChecked()
        self.busy("正在解析 Blockbench 模型…")
        try:
            from .core import import_bbmodel

            project = import_bbmodel(path, import_bones, import_animations)
            self.load_project(project, path)
            if not import_bones:
                self.statusBar().showMessage(
                    f"已只导入模型：{len(project.parts)} 个部件全部未绑定，"
                    "请在右侧新建骨骼并绑定部件",
                    8000,
                )
            else:
                self.statusBar().showMessage(
                    f"已导入 {len(project.bones)} 根骨骼、{len(project.parts)} 个部件",
                    6000,
                )
        except Exception as exc:
            self.show_error("导入 Blockbench 失败", exc)
        finally:
            self.normal_cursor()

    def open_export(self):
        if not self.project:
            return
        dialog = ExportDialog(self.project, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        animations = self.selected_animations()
        if not animations:
            self.show_error("无法导出", "请先勾选至少一个动作")
            return
        self.busy("正在构建动作 Mod…")
        try:
            jar, project_file = export_mod(
                self.project,
                animations,
                dialog.name.text(),
                dialog.output.text(),
                dialog.install.isChecked(),
            )
            self.settings.setValue("lastExport", dialog.output.text())
            QMessageBox.information(
                self,
                "导出完成",
                f"已生成：\n{jar}\n\n工程备份：\n{project_file}",
            )
        except Exception as exc:
            self.show_error("导出失败", exc)
        finally:
            self.normal_cursor()

    def busy(self, text):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.statusBar().showMessage(text)
        QApplication.processEvents()

    def normal_cursor(self):
        QApplication.restoreOverrideCursor()
        self.statusBar().showMessage("就绪")

    def show_error(self, title, error):
        QMessageBox.critical(self, title, str(error))
        self.statusBar().showMessage(str(error), 5000)

    def dragEnterEvent(self, event):
        if any(
            path.lower().endswith((".blend", ".bbmodel", ".mcasproj"))
            for path in event.mimeData().urls()
        ):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not event.mimeData().urls():
            return
        path = event.mimeData().urls()[0].toLocalFile()
        lower = path.lower()
        if lower.endswith(".blend"):
            self.busy("正在用 Blender 后台读取骨骼和动作…")
            try:
                self.load_project(import_blend(path), path)
            except Exception as exc:
                self.show_error("导入 Blend 失败", exc)
            finally:
                self.normal_cursor()
        elif lower.endswith(".bbmodel"):
            self.import_bbmodel_file(path)
        elif lower.endswith(".mcasproj"):
            try:
                self.load_project(Project.load(path), path)
            except Exception as exc:
                self.show_error("打开工程失败", exc)

    def closeEvent(self, event):
        self.stop_playback()
        super().closeEvent(event)


def make_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor("#25334a"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#64b5ff"))
    painter.setPen(QColor("#f5b941"))
    painter.drawRoundedRect(8, 8, 48, 48, 10, 10)
    painter.setPen(QColor("#ffffff"))
    font = painter.font()
    font.setBold(True)
    font.setPixelSize(23)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "MC")
    painter.end()
    return QIcon(pixmap)
