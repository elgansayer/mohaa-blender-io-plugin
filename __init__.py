"""
MoHAA SKD/SKC Blender Add-on

Import and export Medal of Honor: Allied Assault skeletal models (.skd)
and animations (.skc) in Blender 4.x.

File Formats:
- SKD: Skeletal model with mesh, bones, vertex weights, UV mapping
- SKC: Skeletal animation with per-bone quaternion rotation and position keyframes

Based on the openmohaa source code:
https://github.com/openmoh/openmohaa
"""

bl_info = {
    "name": "MoHAA SKD/SKC Format",
    "author": "OpenMoHAA Community",
    "version": (1, 1, 0),
    "blender": (4, 0, 0),
    "location": "File > Import/Export",
    "description": "Import/Export Medal of Honor: Allied Assault skeletal models and animations",
    "warning": "",
    "doc_url": "https://github.com/openmoh/openmohaa",
    "category": "Import-Export",
}

import bpy
from bpy.props import StringProperty, BoolProperty, FloatProperty, EnumProperty
from bpy.types import Operator, AddonPreferences
from bpy_extras.io_utils import ImportHelper, ExportHelper
import os


# =============================================================================
# Addon Preferences
# =============================================================================

class MOHAA_AddonPreferences(AddonPreferences):
    """Addon preferences for MoHAA SKD/SKC importer"""
    bl_idname = __name__
    
    game_path: StringProperty(
        name="Game Data Path",
        description="Path to MoHAA game data (e.g., ~/.local/share/openmohaa/main/EXISTING-DATA/)",
        subtype='DIR_PATH',
        default="",
    )
    
    auto_load_shaders: BoolProperty(
        name="Auto-Load Shaders",
        description="Automatically parse shader files to resolve texture paths",
        default=True,
    )
    
    search_pk3_files: BoolProperty(
        name="Search PK3 Files",
        description="Search inside .pk3 (ZIP) files for textures",
        default=True,
    )
    
    def draw(self, context):
        layout = self.layout
        
        layout.label(text="Game Data Settings", icon='PREFERENCES')
        
        box = layout.box()
        box.prop(self, "game_path")
        box.label(text="Path to game data folder containing textures, scripts, and pk3 files", icon='INFO')
        
        box = layout.box()
        box.label(text="Texture Loading Options", icon='TEXTURE')
        box.prop(self, "auto_load_shaders")
        box.prop(self, "search_pk3_files")


def get_addon_preferences():
    """Get addon preferences instance"""
    return bpy.context.preferences.addons.get(__name__)


# =============================================================================
# Import Operators
# =============================================================================

class IMPORT_OT_skd(Operator, ImportHelper):
    """Import MoHAA SKD skeletal model"""
    bl_idname = "import_mesh.skd"
    bl_label = "Import SKD"
    bl_options = {'REGISTER', 'UNDO'}
    
    # File filter
    filename_ext = ".skd"
    filter_glob: StringProperty(
        default="*.skd",
        options={'HIDDEN'},
        maxlen=255,
    )
    
    # Import options
    flip_uvs: BoolProperty(
        name="Flip UVs",
        description="Flip V coordinate (1.0 - v) for game texture compatibility",
        default=True,
    )
    
    swap_yz: BoolProperty(
        name="Swap Y/Z Axes",
        description="Swap Y and Z axes for coordinate conversion",
        default=False,
    )
    
    scale: FloatProperty(
        name="Scale",
        description="Global scale factor",
        default=1.0,
        min=0.001,
        max=1000.0,
    )
    
    textures_path: StringProperty(
        name="Textures Path",
        description="Override texture search path (leave empty to use addon preferences)",
        default="",
        subtype='DIR_PATH',
    )
    
    use_shaders: BoolProperty(
        name="Parse Shaders",
        description="Parse shader files to resolve texture paths",
        default=True,
    )
    
    auto_import_skc: BoolProperty(
        name="Auto-Import Animation",
        description="Automatically import matching .skc animation file if it exists",
        default=True,
    )
    
    def _find_game_path_from_file(self):
        """Try to find game data path from the SKD file location"""
        # Walk up directory tree looking for scripts/ or textures/ folder
        current = os.path.dirname(self.filepath)
        for _ in range(10):  # Max 10 levels up
            scripts_dir = os.path.join(current, 'scripts')
            textures_dir = os.path.join(current, 'textures')
            if os.path.isdir(scripts_dir) or os.path.isdir(textures_dir):
                print(f"Auto-detected game path: {current}")
                return current
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
        return ""
    
    def execute(self, context):
        from .importers.import_skd import import_skd
        
        # Get game path from addon preferences if not overridden
        textures_path = self.textures_path
        if not textures_path:
            prefs = get_addon_preferences()
            if prefs and prefs.preferences.game_path:
                textures_path = prefs.preferences.game_path
        
        # Fallback: try to find game data from SKD file path
        if not textures_path:
            textures_path = self._find_game_path_from_file()
        
        print(f"Using textures path: {textures_path}")
        
        # Parse shaders if enabled
        shader_map = None
        if self.use_shaders and textures_path:
            try:
                from .utils.shader_parser import ShaderParser
                parser = ShaderParser(textures_path)
                shader_map = parser.parse_all_shaders()
                if shader_map:
                    print(f"Loaded {len(shader_map)} shaders from {textures_path}")
            except Exception as e:
                print(f"Warning: Could not parse shaders: {e}")
        
        # Helper to find SKC path
        skc_path = None
        if self.auto_import_skc:
            skd_dir = os.path.dirname(self.filepath)
            skd_basename = os.path.splitext(os.path.basename(self.filepath))[0]
            check_path = os.path.join(skd_dir, skd_basename + ".skc")
            if os.path.exists(check_path):
                skc_path = check_path
        
        armature, mesh = import_skd(
            self.filepath, 
            flip_uvs=self.flip_uvs,
            swap_yz=self.swap_yz, 
            scale=self.scale,
            textures_path=textures_path,
            shader_map=shader_map,
            skc_filepath=skc_path
        )
        
        # Check for matching SKC file and auto-import (Animation Data)
        if armature and skc_path:
            try:
                print(f"[AUTO-IMPORT] Loading Animation: {skc_path}")
                # Set armature as active for animation import
                armature.select_set(True)
                context.view_layer.objects.active = armature
                
                from .importers.import_skc import import_skc
                
                # NOTE: import_skc also tries to fix Rest Pose (using viewport modifier trick).
                # Since we already patched the data in import_skd, the skeleton is ALREADY in the "Frame 0" shape (approx).
                # So forcing Rest Pose again is redundant but harmless (Delta should be near-zero).
                # HOWEVER, the modifier trick relies on modifiers being present. 
                # import_skd creates objects/meshes.
                # So it should be fine.
                
                action = import_skc(skc_path, armature, self.swap_yz, self.scale)
                
                if action:
                    print(f"[AUTO-IMPORT] Success! Action: {action.name}")
                    self.report({'INFO'}, f"Imported SKD and auto-loaded animation: {os.path.basename(skc_path)}")
                else:
                    self.report({'WARNING'}, "Auto-import returned no action")
            except Exception as e:
                print(f"[AUTO-IMPORT] Exception: {e}")
                import traceback
                traceback.print_exc()
                self.report({'WARNING'}, f"Failed to auto-import SKC: {e}")
        else:
             if armature:
                 self.report({'INFO'}, f"Imported SKD: {os.path.basename(self.filepath)}")
        
        if armature or mesh:
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Failed to import SKD file")
            return {'CANCELLED'}
    
    def draw(self, context):
        layout = self.layout
        
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        # Transform options
        box = layout.box()
        box.label(text="Transform", icon='ORIENTATION_GLOBAL')
        box.prop(self, "scale")
        box.prop(self, "swap_yz")
        box.prop(self, "flip_uvs")
        
        # Texture options
        box = layout.box()
        box.label(text="Textures", icon='TEXTURE')
        box.prop(self, "textures_path")
        box.prop(self, "use_shaders")
        box.prop(self, "auto_import_skc")
        
        # Show current game path from preferences
        prefs = get_addon_preferences()
        if prefs and prefs.preferences.game_path:
            box.label(text=f"Using: {prefs.preferences.game_path}", icon='INFO')


class IMPORT_OT_skc(Operator, ImportHelper):
    """Import MoHAA SKC skeletal animation"""
    bl_idname = "import_anim.skc"
    bl_label = "Import SKC"
    bl_options = {'REGISTER', 'UNDO'}
    
    # File filter
    filename_ext = ".skc"
    filter_glob: StringProperty(
        default="*.skc",
        options={'HIDDEN'},
        maxlen=255,
    )
    
    # Import options
    swap_yz: BoolProperty(
        name="Swap Y/Z Axes",
        description="Swap Y and Z axes for coordinate conversion",
        default=False,
    )
    
    scale: FloatProperty(
        name="Scale",
        description="Global scale factor",
        default=1.0,
        min=0.001,
        max=1000.0,
    )
    
    def execute(self, context):
        from .importers.import_skc import import_skc
        
        # Get active armature
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            # Try to find armature in selection
            for sel_obj in context.selected_objects:
                if sel_obj.type == 'ARMATURE':
                    obj = sel_obj
                    break
        
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Please select an armature to apply animation to")
            return {'CANCELLED'}
        
        action = import_skc(
            self.filepath,
            armature_obj=obj,
            swap_yz=self.swap_yz,
            scale=self.scale,
        )
        
        if action:
            self.report({'INFO'}, f"Imported SKC animation: {action.name}")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Failed to import SKC file")
            return {'CANCELLED'}
    
    def draw(self, context):
        layout = self.layout
        
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        box = layout.box()
        box.label(text="Transform", icon='ORIENTATION_GLOBAL')
        box.prop(self, "scale")
        box.prop(self, "swap_yz")


class IMPORT_OT_skc_standalone(Operator, ImportHelper):
    """Import SKC Animation as Standalone Skeleton (without SKD model)"""
    bl_idname = "import_anim.skc_standalone"
    bl_label = "Import SKC as Skeleton"
    bl_options = {'REGISTER', 'UNDO'}
    
    # File filter
    filename_ext = ".skc"
    filter_glob: StringProperty(
        default="*.skc",
        options={'HIDDEN'},
        maxlen=255,
    )
    
    # Import options
    scale: FloatProperty(
        name="Scale",
        description="Global scale factor",
        default=1.0,
        min=0.001,
        max=1000.0,
    )
    
    def execute(self, context):
        from .importers.import_skc_standalone import import_skc_standalone
        
        armature_obj = import_skc_standalone(
            self.filepath,
            scale=self.scale,
        )
        
        if armature_obj:
            self.report({'INFO'}, f"Imported SKC skeleton: {armature_obj.name}")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Failed to import SKC as skeleton")
            return {'CANCELLED'}
    
    def draw(self, context):
        layout = self.layout
        
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        box = layout.box()
        box.label(text="Transform", icon='ORIENTATION_GLOBAL')
        box.prop(self, "scale")



# =============================================================================
# Export Operators
# =============================================================================

class EXPORT_OT_skd(Operator, ExportHelper):
    """Export MoHAA SKD skeletal model"""
    bl_idname = "export_mesh.skd"
    bl_label = "Export SKD"
    bl_options = {'REGISTER'}
    
    # File filter
    filename_ext = ".skd"
    filter_glob: StringProperty(
        default="*.skd",
        options={'HIDDEN'},
        maxlen=255,
    )
    
    # Export options
    flip_uvs: BoolProperty(
        name="Flip UVs",
        description="Flip V coordinate for game texture compatibility",
        default=True,
    )
    
    swap_yz: BoolProperty(
        name="Swap Y/Z Axes",
        description="Swap Y and Z axes for coordinate conversion",
        default=False,
    )
    
    scale: FloatProperty(
        name="Scale",
        description="Global scale factor",
        default=1.0,
        min=0.001,
        max=1000.0,
    )
    
    version: EnumProperty(
        name="Version",
        description="SKD File Version",
        items=[
            ('6', "Version 6 (Standard)", "Supports morph targets and scaling"),
            ('5', "Version 5 (Old)", "Older format, no morph targets"),
        ],
        default='6',
    )

    def execute(self, context):
        from .exporters.export_skd import export_skd
        
        # Get active mesh and armature
        mesh_obj = None
        armature_obj = None
        
        for obj in context.selected_objects:
            if obj.type == 'MESH' and mesh_obj is None:
                mesh_obj = obj
            elif obj.type == 'ARMATURE' and armature_obj is None:
                armature_obj = obj
        
        if not mesh_obj:
            self.report({'ERROR'}, "Please select a mesh to export")
            return {'CANCELLED'}
        
        success = export_skd(
            self.filepath,
            mesh_obj=mesh_obj,
            armature_obj=armature_obj,
            flip_uvs=self.flip_uvs,
            swap_yz=self.swap_yz,
            scale=self.scale,
            version=int(self.version)
        )
        
        if success:
            self.report({'INFO'}, f"Exported SKD: {os.path.basename(self.filepath)}")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Failed to export SKD file")
            return {'CANCELLED'}
    
    def draw(self, context):
        layout = self.layout
        
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        box = layout.box()
        box.label(text="Transform", icon='ORIENTATION_GLOBAL')
        box.prop(self, "scale")
        box.prop(self, "swap_yz")
        box.prop(self, "flip_uvs")

        box = layout.box()
        box.label(text="Format", icon='FILE')
        box.prop(self, "version")


class EXPORT_OT_skc(Operator, ExportHelper):
    """Export MoHAA SKC skeletal animation"""
    bl_idname = "export_anim.skc"
    bl_label = "Export SKC"
    bl_options = {'REGISTER'}
    
    # File filter
    filename_ext = ".skc"
    filter_glob: StringProperty(
        default="*.skc",
        options={'HIDDEN'},
        maxlen=255,
    )
    
    # Export options
    swap_yz: BoolProperty(
        name="Swap Y/Z Axes",
        description="Swap Y and Z axes for coordinate conversion",
        default=False,
    )
    
    scale: FloatProperty(
        name="Scale",
        description="Global scale factor",
        default=1.0,
        min=0.001,
        max=1000.0,
    )
    
    version: EnumProperty(
        name="Version",
        description="SKC File Version",
        items=[
            ('14', "Version 14 (Standard)", "Standard animation format"),
            ('13', "Version 13 (Old)", "Old animation format"),
        ],
        default='14',
    )

    def execute(self, context):
        from .exporters.export_skc import export_skc
        
        # Get active armature
        obj = context.active_object
        if not obj or obj.type != 'ARMATURE':
            for sel_obj in context.selected_objects:
                if sel_obj.type == 'ARMATURE':
                    obj = sel_obj
                    break
        
        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Please select an armature to export animation from")
            return {'CANCELLED'}
        
        success = export_skc(
            self.filepath,
            armature_obj=obj,
            swap_yz=self.swap_yz,
            scale=self.scale,
            version=int(self.version)
        )
        
        if success:
            self.report({'INFO'}, f"Exported SKC: {os.path.basename(self.filepath)}")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Failed to export SKC file")
            return {'CANCELLED'}
    
    def draw(self, context):
        layout = self.layout
        
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        box = layout.box()
        box.label(text="Transform", icon='ORIENTATION_GLOBAL')
        box.prop(self, "scale")
        box.prop(self, "swap_yz")

        box = layout.box()
        box.label(text="Format", icon='FILE')
        box.prop(self, "version")


# =============================================================================
# Menu Functions
# =============================================================================

def menu_func_import_skd(self, context):
    self.layout.operator(IMPORT_OT_skd.bl_idname, text="MoHAA Model (.skd)")

def menu_func_import_skc(self, context):
    self.layout.operator(IMPORT_OT_skc.bl_idname, text="MoHAA Animation (.skc)")

def menu_func_import_skc_standalone(self, context):
    self.layout.operator(IMPORT_OT_skc_standalone.bl_idname, text="MoHAA SKC as Skeleton (.skc)")

def menu_func_export_skd(self, context):
    self.layout.operator(EXPORT_OT_skd.bl_idname, text="MoHAA Model (.skd)")

def menu_func_export_skc(self, context):
    self.layout.operator(EXPORT_OT_skc.bl_idname, text="MoHAA Animation (.skc)")


# =============================================================================
# Registration
# =============================================================================

classes = (
    MOHAA_AddonPreferences,
    IMPORT_OT_skd,
    IMPORT_OT_skc,
    IMPORT_OT_skc_standalone,
    EXPORT_OT_skd,
    EXPORT_OT_skc,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Add menu items
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import_skd)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import_skc)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import_skc_standalone)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export_skd)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export_skc)


def unregister():
    # Remove menu items
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import_skd)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import_skc)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import_skc_standalone)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export_skd)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export_skc)
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
