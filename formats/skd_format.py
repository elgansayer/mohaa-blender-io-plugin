"""
SKD (Skeletal Model) Binary Format Definitions

This module defines Python struct formats that mirror the C++ structures from openmohaa:
- Source: code/tiki/tiki_shared.h
- Source: code/skeletor/skeletor_model_file_format.h

SKD files use 'SKMD' identifier with version 5 (old) or 6 (current).
"""

import struct
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from io import BytesIO

# =============================================================================
# Constants from tiki_shared.h
# =============================================================================

# SKD file identifiers
SKD_IDENT = b'SKMD'  # (*(int *)"SKMD") = 0x444D4B53
SKD_IDENT_INT = 0x444D4B53

# Supported versions
SKD_VERSION_OLD = 5  # TIKI_SKD_HEADER_OLD_VERSION
SKD_VERSION_CURRENT = 6  # TIKI_SKD_HEADER_VERSION
SKD_SUPPORTED_VERSIONS = (5, 6)

# SKB (older format) identifiers
SKB_IDENT = b'SKL '  # (*(int *)"SKL ") 
SKB_IDENT_INT = 0x204C4B53
SKB_VERSION_3 = 3
SKB_VERSION_4 = 4

# Limits
MAX_QPATH = 64
TIKI_SKEL_LOD_INDEXES = 10
MAX_CHANNEL_NAME = 32

# Bone types from skeletor_model_file_format.h
SKELBONE_ROTATION = 0
SKELBONE_POSROT = 1
SKELBONE_IKSHOULDER = 2
SKELBONE_IKELBOW = 3
SKELBONE_IKWRIST = 4
SKELBONE_HOSEROT = 5
SKELBONE_AVROT = 6
SKELBONE_ZERO = 7
SKELBONE_NUMBONETYPES = 8
SKELBONE_WORLD = 9
SKELBONE_HOSEROTBOTH = 10
SKELBONE_HOSEROTPARENT = 11

BONE_TYPE_NAMES = {
    0: 'ROTATION',
    1: 'POSROT',
    2: 'IKSHOULDER',
    3: 'IKELBOW',
    4: 'IKWRIST',
    5: 'HOSEROT',
    6: 'AVROT',
    7: 'ZERO',
    8: 'NUMBONETYPES',
    9: 'WORLD',
    10: 'HOSEROTBOTH',
    11: 'HOSEROTPARENT',
}


# =============================================================================
# Struct format strings
# =============================================================================

# skelHeader_t - Main file header
# V5: 140 bytes (no morph targets, no scale)
# V6: 148 bytes (adds numMorphTargets, ofsMorphTargets, scale)
# typedef struct {
#     int  ident;           // 4 bytes - File identifier ('SKMD')
#     int  version;         // 4 bytes - Version number
#     char name[64];        // 64 bytes - Model name
#     int  numSurfaces;     // 4 bytes
#     int  numBones;        // 4 bytes
#     int  ofsBones;        // 4 bytes - Offset to bone data
#     int  ofsSurfaces;     // 4 bytes - Offset to surface data
#     int  ofsEnd;          // 4 bytes - End of file offset
#     int  lodIndex[10];    // 40 bytes - LOD level indices
#     int  numBoxes;        // 4 bytes - Number of hit boxes
#     int  ofsBoxes;        // 4 bytes - Offset to hit boxes
#     // V6 only:
#     int  numMorphTargets; // 4 bytes - Number of morph targets
#     int  ofsMorphTargets; // 4 bytes - Offset to morph targets
#     float scale;          // 4 bytes - Model scale
# } skelHeader_t;

SKD_HEADER_V5_SIZE = 140  # 4+4+64+4+4+4+4+4+40+4+4 = 140
SKD_HEADER_V6_SIZE = 152  # 140 + 4+4+4 = 152
SKD_HEADER_V5_FORMAT = '<i i 64s i i i i i 10i i i'  # No morph fields
SKD_HEADER_V6_FORMAT = '<i i 64s i i i i i 10i i i i i f'  # Has morph fields + scale

# skelSurface_t - Surface header (84 bytes)
# typedef struct {
#     int  ident;                 // 4 bytes - Surface identifier
#     char name[64];              // 64 bytes - Surface/material name
#     int  numTriangles;          // 4 bytes
#     int  numVerts;              // 4 bytes
#     int  staticSurfProcessed;   // 4 bytes
#     int  ofsTriangles;          // 4 bytes - Offset to triangle indices
#     int  ofsVerts;              // 4 bytes - Offset to vertex data
#     int  ofsCollapse;           // 4 bytes - Offset to collapse map (LOD)
#     int  ofsEnd;                // 4 bytes - Offset to next surface
#     int  ofsCollapseIndex;      // 4 bytes - Offset to collapse index
# } skelSurface_t;

SKD_SURFACE_SIZE = 100  # 4 + 64 + 4*8 = 100  
SKD_SURFACE_FORMAT = '<i 64s i i i i i i i i'

# skeletorVertex_t - Vertex header (24 bytes, followed by morphs and weights)
# typedef struct skeletorVertex_s {
#     vec3_t normal;      // 12 bytes - Vertex normal
#     vec2_t texCoords;   // 8 bytes - UV coordinates
#     int    numWeights;  // 4 bytes - Number of bone weights
#     int    numMorphs;   // 4 bytes - Number of morph offsets
# } skeletorVertex_t;

SKD_VERTEX_SIZE = 28  # 3*4 + 2*4 + 4 + 4 = 28
SKD_VERTEX_FORMAT = '<3f 2f i i'

# skelWeight_t - Bone weight (20 bytes)
# typedef struct skelWeight_s {
#     int    boneIndex;   // 4 bytes - Index of bone
#     float  boneWeight;  // 4 bytes - Weight value (0.0-1.0)
#     vec3_t offset;      // 12 bytes - Offset from bone
# } skelWeight_t;

SKD_WEIGHT_SIZE = 20
SKD_WEIGHT_FORMAT = '<i f 3f'

# skeletorMorph_t - Morph target offset (16 bytes)
# typedef struct {
#     int    morphIndex;  // 4 bytes - Index of morph target
#     vec3_t offset;      // 12 bytes - Position offset for this morph
# } skeletorMorph_t;

SKD_MORPH_SIZE = 16
SKD_MORPH_FORMAT = '<i 3f'

# boneFileData_t - Bone data in file (variable size, base 76 bytes)
# typedef struct boneFileData_s {
#     char       name[32];        // 32 bytes - Bone name
#     char       parent[32];      // 32 bytes - Parent bone name
#     boneType_t boneType;        // 4 bytes - Bone type enum
#     int        ofsBaseData;     // 4 bytes - Offset to base data
#     int        ofsChannelNames; // 4 bytes - Offset to channel names
#     int        ofsBoneNames;    // 4 bytes - Offset to bone reference names
#     int        ofsEnd;          // 4 bytes - Offset to end/next bone
# } boneFileData_t;

SKD_BONE_FILE_DATA_BASE_SIZE = 84  # 32 + 32 + 4*5 = 84
SKD_BONE_FILE_DATA_FORMAT = '<32s 32s i i i i i'

# skelBoneName_t - Simple bone name structure (68 bytes, for older SKB format)
# typedef struct {
#     short int parent;    // 2 bytes - Parent bone index (-1 for root)
#     short int boxIndex;  // 2 bytes - Hit box index
#     int       flags;     // 4 bytes - Bone flags
#     char      name[64];  // 64 bytes - Bone name
# } skelBoneName_t;

SKD_BONE_NAME_SIZE = 72
SKD_BONE_NAME_FORMAT = '<h h i 64s'

# Triangle indices - 3 ints per triangle (12 bytes)
SKD_TRIANGLE_FORMAT = '<3i'
SKD_TRIANGLE_SIZE = 12


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SKDHeader:
    """SKD file header"""
    ident: int
    version: int
    name: str
    num_surfaces: int
    num_bones: int
    ofs_bones: int
    ofs_surfaces: int
    ofs_end: int
    lod_index: List[int]
    num_boxes: int
    ofs_boxes: int
    num_morph_targets: int
    ofs_morph_targets: int
    scale: float = 1.0  # Only in v6
    
    @classmethod
    def read(cls, f: BytesIO) -> 'SKDHeader':
        """Read header from file"""
        # Read first 8 bytes to get ident and version
        data = f.read(8)
        ident, version = struct.unpack('<ii', data)
        
        # Seek back 8 bytes
        f.seek(-8, 1)
        
        if version >= SKD_VERSION_CURRENT:
            data = f.read(SKD_HEADER_V6_SIZE)
            unpacked = struct.unpack(SKD_HEADER_V6_FORMAT, data)
            return cls(
                ident=unpacked[0],
                version=unpacked[1],
                name=unpacked[2].rstrip(b'\x00').decode('latin-1'),
                num_surfaces=unpacked[3],
                num_bones=unpacked[4],
                ofs_bones=unpacked[5],
                ofs_surfaces=unpacked[6],
                ofs_end=unpacked[7],
                lod_index=list(unpacked[8:18]),
                num_boxes=unpacked[18],
                ofs_boxes=unpacked[19],
                num_morph_targets=unpacked[20],
                ofs_morph_targets=unpacked[21],
                scale=unpacked[22]
            )
        else:
            # V5 format has no morph target fields
            data = f.read(SKD_HEADER_V5_SIZE)
            unpacked = struct.unpack(SKD_HEADER_V5_FORMAT, data)
            return cls(
                ident=unpacked[0],
                version=unpacked[1],
                name=unpacked[2].rstrip(b'\x00').decode('latin-1'),
                num_surfaces=unpacked[3],
                num_bones=unpacked[4],
                ofs_bones=unpacked[5],
                ofs_surfaces=unpacked[6],
                ofs_end=unpacked[7],
                lod_index=list(unpacked[8:18]),
                num_boxes=unpacked[18],
                ofs_boxes=unpacked[19],
                num_morph_targets=0,  # Not in v5
                ofs_morph_targets=0,  # Not in v5
                scale=1.0  # Default scale for v5
            )
    
    def write(self, f: BytesIO) -> None:
        """Write header to file"""
        if self.version >= SKD_VERSION_CURRENT:
            data = struct.pack(
                SKD_HEADER_V6_FORMAT,
                self.ident, self.version,
                self.name.encode('latin-1').ljust(64, b'\x00'),
                self.num_surfaces, self.num_bones,
                self.ofs_bones, self.ofs_surfaces, self.ofs_end,
                *self.lod_index,
                self.num_boxes, self.ofs_boxes,
                self.num_morph_targets, self.ofs_morph_targets,
                self.scale
            )
        else:
            data = struct.pack(
                SKD_HEADER_V5_FORMAT,
                self.ident, self.version,
                self.name.encode('latin-1').ljust(64, b'\x00'),
                self.num_surfaces, self.num_bones,
                self.ofs_bones, self.ofs_surfaces, self.ofs_end,
                *self.lod_index,
                self.num_boxes, self.ofs_boxes,
                self.num_morph_targets, self.ofs_morph_targets
            )
        f.write(data)


@dataclass
class SKDSurface:
    """SKD surface (mesh group)"""
    ident: int
    name: str
    num_triangles: int
    num_verts: int
    static_surf_processed: int
    ofs_triangles: int
    ofs_verts: int
    ofs_collapse: int
    ofs_end: int
    ofs_collapse_index: int
    
    @classmethod
    def read(cls, f: BytesIO) -> 'SKDSurface':
        """Read surface header from file"""
        data = f.read(SKD_SURFACE_SIZE)
        unpacked = struct.unpack(SKD_SURFACE_FORMAT, data)
        return cls(
            ident=unpacked[0],
            name=unpacked[1].rstrip(b'\x00').decode('latin-1'),
            num_triangles=unpacked[2],
            num_verts=unpacked[3],
            static_surf_processed=unpacked[4],
            ofs_triangles=unpacked[5],
            ofs_verts=unpacked[6],
            ofs_collapse=unpacked[7],
            ofs_end=unpacked[8],
            ofs_collapse_index=unpacked[9]
        )
    
    def write(self, f: BytesIO) -> None:
        """Write surface header to file"""
        data = struct.pack(
            SKD_SURFACE_FORMAT,
            self.ident,
            self.name.encode('latin-1').ljust(64, b'\x00'),
            self.num_triangles, self.num_verts,
            self.static_surf_processed,
            self.ofs_triangles, self.ofs_verts,
            self.ofs_collapse, self.ofs_end,
            self.ofs_collapse_index
        )
        f.write(data)


@dataclass
class SKDWeight:
    """Bone weight for a vertex"""
    bone_index: int
    bone_weight: float
    offset: Tuple[float, float, float]
    
    @classmethod
    def read(cls, f: BytesIO) -> 'SKDWeight':
        """Read weight from file"""
        data = f.read(SKD_WEIGHT_SIZE)
        unpacked = struct.unpack(SKD_WEIGHT_FORMAT, data)
        return cls(
            bone_index=unpacked[0],
            bone_weight=unpacked[1],
            offset=(unpacked[2], unpacked[3], unpacked[4])
        )
    
    def write(self, f: BytesIO) -> None:
        """Write weight to file"""
        data = struct.pack(
            SKD_WEIGHT_FORMAT,
            self.bone_index, self.bone_weight,
            self.offset[0], self.offset[1], self.offset[2]
        )
        f.write(data)


@dataclass
class SKDMorph:
    """Morph target offset for a vertex"""
    morph_index: int
    offset: Tuple[float, float, float]
    
    @classmethod
    def read(cls, f: BytesIO) -> 'SKDMorph':
        """Read morph from file"""
        data = f.read(SKD_MORPH_SIZE)
        unpacked = struct.unpack(SKD_MORPH_FORMAT, data)
        return cls(
            morph_index=unpacked[0],
            offset=(unpacked[1], unpacked[2], unpacked[3])
        )
    
    def write(self, f: BytesIO) -> None:
        """Write morph to file"""
        data = struct.pack(
            SKD_MORPH_FORMAT,
            self.morph_index,
            self.offset[0], self.offset[1], self.offset[2]
        )
        f.write(data)


@dataclass
class SKDVertex:
    """SKD vertex with weights and morphs"""
    normal: Tuple[float, float, float]
    tex_coords: Tuple[float, float]
    weights: List[SKDWeight] = field(default_factory=list)
    morphs: List[SKDMorph] = field(default_factory=list)
    
    @classmethod
    def read(cls, f: BytesIO) -> 'SKDVertex':
        """Read vertex from file (variable size)"""
        data = f.read(SKD_VERTEX_SIZE)
        unpacked = struct.unpack(SKD_VERTEX_FORMAT, data)
        
        normal = (unpacked[0], unpacked[1], unpacked[2])
        tex_coords = (unpacked[3], unpacked[4])
        num_weights = unpacked[5]
        num_morphs = unpacked[6]
        
        # Read morphs first (they come before weights in file)
        morphs = []
        for _ in range(num_morphs):
            morphs.append(SKDMorph.read(f))
        
        # Read weights
        weights = []
        for _ in range(num_weights):
            weights.append(SKDWeight.read(f))
        
        return cls(
            normal=normal,
            tex_coords=tex_coords,
            weights=weights,
            morphs=morphs
        )

    @classmethod
    def read_vertices(cls, f: BytesIO, num_verts: int) -> List['SKDVertex']:
        """Read multiple vertices efficiently"""
        vertices = []
        try:
            buf = f.getbuffer()
        except AttributeError:
            # Fallback for non-BytesIO
            for _ in range(num_verts):
                vertices.append(cls.read(f))
            return vertices

        offset = f.tell()

        # Pre-bind struct methods for loop efficiency
        unpack_vertex = struct.Struct(SKD_VERTEX_FORMAT).unpack_from
        unpack_morph = struct.Struct(SKD_MORPH_FORMAT).unpack_from
        unpack_weight = struct.Struct(SKD_WEIGHT_FORMAT).unpack_from

        for _ in range(num_verts):
            # Read vertex header
            unpacked = unpack_vertex(buf, offset)
            offset += SKD_VERTEX_SIZE

            normal = (unpacked[0], unpacked[1], unpacked[2])
            tex_coords = (unpacked[3], unpacked[4])
            num_weights = unpacked[5]
            num_morphs = unpacked[6]

            morphs = []
            for _ in range(num_morphs):
                m_unpacked = unpack_morph(buf, offset)
                offset += SKD_MORPH_SIZE
                morphs.append(SKDMorph(
                    morph_index=m_unpacked[0],
                    offset=(m_unpacked[1], m_unpacked[2], m_unpacked[3])
                ))

            weights = []
            for _ in range(num_weights):
                w_unpacked = unpack_weight(buf, offset)
                offset += SKD_WEIGHT_SIZE
                weights.append(SKDWeight(
                    bone_index=w_unpacked[0],
                    bone_weight=w_unpacked[1],
                    offset=(w_unpacked[2], w_unpacked[3], w_unpacked[4])
                ))

            vertices.append(cls(
                normal=normal,
                tex_coords=tex_coords,
                weights=weights,
                morphs=morphs
            ))

        f.seek(offset)
        return vertices
    
    def write(self, f: BytesIO) -> None:
        """Write vertex to file"""
        data = struct.pack(
            SKD_VERTEX_FORMAT,
            self.normal[0], self.normal[1], self.normal[2],
            self.tex_coords[0], self.tex_coords[1],
            len(self.weights), len(self.morphs)
        )
        f.write(data)
        
        # Write morphs first
        for morph in self.morphs:
            morph.write(f)
        
        # Write weights
        for weight in self.weights:
            weight.write(f)
    
    def get_position(self) -> Tuple[float, float, float]:
        """Calculate vertex position from weighted bone offsets"""
        if not self.weights:
            return (0.0, 0.0, 0.0)
        
        # For import, we use the first weight's offset as the base position
        # This is a simplification - full skinning requires the bone transforms
        pos = [0.0, 0.0, 0.0]
        for weight in self.weights:
            pos[0] += weight.offset[0] * weight.bone_weight
            pos[1] += weight.offset[1] * weight.bone_weight
            pos[2] += weight.offset[2] * weight.bone_weight
        
        return tuple(pos)


@dataclass
class SKDBoneFileData:
    """Bone data from file (boneFileData_t)"""
    name: str
    parent: str
    bone_type: int
    ofs_base_data: int
    ofs_channel_names: int
    ofs_bone_names: int
    ofs_end: int
    # Additional data parsed from base_data offset
    offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    
    @classmethod
    def read(cls, f: BytesIO, file_start_pos: int) -> 'SKDBoneFileData':
        """Read bone data from file"""
        bone_start = f.tell()
        data = f.read(SKD_BONE_FILE_DATA_BASE_SIZE)
        unpacked = struct.unpack(SKD_BONE_FILE_DATA_FORMAT, data)
        
        bone = cls(
            name=unpacked[0].rstrip(b'\x00').decode('latin-1'),
            parent=unpacked[1].rstrip(b'\x00').decode('latin-1'),
            bone_type=unpacked[2],
            ofs_base_data=unpacked[3],
            ofs_channel_names=unpacked[4],
            ofs_bone_names=unpacked[5],
            ofs_end=unpacked[6]
        )
        
        # Read base data (offset) if available
        if bone.ofs_base_data > 0 and bone.bone_type in (
            SKELBONE_ROTATION, SKELBONE_IKSHOULDER, SKELBONE_AVROT,
            SKELBONE_HOSEROT, SKELBONE_HOSEROTBOTH, SKELBONE_HOSEROTPARENT
        ):
            current_pos = f.tell()
            f.seek(bone_start + bone.ofs_base_data)
            
            if bone.bone_type == SKELBONE_ROTATION:
                offset_data = f.read(12)
                offsets = struct.unpack('<3f', offset_data)
                bone.offset = offsets
            elif bone.bone_type == SKELBONE_IKSHOULDER:
                # Skip 4 floats (quaternion), then read offset
                f.read(16)
                offset_data = f.read(12)
                offsets = struct.unpack('<3f', offset_data)
                bone.offset = offsets
            elif bone.bone_type == SKELBONE_AVROT:
                # First float is length, then offset
                length_data = f.read(4)
                offset_data = f.read(12)
                offsets = struct.unpack('<3f', offset_data)
                bone.offset = offsets
            elif bone.bone_type in (SKELBONE_HOSEROT, SKELBONE_HOSEROTBOTH, SKELBONE_HOSEROTPARENT):
                # Skip 3 floats (bendRatio, bendMax, spinRatio), then read offset
                f.read(12)
                offset_data = f.read(12)
                offsets = struct.unpack('<3f', offset_data)
                bone.offset = offsets
            
            f.seek(current_pos)
        
        return bone


@dataclass 
class SKDBoneName:
    """Simple bone name structure (for older SKB format)"""
    parent: int
    box_index: int
    flags: int
    name: str
    
    @classmethod
    def read(cls, f: BytesIO) -> 'SKDBoneName':
        """Read bone name from file"""
        data = f.read(SKD_BONE_NAME_SIZE)
        unpacked = struct.unpack(SKD_BONE_NAME_FORMAT, data)
        return cls(
            parent=unpacked[0],
            box_index=unpacked[1],
            flags=unpacked[2],
            name=unpacked[3].rstrip(b'\x00').decode('latin-1')
        )


@dataclass
class SKDTriangle:
    """Triangle face indices"""
    indices: Tuple[int, int, int]
    
    @classmethod
    def read(cls, f: BytesIO) -> 'SKDTriangle':
        """Read triangle from file"""
        data = f.read(SKD_TRIANGLE_SIZE)
        unpacked = struct.unpack(SKD_TRIANGLE_FORMAT, data)
        return cls(indices=unpacked)
    
    def write(self, f: BytesIO) -> None:
        """Write triangle to file"""
        data = struct.pack(SKD_TRIANGLE_FORMAT, *self.indices)
        f.write(data)


@dataclass
class SKDModel:
    """Complete SKD model data"""
    header: SKDHeader
    surfaces: List['SKDSurfaceData']
    bones: List[SKDBoneFileData]
    morph_target_names: List[str] = field(default_factory=list)
    
    @classmethod
    def read(cls, filepath: str) -> 'SKDModel':
        """Read complete SKD model from file"""
        with open(filepath, 'rb') as f:
            file_data = f.read()
        
        return cls.read_from_bytes(file_data)
    
    @classmethod
    def read_from_bytes(cls, data: bytes) -> 'SKDModel':
        """Read complete SKD model from bytes"""
        f = BytesIO(data)
        file_start = 0
        
        # Read header
        header = SKDHeader.read(f)
        
        # Validate header
        if header.ident not in (SKD_IDENT_INT, SKB_IDENT_INT):
            raise ValueError(f"Invalid SKD file identifier: {header.ident}")
        
        # Read surfaces
        surfaces = []
        f.seek(header.ofs_surfaces)
        
        for i in range(header.num_surfaces):
            surface_start = f.tell()
            surface_header = SKDSurface.read(f)
            
            # Read triangles
            f.seek(surface_start + surface_header.ofs_triangles)

            # Bulk read triangles for performance
            if surface_header.num_triangles > 0:
                tri_data_size = surface_header.num_triangles * SKD_TRIANGLE_SIZE
                tri_data = f.read(tri_data_size)
                triangles = [
                    SKDTriangle(indices=t)
                    for t in struct.iter_unpack(SKD_TRIANGLE_FORMAT, tri_data)
                ]
            else:
                triangles = []
            
            # Read vertices
            f.seek(surface_start + surface_header.ofs_verts)
            vertices = SKDVertex.read_vertices(f, surface_header.num_verts)
            
            surfaces.append(SKDSurfaceData(
                header=surface_header,
                triangles=triangles,
                vertices=vertices
            ))
            
            # Move to next surface
            f.seek(surface_start + surface_header.ofs_end)
        
        # Read bones
        bones = []
        if header.num_bones > 0:
            f.seek(header.ofs_bones)
            
            # Check if this is SKB format (uses skelBoneName_t) or SKD format (uses boneFileData_t)
            is_skb = header.ident == SKB_IDENT_INT or header.version <= SKB_VERSION_4
            
            for i in range(header.num_bones):
                if is_skb:
                    bone_name = SKDBoneName.read(f)
                    # Convert to SKDBoneFileData format
                    parent_name = "worldbone" if bone_name.parent == -1 else ""
                    bones.append(SKDBoneFileData(
                        name=bone_name.name,
                        parent=parent_name,
                        bone_type=SKELBONE_POSROT,
                        ofs_base_data=0,
                        ofs_channel_names=0,
                        ofs_bone_names=0,
                        ofs_end=0
                    ))
                else:
                    bone_start = f.tell()
                    bone = SKDBoneFileData.read(f, file_start)
                    bones.append(bone)
                    # Move to next bone
                    f.seek(bone_start + bone.ofs_end)
            
            # Fix parent names for SKB format
            if is_skb:
                f.seek(header.ofs_bones)
                for i in range(header.num_bones):
                    bone_name = SKDBoneName.read(f)
                    if bone_name.parent >= 0 and bone_name.parent < len(bones):
                        bones[i].parent = bones[bone_name.parent].name
        
        # Read morph target names
        morph_target_names = []
        if header.num_morph_targets > 0 and header.ofs_morph_targets > 0:
            f.seek(header.ofs_morph_targets)
            for _ in range(header.num_morph_targets):
                # Read null-terminated string
                name_bytes = b''
                while True:
                    byte = f.read(1)
                    if byte == b'\x00' or not byte:
                        break
                    name_bytes += byte
                morph_target_names.append(name_bytes.decode('latin-1'))
        
        return cls(
            header=header,
            surfaces=surfaces,
            bones=bones,
            morph_target_names=morph_target_names
        )


@dataclass
class SKDSurfaceData:
    """Complete surface data including geometry"""
    header: SKDSurface
    triangles: List[SKDTriangle]
    vertices: List[SKDVertex]
