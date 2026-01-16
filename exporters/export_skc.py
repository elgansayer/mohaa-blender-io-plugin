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
    SKC_HEADER_SIZE, SKC_FRAME_SIZE, SKC_CHANNEL_DATA_SIZE, SKC_CHANNEL_NAME_SIZE
)


class SKCExporter:
    """Exports Blender animations to SKC format"""
    
    def __init__(self, filepath: str,
                 armature_obj: bpy.types.Object,
                 action: Optional[bpy.types.Action] = None,
                 swap_yz: bool = False,
                 scale: float = 1.0):
        """
        Initialize exporter.
        
        Args:
            filepath: Output .skc file path
            armature_obj: Armature object with animation
            action: Specific action to export (or use active)
            swap_yz: Swap Y and Z axes
            scale: Global scale factor
        """
        self.filepath = filepath
        self.armature_obj = armature_obj
        self.action = action
        self.swap_yz = swap_yz
        self.scale = scale
    
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
        # Header: 48 bytes base (reduced to match actual file format)
        # Then (numFrames - 1) * 48 bytes for additional frame headers embedded in header
        # Actually, the header includes first frame, so frames are embedded
        
        # SKC file structure:
        # - skelAnimDataFileHeader_t (48 bytes + (numFrames-1)*48 for frame array)
        # - Channel data: numFrames * numChannels * 16 bytes
        # - Channel names: numChannels * 32 bytes
        
        header_and_frames_size = SKC_HEADER_SIZE + (num_frames - 1) * SKC_FRAME_SIZE  # First frame in header
        channel_data_size = num_frames * num_channels * SKC_CHANNEL_DATA_SIZE
        channel_names_size = num_channels * SKC_CHANNEL_NAME_SIZE
        
        ofs_channel_names = header_and_frames_size + channel_data_size
        total_size = ofs_channel_names + channel_names_size
        
        # Store current frame
        orig_frame = bpy.context.scene.frame_current
        
        # Collect frame data
        frame_data = []  # List of (bounds_min, bounds_max, radius, delta, angle_delta)
        channel_values = []  # List of List of (x, y, z, w) per frame per channel
        
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
            
            # Delta and angle delta (simplified - would need root motion tracking)
            delta = (0.0, 0.0, 0.0)
            angle_delta = 0.0
            
            frame_data.append({
                'bounds_min': tuple(min_bounds),
                'bounds_max': tuple(max_bounds),
                'radius': radius,
                'delta': delta,
                'angle_delta': angle_delta
            })
            
            # Collect channel data for this frame
            frame_channels = []
            for channel_name, channel_type in channels:
                bone_name = channel_name.rsplit(' ', 1)[0]
                
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
                
                frame_channels.append(data)
            
            channel_values.append(frame_channels)
        
        # Restore original frame
        bpy.context.scene.frame_set(orig_frame)
        
        # Build binary output
        output = BytesIO()
        
        # Write header (48 bytes)
        header = struct.pack(
            '<i i i i f 3f f i i i',
            SKC_IDENT_INT,  # ident ('SKAN')
            SKC_VERSION_CURRENT,  # version (14)
            0,  # flags
            total_size,  # nBytesUsed
            frame_time,  # frameTime
            total_delta[0], total_delta[1], total_delta[2],  # totalDelta
            0.0,  # totalAngleDelta
            num_channels,  # numChannels
            ofs_channel_names,  # ofsChannelNames
            num_frames  # numFrames
        )
        output.write(header)
        
        # Write frame headers (48 bytes each, first one is part of header struct)
        # Actually write all frames including first one
        for i, frame in enumerate(frame_data):
            # Calculate channel offset for this frame
            # Channels start after all frame headers
            channel_offset = header_and_frames_size + (i * num_channels * SKC_CHANNEL_DATA_SIZE)
            
            # Only write additional frames (first is in header)
            if i > 0:
                frame_struct = struct.pack(
                    '<3f 3f f 3f f i',
                    frame['bounds_min'][0], frame['bounds_min'][1], frame['bounds_min'][2],
                    frame['bounds_max'][0], frame['bounds_max'][1], frame['bounds_max'][2],
                    frame['radius'],
                    frame['delta'][0], frame['delta'][1], frame['delta'][2],
                    frame['angle_delta'],
                    channel_offset
                )
                output.write(frame_struct)
        
        # Pad/write first frame data if needed
        # The first frame header is embedded in the main header - we handle this by
        # ensuring our header matches the expected format
        
        # For simplicity, write a separate first frame header to complete the structure
        if num_frames > 0:
            frame = frame_data[0]
            channel_offset = header_and_frames_size
            first_frame = struct.pack(
                '<3f 3f f 3f f i',
                frame['bounds_min'][0], frame['bounds_min'][1], frame['bounds_min'][2],
                frame['bounds_max'][0], frame['bounds_max'][1], frame['bounds_max'][2],
                frame['radius'],
                frame['delta'][0], frame['delta'][1], frame['delta'][2],
                frame['angle_delta'],
                channel_offset
            )
            # Insert at correct position (after base header, before other frames)
            # Actually rewrite the output properly
        
        # Rewrite with correct structure
        output = BytesIO()
        
        # Write complete header with embedded first frame
        # skelAnimDataFileHeader_t ends with frame[1] which is the first skelAnimFileFrame_t
        # So header is 48 bytes, but the frame[1] array extends it
        
        # Write base header fields
        output.write(struct.pack('<i', SKC_IDENT_INT))  # ident
        output.write(struct.pack('<i', SKC_VERSION_CURRENT))  # version
        output.write(struct.pack('<i', 0))  # flags
        output.write(struct.pack('<i', total_size))  # nBytesUsed
        output.write(struct.pack('<f', frame_time))  # frameTime
        output.write(struct.pack('<3f', total_delta[0], total_delta[1], total_delta[2]))  # totalDelta
        output.write(struct.pack('<f', 0.0))  # totalAngleDelta
        output.write(struct.pack('<i', num_channels))  # numChannels
        output.write(struct.pack('<i', ofs_channel_names))  # ofsChannelNames
        output.write(struct.pack('<i', num_frames))  # numFrames
        
        # Write all frame headers (first one is frame[1] in the header struct)
        for i, frame in enumerate(frame_data):
            channel_offset = header_and_frames_size + (i * num_channels * SKC_CHANNEL_DATA_SIZE)
            
            output.write(struct.pack(
                '<3f 3f f 3f f i',
                frame['bounds_min'][0], frame['bounds_min'][1], frame['bounds_min'][2],
                frame['bounds_max'][0], frame['bounds_max'][1], frame['bounds_max'][2],
                frame['radius'],
                frame['delta'][0], frame['delta'][1], frame['delta'][2],
                frame['angle_delta'],
                channel_offset
            ))
        
        # Write channel data for all frames
        for frame_idx, frame_channels in enumerate(channel_values):
            for channel_data in frame_channels:
                output.write(struct.pack('<4f', *channel_data))
        
        # Write channel names
        for channel_name, _ in channels:
            name_bytes = channel_name.encode('latin-1')[:32].ljust(32, b'\x00')
            output.write(name_bytes)
        
        # Write to file
        with open(self.filepath, 'wb') as f:
            f.write(output.getvalue())
        
        print(f"  Frames: {num_frames}")
        print(f"  Channels: {num_channels}")
        print(f"  FPS: {fps}")


def export_skc(filepath: str,
               armature_obj: bpy.types.Object,
               action: Optional[bpy.types.Action] = None,
               swap_yz: bool = False,
               scale: float = 1.0) -> bool:
    """
    Export animation to SKC file.
    
    Args:
        filepath: Output file path
        armature_obj: Armature object
        action: Action to export
        swap_yz: Swap Y and Z axes
        scale: Global scale factor
        
    Returns:
        True on success
    """
    exporter = SKCExporter(filepath, armature_obj, action, swap_yz, scale)
    return exporter.execute()
