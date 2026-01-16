"""
SKC (Skeletal Animation) Binary Format Definitions

This module defines Python struct formats that mirror the C++ structures from openmohaa:
- Source: code/skeletor/skeletor_animation_file_format.h
- Source: code/skeletor/skeletor_loadanimation.cpp

SKC files use 'SKAN' identifier with version 13 (old) or 14 (current).
"""

import struct
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from io import BytesIO

# =============================================================================
# Constants from tiki_shared.h and skeletor_animation_file_format.h
# =============================================================================

# SKC file identifiers
SKC_IDENT = b'SKAN'  # (*(int *)"SKAN") = 0x4E414B53
SKC_IDENT_INT = 0x4E414B53

# Supported versions
SKC_VERSION_OLD = 13  # TIKI_SKC_HEADER_OLD_VERSION
SKC_VERSION_CURRENT = 14  # TIKI_SKC_HEADER_VERSION

# Channel name max length
MAX_CHANNEL_NAME = 32

# Animation flags from tiki_shared.h
TAF_RANDOM = 0x1
TAF_NOREPEAT = 0x2
TAF_DONTREPEAT = TAF_RANDOM | TAF_NOREPEAT
TAF_DEFAULT_ANGLES = 0x8
TAF_NOTIMECHECK = 0x10
TAF_DELTADRIVEN = 0x20
TAF_HASDELTA = 0x40
TAF_HASMORPH = 0x80
TAF_HASUPPER = 0x100
TAF_AUTOSTEPS = 0x400
TAF_AUTOSTEPS_RUNNING = 0x800
TAF_AUTOSTEPS_EQUIPMENT = 0x1000

# Channel types (from skeletor_name_lists.h)
CHANNEL_ROTATION = 0  # Quaternion (4 floats)
CHANNEL_POSITION = 1  # Position (3 floats)
CHANNEL_NONE = 2
CHANNEL_VALUE = 3  # Single float value


# =============================================================================
# Struct format strings
# =============================================================================

# skelAnimDataFileHeader_t - Animation file header (variable size)
# typedef struct {
#     int                 ident;           // 4 bytes - 'SKAN'
#     int                 version;         // 4 bytes - Version number
#     int                 flags;           // 4 bytes - Animation flags
#     int                 nBytesUsed;      // 4 bytes - Size of animation data
#     float               frameTime;       // 4 bytes - Time per frame (1/fps)
#     SkelVec3            totalDelta;      // 12 bytes - Total movement delta
#     float               totalAngleDelta; // 4 bytes - Total rotation delta
#     int                 numChannels;     // 4 bytes - Number of channels
#     int                 ofsChannelNames; // 4 bytes - Offset to channel names
#     int                 numFrames;       // 4 bytes - Number of frames
#     skelAnimFileFrame_t frame[1];        // Variable - Frame data starts here
# } skelAnimDataFileHeader_t;

SKC_HEADER_SIZE = 48  # Base size without frames
SKC_HEADER_FORMAT = '<i i i i f 3f f i i i'

# skelAnimFileFrame_t - Per-frame data (48 bytes)
# typedef struct {
#     SkelVec3 bounds[2];   // 24 bytes - Bounding box (min[3], max[3])
#     float    radius;      // 4 bytes - Bounding sphere radius
#     SkelVec3 delta;       // 12 bytes - Frame movement delta
#     float    angleDelta;  // 4 bytes - Frame rotation delta
#     int      iOfsChannels;// 4 bytes - Offset to channel data for this frame
# } skelAnimFileFrame_t;

SKC_FRAME_SIZE = 48
SKC_FRAME_FORMAT = '<3f 3f f 3f f i'

# Channel data - 16 bytes per channel (vec4_t)
# Rotation channels use all 4 floats (quaternion XYZW)
# Position channels use 3 floats + padding
# Value channels use 1 float + padding
SKC_CHANNEL_DATA_SIZE = 16
SKC_CHANNEL_DATA_FORMAT = '<4f'

# Channel name - 32 bytes null-padded
SKC_CHANNEL_NAME_SIZE = 32
SKC_CHANNEL_NAME_FORMAT = '<32s'


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SKCHeader:
    """SKC animation file header"""
    ident: int
    version: int
    flags: int
    n_bytes_used: int
    frame_time: float
    total_delta: Tuple[float, float, float]
    total_angle_delta: float
    num_channels: int
    ofs_channel_names: int
    num_frames: int
    
    @classmethod
    def read(cls, f: BytesIO) -> 'SKCHeader':
        """Read header from file"""
        data = f.read(SKC_HEADER_SIZE)
        unpacked = struct.unpack(SKC_HEADER_FORMAT, data)
        return cls(
            ident=unpacked[0],
            version=unpacked[1],
            flags=unpacked[2],
            n_bytes_used=unpacked[3],
            frame_time=unpacked[4],
            total_delta=(unpacked[5], unpacked[6], unpacked[7]),
            total_angle_delta=unpacked[8],
            num_channels=unpacked[9],
            ofs_channel_names=unpacked[10],
            num_frames=unpacked[11]
        )
    
    def write(self, f: BytesIO) -> None:
        """Write header to file"""
        data = struct.pack(
            SKC_HEADER_FORMAT,
            self.ident, self.version,
            self.flags, self.n_bytes_used,
            self.frame_time,
            self.total_delta[0], self.total_delta[1], self.total_delta[2],
            self.total_angle_delta,
            self.num_channels, self.ofs_channel_names, self.num_frames
        )
        f.write(data)
    
    @property
    def fps(self) -> float:
        """Get frames per second"""
        if self.frame_time > 0:
            return 1.0 / self.frame_time
        return 20.0  # Default
    
    @property
    def has_delta(self) -> bool:
        return bool(self.flags & TAF_HASDELTA)
    
    @property
    def has_morph(self) -> bool:
        return bool(self.flags & TAF_HASMORPH)
    
    @property
    def has_upper(self) -> bool:
        return bool(self.flags & TAF_HASUPPER)


@dataclass
class SKCFrame:
    """Animation frame data"""
    bounds_min: Tuple[float, float, float]
    bounds_max: Tuple[float, float, float]
    radius: float
    delta: Tuple[float, float, float]
    angle_delta: float
    ofs_channels: int
    
    @classmethod
    def read(cls, f: BytesIO) -> 'SKCFrame':
        """Read frame from file"""
        data = f.read(SKC_FRAME_SIZE)
        unpacked = struct.unpack(SKC_FRAME_FORMAT, data)
        return cls(
            bounds_min=(unpacked[0], unpacked[1], unpacked[2]),
            bounds_max=(unpacked[3], unpacked[4], unpacked[5]),
            radius=unpacked[6],
            delta=(unpacked[7], unpacked[8], unpacked[9]),
            angle_delta=unpacked[10],
            ofs_channels=unpacked[11]
        )
    
    def write(self, f: BytesIO) -> None:
        """Write frame to file"""
        data = struct.pack(
            SKC_FRAME_FORMAT,
            self.bounds_min[0], self.bounds_min[1], self.bounds_min[2],
            self.bounds_max[0], self.bounds_max[1], self.bounds_max[2],
            self.radius,
            self.delta[0], self.delta[1], self.delta[2],
            self.angle_delta,
            self.ofs_channels
        )
        f.write(data)


@dataclass
class SKCChannel:
    """Animation channel (bone transform component)"""
    name: str
    channel_type: int  # CHANNEL_ROTATION, CHANNEL_POSITION, etc.
    
    @classmethod
    def from_name(cls, name: str) -> 'SKCChannel':
        """Create channel and determine type from name"""
        channel_type = get_channel_type(name)
        return cls(name=name, channel_type=channel_type)


@dataclass
class SKCChannelFrame:
    """Channel data for a single frame"""
    data: Tuple[float, ...]  # 4 floats for rotation, 3 for position, 1 for value
    
    @classmethod
    def read(cls, f: BytesIO) -> 'SKCChannelFrame':
        """Read channel frame data"""
        data = f.read(SKC_CHANNEL_DATA_SIZE)
        unpacked = struct.unpack(SKC_CHANNEL_DATA_FORMAT, data)
        return cls(data=unpacked)
    
    def write(self, f: BytesIO) -> None:
        """Write channel frame data"""
        # Pad with zeros if less than 4 values
        data_padded = tuple(self.data) + (0.0,) * (4 - len(self.data))
        struct_data = struct.pack(SKC_CHANNEL_DATA_FORMAT, *data_padded[:4])
        f.write(struct_data)
    
    @property
    def as_quaternion(self) -> Tuple[float, float, float, float]:
        """Get as quaternion (x, y, z, w)"""
        return self.data[:4]
    
    @property
    def as_position(self) -> Tuple[float, float, float]:
        """Get as position (x, y, z)"""
        return self.data[:3]
    
    @property
    def as_value(self) -> float:
        """Get as single value"""
        return self.data[0]


@dataclass
class SKCAnimation:
    """Complete SKC animation data"""
    header: SKCHeader
    frames: List[SKCFrame]
    channels: List[SKCChannel]
    channel_data: List[List[SKCChannelFrame]]  # [frame][channel]
    
    @classmethod
    def read(cls, filepath: str) -> 'SKCAnimation':
        """Read complete SKC animation from file"""
        with open(filepath, 'rb') as f:
            file_data = f.read()
        
        return cls.read_from_bytes(file_data)
    
    @classmethod
    def read_from_bytes(cls, data: bytes) -> 'SKCAnimation':
        """Read complete SKC animation from bytes"""
        f = BytesIO(data)
        file_start = 0
        
        # Read header
        header = SKCHeader.read(f)
        
        # Validate header
        if header.ident != SKC_IDENT_INT:
            raise ValueError(f"Invalid SKC file identifier: {header.ident:08x}")
        
        if header.version not in (SKC_VERSION_OLD, SKC_VERSION_CURRENT):
            raise ValueError(f"Unsupported SKC version: {header.version}")
        
        # Read frame headers
        frames = []
        for _ in range(header.num_frames):
            frames.append(SKCFrame.read(f))
        
        # Read channel names
        channels = []
        f.seek(header.ofs_channel_names)
        for _ in range(header.num_channels):
            name_data = f.read(SKC_CHANNEL_NAME_SIZE)
            name = name_data.rstrip(b'\x00').decode('latin-1')
            channels.append(SKCChannel.from_name(name))
        
        # Read channel data for each frame
        # Channel data is stored after the header + frame headers
        # Each frame has num_channels * 16 bytes of channel data
        channel_data_start = SKC_HEADER_SIZE + (header.num_frames * SKC_FRAME_SIZE)
        
        channel_data = []
        for frame_idx, frame in enumerate(frames):
            frame_channels = []
            # Calculate offset to this frame's channel data
            # In the file format, channel data follows all frame headers
            frame_channel_offset = channel_data_start + (frame_idx * header.num_channels * SKC_CHANNEL_DATA_SIZE)
            f.seek(frame_channel_offset)
            
            for _ in range(header.num_channels):
                frame_channels.append(SKCChannelFrame.read(f))
            
            channel_data.append(frame_channels)
        
        return cls(
            header=header,
            frames=frames,
            channels=channels,
            channel_data=channel_data
        )
    
    def get_channel_by_name(self, name: str) -> Optional[int]:
        """Get channel index by name"""
        for i, channel in enumerate(self.channels):
            if channel.name == name:
                return i
        return None
    
    def get_bone_channels(self, bone_name: str) -> Tuple[Optional[int], Optional[int]]:
        """Get rotation and position channel indices for a bone"""
        rot_idx = self.get_channel_by_name(f"{bone_name} rot")
        pos_idx = self.get_channel_by_name(f"{bone_name} pos")
        return rot_idx, pos_idx
    
    def get_frame_data(self, frame_idx: int, channel_idx: int) -> SKCChannelFrame:
        """Get channel data for a specific frame"""
        return self.channel_data[frame_idx][channel_idx]


def get_channel_type(name: str) -> int:
    """Determine channel type from name (mimics GetBoneChannelType from C++)"""
    name_lower = name.lower()
    
    if name_lower.endswith(' rot'):
        return CHANNEL_ROTATION
    elif name_lower.endswith(' pos'):
        return CHANNEL_POSITION
    elif name_lower.startswith('brow_') or name_lower.startswith('eye') or \
         name_lower.startswith('mouth_') or name_lower.startswith('jaw_') or \
         name_lower.startswith('lips_') or name_lower.startswith('viseme') or \
         name_lower.startswith('visme'):
        return CHANNEL_VALUE
    else:
        return CHANNEL_NONE


def get_bone_name_from_channel(channel_name: str) -> str:
    """Extract bone name from channel name"""
    if channel_name.endswith(' rot'):
        return channel_name[:-4]
    elif channel_name.endswith(' pos'):
        return channel_name[:-4]
    return channel_name
