"""
SKC (Skeletal Animation) Importer for Blender

Imports MoHAA .skc animation files and applies them to an existing armature.

Channel Convention:
- Rotation channels end with " rot" and contain quaternions (XYZW)
- Position channels end with " pos" and contain positions (XYZ)
"""

import bpy
from mathutils import Vector, Matrix, Quaternion, Euler
from typing import Dict, List, Tuple, Optional
import os
import math

from ..formats.skc_format import (
    SKCAnimation, SKCHeader, SKCFrame, SKCChannel, SKCChannelFrame,
    CHANNEL_ROTATION, CHANNEL_POSITION, CHANNEL_VALUE,
    get_bone_name_from_channel
)


class SKCImporter:
    """Imports SKC animations into Blender"""
    
    def __init__(self, filepath: str,
                 armature_obj: bpy.types.Object,
                 swap_yz: bool = False,
                 scale: float = 1.0):
        """
        Initialize importer.
        
        Args:
            filepath: Path to .skc file
            armature_obj: Target armature object
            swap_yz: Swap Y and Z axes
            scale: Global scale factor
        """
        self.filepath = filepath
        self.armature_obj = armature_obj
        self.swap_yz = swap_yz
        self.scale = scale
        
        self.animation: Optional[SKCAnimation] = None
        self.action: Optional[bpy.types.Action] = None
    
    def execute(self) -> Optional[bpy.types.Action]:
        """
        Execute import.
        
        Returns:
            Created action or None on failure
        """
        if not self.armature_obj or self.armature_obj.type != 'ARMATURE':
            print("Error: No valid armature object provided")
            return None
        
        # Load SKC file
        try:
            self.animation = SKCAnimation.read(self.filepath)
        except Exception as e:
            print(f"Error loading SKC file: {e}")
            return None
        
        # Get action name from file
        action_name = os.path.splitext(os.path.basename(self.filepath))[0]
        
        # Create action
        self.action = self._create_action(action_name)
        
        return self.action
    
    def _transform_position(self, pos: Tuple[float, float, float]) -> Vector:
        """Transform position from MoHAA to Blender coordinates"""
        x, y, z = pos
        
        if self.swap_yz:
            return Vector((x * self.scale, -z * self.scale, y * self.scale))
        else:
            return Vector((x * self.scale, -y * self.scale, z * self.scale))
    
    def _transform_quaternion(self, quat: Tuple[float, float, float, float]) -> Quaternion:
        """Transform quaternion from MoHAA to Blender coordinates"""
        # MoHAA quaternion is (x, y, z, w)
        # Blender Quaternion is (w, x, y, z)
        x, y, z, w = quat
        
        if self.swap_yz:
            # Swap Y and Z, negate rotation
            return Quaternion((w, x, -z, y))
        else:
            # Negate Y rotation
            return Quaternion((w, x, -y, z))
    
    def _create_action(self, name: str) -> bpy.types.Action:
        """Create animation action from SKC data"""
        # Create new action
        action = bpy.data.actions.new(name=name)
        action.use_fake_user = True
        
        # Assign to armature
        if not self.armature_obj.animation_data:
            self.armature_obj.animation_data_create()
        self.armature_obj.animation_data.action = action
        
        # Set frame range
        fps = self.animation.header.fps
        bpy.context.scene.render.fps = int(fps)
        bpy.context.scene.frame_start = 0
        bpy.context.scene.frame_end = self.animation.header.num_frames - 1
        
        # Get armature bones
        armature = self.armature_obj.data
        pose_bones = self.armature_obj.pose.bones
        
        # Build channel to bone mapping
        bone_channels: Dict[str, Tuple[Optional[int], Optional[int]]] = {}
        
        for i, channel in enumerate(self.animation.channels):
            bone_name = get_bone_name_from_channel(channel.name)
            
            if bone_name not in bone_channels:
                bone_channels[bone_name] = (None, None)
            
            rot_idx, pos_idx = bone_channels[bone_name]
            
            if channel.channel_type == CHANNEL_ROTATION:
                bone_channels[bone_name] = (i, pos_idx)
            elif channel.channel_type == CHANNEL_POSITION:
                bone_channels[bone_name] = (rot_idx, i)
        
        # Create keyframes for each bone
        for bone_name, (rot_idx, pos_idx) in bone_channels.items():
            if bone_name not in pose_bones:
                continue
            
            pose_bone = pose_bones[bone_name]
            
            # Create fcurves for rotation (quaternion)
            if rot_idx is not None:
                data_path = f'pose.bones["{bone_name}"].rotation_quaternion'
                
                # Create 4 curves for WXYZ
                rot_curves = []
                for i in range(4):
                    fc = action.fcurves.new(data_path=data_path, index=i)
                    rot_curves.append(fc)
                
                # Add keyframes
                for frame_idx in range(self.animation.header.num_frames):
                    channel_data = self.animation.channel_data[frame_idx][rot_idx]
                    quat = self._transform_quaternion(channel_data.as_quaternion)
                    
                    for i, fc in enumerate(rot_curves):
                        fc.keyframe_points.insert(frame_idx, quat[i])
            
            # Create fcurves for position
            if pos_idx is not None:
                data_path = f'pose.bones["{bone_name}"].location'
                
                # Create 3 curves for XYZ
                loc_curves = []
                for i in range(3):
                    fc = action.fcurves.new(data_path=data_path, index=i)
                    loc_curves.append(fc)
                
                # Add keyframes
                for frame_idx in range(self.animation.header.num_frames):
                    channel_data = self.animation.channel_data[frame_idx][pos_idx]
                    pos = self._transform_position(channel_data.as_position)
                    
                    for i, fc in enumerate(loc_curves):
                        fc.keyframe_points.insert(frame_idx, pos[i])
        
        # Set rotation mode for all bones with rotation keyframes
        for bone_name in bone_channels:
            if bone_name in pose_bones:
                pose_bones[bone_name].rotation_mode = 'QUATERNION'
        
        # Update fcurve handles for smooth interpolation
        for fc in action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'LINEAR'
        
        return action


def import_skc(filepath: str,
               armature_obj: bpy.types.Object,
               swap_yz: bool = False,
               scale: float = 1.0) -> Optional[bpy.types.Action]:
    """
    Import an SKC animation file.
    
    Args:
        filepath: Path to .skc file
        armature_obj: Target armature object
        swap_yz: Swap Y and Z axes
        scale: Global scale factor
        
    Returns:
        Created action or None on failure
    """
    importer = SKCImporter(filepath, armature_obj, swap_yz, scale)
    return importer.execute()
