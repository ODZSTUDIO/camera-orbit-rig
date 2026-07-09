# Camera Orbit Rig — 중심점 기준으로 회전하는 카메라 리그
# Blender Extension (blender_manifest.toml 참조)

import math
import bpy
from bpy.props import FloatProperty, PointerProperty, StringProperty


# -----------------------------------------------------------------------------
# 리그 구조
#   Root (Empty, 중심점/마스터)  - Orbit(Z 회전), 이동(G), 스케일(S)=Distance 배율
#     ├ OrbitPath (Curve)       - 카메라 궤도 시각 표시 (선택 불가, 드라이버로 자동 갱신)
#     ├ Target (Empty)          - 카메라 조준점. G로 옮기면 카메라가 따라봄 (Damped Track)
#     ├ Focus (Empty)           - DOF 초점 오브젝트. G로 옮기면 초점이 따라감
#     └ Pivot (Empty)           - Tilt(X 회전)
#         └ Camera              - Distance(-Y 위치), Bank(뷰 축 롤)
#
# 슬라이더는 오브젝트 트랜스폼을 직접 읽고 쓴다(get/set 프로퍼티).
# 그래서 뷰포트에서 G/R/S로 움직여도 슬라이더에 그대로 반영되고, 반대도 마찬가지.
# 리그에 필요 없는 축은 잠가 두어 G/R/S가 정확히 해당 컨트롤만 움직인다.
# Damped Track은 Track To와 달리 롤을 보존해서 Bank가 그대로 동작한다.
# -----------------------------------------------------------------------------

ROOT_MARKER = "is_camrig_root"
RIG_VERSION = 3  # 1: 드라이버 방식, 2: 트랜스폼 직접 제어, 3: Target/Focus/궤도 추가
PART_PROP = "camrig_part"
TRACK_CON_NAME = "CamRig Track"

BEZIER_CIRCLE_C = 0.5522847498  # 반지름 1 원의 베지어 핸들 길이


def get_rig_root(obj):
    """선택한 오브젝트에서 부모를 거슬러 올라가며 리그 루트를 찾음"""
    while obj is not None:
        if obj.get(ROOT_MARKER):
            return obj
        obj = obj.parent
    return None


def find_part(root, part):
    return next((c for c in root.children_recursive if c.get(PART_PROP) == part), None)


def get_rig_objects(root):
    """(pivot, camera) 반환. 없으면 None"""
    cam = find_part(root, "camera")
    if cam is None:
        cam = next((c for c in root.children_recursive if c.type == 'CAMERA'), None)
    pivot = cam.parent if cam else None
    return pivot, cam


def apply_rig_locks(root, pivot, cam, target=None, focus=None):
    """G/R/S가 리그 컨트롤만 움직이도록 불필요한 축 잠금"""
    # Root: G 이동, R = Orbit(Z만), S = Distance 배율
    root.lock_rotation = (True, True, False)
    # Pivot: R = Tilt(X만)
    pivot.lock_location = (True, True, True)
    pivot.lock_rotation = (False, True, True)
    pivot.lock_scale = (True, True, True)
    # Camera: G = Distance(Y만), R = Bank(Z만)
    cam.lock_location = (True, False, True)
    cam.lock_rotation = (True, True, False)
    cam.lock_scale = (True, True, True)
    # Target/Focus: G 이동만
    for obj in (target, focus):
        if obj:
            obj.lock_rotation = (True, True, True)
            obj.lock_scale = (True, True, True)


def _avg_scale(obj):
    s = (abs(obj.scale.x) + abs(obj.scale.y) + abs(obj.scale.z)) / 3.0
    return s if s > 1e-6 else 1.0


# --- 슬라이더 <-> 트랜스폼 양방향 연결 ---------------------------------------

def _get_orbit(self):
    return math.degrees(self.id_data.rotation_euler.z)


def _set_orbit(self, value):
    self.id_data.rotation_euler.z = math.radians(value)


def _get_tilt(self):
    pivot, _ = get_rig_objects(self.id_data)
    return math.degrees(-pivot.rotation_euler.x) if pivot else 0.0


def _set_tilt(self, value):
    pivot, _ = get_rig_objects(self.id_data)
    if pivot:
        pivot.rotation_euler.x = -math.radians(value)


def _get_bank(self):
    _, cam = get_rig_objects(self.id_data)
    return math.degrees(cam.rotation_euler.z) if cam else 0.0


def _set_bank(self, value):
    _, cam = get_rig_objects(self.id_data)
    if cam:
        cam.rotation_euler.z = math.radians(value)


def _get_distance(self):
    root = self.id_data
    _, cam = get_rig_objects(root)
    return -cam.location.y * _avg_scale(root) if cam else 0.0


def _set_distance(self, value):
    root = self.id_data
    _, cam = get_rig_objects(root)
    if cam:
        cam.location.y = -value / _avg_scale(root)


class CamRigSettings(bpy.types.PropertyGroup):
    orbit: FloatProperty(
        name="Orbit", description="중심점 기준 수평 회전 (도) — 뷰포트에서 Root를 R로 돌려도 됨",
        get=_get_orbit, set=_set_orbit, soft_min=-360.0, soft_max=360.0)
    tilt: FloatProperty(
        name="Tilt", description="카메라 상하 각도 (도) — 뷰포트에서 Pivot을 R로 돌려도 됨",
        get=_get_tilt, set=_set_tilt, soft_min=-89.0, soft_max=89.0)
    bank: FloatProperty(
        name="Bank", description="뷰 축 기준 롤 (도) — 뷰포트에서 Camera를 R로 돌려도 됨",
        get=_get_bank, set=_set_bank, soft_min=-180.0, soft_max=180.0)
    distance: FloatProperty(
        name="Distance", description="중심점에서 카메라까지 거리 — Camera를 G로 밀거나 Root를 S로 스케일해도 됨",
        get=_get_distance, set=_set_distance, min=0.0, soft_max=100.0)


# --- 리그 부품 생성 -----------------------------------------------------------

def make_orbit_path_curve(name):
    """반지름 1짜리 베지어 원 커브 데이터 생성"""
    curve = bpy.data.curves.new(name, 'CURVE')
    curve.dimensions = '3D'
    spline = curve.splines.new('BEZIER')
    spline.bezier_points.add(3)
    c = BEZIER_CIRCLE_C
    # (좌표, 왼쪽 핸들, 오른쪽 핸들) — 반시계 방향
    points = (
        ((1, 0, 0), (1, -c, 0), (1, c, 0)),
        ((0, 1, 0), (c, 1, 0), (-c, 1, 0)),
        ((-1, 0, 0), (-1, c, 0), (-1, -c, 0)),
        ((0, -1, 0), (-c, -1, 0), (c, -1, 0)),
    )
    for bp, (co, hl, hr) in zip(spline.bezier_points, points):
        bp.co = co
        bp.handle_left = hl
        bp.handle_right = hr
        bp.handle_left_type = 'FREE'
        bp.handle_right_type = 'FREE'
    spline.use_cyclic_u = True
    return curve


def add_orbit_path_drivers(path, pivot, cam):
    """궤도 원이 카메라 거리/틸트를 따라가도록 드라이버 연결 (시각 표시 전용)"""

    def make_driver(fcurve, expression):
        driver = fcurve.driver
        driver.type = 'SCRIPTED'
        v = driver.variables.new()
        v.name = "cy"
        v.type = 'TRANSFORMS'
        v.targets[0].id = cam
        v.targets[0].transform_type = 'LOC_Y'
        v.targets[0].transform_space = 'TRANSFORM_SPACE'
        v = driver.variables.new()
        v.name = "px"
        v.type = 'TRANSFORMS'
        v.targets[0].id = pivot
        v.targets[0].transform_type = 'ROT_X'
        v.targets[0].transform_space = 'TRANSFORM_SPACE'
        driver.expression = expression

    for i in range(3):
        make_driver(path.driver_add("scale", i), "-cy * cos(px)")
    make_driver(path.driver_add("location", 2), "cy * sin(px)")


def add_rig_extras(context, root, pivot, cam):
    """Target / Focus / 궤도 원 생성 및 연결 (v3 파트)"""
    collection = context.collection

    # Target: 카메라 조준점
    target = bpy.data.objects.new("CamRig_Target", None)
    target.empty_display_type = 'PLAIN_AXES'
    target.empty_display_size = 0.25
    target.parent = root
    target[PART_PROP] = "target"
    collection.objects.link(target)

    # Focus: DOF 초점
    focus = bpy.data.objects.new("CamRig_Focus", None)
    focus.empty_display_type = 'SPHERE'
    focus.empty_display_size = 0.15
    focus.parent = root
    focus[PART_PROP] = "focus"
    collection.objects.link(focus)

    # OrbitPath: 시각 표시 전용 궤도 원
    path = bpy.data.objects.new("CamRig_OrbitPath", make_orbit_path_curve("CamRig_OrbitPath"))
    path.parent = root
    path[PART_PROP] = "path"
    path.hide_select = True
    path.hide_render = True
    collection.objects.link(path)
    add_orbit_path_drivers(path, pivot, cam)

    # Damped Track: 롤(Bank)을 보존하면서 Target을 바라봄
    con = cam.constraints.new('DAMPED_TRACK')
    con.name = TRACK_CON_NAME
    con.target = target
    con.track_axis = 'TRACK_NEGATIVE_Z'

    # DOF 초점을 Focus 엠프티로
    cam.data.dof.focus_object = focus

    cam[PART_PROP] = "camera"
    pivot[PART_PROP] = "pivot"
    return target, focus, path


# --- 오퍼레이터 ---------------------------------------------------------------

class CAMRIG_OT_add(bpy.types.Operator):
    """3D 커서 위치에 오빗 카메라 리그 생성"""
    bl_idname = "camrig.add"
    bl_label = "Add Camera Rig"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        cursor = context.scene.cursor.location.copy()
        collection = context.collection

        # Root: 중심점/마스터
        root = bpy.data.objects.new("CamRig_Root", None)
        root.empty_display_type = 'SPHERE'
        root.empty_display_size = 0.35
        root.location = cursor
        collection.objects.link(root)

        # Pivot: 틸트용
        pivot = bpy.data.objects.new("CamRig_Pivot", None)
        pivot.empty_display_type = 'CIRCLE'
        pivot.empty_display_size = 0.3
        pivot.parent = root
        pivot.rotation_euler.x = -math.radians(20.0)  # 기본 틸트 20도
        collection.objects.link(pivot)

        # Camera
        cam_data = bpy.data.cameras.new("CamRig_Camera")
        cam = bpy.data.objects.new("CamRig_Camera", cam_data)
        cam.parent = pivot
        cam.location = (0.0, -5.0, 0.0)  # 기본 거리 5
        # ZXY 오일러: Z(bank)가 먼저 적용되어 뷰 축 기준 순수한 롤이 됨
        cam.rotation_mode = 'ZXY'
        cam.rotation_euler = (math.radians(90.0), 0.0, 0.0)
        collection.objects.link(cam)

        target, focus, _ = add_rig_extras(context, root, pivot, cam)

        root[ROOT_MARKER] = RIG_VERSION
        apply_rig_locks(root, pivot, cam, target, focus)

        # 씬 카메라로 지정하고 루트 선택
        context.scene.camera = cam
        for obj in context.selected_objects:
            obj.select_set(False)
        root.select_set(True)
        context.view_layer.objects.active = root

        self.report({'INFO'}, "카메라 리그 생성 완료")
        return {'FINISHED'}


class CAMRIG_OT_upgrade(bpy.types.Operator):
    """구버전 리그를 최신 구조(Target/Focus/궤도 표시)로 변환"""
    bl_idname = "camrig.upgrade"
    bl_label = "Upgrade Rig"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        root = get_rig_root(context.active_object)
        if root is None:
            return {'CANCELLED'}
        pivot, cam = get_rig_objects(root)
        if pivot is None or cam is None:
            self.report({'WARNING'}, "리그 구조를 찾을 수 없습니다")
            return {'CANCELLED'}

        # v1: 드라이버 방식 → 값을 트랜스폼으로 옮기고 드라이버 제거
        if "orbit" in root.keys():
            orbit = float(root.get("orbit", 0.0))
            tilt = float(root.get("tilt", 20.0))
            bank = float(root.get("bank", 0.0))
            distance = float(root.get("distance", 5.0))

            root.driver_remove("rotation_euler", 2)
            pivot.driver_remove("rotation_euler", 0)
            cam.driver_remove("location", 1)
            cam.driver_remove("rotation_euler", 2)

            root.rotation_euler.z = math.radians(orbit)
            pivot.rotation_euler.x = -math.radians(tilt)
            cam.location.y = -distance
            cam.rotation_euler.z = math.radians(bank)

            for key in ("orbit", "tilt", "bank", "distance"):
                if key in root.keys():
                    del root[key]

        # v2 → v3: Target / Focus / 궤도 원 추가
        target = find_part(root, "target")
        focus = find_part(root, "focus")
        if target is None or focus is None:
            target, focus, _ = add_rig_extras(context, root, pivot, cam)

        root[ROOT_MARKER] = RIG_VERSION
        apply_rig_locks(root, pivot, cam, target, focus)

        self.report({'INFO'}, "리그 업그레이드 완료")
        return {'FINISHED'}


class CAMRIG_OT_look_through(bpy.types.Operator):
    """리그 카메라를 씬 카메라로 지정하고 카메라 뷰로 전환"""
    bl_idname = "camrig.look_through"
    bl_label = "Look Through Camera"

    def execute(self, context):
        root = get_rig_root(context.active_object)
        cam = get_rig_objects(root)[1] if root else None
        if cam is None:
            self.report({'WARNING'}, "리그 카메라를 찾을 수 없습니다")
            return {'CANCELLED'}
        context.scene.camera = cam
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.region_3d.view_perspective = 'CAMERA'
                break
        return {'FINISHED'}


class CAMRIG_OT_keyframe(bpy.types.Operator):
    """현재 프레임에 리그 전체(Orbit/Tilt/Bank/Distance/중심점/Target/Focus) 키프레임 삽입"""
    bl_idname = "camrig.keyframe"
    bl_label = "Keyframe Rig"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        root = get_rig_root(context.active_object)
        if root is None:
            return {'CANCELLED'}
        pivot, cam = get_rig_objects(root)
        root.keyframe_insert("location")
        root.keyframe_insert("rotation_euler", index=2)
        root.keyframe_insert("scale")
        if pivot:
            pivot.keyframe_insert("rotation_euler", index=0)
        if cam:
            cam.keyframe_insert("location", index=1)
            cam.keyframe_insert("rotation_euler", index=2)
        for part in ("target", "focus"):
            obj = find_part(root, part)
            if obj:
                obj.keyframe_insert("location")
        self.report({'INFO'}, "리그 키프레임 삽입 완료")
        return {'FINISHED'}


class CAMRIG_OT_reset_aim(bpy.types.Operator):
    """Target을 중심점으로 되돌리고 카메라 조준 축을 정리 (Bank는 유지)"""
    bl_idname = "camrig.reset_aim"
    bl_label = "Reset Aim"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        root = get_rig_root(context.active_object)
        if root is None:
            return {'CANCELLED'}
        pivot, cam = get_rig_objects(root)
        if pivot:
            pivot.location = (0.0, 0.0, 0.0)
            pivot.rotation_euler.y = 0.0
            pivot.rotation_euler.z = 0.0
        if cam:
            cam.location.x = 0.0
            cam.location.z = 0.0
            cam.rotation_mode = 'ZXY'
            cam.rotation_euler.x = math.radians(90.0)
            cam.rotation_euler.y = 0.0
        target = find_part(root, "target")
        if target:
            target.location = (0.0, 0.0, 0.0)
        return {'FINISHED'}


class CAMRIG_OT_select_part(bpy.types.Operator):
    """리그 부품 선택"""
    bl_idname = "camrig.select_part"
    bl_label = "Select Rig Part"
    bl_options = {'REGISTER', 'UNDO'}

    part: StringProperty()

    def execute(self, context):
        root = get_rig_root(context.active_object)
        if root is None:
            return {'CANCELLED'}
        if self.part == "root":
            obj = root
        elif self.part == "pivot":
            obj = get_rig_objects(root)[0]
        elif self.part == "camera":
            obj = get_rig_objects(root)[1]
        else:
            obj = find_part(root, self.part)
        if obj is None:
            self.report({'WARNING'}, "해당 부품이 없습니다")
            return {'CANCELLED'}
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {'FINISHED'}


# --- N 패널 -------------------------------------------------------------------

class CAMRIG_PT_panel(bpy.types.Panel):
    bl_label = "Camera Orbit Rig"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Camera Rig"

    def draw(self, context):
        layout = self.layout
        layout.operator("camrig.add", icon='OUTLINER_OB_CAMERA')

        root = get_rig_root(context.active_object)
        if root is None:
            layout.label(text="리그를 선택하세요", icon='INFO')
            return

        # 구버전 리그는 업그레이드 필요
        if root.get(ROOT_MARKER, 0) < RIG_VERSION:
            box = layout.box()
            box.label(text="구버전 리그입니다", icon='ERROR')
            box.operator("camrig.upgrade", icon='FILE_REFRESH')
            return

        pivot, cam = get_rig_objects(root)

        row = layout.row(align=True)
        row.operator("camrig.look_through", text="Look Through", icon='VIEW_CAMERA')
        row.operator("camrig.keyframe", text="", icon='KEY_HLT')
        row.operator("camrig.reset_aim", text="", icon='CON_TRACKTO')

        # 부품 빠른 선택
        row = layout.row(align=True)
        row.label(text="선택:")
        row.operator("camrig.select_part", text="Root").part = "root"
        row.operator("camrig.select_part", text="Cam").part = "camera"
        row.operator("camrig.select_part", text="Target").part = "target"
        row.operator("camrig.select_part", text="Focus").part = "focus"

        col = layout.column(align=True)
        col.prop(root.camrig, "orbit", slider=True)
        col.prop(root.camrig, "tilt", slider=True)
        col.prop(root.camrig, "bank", slider=True)
        col.prop(root.camrig, "distance", slider=True)

        if cam is None:
            layout.label(text="카메라가 없습니다", icon='ERROR')
            return

        # Target 추적 강도
        con = cam.constraints.get(TRACK_CON_NAME)
        if con:
            layout.prop(con, "influence", text="Target Tracking", slider=True)

        box = layout.box()
        box.label(text="뷰포트 단축키", icon='VIEW3D')
        col = box.column(align=True)
        col.label(text="Root:  G 이동 · R 회전(Orbit) · S 거리")
        col.label(text="Pivot:  R 틸트")
        col.label(text="Camera:  G 거리 · R 뱅크")
        col.label(text="Target/Focus:  G 이동")

        layout.separator()
        box = layout.box()
        box.label(text="Focus", icon='CAMERA_DATA')
        box.prop(cam.data, "lens", text="Focal Length")

        dof = cam.data.dof
        box.prop(dof, "use_dof", text="Depth of Field")
        sub = box.column(align=True)
        sub.enabled = dof.use_dof
        sub.prop(dof, "focus_object", text="Focus Object")
        row = sub.row()
        row.enabled = dof.focus_object is None
        row.prop(dof, "focus_distance", text="Focus Distance")
        sub.prop(dof, "aperture_fstop", text="F-Stop")


classes = (
    CamRigSettings,
    CAMRIG_OT_add,
    CAMRIG_OT_upgrade,
    CAMRIG_OT_look_through,
    CAMRIG_OT_keyframe,
    CAMRIG_OT_reset_aim,
    CAMRIG_OT_select_part,
    CAMRIG_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.camrig = PointerProperty(type=CamRigSettings)


def unregister():
    del bpy.types.Object.camrig
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
