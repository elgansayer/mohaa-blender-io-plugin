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
SKC_VERSION_MOHSH = 10  # Medal of Honor: Spearhead
SKC_VERSION_MOHBT = 11  # Medal of Honor: Breakthrough
SKC_VERSION_MOHSH2 = 12  # Some Spearhead animations
SKC_VERSION_OLD = 13  # TIKI_SKC_HEADER_OLD_VERSION
SKC_VERSION_CURRENT = 14  # TIKI_SKC_HEADER_VERSION

# All known/supported versions
SKC_SUPPORTED_VERSIONS = (10, 11, 12, 13, 14)

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
        
        # First, peek at ident and version
        ident_data = f.read(8)  # ident + version
        ident, version = struct.unpack('<ii', ident_data)
        
        # Validate ident
        if ident != SKC_IDENT_INT:
            raise ValueError(f"Invalid SKC file identifier: {ident:08x}")
        
        # Check version and determine header format
        if version < 13:
            # Old format (10-12) or unknown older version
            # Format: [ident:4][version:4][filename:64][...rest of header]
            if version not in (10, 11, 12):
                print(f"Warning: Unknown SKC version {version}, attempting to parse as Old format")

            header = cls._read_old_header(f, ident, version)
            header_size = 8 + 64 + 40  # ident+ver + filename + rest of old header
        else:
            # Standard format (13-14) or newer
            if version > 14:
                print(f"Warning: Newer SKC version {version} detected, attempting to parse as Standard format")

            f.seek(0)
            header = SKCHeader.read(f)
            header_size = SKC_HEADER_SIZE
        
        if header.num_frames == 0 or header.num_channels == 0:
            # Empty animation, return early
            return cls(header=header, frames=[], channels=[], channel_data=[])
        
        # Read frame headers
        # Bulk read optimization
        frames = []
        if header.num_frames > 0:
            frame_data_block = f.read(header.num_frames * SKC_FRAME_SIZE)
            for unpacked in struct.iter_unpack(SKC_FRAME_FORMAT, frame_data_block):
                frames.append(SKCFrame(
                    bounds_min=(unpacked[0], unpacked[1], unpacked[2]),
                    bounds_max=(unpacked[3], unpacked[4], unpacked[5]),
                    radius=unpacked[6],
                    delta=(unpacked[7], unpacked[8], unpacked[9]),
                    angle_delta=unpacked[10],
                    ofs_channels=unpacked[11]
                ))
        
        # Read channel names
        channels = []
        if header.ofs_channel_names > 0:
            f.seek(header.ofs_channel_names)
            for _ in range(header.num_channels):
                name_data = f.read(SKC_CHANNEL_NAME_SIZE)
                name = name_data.rstrip(b'\x00').decode('latin-1')
                channels.append(SKCChannel.from_name(name))
        
        # Read channel data for each frame
        channel_data_start = header_size + (header.num_frames * SKC_FRAME_SIZE)
        
        channel_data = []
        for frame_idx, frame in enumerate(frames):
            frame_channels = []
            frame_channel_offset = channel_data_start + (frame_idx * header.num_channels * SKC_CHANNEL_DATA_SIZE)
            f.seek(frame_channel_offset)
            
            # Bulk read optimization: Read all channel data for this frame at once
            bytes_to_read = header.num_channels * SKC_CHANNEL_DATA_SIZE
            frame_data_block = f.read(bytes_to_read)

            # Use iter_unpack for efficient unpacking
            # frame_channels = [SKCChannelFrame(data=t) for t in struct.iter_unpack(SKC_CHANNEL_DATA_FORMAT, frame_data_block)]

            # Since we need to construct the list anyway, list comprehension is fast
            # We use struct.iter_unpack available in Python 3.4+
            frame_channels = [
                SKCChannelFrame(data=unpacked_data)
                for unpacked_data in struct.iter_unpack(SKC_CHANNEL_DATA_FORMAT, frame_data_block)
            ]
            
            channel_data.append(frame_channels)
        
        return cls(
            header=header,
            frames=frames,
            channels=channels,
            channel_data=channel_data
        )
    
    @classmethod
    def _read_old_header(cls, f: BytesIO, ident: int, version: int) -> 'SKCHeader':
        """Read old-format SKC header (versions 10-12)
        
        Old format layout (analyzed from hex dump):
        - Offset 0: ident (4 bytes) = 'SKAN'
        - Offset 4: version (4 bytes) = 10/11/12
        - Offset 8: filename (64 bytes, null-padded)
        - Offset 72: padding/garbage (4 bytes)
        - Offset 76: flags or similar (4 bytes)
        - Offset 80: frameTime (4 bytes, float)
        - Offset 84: totalDelta (12 bytes, 3 floats)
        - Offset 96: ofsChannelData (4 bytes)
        - Offset 100: ofsChannelInfo (4 bytes) - contains numChannels, numFrames, then channel names
        - Offset 104: unused (4 bytes)
        - Offset 108: numFrames (4 bytes)
        
        At ofsChannelInfo:
        - numChannels (4 bytes)
        - numFrames (4 bytes)
        - channel names (32 bytes each)
        """
        # Skip filename (64 bytes, already read ident+version)
        filename_data = f.read(64)  # offset 8-72
        
        # Read header fields starting at offset 72
        header_data = f.read(40)  # Read 40 bytes: offsets 72-112
        
        try:
            # Parse the header structure
            unpacked = struct.unpack('<iiffffiiiii', header_data[:44] if len(header_data) >= 44 else header_data + b'\x00' * (44 - len(header_data)))
            
            # Field mapping based on hex dump analysis
            padding = unpacked[0]          # offset 72: garbage/padding
            flags = unpacked[1]            # offset 76: flags (or nBytesUsed)
            frame_time = unpacked[2]       # offset 80: frameTime
            total_delta = (unpacked[3], unpacked[4], unpacked[5])  # offset 84-96: totalDelta
            ofs_channel_data = unpacked[6]  # offset 96: where channel data starts
            ofs_channel_info = unpacked[7]  # offset 100: secondary info block
            unused = unpacked[8]            # offset 104: unused
            num_frames = unpacked[9]        # offset 108: numFrames
            
            # Read numChannels from the secondary info block (if ofsChannelInfo is valid)
            num_channels = 0
            ofs_channel_names = ofs_channel_info + 8  # Skip numChannels + numFrames
            
            if ofs_channel_info > 0:
                current_pos = f.tell()
                f.seek(ofs_channel_info)
                info_data = f.read(8)
                if len(info_data) == 8:
                    num_channels, num_frames_check = struct.unpack('<ii', info_data)
                    # Use this as the actual offset for channel names
                    ofs_channel_names = ofs_channel_info + 8
                f.seek(current_pos)
            
            # Sanity checks
            if num_frames < 0 or num_frames > 100000:
                num_frames = 0
            if num_channels < 0 or num_channels > 1000:
                num_channels = 0
                
        except Exception as e:
            print(f"Warning: Could not parse old SKC header: {e}")
            flags = 0
            frame_time = 0.05
            total_delta = (0, 0, 0)
            num_channels = 0
            ofs_channel_names = 0
            num_frames = 0
        
        return SKCHeader(
            ident=ident,
            version=version,
            flags=flags,
            n_bytes_used=0,
            frame_time=frame_time,
            total_delta=total_delta,
            total_angle_delta=0,
            num_channels=num_channels,
            ofs_channel_names=ofs_channel_names,
            num_frames=num_frames
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
