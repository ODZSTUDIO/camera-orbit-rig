# Camera Orbit Rig — 중심점 기준으로 회전하는 카메라 리그
# Blender Extension (blender_manifest.toml 참조)

import math
import bpy


# -----------------------------------------------------------------------------
# 리그 구조
#   Root (Empty, 중심점)  - Orbit(Z 회전)
#     └ Pivot (Empty)     - Tilt(X 회전)
#         └ Camera        - Distance(-Y 위치), Bank(뷰 축 롤)
#
# 슬라이더 값은 Root의 커스텀 프로퍼티에 저장되고 드라이버로 각 트랜스폼에 연결됨.
# 커스텀 프로퍼티라서 키프레임 애니메이션 가능.
# -----------------------------------------------------------------------------

ROOT_MARKER = "is_camrig_root"

PROP_DEFS = {
    # name: (default, min, max, soft_min, soft_max, description)
    "orbit":    (0.0,   -36000.0, 36000.0, -360.0, 360.0, "중심점 기준 수평 회전 (도)"),
    "tilt":     (20.0,  -180.0,   180.0,   -89.0,  89.0,  "카메라 상하 각도 (도)"),
    "bank":     (0.0,   -360.0,   360.0,   -180.0, 180.0, "뷰 축 기준 롤 (도)"),
    "distance": (5.0,    0.001,   100000.0, 0.1,   50.0,  "중심점에서 카메라까지 거리"),
}


def get_rig_root(obj):
    """선택한 오브젝트에서 부모를 거슬러 올라가며 리그 루트를 찾음"""
    while obj is not None:
        if obj.get(ROOT_MARKER):
            return obj
        obj = obj.parent
    return None


def get_rig_camera(root):
    for child in root.children_recursive:
        if child.type == 'CAMERA':
            return child
    return None


def add_driver(id_data, path, index, root, prop_name, expression):
    fcurve = id_data.driver_add(path, index) if index >= 0 else id_data.driver_add(path)
    driver = fcurve.driver
    driver.type = 'SCRIPTED'
    var = driver.variables.new()
    var.name = "v"
    var.type = 'SINGLE_PROP'
    target = var.targets[0]
    target.id_type = 'OBJECT'
    target.id = root
    target.data_path = f'["{prop_name}"]'
    driver.expression = expression
    return fcurve


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
        collection.objects.link(pivot)

        # Camera
        cam_data = bpy.data.cameras.new("CamRig_Camera")
        cam = bpy.data.objects.new("CamRig_Camera", cam_data)
        cam.parent = pivot
        cam.location = (0.0, -PROP_DEFS["distance"][0], 0.0)
        # ZXY 오일러: Z(bank)가 먼저 적용되어 뷰 축 기준 순수한 롤이 됨
        cam.rotation_mode = 'ZXY'
        cam.rotation_euler = (math.radians(90.0), 0.0, 0.0)
        collection.objects.link(cam)

        # 커스텀 프로퍼티 등록
        root[ROOT_MARKER] = 1
        for name, (default, mn, mx, smn, smx, desc) in PROP_DEFS.items():
            root[name] = default
            ui = root.id_properties_ui(name)
            ui.update(min=mn, max=mx, soft_min=smn, soft_max=smx,
                      default=default, description=desc)

        # 드라이버 연결
        add_driver(root, "rotation_euler", 2, root, "orbit", "radians(v)")
        add_driver(pivot, "rotation_euler", 0, root, "tilt", "-radians(v)")
        add_driver(cam, "location", 1, root, "distance", "-v")
        add_driver(cam, "rotation_euler", 2, root, "bank", "radians(v)")

        # 씬 카메라로 지정하고 루트 선택
        context.scene.camera = cam
        for obj in context.selected_objects:
            obj.select_set(False)
        root.select_set(True)
        context.view_layer.objects.active = root

        self.report({'INFO'}, "카메라 리그 생성 완료")
        return {'FINISHED'}


class CAMRIG_OT_look_through(bpy.types.Operator):
    """리그 카메라를 씬 카메라로 지정하고 카메라 뷰로 전환"""
    bl_idname = "camrig.look_through"
    bl_label = "Look Through Camera"

    def execute(self, context):
        root = get_rig_root(context.active_object)
        cam = get_rig_camera(root) if root else None
        if cam is None:
            self.report({'WARNING'}, "리그 카메라를 찾을 수 없습니다")
            return {'CANCELLED'}
        context.scene.camera = cam
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.region_3d.view_perspective = 'CAMERA'
                break
        return {'FINISHED'}


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

        cam = get_rig_camera(root)

        layout.operator("camrig.look_through", icon='VIEW_CAMERA')

        col = layout.column(align=True)
        col.prop(root, '["orbit"]', text="Orbit", slider=True)
        col.prop(root, '["tilt"]', text="Tilt", slider=True)
        col.prop(root, '["bank"]', text="Bank", slider=True)
        col.prop(root, '["distance"]', text="Distance", slider=True)

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
    CAMRIG_OT_add,
    CAMRIG_OT_look_through,
    CAMRIG_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
