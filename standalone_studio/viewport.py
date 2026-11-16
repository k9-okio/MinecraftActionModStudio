from __future__ import annotations

import math
import base64
from pathlib import Path

import numpy as np
import pyqtgraph.opengl as gl
from OpenGL import GL
from PySide6.QtGui import QImage
from PySide6.QtOpenGL import QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram, QOpenGLTexture
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QVector3D, QVector4D

from .core import Animation, Project


class GLTexturedMeshItem(gl.GLGraphicsItem.GLGraphicsItem):
    _shared_program = None
    _shared_textures = {}

    def __init__(self, vertexes, faces, face_uvs, texture_source, parentItem=None):
        super().__init__(parentItem=parentItem)
        self.setGLOptions("opaque")
        self.program = None
        self.texture = None
        self.position_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self.uv_buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self.render_indices = []
        self.uv_data = []
        for face, uvs in zip(faces, face_uvs):
            if len(face) < 3 or len(uvs) < 3:
                continue
            for index in range(1, len(face) - 1):
                self.render_indices.extend((face[0], face[index], face[index + 1]))
                self.uv_data.extend((uvs[0], uvs[index], uvs[index + 1]))
        self.render_indices = np.asarray(self.render_indices, dtype=np.int32)
        self.uv_data = np.asarray(self.uv_data, dtype=np.float32)
        self.position_data = np.zeros((len(self.render_indices), 3), dtype=np.float32)
        self.texture_source = texture_source
        self.dirty = True
        self.setPositions(vertexes)

    def setPositions(self, vertices):
        vertices = np.asarray(vertices, dtype=np.float32)
        self.position_data = vertices[self.render_indices].astype(np.float32)
        self.dirty = True
        self.update()

    def load_texture(self):
        source = self.texture_source
        if not source:
            return None
        if source.startswith("data:image/") and "," in source:
            image = QImage.fromData(base64.b64decode(source.split(",", 1)[1]))
        else:
            path = Path(source)
            if not path.exists():
                return None
            image = QImage(str(path))
        if image.isNull():
            return None
        image = image.convertToFormat(QImage.Format.Format_RGBA8888).mirrored(False, True)
        texture = QOpenGLTexture(image)
        texture.setMinMagFilters(
            QOpenGLTexture.Filter.Nearest,
            QOpenGLTexture.Filter.Nearest,
        )
        texture.setWrapMode(QOpenGLTexture.WrapMode.ClampToEdge)
        return texture

    def ensure_gl(self):
        if self.program is None:
            if GLTexturedMeshItem._shared_program is None:
                program = QOpenGLShaderProgram()
                program.addShaderFromSourceCode(
                    QOpenGLShader.ShaderTypeBit.Vertex,
                    """
                    #version 120
                    attribute vec3 a_position;
                    attribute vec2 a_uv;
                    uniform mat4 u_mvp;
                    varying vec2 v_uv;
                    void main() {
                        gl_Position = u_mvp * vec4(a_position, 1.0);
                        v_uv = a_uv;
                    }
                    """,
                )
                program.addShaderFromSourceCode(
                    QOpenGLShader.ShaderTypeBit.Fragment,
                    """
                    #version 120
                    uniform sampler2D u_texture;
                    varying vec2 v_uv;
                    void main() {
                        vec4 color = texture2D(u_texture, v_uv);
                        if (color.a < 0.05) discard;
                        gl_FragColor = color;
                    }
                    """,
                )
                program.link()
                GLTexturedMeshItem._shared_program = program
            self.program = GLTexturedMeshItem._shared_program
        if self.texture is None:
            key = hash(self.texture_source)
            self.texture = GLTexturedMeshItem._shared_textures.get(key)
            if self.texture is None:
                self.texture = self.load_texture()
                if self.texture is not None:
                    GLTexturedMeshItem._shared_textures[key] = self.texture
        if not self.position_buffer.isCreated():
            self.position_buffer.create()
        if not self.uv_buffer.isCreated():
            self.uv_buffer.create()
            self.uv_buffer.bind()
            self.uv_buffer.allocate(self.uv_data.tobytes(), self.uv_data.nbytes)
            self.uv_buffer.release()

    def paint(self):
        if self.texture is None and self.program is None:
            pass
        self.ensure_gl()
        if self.texture is None:
            return
        self.setupGLState()
        if self.dirty:
            self.position_buffer.bind()
            if self.position_buffer.size() == self.position_data.nbytes:
                self.position_buffer.write(0, self.position_data.tobytes(), self.position_data.nbytes)
            else:
                self.position_buffer.allocate(
                    self.position_data.tobytes(), self.position_data.nbytes
                )
            self.position_buffer.release()
            self.dirty = False

        mvp = self.mvpMatrix()
        self.program.bind()
        self.program.setUniformValue1i("u_texture", 0)
        self.program.setUniformValue("u_mvp", mvp)

        location = self.program.attributeLocation("a_position")
        self.position_buffer.bind()
        self.program.enableAttributeArray(location)
        self.program.setAttributeBuffer(location, GL.GL_FLOAT, 0, 3)
        self.position_buffer.release()

        uv_location = self.program.attributeLocation("a_uv")
        self.uv_buffer.bind()
        self.program.enableAttributeArray(uv_location)
        self.program.setAttributeBuffer(uv_location, GL.GL_FLOAT, 0, 2)
        self.uv_buffer.release()

        GL.glActiveTexture(GL.GL_TEXTURE0)
        self.texture.bind()
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, len(self.position_data))
        self.texture.release()
        self.program.disableAttributeArray(location)
        self.program.disableAttributeArray(uv_location)
        self.program.release()


class ModelViewport(gl.GLViewWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setBackgroundColor(QColor(24, 27, 34))
        self.setCameraPosition(distance=4.2, elevation=18, azimuth=-42)
        self.mesh_items = []
        self.bone_mesh_items = {}
        self._bone_segments = {}
        self._part_vertices = []
        self.joints = gl.GLScatterPlotItem(
            pos=np.zeros((1, 3)),
            color=(0.55, 0.9, 1.0, 1.0),
            size=9,
        )
        self.joints.setGLOptions("additive")
        self.joints.setDepthValue(1001)
        self.addItem(self.joints)
        self.rotate_rings = []
        for color in (
            (1.0, 0.25, 0.25, 0.9),
            (0.25, 1.0, 0.35, 0.9),
            (0.3, 0.55, 1.0, 0.9),
        ):
            ring = gl.GLLinePlotItem(
                pos=np.zeros((2, 3)),
                color=color,
                width=3,
                antialias=True,
                mode="line_strip",
            )
            ring.setGLOptions("additive")
            ring.setDepthValue(1003)
            self.addItem(ring)
            self.rotate_rings.append(ring)
        self.gizmo_arrows = []
        for color in (
            (1.0, 0.32, 0.28, 1.0),
            (0.35, 1.0, 0.45, 1.0),
            (0.4, 0.62, 1.0, 1.0),
        ):
            shaft = gl.GLLinePlotItem(
                pos=np.zeros((2, 3)),
                color=color,
                width=4,
                antialias=True,
                mode="lines",
            )
            shaft.setGLOptions("additive")
            shaft.setDepthValue(1002)
            self.addItem(shaft)
            head = gl.GLMeshItem(
                vertexes=np.zeros((5, 3)),
                faces=np.asarray(
                    [
                        (0, 1, 2),
                        (0, 2, 3),
                        (0, 3, 4),
                        (0, 4, 1),
                        (1, 2, 3),
                        (1, 3, 4),
                    ],
                    dtype=np.uint32,
                ),
                faceColors=np.tile(color, (6, 1)),
                smooth=False,
                shader="shaded",
            )
            head.setGLOptions("additive")
            head.setDepthValue(1002)
            self.addItem(head)
            self.gizmo_arrows.append((shaft, head))
        self.pivot_marker = gl.GLScatterPlotItem(
            pos=np.zeros((1, 3)),
            color=(1.0, 0.25, 0.85, 1.0),
            size=14,
        )
        self.pivot_marker.setGLOptions("additive")
        self.pivot_marker.setDepthValue(1004)
        self.addItem(self.pivot_marker)
        self.selection_box = gl.GLLinePlotItem(
            pos=np.zeros((0, 3)),
            color=(1.0, 0.62, 0.15, 1.0),
            width=2,
            antialias=True,
            mode="lines",
        )
        self.selection_box.setGLOptions("additive")
        self.selection_box.setDepthValue(1005)
        self.addItem(self.selection_box)
        self.grid = gl.GLGridItem()
        self.grid.setSize(8, 8)
        self.grid.setSpacing(0.5, 0.5)
        self.addItem(self.grid)
        self.project: Project | None = None
        self.direct_edit_enabled = False
        self.transform_mode = "rotate"
        self.transform_callback = None
        self.pick_callback = None
        self.whole_model_mode = False
        self.whole_model_bone = None
        self.locked_bone = None
        self.selected_parts = set()
        self._last_animation = None
        self._last_frame = 1.0
        self._last_selected_bone = None
        self._last_pivot_marker = None
        self._dragging_transform = False
        self._last_mouse = QPointF()
        self._press_position = QPointF()
        self.gizmo_callback = None
        self.mode_callback = None
        self.gizmo_scale = 0.25
        self._gizmo_center = None
        self._gizmo_axis = None
        self._gizmo_dragging = False
        self.AXES = (
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
            np.array([0.0, 0.0, 1.0]),
        )

    def set_project(self, project: Project):
        for item in self.mesh_items:
            self.removeItem(item)
        self.mesh_items.clear()
        for item in self.bone_mesh_items.values():
            self.removeItem(item)
        self.bone_mesh_items.clear()
        self.project = project
        for part in project.parts:
            if part.face_uvs and part.texture_source:
                item = GLTexturedMeshItem(
                    part.vertices,
                    part.faces,
                    part.face_uvs,
                    part.texture_source,
                )
                item._mcas_textured = True
            else:
                source_faces = np.asarray(part.faces, dtype=np.uint32)
                triangles = []
                for face in source_faces:
                    if len(face) < 3:
                        continue
                    for index in range(1, len(face) - 1):
                        triangles.append((face[0], face[index], face[index + 1]))
                faces = np.asarray(triangles, dtype=np.uint32)
                colors = np.tile(np.asarray(part.color, dtype=float), (len(faces), 1))
                item = gl.GLMeshItem(
                    vertexes=np.asarray(part.vertices),
                    faces=faces,
                    faceColors=colors,
                    smooth=False,
                    drawEdges=True,
                    edgeColor=(0.05, 0.06, 0.08, 0.75),
                    shader="shaded",
                )
                item._mcas_textured = False
                item._mcas_faces = faces
                item._mcas_colors = colors
            self.addItem(item)
            self.mesh_items.append(item)

        self.sync_bones()

        if project.parts:
            all_vertices = np.concatenate([part.vertices for part in project.parts], axis=0)
            minimum = all_vertices.min(axis=0)
            maximum = all_vertices.max(axis=0)
            center = (minimum + maximum) * 0.5
            size = max(1.5, float(np.linalg.norm(maximum - minimum)))
            self.gizmo_scale = max(0.22, min(0.7, size * 0.16))
            self.setCameraPosition(
                pos=QVector3D(float(center[0]), float(center[1]), float(center[2])),
                distance=size * 2.2,
                elevation=18,
                azimuth=-42,
            )
            self.grid.resetTransform()
            self.grid.translate(center[0] - 4, center[1] - 4, minimum[2] - 0.01)
        self.update_pose(None, 1.0, None, None)

    @staticmethod
    def make_bone_item():
        return gl.GLMeshItem(
            vertexes=np.zeros((6, 3)),
            faces=np.asarray(
                [
                    (0, 1, 2),
                    (0, 2, 3),
                    (0, 3, 4),
                    (0, 4, 1),
                    (5, 2, 1),
                    (5, 3, 2),
                    (5, 4, 3),
                    (5, 1, 4),
                ],
                dtype=np.uint32,
            ),
            faceColors=np.tile((0.55, 0.62, 0.7, 0.9), (8, 1)),
            smooth=False,
            drawEdges=True,
            edgeColor=(0.85, 0.9, 0.95, 0.9),
            shader="shaded",
        )

    def sync_bones(self):
        if self.project is None:
            return
        for name in list(self.bone_mesh_items):
            if name not in self.project.bones:
                self.removeItem(self.bone_mesh_items.pop(name))
        for name in self.project.bones:
            if name in self.bone_mesh_items:
                continue
            item = self.make_bone_item()
            item.setGLOptions("additive")
            item.setDepthValue(1000)
            self.addItem(item)
            self.bone_mesh_items[name] = item

    def set_selected_parts(self, indices):
        self.selected_parts = {int(index) for index in indices}
        self.update_pose(
            self._last_animation,
            self._last_frame,
            self._last_selected_bone,
            self._last_pivot_marker,
        )

    def update_pose(
        self,
        animation: Animation | None,
        frame: float,
        selected_bone: str | None,
        pivot_marker: np.ndarray | None = None,
    ):
        if not self.project:
            return
        self._last_animation = animation
        self._last_frame = float(frame)
        self._last_selected_bone = selected_bone
        self._last_pivot_marker = pivot_marker
        transforms = self.project.bone_transforms(animation, frame)
        self._part_vertices = []

        for item, part in zip(self.mesh_items, self.project.parts):
            vertices = np.asarray(part.vertices, dtype=float)
            homogeneous = np.concatenate(
                (vertices, np.ones((len(vertices), 1), dtype=float)), axis=1
            )
            if part.weights:
                transformed = np.zeros_like(vertices)
                for bone_name, weights in part.weights.items():
                    transform = transforms.get(bone_name, np.eye(4))
                    bone_vertices = (transform @ homogeneous.T).T[:, :3]
                    transformed += np.asarray(weights)[:, None] * bone_vertices
            else:
                transform = transforms.get(part.bone, np.eye(4))
                transformed = (transform @ homogeneous.T).T[:, :3]
            self._part_vertices.append(transformed)
            if item._mcas_textured:
                item.setPositions(transformed)
            else:
                item.setMeshData(
                    vertexes=transformed,
                    faces=item._mcas_faces,
                    faceColors=item._mcas_colors,
                )

        segments = []
        for index in self.selected_parts:
            if index < 0 or index >= len(self._part_vertices):
                continue
            vertices = self._part_vertices[index]
            if not len(vertices):
                continue
            low = vertices.min(axis=0)
            high = vertices.max(axis=0)
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
            for first, second in (
                (0, 1), (1, 2), (2, 3), (3, 0),
                (4, 5), (5, 6), (6, 7), (7, 4),
                (0, 4), (1, 5), (2, 6), (3, 7),
            ):
                segments.append(corners[first])
                segments.append(corners[second])
        if segments:
            self.selection_box.setData(pos=np.asarray(segments), width=2)
        else:
            self.selection_box.setData(pos=np.zeros((0, 3)), width=2)

        joint_points = []
        selected_head = None
        selected_tail = None
        self._bone_segments.clear()
        for name, bone in self.project.bones.items():
            transform = transforms.get(name, np.eye(4))
            head = (transform @ np.append(bone.head, 1.0))[:3]
            tail = (transform @ np.append(bone.tail, 1.0))[:3]
            self._bone_segments[name] = (head, tail)
            joint_points.append(head)
            if name == selected_bone:
                selected_head = head
                selected_tail = tail
            octahedron = self.make_bone_octahedron(head, tail)
            item = self.bone_mesh_items.get(name)
            if item is None:
                continue
            color = (
                (0.35, 0.9, 0.55, 1.0)
                if name == selected_bone
                else (0.70, 0.76, 0.82, 0.92)
            )
            item.setMeshData(
                vertexes=octahedron,
                faces=np.asarray(
                    [
                        (0, 1, 2),
                        (0, 2, 3),
                        (0, 3, 4),
                        (0, 4, 1),
                        (5, 2, 1),
                        (5, 3, 2),
                        (5, 4, 3),
                        (5, 1, 4),
                    ],
                    dtype=np.uint32,
                ),
                faceColors=np.tile(color, (8, 1)),
            )
        if joint_points:
            self.joints.setData(pos=np.asarray(joint_points), size=9)
        else:
            self.joints.setData(pos=np.zeros((0, 3)), size=9)
        self._gizmo_center = None
        if selected_head is not None:
            self._gizmo_center = np.asarray(
                pivot_marker if pivot_marker is not None else selected_head,
                dtype=float,
            )
        self.update_gizmo()
        if pivot_marker is not None:
            self.pivot_marker.setData(pos=np.asarray([pivot_marker]), size=14)
        else:
            self.pivot_marker.setData(pos=np.zeros((0, 3)), size=14)

    def update_gizmo(self):
        center = self._gizmo_center
        rotating = center is not None and self.transform_mode == "rotate"
        moving = center is not None and self.transform_mode == "move"
        radius = self.gizmo_scale
        for ring, axis in zip(self.rotate_rings, self.AXES):
            if rotating:
                ring.setData(pos=self.circle_points(center, radius, axis), width=3)
            else:
                ring.setData(pos=np.zeros((0, 3)), width=3)
            ring.setVisible(bool(rotating))
        length = radius * 1.35
        for index, (shaft, head) in enumerate(self.gizmo_arrows):
            shaft.setVisible(bool(moving))
            head.setVisible(bool(moving))
            if not moving:
                continue
            axis = self.AXES[index]
            tip = center + axis * length
            shaft.setData(pos=np.asarray([center, tip]), width=4)
            head.setMeshData(
                vertexes=self.arrow_cone(center, axis, length, radius * 0.16),
                faces=np.asarray(
                    [
                        (0, 1, 2),
                        (0, 2, 3),
                        (0, 3, 4),
                        (0, 4, 1),
                        (1, 2, 3),
                        (1, 3, 4),
                    ],
                    dtype=np.uint32,
                ),
            )

    @staticmethod
    def arrow_cone(center, direction, length, radius):
        direction = np.asarray(direction, dtype=float)
        direction /= max(1e-9, np.linalg.norm(direction))
        helper = np.array([1.0, 0.0, 0.0])
        if abs(float(np.dot(direction, helper))) > 0.9:
            helper = np.array([0.0, 0.0, 1.0])
        u = np.cross(direction, helper)
        u /= max(1e-9, np.linalg.norm(u))
        v = np.cross(direction, u)
        base = np.asarray(center, dtype=float) + direction * (length * 0.72)
        tip = np.asarray(center, dtype=float) + direction * length
        return np.asarray(
            [
                tip,
                base + u * radius,
                base + v * radius,
                base - u * radius,
                base - v * radius,
            ]
        )

    def ring_points(self, axis_index):
        if self._gizmo_center is None:
            return None
        return self.circle_points(
            self._gizmo_center, self.gizmo_scale, self.AXES[axis_index], segments=48
        )

    def pick_gizmo_axis(self, position):
        if self._gizmo_center is None:
            return None
        cursor = np.array([position.x(), position.y()])
        best = None
        best_distance = 12.0
        if self.transform_mode == "rotate":
            for index in range(3):
                points = self.ring_points(index)
                if points is None:
                    continue
                projected = [self.project_point(point) for point in points]
                for first, second in zip(projected, projected[1:] + projected[:1]):
                    if first is None or second is None:
                        continue
                    distance = self.point_segment_distance(cursor, first, second)
                    if distance < best_distance:
                        best_distance = distance
                        best = index
            return best
        center_2d = self.project_point(self._gizmo_center)
        if center_2d is None:
            return None
        length = self.gizmo_scale * 1.35
        for index in range(3):
            tip = self._gizmo_center + self.AXES[index] * length
            tip_2d = self.project_point(tip)
            if tip_2d is None:
                continue
            distance = self.point_segment_distance(cursor, center_2d, tip_2d)
            if distance < best_distance:
                best_distance = distance
                best = index
        return best

    def apply_gizmo_drag(self, previous, current):
        if (
            self._gizmo_center is None
            or self._gizmo_axis is None
            or self.gizmo_callback is None
        ):
            return
        axis = self.AXES[self._gizmo_axis]
        center_2d = self.project_point(self._gizmo_center)
        if center_2d is None:
            return
        delta = np.array([current.x() - previous.x(), current.y() - previous.y()])
        if self.transform_mode == "rotate":
            previous_vector = np.array(
                [previous.x() - center_2d[0], -(previous.y() - center_2d[1])]
            )
            current_vector = np.array(
                [current.x() - center_2d[0], -(current.y() - center_2d[1])]
            )
            if (
                float(np.linalg.norm(previous_vector)) < 4.0
                or float(np.linalg.norm(current_vector)) < 4.0
            ):
                return
            angle = math.degrees(
                math.atan2(
                    float(
                        previous_vector[0] * current_vector[1]
                        - previous_vector[1] * current_vector[0]
                    ),
                    float(np.dot(previous_vector, current_vector)),
                )
            )
            camera = self.cameraPosition()
            forward = np.array(
                [
                    self.opts["center"].x() - camera.x(),
                    self.opts["center"].y() - camera.y(),
                    self.opts["center"].z() - camera.z(),
                ]
            )
            if float(np.dot(axis, forward)) > 0:
                angle = -angle
            if abs(angle) > 1e-4:
                self.gizmo_callback("rotate", self._gizmo_axis, angle)
            return
        tip_2d = self.project_point(self._gizmo_center + axis * 1.0)
        if tip_2d is None:
            return
        screen_axis = tip_2d - center_2d
        pixels_per_unit = float(np.linalg.norm(screen_axis))
        if pixels_per_unit < 1e-6:
            return
        unit = screen_axis / pixels_per_unit
        amount = float(np.dot(delta, unit)) / pixels_per_unit
        if abs(amount) > 1e-6:
            self.gizmo_callback("move", self._gizmo_axis, amount)

    def set_transform_controls(self, enabled: bool, mode: str):
        changed = self.transform_mode != mode
        self.direct_edit_enabled = enabled
        self.transform_mode = mode
        if changed and self.project is not None:
            self.update_pose(
                self._last_animation,
                self._last_frame,
                self._last_selected_bone,
                self._last_pivot_marker,
            )

    @staticmethod
    def make_bone_octahedron(head, tail):
        head = np.asarray(head, dtype=float)
        tail = np.asarray(tail, dtype=float)
        direction = tail - head
        length = np.linalg.norm(direction)
        if length < 1e-6:
            direction = np.array([0.0, 1.0, 0.0])
            length = 1.0
        else:
            direction /= length
        helper = np.array([1.0, 0.0, 0.0])
        if abs(float(np.dot(direction, helper))) > 0.9:
            helper = np.array([0.0, 0.0, 1.0])
        u = np.cross(direction, helper)
        u /= max(1e-9, np.linalg.norm(u))
        v = np.cross(direction, u)
        ring_center = head + direction * min(length * 0.22, 0.12)
        radius = max(0.012, min(0.065, length * 0.13))
        return np.asarray(
            [
                head,
                ring_center + u * radius,
                ring_center + v * radius,
                ring_center - u * radius,
                ring_center - v * radius,
                tail,
            ]
        )

    @staticmethod
    def circle_points(center, radius, axis, segments=64):
        axis = np.asarray(axis, dtype=float)
        axis /= max(1e-9, np.linalg.norm(axis))
        helper = np.array([1.0, 0.0, 0.0])
        if abs(float(np.dot(axis, helper))) > 0.9:
            helper = np.array([0.0, 0.0, 1.0])
        u = np.cross(axis, helper)
        u /= max(1e-9, np.linalg.norm(u))
        v = np.cross(axis, u)
        angles = np.linspace(0, math.tau, segments)
        return np.asarray(
            [
                np.asarray(center)
                + radius * math.cos(angle) * u
                + radius * math.sin(angle) * v
                for angle in angles
            ]
        )

    def keyPressEvent(self, event):
        mode = None
        if event.key() == Qt.Key.Key_V:
            mode = "move"
        elif event.key() == Qt.Key.Key_R:
            mode = "rotate"
        if mode is not None:
            if self.mode_callback:
                self.mode_callback(mode)
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if event.button() == Qt.MouseButton.LeftButton and self._gizmo_center is not None:
            axis = self.pick_gizmo_axis(event.position())
            if axis is not None:
                self._gizmo_axis = axis
                self._gizmo_dragging = True
                self._last_mouse = event.position()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
        if (
            self.direct_edit_enabled
            and event.button() == Qt.MouseButton.LeftButton
        ):
            bone_name = self.pick_bone(event.position())
            part_index = None if bone_name is not None else self.pick_part(event.position())
            if part_index is not None:
                bone_name = self.project.parts[part_index].bone or None
            if self.locked_bone is not None:
                if bone_name is not None or part_index is not None:
                    bone_name = self.locked_bone
            elif self.whole_model_mode:
                if bone_name is not None or part_index is not None:
                    bone_name = self.whole_model_bone
            if bone_name is not None or part_index is not None:
                if self.pick_callback:
                    self.pick_callback(bone_name or "", part_index)
                if bone_name is None:
                    event.accept()
                    return
                self._dragging_transform = True
                self._last_mouse = event.position()
                self._press_position = event.position()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def hover_gizmo(self, position):
        if self._gizmo_center is None:
            return False
        center_2d = self.project_point(self._gizmo_center)
        axis_2d = self.project_point(
            self._gizmo_center + self.AXES[0] * self.gizmo_scale
        )
        if center_2d is None or axis_2d is None:
            return False
        radius = max(18.0, float(np.linalg.norm(axis_2d - center_2d)))
        cursor = np.array([position.x(), position.y()])
        if float(np.linalg.norm(cursor - center_2d)) > radius + 24.0:
            return False
        return self.pick_gizmo_axis(position) is not None

    def mouseMoveEvent(self, event):
        if self._gizmo_dragging:
            previous = self._last_mouse
            self._last_mouse = event.position()
            self.apply_gizmo_drag(previous, event.position())
            event.accept()
            return
        if event.buttons() == Qt.MouseButton.NoButton:
            self.setCursor(
                Qt.CursorShape.OpenHandCursor
                if self.hover_gizmo(event.position())
                else Qt.CursorShape.ArrowCursor
            )
        if self._dragging_transform:
            delta = event.position() - self._last_mouse
            self._last_mouse = event.position()
            if self.transform_callback:
                self.transform_callback(
                    delta.x(),
                    delta.y(),
                    bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier),
                    self.transform_mode,
                )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._gizmo_dragging and event.button() == Qt.MouseButton.LeftButton:
            self._gizmo_dragging = False
            self._gizmo_axis = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        if self._dragging_transform and event.button() == Qt.MouseButton.LeftButton:
            self._dragging_transform = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def screen_ray(self, position):
        width = max(1.0, float(self.width()))
        height = max(1.0, float(self.height()))
        projection = self.projectionMatrix(
            (0, 0, int(width), int(height)),
            (0, 0, int(width), int(height)),
        )
        view_rotation = self.viewMatrix()
        inverse = (projection * view_rotation).inverted()[0]
        x = 2.0 * position.x() / width - 1.0
        y = 1.0 - 2.0 * position.y() / height

        def unproject(z):
            value = inverse.map(QVector4D(x, y, z, 1.0))
            if abs(value.w()) < 1e-9:
                return np.zeros(3)
            return np.array(
                [value.x() / value.w(), value.y() / value.w(), value.z() / value.w()]
            )

        return unproject(-1.0), unproject(1.0)

    def project_point(self, point):
        width = max(1.0, float(self.width()))
        height = max(1.0, float(self.height()))
        projection = self.projectionMatrix(
            (0, 0, int(width), int(height)),
            (0, 0, int(width), int(height)),
        )
        clip = (projection * self.viewMatrix()).map(
            QVector4D(float(point[0]), float(point[1]), float(point[2]), 1.0)
        )
        if clip.w() <= 1e-9:
            return None
        return np.array(
            [
                (clip.x() / clip.w() * 0.5 + 0.5) * width,
                (1.0 - (clip.y() / clip.w() * 0.5 + 0.5)) * height,
            ]
        )

    @staticmethod
    def point_segment_distance(point, start, end):
        segment = end - start
        denominator = float(np.dot(segment, segment))
        if denominator < 1e-9:
            return float(np.linalg.norm(point - start))
        amount = max(0.0, min(1.0, float(np.dot(point - start, segment)) / denominator))
        closest = start + amount * segment
        return float(np.linalg.norm(point - closest))

    def pick_bone(self, position):
        best_name = None
        best_distance = 18.0
        for name, (head, tail) in self._bone_segments.items():
            head_2d = self.project_point(head)
            tail_2d = self.project_point(tail)
            if head_2d is None or tail_2d is None:
                continue
            distance = self.point_segment_distance(
                np.array([position.x(), position.y()]), head_2d, tail_2d
            )
            screen_length = float(np.linalg.norm(tail_2d - head_2d))
            score = distance + min(4.0, screen_length * 0.02)
            if score < best_distance:
                best_distance = score
                best_name = name
        return best_name

    @staticmethod
    def ray_triangle_intersection(origin, direction, a, b, c):
        edge1 = b - a
        edge2 = c - a
        pvec = np.cross(direction, edge2)
        determinant = float(np.dot(edge1, pvec))
        if abs(determinant) < 1e-9:
            return None
        inverse = 1.0 / determinant
        tvec = origin - a
        u = float(np.dot(tvec, pvec)) * inverse
        if u < 0 or u > 1:
            return None
        qvec = np.cross(tvec, edge1)
        v = float(np.dot(direction, qvec)) * inverse
        if v < 0 or u + v > 1:
            return None
        distance = float(np.dot(edge2, qvec)) * inverse
        return distance if distance > 1e-6 else None

    def pick_part(self, position):
        if self.project is None:
            return None
        origin, far = self.screen_ray(position)
        direction = far - origin
        direction /= max(1e-9, np.linalg.norm(direction))
        best = None
        best_distance = float("inf")
        for part_index, part in enumerate(self.project.parts):
            if part_index >= len(self._part_vertices):
                continue
            vertices = self._part_vertices[part_index]
            for face in part.faces:
                if len(face) < 3:
                    continue
                for index in range(1, len(face) - 1):
                    distance = self.ray_triangle_intersection(
                        origin,
                        direction,
                        vertices[face[0]],
                        vertices[face[index]],
                        vertices[face[index + 1]],
                    )
                    if distance is not None and distance < best_distance:
                        best_distance = distance
                        best = part_index
        return best
