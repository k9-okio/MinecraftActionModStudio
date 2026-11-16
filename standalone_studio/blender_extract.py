import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args():
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    return parser.parse_args(values)


def choose_armature():
    active = bpy.context.view_layer.objects.active
    if active and active.type == "ARMATURE":
        return active
    return next((obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"), None)


def sample_action(armature, action):
    scene = bpy.context.scene
    known_bones = {bone.name for bone in armature.data.bones}
    frames = set()
    for curve in action.fcurves:
        path = curve.data_path
        if not path.startswith('pose.bones["'):
            continue
        name = path.split('"]', 1)[0][len('pose.bones["') :]
        if name not in known_bones:
            continue
        for point in curve.keyframe_points:
            frames.add(float(point.co.x))

    start, end = [float(value) for value in action.frame_range]
    frames.add(start)
    frames.add(end)
    if len(frames) > 180:
        frames = {
            start + index * (end - start) / 179.0 for index in range(180)
        } | {end}

    previous = armature.animation_data.action if armature.animation_data else None
    armature.animation_data_create()
    armature.animation_data.action = action
    keys = []
    duration = max(1.0, end - start)
    for frame in sorted(frames):
        scene.frame_set(round(frame), subframe=frame - round(frame))
        bpy.context.view_layer.update()
        rotations = {}
        locations = {}
        deforms = {}
        for bone in armature.data.bones:
            matrix_basis = armature.pose.bones[bone.name].matrix_basis
            rotation = matrix_basis.to_quaternion()
            rotations[bone.name] = [
                round(rotation.w, 8),
                round(rotation.x, 8),
                round(rotation.y, 8),
                round(rotation.z, 8),
            ]
            location = matrix_basis.translation
            locations[bone.name] = [
                round(location.x, 8),
                round(location.y, 8),
                round(location.z, 8),
            ]
            deform = (
                armature.pose.bones[bone.name].matrix
                @ bone.matrix_local.inverted()
            )
            deforms[bone.name] = [
                [round(deform[row][column], 8) for column in range(4)]
                for row in range(4)
            ]
        keys.append(
            {
                "frame": round(frame, 5),
                "phase": round((frame - start) / duration, 8),
                "rotations": rotations,
                "locations": locations,
                "deforms": deforms,
            }
        )
    if armature.animation_data:
        armature.animation_data.action = previous
    return {
        "name": action.name,
        "fps": scene.render.fps / scene.render.fps_base,
        "start": start,
        "end": end,
        "loop": bool(action.use_cyclic),
        "keys": keys,
    }


def main():
    args = parse_args()
    output = Path(args.output)
    armature = choose_armature()
    if not armature:
        raise RuntimeError("Blend file does not contain an armature")

    inverse_armature = armature.matrix_world.inverted()
    bones = []
    for bone in armature.data.bones:
        basis = bone.matrix_local.to_3x3().normalized()
        bones.append(
            {
                "name": bone.name,
                "parent": bone.parent.name if bone.parent else None,
                "head": list(bone.head_local),
                "tail": list(bone.tail_local),
                "basis": [[basis[row][column] for column in range(3)] for row in range(3)],
                "rest_matrix": [
                    [bone.matrix_local[row][column] for column in range(4)]
                    for row in range(4)
                ],
                "deform": bone.use_deform,
            }
        )

    parts = []
    for mesh_object in bpy.context.scene.objects:
        if mesh_object.type != "MESH":
            continue
        if not any(
            modifier.type == "ARMATURE" and modifier.object == armature
            for modifier in mesh_object.modifiers
        ):
            continue
        group_names = {group.index: group.name for group in mesh_object.vertex_groups}
        vertex_bones = []
        for vertex in mesh_object.data.vertices:
            weights = [
                (group_names.get(item.group), item.weight)
                for item in vertex.groups
                if group_names.get(item.group) in armature.data.bones
            ]
            vertex_bones.append(
                max(weights, key=lambda pair: pair[1])[0] if weights else None
            )

        transformed_vertices = [
            inverse_armature @ (mesh_object.matrix_world @ vertex.co)
            for vertex in mesh_object.data.vertices
        ]
        material_groups = {}
        for polygon in mesh_object.data.polygons:
            material_groups.setdefault(polygon.material_index, []).append(polygon)

        for material_index, polygons in material_groups.items():
            used = sorted(
                {vertex_index for polygon in polygons for vertex_index in polygon.vertices}
            )
            index_map = {old_index: new_index for new_index, old_index in enumerate(used)}
            vertices = [
                list(transformed_vertices[index]) for index in used
            ]
            faces = [
                [index_map[index] for index in polygon.vertices]
                for polygon in polygons
            ]

            weights_by_bone = {}
            bone_totals = {}
            for new_index, vertex_index in enumerate(used):
                vertex = mesh_object.data.vertices[vertex_index]
                weights = [
                    (group_names.get(item.group), float(item.weight))
                    for item in vertex.groups
                    if group_names.get(item.group) in armature.data.bones
                    and item.weight > 0.000001
                ]
                if not weights:
                    root_name = next(
                        (bone.name for bone in armature.data.bones if bone.parent is None),
                        armature.data.bones[0].name if armature.data.bones else "root",
                    )
                    weights = [(root_name, 1.0)]
                weights.sort(key=lambda pair: pair[1], reverse=True)
                weights = weights[:4]
                total = sum(weight for _, weight in weights)
                for bone_name, weight in weights:
                    normalized = weight / max(1e-9, total)
                    values = weights_by_bone.setdefault(
                        bone_name, [0.0] * len(used)
                    )
                    values[new_index] = normalized
                    bone_totals[bone_name] = bone_totals.get(bone_name, 0.0) + normalized

            dominant_bone = max(bone_totals, key=bone_totals.get)
            color = [0.7, 0.7, 0.7, 1.0]
            if mesh_object.material_slots:
                material = mesh_object.material_slots[
                    min(material_index, len(mesh_object.material_slots) - 1)
                ].material
                if material:
                    color = list(material.diffuse_color)
            parts.append(
                {
                    "name": f"{mesh_object.name}:material_{material_index}",
                    "bone": dominant_bone,
                    "vertices": vertices,
                    "faces": faces,
                    "color": color,
                    "weights": weights_by_bone,
                }
            )

    animations = [
        sample_action(armature, action)
        for action in bpy.data.actions
        if action.fcurves
    ]
    result = {
        "format": "MinecraftActionStudioBlend",
        "version": 1,
        "name": bpy.path.basename(bpy.data.filepath).rsplit(".", 1)[0],
        "source": bpy.data.filepath,
        "bones": bones,
        "parts": parts,
        "animations": animations,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"MCAS_BLEND_EXTRACT_OK {output}")


main()
