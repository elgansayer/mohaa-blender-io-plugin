"""
SKC Importer - DATA TRANSFORM + REST POSE FIX

Fixes distortion caused by SKD's collapsed "Rest Pose".
1. Applies SKC Frame 0 transforms to the Pose.
2. Calls 'armature_apply' to bake this as the new Rest Pose and update Mesh binding.
3. Creates Animation Action using proper deltas.
"""

import bpy
from mathutils import Vector, Matrix, Quaternion
from typing import Dict, List, Tuple, Optional
import os

from ..formats.skc_format import (
    SKCAnimation, CHANNEL_ROTATION, CHANNEL_POSITION,
    get_bone_name_from_channel
)

class SKCImporter:
    def __init__(self, filepath: str,
                 armature_obj: bpy.types.Object,
                 swap_yz: bool = False,
                 scale: float = 1.0):
        self.filepath = filepath
        self.armature_obj = armature_obj
        self.swap_yz = swap_yz
        self.scale = scale
        self.animation = None
        self.action = None

    def execute(self) -> Optional[bpy.types.Action]:
        if not self.armature_obj or self.armature_obj.type != 'ARMATURE':
            print("Error: No valid armature object provided")
            return None
        
        try:
            self.animation = SKCAnimation.read(self.filepath)
        except Exception as e:
            print(f"Error loading SKC file: {e}")
            return None
        
        # NOTE: Rest pose is now fixed at data level in import_skd via skd_patcher.
        # The following call is disabled to avoid double-fixing which causes conflicts.
        # self._fix_rest_pose()
        
        # Create Animation Action
        action_name = os.path.splitext(os.path.basename(self.filepath))[0]
        self.action = self._create_action(action_name)
        
        print(f"Info: Imported SKC animation: {action_name}")
        return self.action
    
    def _transform_pos(self, pos: Tuple[float, float, float]) -> Vector:
        """Transform position: MoHAA (X,Y,Z) -> Blender (X,-Z,Y) if swapped"""
        x, y, z = pos
        if self.swap_yz:
            return Vector((x, -z, y)) * self.scale
        else:
            return Vector((x, y, z)) * self.scale
    
    def _transform_quat(self, quat: Tuple[float, float, float, float]) -> Quaternion:
        """Transform quaternion: MoHAA -> Blender"""
        x, y, z, w = quat
        if self.swap_yz:
            # Swap Y/Z in quaternion too: (w,x,y,z) -> (w,x,-z,y)
            return Quaternion((w, x, -z, y))
        else:
            return Quaternion((w, x, y, z))

    def _fix_rest_pose(self):
        """Apply SKC Frame 0 as the new Rest Pose to fix collapsed skeleton"""
        print("Applying SKC Frame 0 as Rest Pose...")
        
        # Ensure we are in Pose Mode
        bpy.context.view_layer.objects.active = self.armature_obj
        if bpy.context.mode != 'POSE':
            bpy.ops.object.mode_set(mode='POSE')
        
        # Temporarily ENABLE Armature Modifiers on child meshes
        # This allows 'armature_apply' to update the mesh geometry to match the new skeleton
        meshes = [child for child in self.armature_obj.children if child.type == 'MESH']
        modifiers = {}
        for mesh in meshes:
            for mod in mesh.modifiers:
                if mod.type == 'ARMATURE' and mod.object == self.armature_obj:
                    modifiers[(mesh, mod)] = mod.show_viewport
                    mod.show_viewport = True 
                    print(f"Enabled modifier {mod.name} on {mesh.name} for update")

        pose_bones = self.armature_obj.pose.bones
        
        # Map SKC channels
        bone_channels = {}
        for i, channel in enumerate(self.animation.channels):
            bone_name = get_bone_name_from_channel(channel.name)
            if bone_name not in bone_channels:
                bone_channels[bone_name] = {'rot': None, 'pos': None}
            if channel.channel_type == CHANNEL_ROTATION:
                bone_channels[bone_name]['rot'] = i
            elif channel.channel_type == CHANNEL_POSITION:
                bone_channels[bone_name]['pos'] = i
        
        # Pre-calculate Rest Local Matrices (Current collapsed state)
        armature_data = self.armature_obj.data
        rest_local_matrices = {} 
        for bone in armature_data.bones:
            rest_world = bone.matrix_local
            if bone.parent:
                parent_rest_world = bone.parent.matrix_local
                rest_local = parent_rest_world.inverted() @ rest_world
            else:
                rest_local = rest_world
            rest_local_matrices[bone.name] = rest_local

        # Apply Frame 0 transforms
        for bone_name, data in bone_channels.items():
            if bone_name not in pose_bones:
                continue
            
            pose_bone = pose_bones[bone_name]
            rest_local = rest_local_matrices.get(bone_name, Matrix.Identity(4))
            
            target_pos = rest_local.to_translation()
            target_quat = rest_local.to_quaternion()
            
            # Override with Frame 0 data
            pos_idx = data['pos']
            rot_idx = data['rot']
            
            if pos_idx is not None:
                raw_pos = self.animation.channel_data[0][pos_idx].as_position
                target_pos = self._transform_pos(raw_pos)
            
            if rot_idx is not None:
                raw_quat = self.animation.channel_data[0][rot_idx].as_quaternion
                target_quat = self._transform_quat(raw_quat)
            
            # Build Absolute Local Matrix (Parent-Relative)
            target_matrix = target_quat.to_matrix().to_4x4()
            target_matrix.translation = target_pos
            
            # Calculate matrix_basis (Delta from Current Rest)
            delta_matrix = rest_local.inverted() @ target_matrix
            
            pose_bone.matrix_basis = delta_matrix
            
        # FORCE UPDATE SCENE
        bpy.context.view_layer.update()
        
        # Select all bones for apply
        bpy.ops.pose.select_all(action='SELECT')
        
        # APPLY POSE AS REST POSE
        # This fixes the Skeleton AND updates Mesh Binding
        # selected=True only applies to selected bones, but updates linked meshes
        try:
            bpy.ops.pose.armature_apply(selected=True)
            print("Rest Pose Updated.")
        except Exception as e:
            print(f"Error applying rest pose: {e}")

        # Restore modifier visibility (optional, usually True is what we want)
        for (mesh, mod), visible in modifiers.items():
             pass # Leave them enabled? User wants to see deformation.
             # mod.show_viewport = visible

    def _create_action(self, name: str) -> bpy.types.Action:
        """Create animation action (deltas now calculated against FIXED Rest Pose)"""
        if name in bpy.data.actions:
            bpy.data.actions.remove(bpy.data.actions[name])
            
        action = bpy.data.actions.new(name=name)
        action.use_fake_user = True
        
        if not self.armature_obj.animation_data:
            self.armature_obj.animation_data_create()
        self.armature_obj.animation_data.action = action
        
        self.armature_obj.animation_data.action.frame_range = (0, self.animation.header.num_frames - 1)
        
        pose_bones = self.armature_obj.pose.bones
        armature_data = self.armature_obj.data
        
        # Re-Calculate Rest Pose Matrices (NOW FIXED)
        rest_local_matrices = {}
        for bone in armature_data.bones:
            rest_world = bone.matrix_local
            if bone.parent:
                parent_rest_world = bone.parent.matrix_local
                rest_local = parent_rest_world.inverted() @ rest_world
            else:
                rest_local = rest_world
            rest_local_matrices[bone.name] = rest_local
            
        # Map channels
        bone_channels = {}
        for i, channel in enumerate(self.animation.channels):
            bone_name = get_bone_name_from_channel(channel.name)
            if bone_name not in bone_channels:
                bone_channels[bone_name] = {'rot': None, 'pos': None}
            if channel.channel_type == CHANNEL_ROTATION:
                bone_channels[bone_name]['rot'] = i
            elif channel.channel_type == CHANNEL_POSITION:
                bone_channels[bone_name]['pos'] = i

        # Process Keyframes
        for bone_name, data in bone_channels.items():
            if bone_name not in pose_bones:
                continue
            
            pose_bone = pose_bones[bone_name]
            rest_local = rest_local_matrices.get(bone_name, Matrix.Identity(4))
            rest_local_inv = rest_local.inverted()
            
            rot_idx = data['rot']
            pos_idx = data['pos']
            
            if rot_idx is None and pos_idx is None:
                continue

            for frame_idx in range(self.animation.header.num_frames):
                target_pos = rest_local.to_translation()
                target_quat = rest_local.to_quaternion()
                
                if pos_idx is not None:
                    raw_pos = self.animation.channel_data[frame_idx][pos_idx].as_position
                    target_pos = self._transform_pos(raw_pos)
                    
                if rot_idx is not None:
                    raw_quat = self.animation.channel_data[frame_idx][rot_idx].as_quaternion
                    target_quat = self._transform_quat(raw_quat)
                    
                target_matrix = target_quat.to_matrix().to_4x4()
                target_matrix.translation = target_pos
                
                delta_matrix = rest_local_inv @ target_matrix
                
                pose_bone.location = delta_matrix.to_translation()
                pose_bone.rotation_quaternion = delta_matrix.to_quaternion()
                
                pose_bone.keyframe_insert(data_path="location", frame=frame_idx)
                pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame_idx)
        
        for bone_name in bone_channels:
            if bone_name in pose_bones:
                pose_bones[bone_name].rotation_mode = 'QUATERNION'
                
        return action

def import_skc(filepath: str, armature_obj: bpy.types.Object, swap_yz: bool = False, scale: float = 1.0):
    importer = SKCImporter(filepath, armature_obj, swap_yz, scale)
    return importer.execute()
