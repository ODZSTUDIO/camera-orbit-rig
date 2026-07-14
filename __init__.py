# Camera Orbit Rig — 중심점 기준으로 회전하는 카메라 리그
# Blender Extension (blender_manifest.toml 참조)

import math
import bpy
from bpy.props import FloatProperty, PointerProperty, StringProperty


# -----------------------------------------------------------------------------
# 리그 구조
#   📷 Root (Empty, 중심점)   - 이동(G), 스케일(S)=Distance 배율. 회전 없음
#     ├ Target (Empty)        - 카메라 조준점. G로 옮기면 카메라가 따라봄 (Damped Track)
#     ├ Focus (Empty)         - DOF 초점 오브젝트. G로 옮기면 초점이 따라감
#     └ OrbitPath (Curve)     - Orbit(Z 회전) — 직접 선택해서 돌리는 컨트롤(마스터)
#         └ Camera            - G(Z만)=Tilt, 자유 회전(XYZ, Bank=Z)
#
# OrbitPath가 Camera의 실제 부모라서, OrbitPath를 R로 돌리면 그 아래의
# Camera가 그대로 함께 돌아간다 — 드라이버 없이 순수 부모-자식 관계라
# 의존성 순환(dependency cycle)이 생기지 않는다. (Root가 자신의 자식인
# OrbitPath 회전을 드라이버로 참조하는 이전 방식은 부모가 자식의 트랜스폼에
# 의존하는 순환을 만들어 실제로는 깨져 있었다.)
#
# Pivot은 없다. Camera의 Z 위치 자체가 Tilt다. Camera는 OrbitPath 중심으로
# 부터 항상 일정 거리(camrig_radius)를 유지한 채 Z로만 움직이도록 Y 위치가
# 드라이버로 자동 계산된다(Y = -sqrt(radius² - Z²), 이 드라이버는 Camera
# 자기 자신의 다른 채널만 참조하므로 순환이 없다). 그래서 Camera를 잡고
# Z로만 이동해도(G, Z) 거리는 그대로 유지되면서 Tilt만 바뀐다. 조준 자체는
# 회전이 아니라 Target을 향한 Damped Track이 항상 담당하므로, 위치가
# 바뀌어도 자동으로 다시 조준된다.
#
# Camera의 회전은 X/Y/Z 모두 열려 있지만, Damped Track이 Target을 계속
# 바라보게 만들기 때문에 Target Tracking 영향력이 1(기본값)일 때는 X/Y
# 회전이 거의 상쇄되고 Z(Bank)만 항상 반영된다. 영향력을 낮추면 X/Y/Z
# 모두 완전한 수동 조준이 된다.
# -----------------------------------------------------------------------------

ROOT_MARKER = "is_camrig_root"
RIG_VERSION = 5  # 1: 드라이버 방식, 2: 트랜스폼 직접 제어, 3: Target/Focus/궤도,
                 # 4: OrbitPath 직접 조작(구버전, 순환 드라이버 버그 있었음),
                 # 5: Pivot 제거 + OrbitPath가 Camera의 실부모(순환 없음) +
                 #    Camera의 Z 위치가 곧 Tilt
PART_PROP = "camrig_part"
TRACK_CON_NAME = "CamRig Track"
RADIUS_PROP = "camrig_radius"
ROOT_ICON = "📷"

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


def get_camera(root):
    """리그 카메라 오브젝트 반환. 없으면 None"""
    cam = find_part(root, "camera")
    if cam is None:
        cam = next((c for c in root.children_recursive if c.type == 'CAMERA'), None)
    return cam


def has_driver(obj, data_path, index=-1):
    if not obj.animation_data:
        return False
    return any(fc.data_path == data_path and (index < 0 or fc.array_index == index)
               for fc in obj.animation_data.drivers)


def apply_rig_locks(root, cam, target=None, focus=None, path=None):
    """G/R/S가 리그 컨트롤만 움직이도록 불필요한 축 잠금"""
    # Root: G 이동, S = Distance 배율. 회전은 쓰지 않는다
    root.lock_rotation = (True, True, True)
    # OrbitPath: R = Orbit(Z만) — Camera의 실부모라 직접 잡고 돌리면 함께 돈다
    if path:
        path.lock_location = (True, True, True)
        path.lock_rotation = (True, True, False)
        path.lock_scale = (True, True, True)
    # Camera: G(Z만) = Tilt. Y는 Z와 반지름에서 드라이버로 계산되고, X는 잠금.
    # R = 자유 회전(XYZ). Bank 슬라이더는 Z를 쓰고, X/Y는 Target Tracking
    # 영향력을 낮췄을 때 수동 조준용으로 쓴다.
    cam.lock_location = (True, True, False)
    cam.lock_rotation = (False, False, False)
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
    path = find_part(self.id_data, "path")
    return math.degrees(path.rotation_euler.z) if path else 0.0


def _set_orbit(self, value):
    path = find_part(self.id_data, "path")
    if path:
        path.rotation_euler.z = math.radians(value)


def _get_tilt(self):
    cam = get_camera(self.id_data)
    if not cam:
        return 0.0
    radius = cam.get(RADIUS_PROP, 0.0)
    if radius < 1e-6:
        return 0.0
    z = max(-radius, min(radius, cam.location.z))
    return math.degrees(math.asin(z / radius))


def _set_tilt(self, value):
    cam = get_camera(self.id_data)
    if cam:
        radius = cam.get(RADIUS_PROP, 5.0)
        cam.location.z = radius * math.sin(math.radians(value))


def _get_bank(self):
    cam = get_camera(self.id_data)
    return math.degrees(cam.rotation_euler.z) if cam else 0.0


def _set_bank(self, value):
    cam = get_camera(self.id_data)
    if cam:
        cam.rotation_euler.z = math.radians(value)


def _get_distance(self):
    root = self.id_data
    cam = get_camera(root)
    return cam.get(RADIUS_PROP, 0.0) * _avg_scale(root) if cam else 0.0


def _set_distance(self, value):
    root = self.id_data
    cam = get_camera(root)
    if cam:
        radius = max(0.001, value / _avg_scale(root))
        cam[RADIUS_PROP] = radius
        cam.location.z = max(-radius, min(radius, cam.location.z))


class CamRigSettings(bpy.types.PropertyGroup):
    orbit: FloatProperty(
        name="Orbit", description="중심점 기준 수평 회전 (도) — 뷰포트에서 OrbitPath를 R로 돌려도 됨",
        get=_get_orbit, set=_set_orbit, soft_min=-360.0, soft_max=360.0)
    tilt: FloatProperty(
        name="Tilt", description="카메라 상하 각도 (도) — 뷰포트에서 Camera를 G로 Z 이동해도 됨",
        get=_get_tilt, set=_set_tilt, soft_min=-89.0, soft_max=89.0)
    bank: FloatProperty(
        name="Bank", description="뷰 축 기준 롤 (도) — 뷰포트에서 Camera를 R로 돌려도 됨",
        get=_get_bank, set=_set_bank, soft_min=-180.0, soft_max=180.0)
    distance: FloatProperty(
        name="Distance", description="중심점에서 카메라까지 거리 — Root를 S로 스케일해도 됨",
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


def add_camera_radius_driver(cam):
    """Camera의 Y 위치가 Z 위치 + 저장된 반지름(camrig_radius)에서 자동으로
    계산되게 한다. 그래서 Camera를 Z로만 움직여도(G, Z) 중심으로부터의
    거리가 유지된 채 호를 그리며 움직인다 — 이것이 곧 Tilt다. 오브젝트
    자기 자신의 다른 채널만 참조하므로 순환 의존성이 생기지 않는다."""
    fcurve = cam.driver_add("location", 1)
    driver = fcurve.driver
    driver.type = 'SCRIPTED'
    vz = driver.variables.new()
    vz.name = "z"
    vz.type = 'TRANSFORMS'
    vz.targets[0].id = cam
    vz.targets[0].transform_type = 'LOC_Z'
    vz.targets[0].transform_space = 'TRANSFORM_SPACE'
    vr = driver.variables.new()
    vr.name = "r"
    vr.type = 'SINGLE_PROP'
    vr.targets[0].id_type = 'OBJECT'
    vr.targets[0].id = cam
    vr.targets[0].data_path = '["%s"]' % RADIUS_PROP
    driver.expression = "-sqrt(max(r * r - z * z, 0.0001))"


def add_rig_extras(context, root):
    """Target / Focus / OrbitPath 생성. Camera는 이 뒤에 만들어 OrbitPath에
    부모로 지정하고 link_camera_extras()로 마무리한다."""
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

    # OrbitPath: Orbit 마스터 겸 Camera의 실부모 (선택 가능)
    path = bpy.data.objects.new("CamRig_OrbitPath", make_orbit_path_curve("CamRig_OrbitPath"))
    path.parent = root
    path[PART_PROP] = "path"
    path.hide_render = True
    collection.objects.link(path)

    return target, focus, path


def link_camera_extras(cam, target, focus):
    """Damped Track(조준)과 DOF 초점을 연결한다."""
    con = cam.constraints.new('DAMPED_TRACK')
    con.name = TRACK_CON_NAME
    con.target = target
    con.track_axis = 'TRACK_NEGATIVE_Z'
    cam.data.dof.focus_object = focus
    cam[PART_PROP] = "camera"


# --- 오퍼레이터 ---------------------------------------------------------------

class CAMRIG_OT_add(bpy.types.Operator):
    """3D 커서 위치에 오빗 카메라 리그 생성"""
    bl_idname = "camrig.add"
    bl_label = "Add Camera Rig"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        cursor = context.scene.cursor.location.copy()
        collection = context.collection

        # Root: 중심점
        root = bpy.data.objects.new(ROOT_ICON + " CamRig_Root", None)
        root.empty_display_type = 'SPHERE'
        root.empty_display_size = 0.6
        root.location = cursor
        collection.objects.link(root)

        target, focus, path = add_rig_extras(context, root)

        # Camera: OrbitPath의 직속 자식. Z 위치 = Tilt(기본 0), 반지름 = Distance(기본 5)
        cam_data = bpy.data.cameras.new("CamRig_Camera")
        cam = bpy.data.objects.new("CamRig_Camera", cam_data)
        cam.parent = path
        cam[RADIUS_PROP] = 5.0
        cam.location = (0.0, -5.0, 0.0)  # 기본 거리 5, Tilt 0
        # ZXY 오일러: Z(bank)가 먼저 적용되어 뷰 축 기준 순수한 롤이 됨
        cam.rotation_mode = 'ZXY'
        cam.rotation_euler = (math.radians(90.0), 0.0, 0.0)
        collection.objects.link(cam)
        add_camera_radius_driver(cam)
        link_camera_extras(cam, target, focus)

        root[ROOT_MARKER] = RIG_VERSION
        apply_rig_locks(root, cam, target, focus, path)

        # 씬 카메라로 지정하고 루트 선택
        context.scene.camera = cam
        for obj in context.selected_objects:
            obj.select_set(False)
        root.select_set(True)
        context.view_layer.objects.active = root

        self.report({'INFO'}, "카메라 리그 생성 완료")
        return {'FINISHED'}


class CAMRIG_OT_upgrade(bpy.types.Operator):
    """구버전 리그를 최신 구조(Pivot 제거, OrbitPath가 Camera의 실부모)로 변환"""
    bl_idname = "camrig.upgrade"
    bl_label = "Upgrade Rig"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        root = get_rig_root(context.active_object)
        if root is None:
            return {'CANCELLED'}
        cam = get_camera(root)
        if cam is None:
            self.report({'WARNING'}, "리그 구조를 찾을 수 없습니다")
            return {'CANCELLED'}

        # v1: 커스텀 프로퍼티 + 드라이버 방식 → 트랜스폼 값으로 변환
        if "orbit" in root.keys():
            orbit = float(root.get("orbit", 0.0))
            tilt_deg = float(root.get("tilt", 20.0))
            bank = float(root.get("bank", 0.0))
            distance = float(root.get("distance", 5.0))
            root.driver_remove("rotation_euler", 2)
            old_parent = cam.parent
            if old_parent and old_parent != root:
                old_parent.driver_remove("rotation_euler", 0)
                old_parent.rotation_euler.x = -math.radians(tilt_deg)
            cam.driver_remove("location", 1)
            cam.driver_remove("rotation_euler", 2)
            root.rotation_euler.z = math.radians(orbit)
            cam.location.y = -distance
            cam.rotation_euler.z = math.radians(bank)
            for key in ("orbit", "tilt", "bank", "distance"):
                if key in root.keys():
                    del root[key]

        # v4에 있었던 Root↔OrbitPath 순환 드라이버 제거 (더는 필요 없다 —
        # 이제 OrbitPath 자신의 회전이 곧 Orbit이고, Root는 회전을 쓰지 않는다)
        if has_driver(root, "rotation_euler", 2):
            root.driver_remove("rotation_euler", 2)
        root.rotation_euler.z = 0.0

        path = find_part(root, "path")
        # 옛 Pivot(카메라의 부모가 Root도 OrbitPath도 아닌 별도 엠프티였던 경우)
        pivot = cam.parent if (cam.parent is not None and cam.parent not in (root, path)) else None

        if pivot:
            old_radius = abs(cam.location.y)
            old_tilt = -pivot.rotation_euler.x  # 옛 getter와 동일한 부호 규칙
        else:
            computed = math.hypot(cam.location.y, cam.location.z)
            old_radius = computed if computed > 1e-6 else cam.get(RADIUS_PROP, 5.0)
            old_tilt = math.atan2(cam.location.z, -cam.location.y) if computed > 1e-6 else 0.0

        target = find_part(root, "target")
        focus = find_part(root, "focus")
        if target is None or focus is None or path is None:
            new_target, new_focus, new_path = add_rig_extras(context, root)
            target = target or new_target
            focus = focus or new_focus
            path = path or new_path
        else:
            path.hide_select = False
            if path.animation_data:
                path.driver_remove("scale")
                path.driver_remove("location", 2)
            path.scale = (1.0, 1.0, 1.0)
            path.location = (0.0, 0.0, 0.0)

        if cam.parent != path:
            cam.parent = path
            cam.matrix_parent_inverse.identity()
            cam.location.x = 0.0
            cam.location.y = -old_radius * math.cos(old_tilt)
            cam.location.z = old_radius * math.sin(old_tilt)
        cam[RADIUS_PROP] = old_radius

        if pivot:
            bpy.data.objects.remove(pivot, do_unlink=True)

        if not has_driver(cam, "location", 1):
            add_camera_radius_driver(cam)
        if not cam.constraints.get(TRACK_CON_NAME):
            link_camera_extras(cam, target, focus)
        if cam.data.dof.focus_object is None:
            cam.data.dof.focus_object = focus

        root[ROOT_MARKER] = RIG_VERSION
        apply_rig_locks(root, cam, target, focus, path)

        if ROOT_ICON not in root.name:
            root.name = ROOT_ICON + " " + root.name
        root.empty_display_size = max(root.empty_display_size, 0.6)

        self.report({'INFO'}, "리그 업그레이드 완료")
        return {'FINISHED'}


class CAMRIG_OT_look_through(bpy.types.Operator):
    """리그 카메라를 씬 카메라로 지정하고 카메라 뷰로 전환"""
    bl_idname = "camrig.look_through"
    bl_label = "Look Through Camera"

    def execute(self, context):
        root = get_rig_root(context.active_object)
        cam = get_camera(root) if root else None
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
        cam = get_camera(root)
        path = find_part(root, "path")
        root.keyframe_insert("location")
        root.keyframe_insert("scale")
        if path:
            path.keyframe_insert("rotation_euler", index=2)
        if cam:
            cam.keyframe_insert("location", index=2)  # Z = Tilt
            cam.keyframe_insert("rotation_euler", index=2)  # Bank
            cam.keyframe_insert('["%s"]' % RADIUS_PROP)  # Distance
        for part in ("target", "focus"):
            obj = find_part(root, part)
            if obj:
                obj.keyframe_insert("location")
        self.report({'INFO'}, "리그 키프레임 삽입 완료")
        return {'FINISHED'}


class CAMRIG_OT_reset_aim(bpy.types.Operator):
    """Target을 중심점으로 되돌리고 카메라의 수동 조준 회전을 정리 (Bank는 유지)"""
    bl_idname = "camrig.reset_aim"
    bl_label = "Reset Aim"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        root = get_rig_root(context.active_object)
        if root is None:
            return {'CANCELLED'}
        cam = get_camera(root)
        if cam:
            cam.location.x = 0.0
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
        elif self.part == "camera":
            obj = get_camera(root)
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

        cam = get_camera(root)

        row = layout.row(align=True)
        row.operator("camrig.look_through", text="Look Through", icon='VIEW_CAMERA')
        row.operator("camrig.keyframe", text="", icon='KEY_HLT')
        row.operator("camrig.reset_aim", text="", icon='CON_TRACKTO')

        # 부품 빠른 선택
        row = layout.row(align=True)
        row.label(text="선택:")
        row.operator("camrig.select_part", text="Root").part = "root"
        row.operator("camrig.select_part", text="Path").part = "path"
        row.operator("camrig.select_part", text="Cam").part = "camera"
        row = layout.row(align=True)
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
        col.label(text="OrbitPath:  R 오빗 (Camera가 함께 돎)")
        col.label(text="Root:  G 이동 · S 거리")
        col.label(text="Camera:  G(Z만) 틸트 · R 자유 회전(Bank=Z)")
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
