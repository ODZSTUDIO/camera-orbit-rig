# Camera Orbit Rig — 중심점 기준으로 회전하는 카메라 리그
# Blender Extension (blender_manifest.toml 참조)

import math
import bpy
from bpy.props import FloatProperty, PointerProperty


# -----------------------------------------------------------------------------
# 리그 구조
#   Root (Empty, 중심점)  - Orbit(Z 회전), 이동(G), 스케일(S)=Distance 배율
#     └ Pivot (Empty)     - Tilt(X 회전)
#         └ Camera        - Distance(-Y 위치), Bank(뷰 축 롤)
#
# 슬라이더는 오브젝트 트랜스폼을 직접 읽고 쓴다(get/set 프로퍼티).
# 그래서 뷰포트에서 G/R/S로 움직여도 슬라이더에 그대로 반영되고, 반대도 마찬가지.
# 리그에 필요 없는 축은 잠가 두어 G/R/S가 정확히 해당 컨트롤만 움직인다.
# 애니메이션은 오브젝트 트랜스폼에 키프레임을 넣으면 된다 (Keyframe Rig 버튼 참고).
# -----------------------------------------------------------------------------

ROOT_MARKER = "is_camrig_root"
RIG_VERSION = 2  # 1: 구버전(드라이버 방식), 2: 트랜스폼 직접 제어 방식


def get_rig_root(obj):
    """선택한 오브젝트에서 부모를 거슬러 올라가며 리그 루트를 찾음"""
    while obj is not None:
        if obj.get(ROOT_MARKER):
            return obj
        obj = obj.parent
    return None


def get_rig_objects(root):
    """(pivot, camera) 반환. 없으면 None"""
    pivot = next((c for c in root.children if c.type == 'EMPTY'), None)
    cam = next((c for c in root.children_recursive if c.type == 'CAMERA'), None)
    return pivot, cam


def apply_rig_locks(root, pivot, cam):
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
        root = bpy.data.objects.new("CamRig_Root", None)
        root.empty_display_type = 'PLAIN_AXES'
        root.empty_display_size = 0.5
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

        root[ROOT_MARKER] = RIG_VERSION
        apply_rig_locks(root, pivot, cam)

        # 씬 카메라로 지정하고 루트 선택
        context.scene.camera = cam
        for obj in context.selected_objects:
            obj.select_set(False)
        root.select_set(True)
        context.view_layer.objects.active = root

        self.report({'INFO'}, "카메라 리그 생성 완료")
        return {'FINISHED'}


class CAMRIG_OT_upgrade(bpy.types.Operator):
    """구버전(드라이버 방식) 리그를 뷰포트 직접 제어 방식으로 변환"""
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

        root[ROOT_MARKER] = RIG_VERSION
        apply_rig_locks(root, pivot, cam)

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
    """현재 프레임에 리그 전체(Orbit/Tilt/Bank/Distance/중심점) 키프레임 삽입"""
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
        self.report({'INFO'}, "리그 키프레임 삽입 완료")
        return {'FINISHED'}


class CAMRIG_OT_reset_aim(bpy.types.Operator):
    """카메라가 다시 중심점을 바라보도록 잠기지 않은 축을 정리 (Bank는 유지)"""
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

        # 구버전(드라이버 방식) 리그는 업그레이드 필요
        if "orbit" in root.keys():
            box = layout.box()
            box.label(text="구버전 리그입니다", icon='ERROR')
            box.operator("camrig.upgrade", icon='FILE_REFRESH')
            return

        pivot, cam = get_rig_objects(root)

        row = layout.row(align=True)
        row.operator("camrig.look_through", text="Look Through", icon='VIEW_CAMERA')
        row.operator("camrig.keyframe", text="", icon='KEY_HLT')
        row.operator("camrig.reset_aim", text="", icon='CON_TRACKTO')

        col = layout.column(align=True)
        col.prop(root.camrig, "orbit", slider=True)
        col.prop(root.camrig, "tilt", slider=True)
        col.prop(root.camrig, "bank", slider=True)
        col.prop(root.camrig, "distance", slider=True)

        box = layout.box()
        box.label(text="뷰포트 단축키", icon='VIEW3D')
        col = box.column(align=True)
        col.label(text="Root:  G 이동 · R 회전(Orbit) · S 거리")
        col.label(text="Pivot:  R 틸트")
        col.label(text="Camera:  G 거리 · R 뱅크")

        if cam is None:
            layout.label(text="카메라가 없습니다", icon='ERROR')
            return

        layout.separator()
        box = layout.box()
        box.label(text="Focus", icon='CAMERA_DATA')
        box.prop(cam.data, "lens", text="Focal Length")

        dof = cam.data.dof
        box.prop(dof, "use_dof", text="Depth of Field")
        sub = box.column(align=True)
        sub.enabled = dof.use_dof
        sub.prop(dof, "focus_distance", text="Focus Distance")
        sub.prop(dof, "aperture_fstop", text="F-Stop")


classes = (
    CamRigSettings,
    CAMRIG_OT_add,
    CAMRIG_OT_upgrade,
    CAMRIG_OT_look_through,
    CAMRIG_OT_keyframe,
    CAMRIG_OT_reset_aim,
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
