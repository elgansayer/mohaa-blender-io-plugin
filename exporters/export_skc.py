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
    SKC_IDENT_INT, SKC_VERSION_CURRENT, SKC_VERSION_OLD,
    CHANNEL_ROTATION, CHANNEL_POSITION,
    SKC_HEADER_SIZE, SKC_FRAME_SIZE, SKC_CHANNEL_DATA_SIZE, SKC_CHANNEL_NAME_SIZE
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
            version: SKC version (13 or 14)
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
        channels: List[Tuple[str, int]] = []  # (name, type)
        
        for bone in pose_bones:
            channels.append((f"{bone.name} rot", CHANNEL_ROTATION))
            channels.append((f"{bone.name} pos", CHANNEL_POSITION))
        
        num_channels = len(channels)
        
        # Calculate offsets and sizes
        header_and_frames_size = SKC_HEADER_SIZE + (num_frames - 1) * SKC_FRAME_SIZE
        channel_data_size = num_frames * num_channels * SKC_CHANNEL_DATA_SIZE
        channel_names_size = num_channels * SKC_CHANNEL_NAME_SIZE
        
        ofs_channel_names = header_and_frames_size + channel_data_size
        total_size = ofs_channel_names + channel_names_size
        
        # Store current frame
        orig_frame = bpy.context.scene.frame_current
        
        # Collect frame data and channel data
        frame_data_list = []  # List of frame structs (bytes)

        # Optimization: Use bytearray for channel data to avoid huge unpacking overhead
        # Pre-allocate if possible (optional but good)
        channel_data_buffer = bytearray()
        
        total_delta = [0.0, 0.0, 0.0]
        
        # Pre-compile struct packer
        pack_channel = struct.Struct('<4f').pack
        pack_frame = struct.Struct('<3f 3f f 3f f i').pack

        for frame_idx in range(num_frames):
            frame_num = frame_start + frame_idx
            bpy.context.scene.frame_set(frame_num)
            
            # Calculate bounds
            min_bounds = [float('inf')] * 3
            max_bounds = [float('-inf')] * 3
            
            for bone in pose_bones:
                pos = bone.head
                for i in range(3):
                    min_bounds[i] = min(min_bounds[i], pos[i])
                    max_bounds[i] = max(max_bounds[i], pos[i])
            
            if min_bounds[0] == float('inf'):
                min_bounds = [0.0, 0.0, 0.0]
                max_bounds = [1.0, 1.0, 1.0]
            
            size = Vector(max_bounds) - Vector(min_bounds)
            radius = size.length / 2.0
            
            delta = (0.0, 0.0, 0.0)
            angle_delta = 0.0
            
            # Prepare frame header
            channel_offset = header_and_frames_size + (frame_idx * num_channels * SKC_CHANNEL_DATA_SIZE)

            frame_struct = pack_frame(
                min_bounds[0], min_bounds[1], min_bounds[2],
                max_bounds[0], max_bounds[1], max_bounds[2],
                radius,
                delta[0], delta[1], delta[2],
                angle_delta,
                channel_offset
            )
            frame_data_list.append(frame_struct)
            
            # Collect channel data
            for channel_name, channel_type in channels:
                bone_name = channel_name.rsplit(' ', 1)[0]
                
                if bone_name in pose_bones:
                    bone = pose_bones[bone_name]
                    
                    if channel_type == CHANNEL_ROTATION:
                        if bone.rotation_mode == 'QUATERNION':
                            quat = bone.rotation_quaternion
                        else:
                            quat = bone.rotation_euler.to_quaternion()
                        val = self._transform_quaternion_inverse(quat)
                    else:  # CHANNEL_POSITION
                        pos = bone.location
                        mohaa_pos = self._transform_position_inverse(pos)
                        val = (mohaa_pos[0], mohaa_pos[1], mohaa_pos[2], 0.0)
                else:
                    if channel_type == CHANNEL_ROTATION:
                        val = (0.0, 0.0, 0.0, 1.0)
                    else:
                        val = (0.0, 0.0, 0.0, 0.0)
                
                channel_data_buffer.extend(pack_channel(*val))
        
        # Restore original frame
        bpy.context.scene.frame_set(orig_frame)
        
        # --- WRITE OUTPUT ---
        output = BytesIO()
        
        # 1. Write Header
        header = struct.pack(
            '<i i i i f 3f f i i i',
            SKC_IDENT_INT,  # ident
            self.version,   # version
            0,              # flags
            total_size,     # nBytesUsed
            frame_time,     # frameTime
            total_delta[0], total_delta[1], total_delta[2],
            0.0,            # totalAngleDelta
            num_channels,   # numChannels
            ofs_channel_names, # ofsChannelNames
            num_frames      # numFrames
        )
        output.write(header)
        
        # 2. Write all frame headers
        output.write(b''.join(frame_data_list))
        
        # 3. Write channel data
        output.write(channel_data_buffer)
        
        # 4. Write channel names
        for channel_name, _ in channels:
            name_bytes = channel_name.encode('latin-1')[:32].ljust(32, b'\x00')
            output.write(name_bytes)
        
        # Write to file
        with open(self.filepath, 'wb') as f:
            f.write(output.getvalue())
        
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
        version: SKC version (13 or 14)
        
    Returns:
        True on success
    """
    exporter = SKCExporter(filepath, armature_obj, action, swap_yz, scale, version)
    return exporter.execute()
