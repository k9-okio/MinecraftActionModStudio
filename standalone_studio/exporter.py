from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .core import Animation, Project, canonical_bone, quat_matrix, resource_path


def _safe_filename(name: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")
    return clean or "animation"


def _clip_from_animation(project: Project, animation: Animation) -> dict:
    bone_map = project.bone_name_map()
    frames = {animation.start, animation.end}
    for bone_name in bone_map.values():
        frames.update(animation.tracks.get(bone_name, {}).keys())
        frames.update(animation.locations.get(bone_name, {}).keys())
    frames = sorted(frames)
    if len(frames) > 180:
        step = (animation.end - animation.start) / 179.0
        frames = sorted(
            {int(round(animation.start + index * step)) for index in range(180)}
            | {animation.start, animation.end}
        )

    keys = []
    duration = max(1.0, float(animation.end - animation.start))
    for frame in frames:
        transforms = {}
        locations = {}
        for canonical, source_bone in bone_map.items():
            track = animation.tracks.get(source_bone)
            source = project.bones[source_bone]
            quaternion = animation.rotation_at(source_bone, frame)
            if track:
                if quaternion[0] < 0:
                    quaternion = -quaternion
                transforms[canonical] = [round(float(value), 8) for value in quaternion]
            location_track = animation.locations.get(source_bone)
            pivot = animation.pivots.get(source_bone)
            if location_track or pivot is not None:
                rotation = source.basis @ quat_matrix(quaternion) @ source.basis.T
                pivot_point = pivot if pivot is not None else source.head
                location_world = (
                    source.basis @ animation.location_at(source_bone, frame)
                    + (pivot_point - rotation @ pivot_point)
                    - (source.head - rotation @ source.head)
                )
                location = source.basis.T @ location_world
                locations[canonical] = [round(float(value), 8) for value in location]
        keys.append(
            {
                "phase": round((frame - animation.start) / duration, 8),
                "bones": transforms,
                "locations": locations,
            }
        )
    return {
        "name": animation.name,
        "source_fps": animation.fps,
        "source_frames": [animation.start, animation.end],
        "loop": animation.loop,
        "phase_source": "Minecraft walkAnimationPos",
        "keys": keys,
    }


def _run_build(project_dir: Path) -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(project_dir / "build.ps1"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
        cwd=str(project_dir),
    )
    if process.returncode != 0:
        raise RuntimeError((process.stderr or process.stdout or "Mod 构建失败").strip())
    return process.stdout


def export_mod(
    project: Project,
    animations: list[Animation],
    export_name: str,
    output_dir: str | Path,
    auto_install: bool = False,
) -> tuple[Path, Path | None]:
    if not animations:
        raise RuntimeError("至少选择一个动画")
    template = resource_path("standalone_studio/templates/player_model")
    if not template.exists():
        raise RuntimeError("内置 Mod 模板缺失")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="mcas_export_"))
    project_dir = work_dir / "player_model"
    shutil.copytree(template, project_dir)
    animations_dir = project_dir / "src/main/resources/assets/player_model/animations"
    if animations_dir.exists():
        shutil.rmtree(animations_dir)
    animations_dir.mkdir(parents=True)

    entries = []
    used = set()
    for animation in animations:
        filename = _safe_filename(animation.name) + ".json"
        index = 2
        while filename.lower() in used:
            filename = f"{_safe_filename(animation.name)}_{index}.json"
            index += 1
        used.add(filename.lower())
        clip = _clip_from_animation(project, animation)
        (animations_dir / filename).write_text(
            json.dumps(clip, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        entries.append({"name": animation.name, "file": filename})
    (animations_dir / "index.json").write_text(
        json.dumps({"clips": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    project.save(output_dir / f"{_safe_filename(export_name)}.mcasproj")
    _run_build(project_dir)
    built = project_dir / "build" / "libs" / "player_model-1.0.0.jar"
    if not built.exists():
        raise RuntimeError("构建完成但未找到 jar")
    destination = output_dir / f"{_safe_filename(export_name)}.jar"
    shutil.copy2(built, destination)
    if auto_install:
        for mod_dir in (
            Path(r"D:\mc\mods"),
            Path(r"D:\mc\versions\26.3-Forge_66.0.9\mods"),
        ):
            if mod_dir.exists():
                shutil.copy2(built, mod_dir / "player_model-1.0.0.jar")
    return destination, output_dir / f"{_safe_filename(export_name)}.mcasproj"
