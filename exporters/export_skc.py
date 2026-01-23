"""
SKC (Skeletal Animation) Exporter for Blender

Exports Blender animation actions to MoHAA .skc format.

Binary Format (based on openmohaa):
- skelAnimDataFileHeader_t: Animation header
- skelAnimFileFrame_t[]: Per-frame bounds and delta
- Channel data: vec4_t per channel per frame
- Channel names: 32-byte null-terminated strings
"""

import bpy
import struct
from mathutils import Vector, Matrix, Quaternion
from typing import Dict, List, Tuple, Optional
import os
from io import BytesIO

from ..formats.skc_format import (
    SKC_IDENT_INT, SKC_VERSION_CURRENT,
    CHANNEL_ROTATION, CHANNEL_POSITION,
    SKC_HEADER_SIZE, SKC_FRAME_SIZE, SKC_CHANNEL_DATA_SIZE, SKC_CHANNEL_NAME_SIZE,
    SKCAnimation, SKCHeader, SKCFrame, SKCChannel, SKCChannelFrame
)


class SKCExporter:
    """Exports Blender animations to SKC format"""
    
    def __init__(self, filepath: str,
                 armature_obj: bpy.types.Object,
                 action: Optional[bpy.types.Action] = None,
                 swap_yz: bool = False,
                 scale: float = 1.0,
                 version: int = SKC_VERSION_CURRENT):
        """
        Initialize exporter.
        
        Args:
            filepath: Output .skc file path
            armature_obj: Armature object with animation
            action: Specific action to export (or use active)
            swap_yz: Swap Y and Z axes
            scale: Global scale factor
            version: SKC format version (13 or 14)
        """
        self.filepath = filepath
        self.armature_obj = armature_obj
        self.action = action
        self.swap_yz = swap_yz
        self.scale = scale
        self.version = version
    
    def execute(self) -> bool:
        """
        Execute export.
        
        Returns:
            True on success, False on failure
        """
        if not self.armature_obj or self.armature_obj.type != 'ARMATURE':
            print("Error: No valid armature object provided")
            return False
        
        # Get action
        action = self.action
        if not action:
            if self.armature_obj.animation_data:
                action = self.armature_obj.animation_data.action
        
        if not action:
            print("Error: No animation action to export")
            return False
        
        try:
            # Build animation data and write to file
            self._write_animation(action)
            
            print(f"Successfully exported SKC: {self.filepath}")
            return True
            
        except Exception as e:
            print(f"Error exporting SKC: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _transform_position_inverse(self, pos: Vector) -> Tuple[float, float, float]:
        """Transform position from Blender to MoHAA coordinates"""
        x, y, z = pos
        inv_scale = 1.0 / self.scale if self.scale != 0 else 1.0
        
        if self.swap_yz:
            return (x * inv_scale, z * inv_scale, -y * inv_scale)
        else:
            return (x * inv_scale, -y * inv_scale, z * inv_scale)
    
    def _transform_quaternion_inverse(self, quat: Quaternion) -> Tuple[float, float, float, float]:
        """Transform quaternion from Blender to MoHAA coordinates.
        
        Blender Quaternion is (w, x, y, z)
        MoHAA quaternion is (x, y, z, w)
        """
        w, x, y, z = quat
        
        if self.swap_yz:
            return (x, z, -y, w)
        else:
            return (x, -y, z, w)
    
    def _write_animation(self, action: bpy.types.Action) -> None:
        """Build and write animation data to file"""
        pose_bones = self.armature_obj.pose.bones
        
        # Get frame range
        frame_start = int(action.frame_range[0])
        frame_end = int(action.frame_range[1])
        num_frames = max(1, frame_end - frame_start + 1)
        
        fps = bpy.context.scene.render.fps
        frame_time = 1.0 / fps
        
        # Build channel list (rotation + position for each bone)
        channels: List[SKCChannel] = []
        
        for bone in pose_bones:
            channels.append(SKCChannel(name=f"{bone.name} rot", channel_type=CHANNEL_ROTATION))
            channels.append(SKCChannel(name=f"{bone.name} pos", channel_type=CHANNEL_POSITION))
        
        num_channels = len(channels)
        
        # Store current frame
        orig_frame = bpy.context.scene.frame_current
        
        # Collect data
        frames: List[SKCFrame] = []
        all_channel_data: List[List[SKCChannelFrame]] = []
        
        total_delta = [0.0, 0.0, 0.0]
        
        for frame_idx in range(num_frames):
            frame_num = frame_start + frame_idx
            bpy.context.scene.frame_set(frame_num)
            
            # Calculate bounds from bone positions
            min_bounds = [float('inf')] * 3
            max_bounds = [float('-inf')] * 3
            
            for bone in pose_bones:
                pos = bone.head
                for i in range(3):
                    min_bounds[i] = min(min_bounds[i], pos[i])
                    max_bounds[i] = max(max_bounds[i], pos[i])
            
            # Handle empty armature
            if min_bounds[0] == float('inf'):
                min_bounds = [0.0, 0.0, 0.0]
                max_bounds = [1.0, 1.0, 1.0]
            
            # Calculate radius
            size = Vector(max_bounds) - Vector(min_bounds)
            radius = size.length / 2.0
            
            # Delta and angle delta (simplified)
            delta = (0.0, 0.0, 0.0)
            angle_delta = 0.0
            
            frames.append(SKCFrame(
                bounds_min=tuple(min_bounds),
                bounds_max=tuple(max_bounds),
                radius=radius,
                delta=delta,
                angle_delta=angle_delta,
                ofs_channels=0 # Will be calculated by SKCAnimation.write
            ))
            
            # Collect channel data for this frame
            frame_channels = []
            for channel in channels:
                bone_name = channel.name.rsplit(' ', 1)[0]
                channel_type = channel.channel_type
                
                if bone_name in pose_bones:
                    bone = pose_bones[bone_name]
                    
                    if channel_type == CHANNEL_ROTATION:
                        # Get rotation as quaternion
                        if bone.rotation_mode == 'QUATERNION':
                            quat = bone.rotation_quaternion
                        else:
                            quat = bone.rotation_euler.to_quaternion()
                        data = self._transform_quaternion_inverse(quat)
                    else:  # CHANNEL_POSITION
                        pos = bone.location
                        mohaa_pos = self._transform_position_inverse(pos)
                        data = (mohaa_pos[0], mohaa_pos[1], mohaa_pos[2], 0.0)
                else:
                    # Default identity values
                    if channel_type == CHANNEL_ROTATION:
                        data = (0.0, 0.0, 0.0, 1.0)  # Identity quaternion
                    else:
                        data = (0.0, 0.0, 0.0, 0.0)
                
                frame_channels.append(SKCChannelFrame(data=data))
            
            all_channel_data.append(frame_channels)
        
        # Restore original frame
        bpy.context.scene.frame_set(orig_frame)
        
        # Create Header
        header = SKCHeader(
            ident=SKC_IDENT_INT,
            version=self.version,
            flags=0,
            n_bytes_used=0, # Will be calc
            frame_time=frame_time,
            total_delta=tuple(total_delta),
            total_angle_delta=0.0,
            num_channels=num_channels,
            ofs_channel_names=0, # Will be calc
            num_frames=num_frames
        )
        
        # Create Animation Object
        animation = SKCAnimation(
            header=header,
            frames=frames,
            channels=channels,
            channel_data=all_channel_data
        )
        
        # Write to file
        animation.write(self.filepath, version=self.version)
        
        print(f"  Frames: {num_frames}")
        print(f"  Channels: {num_channels}")
        print(f"  FPS: {fps}")
        print(f"  Version: {self.version}")


def export_skc(filepath: str,
               armature_obj: bpy.types.Object,
               action: Optional[bpy.types.Action] = None,
               swap_yz: bool = False,
               scale: float = 1.0,
               version: int = SKC_VERSION_CURRENT) -> bool:
    """
    Export animation to SKC file.
    
    Args:
        filepath: Output file path
        armature_obj: Armature object
        action: Action to export
        swap_yz: Swap Y and Z axes
        scale: Global scale factor
        version: SKC format version
        
    Returns:
        True on success
    """
    exporter = SKCExporter(filepath, armature_obj, action, swap_yz, scale, version)
    return exporter.execute()
