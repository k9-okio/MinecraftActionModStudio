from __future__ import annotations

import base64
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


MOD_ID = "player_model"
MC_VERSION = "26.3"
FORGE_VERSION = "66.0.9"
BLENDER_EXE = Path(r"D:\Blender\blender-4.0.0-windows-x64\blender.exe")

CANONICAL_BONES = [
    "spine",
    "chest",
    "head",
    "upper_arm.L",
    "forearm.L",
    "upper_arm.R",
    "forearm.R",
    "thigh.L",
    "shin.L",
    "thigh.R",
    "shin.R",
]

ALIASES = {
    "body": "spine",
    "spine": "spine",
    "chest": "chest",
    "head": "head",
    "arm": "upper_arm.L",
    "armr": "upper_arm.R",
    "armfore": "forearm.L",
    "armrfore": "forearm.R",
    "leg": "thigh.L",
    "legr": "thigh.R",
    "legx": "shin.L",
    "legs": "shin.R",
    "armleft": "upper_arm.L",
    "armright": "upper_arm.R",
    "legleft": "thigh.L",
    "legright": "thigh.R",
    "armleftupper": "upper_arm.L",
    "armleftlower": "forearm.L",
    "upperarmleft": "upper_arm.L",
    "forearmleft": "forearm.L",
    "leftarm": "upper_arm.L",
    "leftforearm": "forearm.L",
    "armrightupper": "upper_arm.R",
    "armrightlower": "forearm.R",
    "upperarmright": "upper_arm.R",
    "forearmright": "forearm.R",
    "rightarm": "upper_arm.R",
    "rightforearm": "forearm.R",
    "legleftupper": "thigh.L",
    "legleftlower": "shin.L",
    "leftthigh": "thigh.L",
    "leftshin": "shin.L",
    "legrightupper": "thigh.R",
    "legrightlower": "shin.R",
    "rightthigh": "thigh.R",
    "rightshin": "shin.R",
}

PALETTE = [
    (0.72, 0.72, 0.72, 1.0),
    (0.82, 0.34, 0.28, 1.0),
    (0.27, 0.55, 0.86, 1.0),
    (0.33, 0.71, 0.34, 1.0),
    (0.86, 0.72, 0.24, 1.0),
    (0.58, 0.38, 0.78, 1.0),
    (0.30, 0.75, 0.74, 1.0),
    (0.88, 0.55, 0.25, 1.0),
]


def resource_path(relative: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / relative
    return Path(__file__).resolve().parent.parent / relative


def canonical_bone(name: str) -> str | None:
    normalized = re.sub(r"[^a-z0-9.]+", "", name.lower())
    if "arm" in normalized and "left" in normalized and "lower" in normalized:
        return "forearm.L"
    if "arm" in normalized and "left" in normalized and "upper" in normalized:
        return "upper_arm.L"
    if "arm" in normalized and "right" in normalized and "lower" in normalized:
        return "forearm.R"
    if "arm" in normalized and "right" in normalized and "upper" in normalized:
        return "upper_arm.R"
    if "leg" in normalized and "left" in normalized and "lower" in normalized:
        return "shin.L"
    if "leg" in normalized and "left" in normalized and "upper" in normalized:
        return "thigh.L"
    if "leg" in normalized and "right" in normalized and "lower" in normalized:
        return "shin.R"
    if "leg" in normalized and "right" in normalized and "upper" in normalized:
        return "thigh.R"
    return ALIASES.get(normalized)


def _safe_name(name: str, used: set[str]) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.:-]+", "_", name or "bone").strip("_") or "bone"
    candidate = clean
    index = 2
    while candidate in used:
        candidate = f"{clean}.{index}"
        index += 1
    used.add(candidate)
    return candidate


def make_basis(head: np.ndarray, tail: np.ndarray) -> np.ndarray:
    y_axis = np.asarray(tail, dtype=float) - np.asarray(head, dtype=float)
    length = np.linalg.norm(y_axis)
    if length < 1e-6:
        y_axis = np.array([0.0, 1.0, 0.0])
    else:
        y_axis /= length
    helper = np.array([1.0, 0.0, 0.0])
    if abs(float(np.dot(helper, y_axis))) > 0.9:
        helper = np.array([0.0, 0.0, 1.0])
    x_axis = np.cross(y_axis, helper)
    x_axis /= max(1e-9, np.linalg.norm(x_axis))
    z_axis = np.cross(x_axis, y_axis)
    z_axis /= max(1e-9, np.linalg.norm(z_axis))
    return np.column_stack((x_axis, y_axis, z_axis))


def euler_matrix_deg(rotation: tuple[float, float, float] | np.ndarray) -> np.ndarray:
    rx, ry, rz = np.radians(np.asarray(rotation, dtype=float))
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=float)
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=float)
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=float)
    return mz @ my @ mx


def quat_from_matrix(matrix: np.ndarray) -> np.ndarray:
    trace = float(np.trace(matrix))
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        w = 0.25 * s
        x = (matrix[2, 1] - matrix[1, 2]) / s
        y = (matrix[0, 2] - matrix[2, 0]) / s
        z = (matrix[1, 0] - matrix[0, 1]) / s
    elif matrix[0, 0] > matrix[1, 1] and matrix[0, 0] > matrix[2, 2]:
        s = math.sqrt(1.0 + matrix[0, 0] - matrix[1, 1] - matrix[2, 2]) * 2
        w = (matrix[2, 1] - matrix[1, 2]) / s
        x = 0.25 * s
        y = (matrix[0, 1] + matrix[1, 0]) / s
        z = (matrix[0, 2] + matrix[2, 0]) / s
    elif matrix[1, 1] > matrix[2, 2]:
        s = math.sqrt(1.0 + matrix[1, 1] - matrix[0, 0] - matrix[2, 2]) * 2
        w = (matrix[0, 2] - matrix[2, 0]) / s
        x = (matrix[0, 1] + matrix[1, 0]) / s
        y = 0.25 * s
        z = (matrix[1, 2] + matrix[2, 1]) / s
    else:
        s = math.sqrt(1.0 + matrix[2, 2] - matrix[0, 0] - matrix[1, 1]) * 2
        w = (matrix[1, 0] - matrix[0, 1]) / s
        x = (matrix[0, 2] + matrix[2, 0]) / s
        y = (matrix[1, 2] + matrix[2, 1]) / s
        z = 0.25 * s
    quaternion = np.array([w, x, y, z], dtype=float)
    return quaternion / max(1e-9, np.linalg.norm(quaternion))


def quat_from_euler_deg(rotation: tuple[float, float, float]) -> np.ndarray:
    return quat_from_matrix(euler_matrix_deg(rotation))


def quat_from_axis_deg(axis: np.ndarray, degrees: float) -> np.ndarray:
    axis = np.asarray(axis, dtype=float)
    length = float(np.linalg.norm(axis))
    if length < 1e-9:
        return np.array([1.0, 0.0, 0.0, 0.0])
    axis = axis / length
    half = math.radians(float(degrees)) * 0.5
    sine = math.sin(half)
    return np.array(
        [math.cos(half), axis[0] * sine, axis[1] * sine, axis[2] * sine]
    )


def quat_multiply(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    aw, ax, ay, az = np.asarray(a, dtype=float)
    bw, bx, by, bz = np.asarray(b, dtype=float)
    result = np.array(
        [
            aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
        ]
    )
    return result / max(1e-9, float(np.linalg.norm(result)))


def quat_matrix(quaternion: np.ndarray) -> np.ndarray:
    w, x, y, z = np.asarray(quaternion, dtype=float)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=float,
    )


def quat_to_euler_deg(quaternion: np.ndarray) -> tuple[float, float, float]:
    matrix = quat_matrix(quaternion)
    sy = -matrix[2, 0]
    sy = max(-1.0, min(1.0, sy))
    ry = math.asin(sy)
    if abs(math.cos(ry)) > 1e-6:
        rx = math.atan2(matrix[2, 1], matrix[2, 2])
        rz = math.atan2(matrix[1, 0], matrix[0, 0])
    else:
        rx = math.atan2(-matrix[1, 2], matrix[1, 1])
        rz = 0.0
    return tuple(math.degrees(value) for value in (rx, ry, rz))


def slerp(a: np.ndarray, b: np.ndarray, factor: float) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    dot = float(np.dot(a, b))
    if dot < 0:
        b = -b
        dot = -dot
    if dot > 0.9995:
        value = a + factor * (b - a)
        return value / max(1e-9, np.linalg.norm(value))
    theta = math.acos(max(-1.0, min(1.0, dot)))
    return (
        math.sin((1 - factor) * theta) * a + math.sin(factor * theta) * b
    ) / math.sin(theta)


def interpolate_matrix(a: np.ndarray, b: np.ndarray, factor: float) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    translation = a[:3, 3] * (1.0 - factor) + b[:3, 3] * factor
    qa = quat_from_matrix(a[:3, :3])
    qb = quat_from_matrix(b[:3, :3])
    rotation = quat_matrix(slerp(qa, qb, factor))
    return transform_matrix(translation, rotation)


def transform_matrix(translation: np.ndarray, rotation: np.ndarray) -> np.ndarray:
    result = np.eye(4)
    result[:3, :3] = rotation
    result[:3, 3] = translation
    return result


def rest_matrix_from_basis(head: np.ndarray, basis: np.ndarray) -> np.ndarray:
    result = np.eye(4)
    result[:3, :3] = np.asarray(basis, dtype=float)
    result[:3, 3] = np.asarray(head, dtype=float)
    return result


@dataclass
class Bone:
    name: str
    parent: str | None
    head: np.ndarray
    tail: np.ndarray
    basis: np.ndarray
    rest_matrix: np.ndarray | None = None
    deform: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "parent": self.parent,
            "head": self.head.tolist(),
            "tail": self.tail.tolist(),
            "basis": self.basis.tolist(),
            "rest_matrix": (
                self.rest_matrix.tolist()
                if self.rest_matrix is not None
                else None
            ),
            "deform": self.deform,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Bone":
        basis = np.asarray(value["basis"], dtype=float)
        rest_matrix = value.get("rest_matrix")
        if rest_matrix is None:
            rest_matrix = np.eye(4)
            rest_matrix[:3, :3] = basis
            rest_matrix[:3, 3] = np.asarray(value["head"], dtype=float)
        else:
            rest_matrix = np.asarray(rest_matrix, dtype=float)
        return cls(
            value["name"],
            value.get("parent"),
            np.asarray(value["head"], dtype=float),
            np.asarray(value["tail"], dtype=float),
            basis,
            rest_matrix,
            bool(value.get("deform", True)),
        )


@dataclass
class MeshPart:
    name: str
    bone: str
    vertices: np.ndarray
    faces: np.ndarray
    color: tuple[float, float, float, float] = (0.7, 0.7, 0.7, 1.0)
    weights: dict[str, np.ndarray] = field(default_factory=dict)
    face_uvs: list[list[list[float]]] = field(default_factory=list)
    texture_source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "bone": self.bone,
            "vertices": self.vertices.astype(float).tolist(),
            "faces": self.faces.astype(int).tolist(),
            "color": list(self.color),
            "weights": {
                bone: np.asarray(values, dtype=float).tolist()
                for bone, values in self.weights.items()
            },
            "face_uvs": self.face_uvs,
            "texture_source": self.texture_source,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MeshPart":
        return cls(
            value["name"],
            value["bone"],
            np.asarray(value["vertices"], dtype=float),
            np.asarray(value["faces"], dtype=int),
            tuple(value.get("color") or (0.7, 0.7, 0.7, 1.0)),
            {
                bone: np.asarray(values, dtype=float)
                for bone, values in (value.get("weights") or {}).items()
            },
            value.get("face_uvs") or [],
            value.get("texture_source") or "",
        )


@dataclass
class Animation:
    name: str
    fps: float = 24.0
    start: int = 1
    end: int = 24
    loop: bool = True
    tracks: dict[str, dict[int, np.ndarray]] = field(default_factory=dict)
    locations: dict[str, dict[int, np.ndarray]] = field(default_factory=dict)
    pivots: dict[str, np.ndarray] = field(default_factory=dict)
    deform_tracks: dict[str, dict[int, np.ndarray]] = field(default_factory=dict)

    def ensure_track(self, bone: str) -> dict[int, np.ndarray]:
        return self.tracks.setdefault(bone, {})

    def set_key(self, bone: str, frame: int, quaternion: np.ndarray) -> None:
        self.tracks.setdefault(bone, {})[int(frame)] = np.asarray(quaternion, dtype=float)
        self.deform_tracks.pop(bone, None)
        self.end = max(self.end, int(frame))

    def remove_key(self, bone: str, frame: int) -> None:
        self.tracks.get(bone, {}).pop(int(frame), None)
        if not self.tracks.get(bone):
            self.tracks.pop(bone, None)
        self.locations.get(bone, {}).pop(int(frame), None)
        if not self.locations.get(bone):
            self.locations.pop(bone, None)

    def set_location(self, bone: str, frame: int, location: np.ndarray) -> None:
        self.locations.setdefault(bone, {})[int(frame)] = np.asarray(location, dtype=float)
        self.end = max(self.end, int(frame))

    def location_at(self, bone: str, frame: float) -> np.ndarray:
        track = self.locations.get(bone)
        if not track:
            return np.zeros(3)
        frames = sorted(track)
        if frame <= frames[0]:
            return track[frames[0]]
        if frame >= frames[-1]:
            return track[frames[-1]]
        for first, second in zip(frames, frames[1:]):
            if first <= frame <= second:
                factor = (frame - first) / max(1.0, second - first)
                return track[first] * (1.0 - factor) + track[second] * factor
        return track[frames[-1]]

    def set_pivot(self, bone: str, pivot: np.ndarray | None) -> None:
        self.deform_tracks.pop(bone, None)
        if pivot is None:
            self.pivots.pop(bone, None)
        else:
            self.pivots[bone] = np.asarray(pivot, dtype=float)

    def set_deform(self, bone: str, frame: int, matrix: np.ndarray) -> None:
        self.deform_tracks.setdefault(bone, {})[int(frame)] = np.asarray(matrix, dtype=float)

    def deform_at(self, bone: str, frame: float) -> np.ndarray | None:
        track = self.deform_tracks.get(bone)
        if not track:
            return None
        frames = sorted(track)
        if frame <= frames[0]:
            return track[frames[0]]
        if frame >= frames[-1]:
            return track[frames[-1]]
        for first, second in zip(frames, frames[1:]):
            if first <= frame <= second:
                factor = (frame - first) / max(1.0, second - first)
                return interpolate_matrix(track[first], track[second], factor)
        return track[frames[-1]]

    def rotation_at(self, bone: str, frame: float) -> np.ndarray:
        track = self.tracks.get(bone)
        if not track:
            return np.array([1.0, 0.0, 0.0, 0.0])
        frames = sorted(track)
        if frame <= frames[0]:
            return track[frames[0]]
        if frame >= frames[-1]:
            return track[frames[-1]]
        for first, second in zip(frames, frames[1:]):
            if first <= frame <= second:
                factor = (frame - first) / max(1.0, second - first)
                return slerp(track[first], track[second], factor)
        return track[frames[-1]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "fps": self.fps,
            "start": self.start,
            "end": self.end,
            "loop": self.loop,
            "tracks": {
                bone: {
                    str(frame): quaternion.tolist()
                    for frame, quaternion in sorted(keys.items())
                }
                for bone, keys in self.tracks.items()
            },
            "locations": {
                bone: {
                    str(frame): location.tolist()
                    for frame, location in sorted(keys.items())
                }
                for bone, keys in self.locations.items()
            },
            "pivots": {
                bone: pivot.tolist()
                for bone, pivot in self.pivots.items()
            },
            "deform_tracks": {
                bone: {
                    str(frame): matrix.tolist()
                    for frame, matrix in sorted(keys.items())
                }
                for bone, keys in self.deform_tracks.items()
            },
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Animation":
        return cls(
            value["name"],
            float(value.get("fps") or 24),
            int(value.get("start") or 1),
            int(value.get("end") or 24),
            bool(value.get("loop", True)),
            {
                bone: {
                    int(frame): np.asarray(quaternion, dtype=float)
                    for frame, quaternion in keys.items()
                }
                for bone, keys in (value.get("tracks") or {}).items()
            },
            {
                bone: {
                    int(frame): np.asarray(location, dtype=float)
                    for frame, location in keys.items()
                }
                for bone, keys in (value.get("locations") or {}).items()
            },
            {
                bone: np.asarray(pivot, dtype=float)
                for bone, pivot in (value.get("pivots") or {}).items()
            },
            {
                bone: {
                    int(frame): np.asarray(matrix, dtype=float)
                    for frame, matrix in keys.items()
                }
                for bone, keys in (value.get("deform_tracks") or {}).items()
            },
        )


@dataclass
class Project:
    name: str = "Untitled"
    source: str = ""
    bones: dict[str, Bone] = field(default_factory=dict)
    parts: list[MeshPart] = field(default_factory=list)
    animations: list[Animation] = field(default_factory=list)

    def animation(self, name: str) -> Animation | None:
        return next((animation for animation in self.animations if animation.name == name), None)

    def bone_name_map(self) -> dict[str, str]:
        result = {}
        for bone in self.bones:
            canonical = canonical_bone(bone)
            if canonical and canonical not in result:
                result[canonical] = bone
        return result

    def bone_transforms(self, animation: Animation | None, frame: float) -> dict[str, np.ndarray]:
        rotations = {
            name: (
                animation.rotation_at(name, frame)
                if animation
                else np.array([1.0, 0.0, 0.0, 0.0])
            )
            for name in self.bones
        }
        locations = {
            name: animation.location_at(name, frame) if animation else np.zeros(3)
            for name in self.bones
        }
        transforms: dict[str, np.ndarray] = {}
        pose_matrices: dict[str, np.ndarray] = {}

        def visit(name: str, stack: set[str]) -> np.ndarray:
            if name in transforms:
                return transforms[name]
            if name in stack:
                return np.eye(4)
            bone = self.bones[name]
            if animation:
                exact = animation.deform_at(name, frame)
                if exact is not None:
                    transforms[name] = exact
                    rest = (
                        bone.rest_matrix
                        if bone.rest_matrix is not None
                        else rest_matrix_from_basis(bone.head, bone.basis)
                    )
                    pose_matrices[name] = exact @ rest
                    return exact
            parent_transform = (
                visit(bone.parent, stack | {name})
                if bone.parent in self.bones
                else np.eye(4)
            )
            local_basis = (
                transform_matrix(locations[name], np.eye(3))
                @ transform_matrix((0, 0, 0), quat_matrix(rotations[name]))
            )
            if bone.parent in self.bones:
                parent_rest = self.bones[bone.parent].rest_matrix
                bone_rest = bone.rest_matrix
                if parent_rest is not None and bone_rest is not None:
                    pose = (
                        pose_matrices[bone.parent]
                        @ np.linalg.inv(parent_rest)
                        @ bone_rest
                        @ local_basis
                    )
                else:
                    pose = parent_transform @ local_basis
            else:
                bone_rest = (
                    bone.rest_matrix
                    if bone.rest_matrix is not None
                    else rest_matrix_from_basis(bone.head, bone.basis)
                )
                pose = bone_rest @ local_basis
            pose_matrices[name] = pose
            rest = (
                bone.rest_matrix
                if bone.rest_matrix is not None
                else rest_matrix_from_basis(bone.head, bone.basis)
            )
            exact_deform = pose @ np.linalg.inv(rest)

            if animation and name in animation.pivots:
                pivot = animation.pivots[name]
                world_rotation = (
                    bone.basis @ quat_matrix(rotations[name]) @ bone.basis.T
                )
                translation = (
                    bone.basis @ locations[name]
                    + (pivot - world_rotation @ pivot)
                    - (bone.head - world_rotation @ bone.head)
                )
                local = (
                    transform_matrix(translation, np.eye(3))
                    @ transform_matrix(bone.head, world_rotation)
                    @ transform_matrix(-bone.head, np.eye(3))
                )
                transforms[name] = parent_transform @ local
            else:
                transforms[name] = exact_deform
            return transforms[name]

        for name in self.bones:
            visit(name, set())
        return transforms

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "MinecraftActionStudio",
            "version": 1,
            "name": self.name,
            "source": self.source,
            "bones": [bone.to_dict() for bone in self.bones.values()],
            "parts": [part.to_dict() for part in self.parts],
            "animations": [animation.to_dict() for animation in self.animations],
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Project":
        return cls(
            value.get("name") or "Untitled",
            value.get("source") or "",
            {
                bone["name"]: Bone.from_dict(bone)
                for bone in value.get("bones") or []
            },
            [MeshPart.from_dict(part) for part in value.get("parts") or []],
            [Animation.from_dict(animation) for animation in value.get("animations") or []],
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: str | Path) -> "Project":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _convert_bb_point(value) -> np.ndarray:
    x, y, z = (float(value[index]) for index in range(3))
    return np.array([x / 16.0, -z / 16.0, y / 16.0], dtype=float)


def _float3(value, fallback=(0.0, 0.0, 0.0)) -> np.ndarray:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return np.asarray(fallback, dtype=float)
    return np.asarray([float(value[index]) for index in range(3)], dtype=float)


def _bb_rotation_matrix(value) -> np.ndarray:
    base = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]])
    rotation = base @ euler_matrix_deg(value or (0, 0, 0)) @ base.T
    return rotation


def import_bbmodel(
    path: str | Path,
    import_bones: bool = True,
    import_animations: bool = True,
) -> Project:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    groups = {group["uuid"]: group for group in data.get("groups") or []}
    elements = {element["uuid"]: element for element in data.get("elements") or []}
    textures = data.get("textures") or []
    parent_of: dict[str, str] = {}
    element_owner: dict[str, str | None] = {}

    def walk(items, parent_group=None):
        for item in items or []:
            if isinstance(item, str):
                element_owner[item] = parent_group
            elif isinstance(item, dict):
                uuid = item.get("uuid")
                if uuid in groups:
                    if parent_group:
                        parent_of[uuid] = parent_group
                    walk(item.get("children"), uuid)
                elif uuid in elements:
                    element_owner[uuid] = parent_group

    walk(data.get("outliner"))
    used = set()
    names = {uuid: _safe_name(group.get("name", "bone"), used) for uuid, group in groups.items()}

    def group_center(uuid):
        points = []
        for element_uuid, owner in element_owner.items():
            if owner == uuid and element_uuid in elements:
                element = elements[element_uuid]
                if element.get("from") and element.get("to"):
                    points.append(
                        (_float3(element["from"]) + _float3(element["to"])) * 0.5
                    )
        if points:
            return sum(points, np.zeros(3)) / len(points)
        return _float3(groups[uuid].get("origin") or (0, 0, 0))

    group_transforms = {}

    def group_transform(uuid, stack=None):
        if uuid in group_transforms:
            return group_transforms[uuid]
        stack = stack or set()
        if uuid in stack:
            return np.eye(4)
        group = groups[uuid]
        parent_uuid = parent_of.get(uuid)
        origin = np.asarray(group.get("origin") or (0, 0, 0), dtype=float)
        rotation = euler_matrix_deg(group.get("rotation") or (0, 0, 0))
        if parent_uuid in groups:
            parent_group = groups[parent_uuid]
            parent_origin = np.asarray(
                parent_group.get("origin") or (0, 0, 0), dtype=float
            )
            parent_transform = group_transform(parent_uuid, stack | {uuid})
            result = (
                parent_transform
                @ transform_matrix(origin - parent_origin, np.eye(3))
                @ transform_matrix((0, 0, 0), rotation)
            )
        else:
            result = (
                transform_matrix(origin, np.eye(3))
                @ transform_matrix((0, 0, 0), rotation)
            )
        group_transforms[uuid] = result
        return result

    for uuid in groups:
        group_transform(uuid)

    bones = {}
    if import_bones:
        for uuid, group in groups.items():
            group_matrix = group_transform(uuid)
            head_bb = (group_matrix @ np.array([0.0, 0.0, 0.0, 1.0]))[:3]
            children = [child for child in groups if parent_of.get(child) == uuid]
            if children:
                child_origin = np.asarray(
                    groups[children[0]].get("origin") or (0, 0, 0), dtype=float
                )
                group_origin = np.asarray(group.get("origin") or (0, 0, 0), dtype=float)
                tail_bb = (
                    group_matrix @ np.append(child_origin - group_origin, 1.0)
                )[:3]
            else:
                center_bb = group_center(uuid)
                group_origin = np.asarray(group.get("origin") or (0, 0, 0), dtype=float)
                tail_bb = (
                    group_matrix @ np.append(center_bb - group_origin, 1.0)
                )[:3]
            head = _convert_bb_point(head_bb)
            tail = _convert_bb_point(tail_bb)
            if np.linalg.norm(tail - head) < 0.01:
                tail = head + np.array([0.0, 0.25, 0.0])
            basis = make_basis(head, tail)
            bones[names[uuid]] = Bone(
                names[uuid],
                names.get(parent_of.get(uuid)),
                head,
                tail,
                basis,
                rest_matrix_from_basis(head, basis),
            )

    if import_bones and not bones:
        basis = np.eye(3)
        bones["root"] = Bone(
            "root",
            None,
            np.zeros(3),
            np.array([0.0, 0.5, 0.0]),
            basis,
            rest_matrix_from_basis(np.zeros(3), basis),
        )

    face_indices = {
        "north": (0, 1, 2, 3),
        "south": (5, 4, 7, 6),
        "west": (4, 0, 3, 7),
        "east": (1, 5, 6, 2),
        "up": (3, 2, 6, 7),
        "down": (4, 5, 1, 0),
    }
    parts = []
    for element_uuid, element in elements.items():
        if not element.get("export", True) or not element.get("from") or not element.get("to"):
            continue
        low = np.asarray(element["from"], dtype=float)
        high = np.asarray(element["to"], dtype=float)
        origin = np.asarray(element.get("origin") or ((low + high) * 0.5), dtype=float)
        rotation_bb = euler_matrix_deg(element.get("rotation") or (0, 0, 0))
        corners = [
            np.array((low[0], low[1], low[2])),
            np.array((high[0], low[1], low[2])),
            np.array((high[0], high[1], low[2])),
            np.array((low[0], high[1], low[2])),
            np.array((low[0], low[1], high[2])),
            np.array((high[0], low[1], high[2])),
            np.array((high[0], high[1], high[2])),
            np.array((low[0], high[1], high[2])),
        ]
        owner_uuid = element_owner.get(element_uuid)
        if owner_uuid in groups:
            group_origin = np.asarray(
                groups[owner_uuid].get("origin") or (0, 0, 0), dtype=float
            )
            element_transform = (
                group_transforms[owner_uuid]
                @ transform_matrix(origin - group_origin, np.eye(3))
                @ transform_matrix((0, 0, 0), rotation_bb)
                @ transform_matrix(-origin, np.eye(3))
            )
        else:
            element_transform = (
                transform_matrix(origin, np.eye(3))
                @ transform_matrix((0, 0, 0), rotation_bb)
                @ transform_matrix(-origin, np.eye(3))
            )
        vertices_bb = (
            element_transform
            @ np.concatenate(
                (
                    np.asarray(corners, dtype=float),
                    np.ones((len(corners), 1), dtype=float),
                ),
                axis=1,
            ).T
        ).T[:, :3]
        element_vertices = np.asarray(
            [_convert_bb_point(point) for point in vertices_bb],
            dtype=float,
        )
        element_faces = element.get("faces") or {}
        grouped_faces = {}
        for face_name in face_indices:
            face_data = element_faces.get(face_name)
            if face_data is None:
                continue
            texture_index = int(face_data.get("texture", 0) or 0)
            grouped_faces.setdefault(texture_index, []).append((face_name, face_data))
        if not grouped_faces:
            grouped_faces[0] = [
                (
                    face_name,
                    {"uv": (0, 0, 16, 16), "texture": 0},
                )
                for face_name in face_indices
            ]
        vertices = element_vertices
        fallback_bone = next(iter(bones), "")
        bone_name = names.get(owner_uuid, fallback_bone) if import_bones else ""
        color_index = int(element.get("color") or 0)
        for texture_index, face_group in grouped_faces.items():
            faces = []
            face_uvs = []
            texture = textures[texture_index] if 0 <= texture_index < len(textures) else {}
            texture_width = float(texture.get("width") or texture.get("uv_width") or 64)
            texture_height = float(texture.get("height") or texture.get("uv_height") or 64)
            for face_name, face_data in face_group:
                faces.append(face_indices[face_name])
                u1, v1, u2, v2 = [
                    float(value) for value in (face_data.get("uv") or (0, 0, texture_width, texture_height))
                ]
                face_uvs.append(
                    [
                        [u1 / texture_width, 1.0 - v2 / texture_height],
                        [u2 / texture_width, 1.0 - v2 / texture_height],
                        [u2 / texture_width, 1.0 - v1 / texture_height],
                        [u1 / texture_width, 1.0 - v1 / texture_height],
                    ]
                )
            source = texture.get("source") or ""
            if not source and texture.get("relative_path"):
                source = texture["relative_path"]
            parts.append(
                MeshPart(
                    f"{element.get('name') or 'cube'}:texture_{texture_index}",
                    bone_name,
                    vertices,
                    np.asarray(faces, dtype=int),
                    PALETTE[color_index % len(PALETTE)],
                    {},
                    face_uvs,
                    source,
                )
            )

    animations = []
    fps = 24.0
    for animation_data in (data.get("animations") or [] if import_animations and bones else []):
        animation = Animation(
            animation_data.get("name") or f"action_{len(animations) + 1}",
            fps,
            1,
            max(2, int(round(float(animation_data.get("length") or 1) * fps)) + 1),
            str(animation_data.get("loop", "once")).lower() == "loop",
        )
        for animator_uuid, animator in (animation_data.get("animators") or {}).items():
            bone_name = names.get(animator_uuid)
            if not bone_name:
                continue
            keyframes = animator.get("keyframes") or {}
            normalized = []
            if isinstance(keyframes, dict):
                for channel, points in keyframes.items():
                    for point in points:
                        normalized.append(
                            (
                                channel,
                                float(point.get("time") or 0),
                                _float_xyz(point),
                            )
                        )
            elif isinstance(keyframes, list):
                for point in keyframes:
                    points = point.get("data_points") or []
                    if points:
                        normalized.append(
                            (
                                point.get("channel"),
                                float(point.get("time") or 0),
                                _float_xyz(points[0]),
                            )
                        )

            bone = bones[bone_name]
            for channel, time, values in normalized:
                if values is None or channel != "rotation":
                    if values is not None and channel == "position":
                        frame = int(round(1 + time * fps))
                        animation.set_location(
                            bone_name,
                            frame,
                            bone.basis.T @ _convert_bb_point(values),
                        )
                        animation.end = max(animation.end, frame)
                    continue
                world_rotation = _bb_rotation_matrix(values)
                local_rotation = bone.basis.T @ world_rotation @ bone.basis
                frame = int(round(1 + time * fps))
                animation.set_key(bone_name, frame, quat_from_matrix(local_rotation))
                animation.end = max(animation.end, frame)
        animations.append(animation)

    if not animations:
        animations.append(Animation("idle", 24, 1, 24, True))
    return Project(path.stem, str(path), bones, parts, animations)


def _float_xyz(value):
    try:
        return (
            float(value.get("x", 0)),
            float(value.get("y", 0)),
            float(value.get("z", 0)),
        )
    except (TypeError, ValueError, AttributeError):
        return None
