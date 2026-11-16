from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from .core import BLENDER_EXE, Animation, Bone, MeshPart, Project, import_bbmodel, resource_path


def _run_blender_extract(blend_path: str | Path) -> dict:
    blend_path = Path(blend_path)
    if not BLENDER_EXE.exists():
        raise RuntimeError(f"找不到 Blender：{BLENDER_EXE}")
    helper = resource_path("standalone_studio/blender_extract.py")
    if not helper.exists():
        raise RuntimeError("Blender 转换脚本缺失，请重新安装软件")
    temp = Path(tempfile.mkdtemp(prefix="mcas_blend_"))
    output = temp / "model.json"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.run(
        [
            str(BLENDER_EXE),
            "--background",
            str(blend_path),
            "--python",
            str(helper),
            "--",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
        timeout=180,
    )
    if process.returncode != 0 or not output.exists():
        raise RuntimeError((process.stderr or process.stdout or "Blender 转换失败").strip())
    return json.loads(output.read_text(encoding="utf-8"))


def import_blend(path: str | Path) -> Project:
    data = _run_blender_extract(path)
    bones = {
        bone_data["name"]: Bone.from_dict(bone_data)
        for bone_data in data.get("bones") or []
    }
    parts = [MeshPart.from_dict(part) for part in data.get("parts") or []]
    animations = []
    for animation_data in data.get("animations") or []:
        animation = Animation(
            animation_data.get("name") or "action",
            float(animation_data.get("fps") or 24),
            int(round(float(animation_data.get("start") or 1))),
            int(round(float(animation_data.get("end") or 24))),
            bool(animation_data.get("loop", True)),
        )
        deform_by_bone = {}
        for key in animation_data.get("keys") or []:
            frame = int(round(float(key.get("frame") or 1)))
            for bone_name, rotation in (key.get("rotations") or {}).items():
                if bone_name in bones:
                    animation.set_key(
                        bone_name,
                        frame,
                        np.asarray(rotation, dtype=float),
                    )
            for bone_name, location in (key.get("locations") or {}).items():
                if bone_name in bones:
                    animation.set_location(
                        bone_name,
                        frame,
                        np.asarray(location, dtype=float),
                    )
            for bone_name, deform in (key.get("deforms") or {}).items():
                if bone_name in bones:
                    deform_by_bone.setdefault(bone_name, {})[frame] = np.asarray(
                        deform, dtype=float
                    )
        for bone_name, keys in deform_by_bone.items():
            for frame, deform in keys.items():
                animation.set_deform(bone_name, frame, deform)
        animations.append(animation)
    if not animations:
        animations.append(Animation("idle", 24, 1, 24, True))
    return Project(
        data.get("name") or Path(path).stem,
        str(path),
        bones,
        parts,
        animations,
    )
