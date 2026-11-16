import sys
import json
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .core import Animation, import_bbmodel, quat_from_euler_deg
from .exporter import export_mod
from .importers import import_blend
from .window import MainWindow


APP_STYLE = """
QMainWindow, QWidget {
    background: #171c24;
    color: #d8e3ef;
    font-family: "Microsoft YaHei UI", "Segoe UI";
    font-size: 10pt;
}
QTreeWidget, QListWidget, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #202734;
    border: 1px solid #344052;
    border-radius: 5px;
    padding: 4px;
}
QTreeWidget::item:selected, QListWidget::item:selected {
    background: #31597f;
}
QPushButton {
    background: #263447;
    border: 1px solid #3a4b62;
    border-radius: 5px;
    padding: 6px 12px;
}
QPushButton:hover { background: #324762; }
QPushButton:pressed { background: #1f2b3c; }
QToolBar {
    background: #111720;
    border-bottom: 1px solid #2b3545;
    spacing: 4px;
    padding: 4px;
}
QGroupBox {
    border: 1px solid #344052;
    border-radius: 7px;
    margin-top: 10px;
    padding: 10px 8px 8px 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #8ec8ff;
}
QMenuBar { background: #111720; }
QStatusBar { background: #111720; color: #9fb2c8; }
QSplitter::handle { background: #2a3443; width: 3px; height: 3px; }
"""


def main():
    if "--self-test" in sys.argv:
        run_self_test()
        return
    app = QApplication(sys.argv)
    app.setApplicationName("Minecraft Action Mod Studio")
    app.setOrganizationName("Codex")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


def run_self_test():
    report_path = Path(sys.argv[sys.argv.index("--self-test") + 1])
    work_dir = Path(sys.argv[sys.argv.index("--output-dir") + 1])
    work_dir.mkdir(parents=True, exist_ok=True)
    report = {}
    try:
        bb_project = import_bbmodel(r"D:\mc\skeleton_knight\skeleton_knight.bbmodel")
        report["bbmodel"] = {
            "bones": len(bb_project.bones),
            "parts": len(bb_project.parts),
            "animations": len(bb_project.animations),
        }
        bb_project.animations = [
            Animation("idle", 24, 1, 24, True),
            Animation("run", 24, 1, 24, True),
        ]
        for animation in bb_project.animations:
            for bone in bb_project.bones:
                if bone.startswith(("arm", "leg")):
                    animation.set_key(bone, 1, quat_from_euler_deg((0, 0, 0)))
                    animation.set_key(bone, 12, quat_from_euler_deg((18, 0, 0)))
                    animation.set_key(bone, 24, quat_from_euler_deg((0, 0, 0)))
        jar, project_file = export_mod(
            bb_project,
            bb_project.animations,
            "standalone_self_test",
            work_dir,
            False,
        )
        report["export"] = {
            "jar": str(jar),
            "jar_bytes": jar.stat().st_size,
            "project": str(project_file),
        }
        blend_project = import_blend(
            r"C:\Users\10859\Documents\Codex\2026-11-09\bang-w\project_player_model\model_source\player_model_run.blend"
        )
        report["blend"] = {
            "bones": len(blend_project.bones),
            "parts": len(blend_project.parts),
            "animations": [animation.name for animation in blend_project.animations],
        }
        report["ok"] = True
    except Exception as exc:
        report["ok"] = False
        report["error"] = str(exc)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    raise SystemExit(0 if report.get("ok") else 1)


if __name__ == "__main__":
    main()
