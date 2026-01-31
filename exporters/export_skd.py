"""
SKD (Skeletal Model) Exporter for Blender

Exports Blender mesh + armature to MoHAA .skd format.

Reverses the coordinate transformation applied during import:
- Blender: (x, y, z) -> MoHAA: (x, -y, z)

Binary Format (based on openmohaa):
- skelHeader_t: File header with offsets
- skelSurface_t[]: Surface headers with mesh data
- boneFileData_t[] or skelBoneName_t[]: Bone definitions
"""

import bpy
import bmesh
import struct
from mathutils import Vector, Matrix, Quaternion
from typing import Dict, List, Tuple, Optional, Set
import os
from io import BytesIO

from ..formats.skd_format import (
    SKDModel, SKDHeader, SKDSurface, SKDSurfaceData,
    SKDVertex, SKDWeight, SKDMorph, SKDBoneFileData, SKDTriangle,
    SKD_IDENT_INT, SKD_VERSION_CURRENT, SKD_VERSION_OLD, SKELBONE_POSROT,
    SKD_HEADER_V6_SIZE, SKD_HEADER_V5_SIZE, SKD_SURFACE_SIZE, SKD_VERTEX_SIZE,
    SKD_WEIGHT_SIZE, SKD_MORPH_SIZE, SKD_TRIANGLE_SIZE,
    SKD_BONE_NAME_SIZE, SKD_BONE_FILE_DATA_BASE_SIZE,
    SKD_HEADER_V6_FORMAT, SKD_HEADER_V5_FORMAT
)


class SKDExporter:
    """Exports Blender models to SKD format"""
    
    def __init__(self, filepath: str,
                 mesh_obj: bpy.types.Object,
                 armature_obj: Optional[bpy.types.Object] = None,
                 flip_uvs: bool = True,
                 swap_yz: bool = False,
                 scale: float = 1.0,
                 version: int = SKD_VERSION_CURRENT):
        """
        Initialize exporter.
        
        Args:
            filepath: Output .skd file path
            mesh_obj: Mesh object to export
            armature_obj: Optional armature object
            flip_uvs: Flip V coordinate (reverse of import)
            swap_yz: Swap Y and Z axes (reverse of import)
            scale: Global scale factor (inverse applied)
            version: SKD version (default: 6)
        """
        self.filepath = filepath
        self.mesh_obj = mesh_obj
        self.armature_obj = armature_obj
        self.flip_uvs = flip_uvs
        self.swap_yz = swap_yz
        self.scale = scale
        self.version = version
        
        self.bone_indices: Dict[str, int] = {}  # Bone name -> index
    
    def execute(self) -> bool:
        """
        Execute export.
        
        Returns:
            True on success, False on failure
        """
        if not self.mesh_obj or self.mesh_obj.type != 'MESH':
            print("Error: No valid mesh object provided")
            return False
        
        try:
            # Build bone data
            bones = self._build_bones()
            
            # Build surface data
            surfaces = self._build_surfaces()
            
            # Write to file
            self._write_file(surfaces, bones)
            
            print(f"Successfully exported SKD: {self.filepath}")
            print(f"  Surfaces: {len(surfaces)}")
            print(f"  Bones: {len(bones)}")
            
            return True
            
        except Exception as e:
            print(f"Error exporting SKD: {e}")
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
    
    def _transform_normal_inverse(self, normal: Vector) -> Tuple[float, float, float]:
        """Transform normal from Blender to MoHAA coordinates"""
        x, y, z = normal.normalized()
        
        if self.swap_yz:
            return (x, z, -y)
        else:
            return (x, -y, z)
    
    def _transform_uv_inverse(self, uv: Tuple[float, float]) -> Tuple[float, float]:
        """Transform UV from Blender to MoHAA coordinates"""
        u, v = uv
        
        if self.flip_uvs:
            return (u, 1.0 - v)
        return (u, v)
    
    def _build_bones(self) -> List[Tuple[str, str, Tuple[float, float, float]]]:
        """Build bone data from armature. Returns list of (name, parent, offset)"""
        bones = []
        
        if not self.armature_obj or self.armature_obj.type != 'ARMATURE':
            # Create a single default bone if no armature
            bones.append(("Bip01", "worldbone", (0.0, 0.0, 0.0)))
            self.bone_indices["Bip01"] = 0
            return bones
        
        armature = self.armature_obj.data
        
        # Sort bones by hierarchy (parents first)
        sorted_bones = []
        processed: Set[str] = set()
        
        def add_bone_hierarchy(bone: bpy.types.Bone):
            if bone.name in processed:
                return
            if bone.parent and bone.parent.name not in processed:
                add_bone_hierarchy(bone.parent)
            sorted_bones.append(bone)
            processed.add(bone.name)
        
        for bone in armature.bones:
            add_bone_hierarchy(bone)
        
        # Create bone data
        for bone in sorted_bones:
            parent_name = "worldbone"
            if bone.parent:
                parent_name = bone.parent.name
            
            # Get bone head position in armature space
            head_pos = self._transform_position_inverse(bone.head_local)
            
            self.bone_indices[bone.name] = len(bones)
            bones.append((bone.name, parent_name, head_pos))
        
        return bones
    
    def _build_surfaces(self) -> List[Dict]:
        """Build surface data from mesh. Returns list of surface dicts."""
        surfaces = []
        
        # Get evaluated mesh with modifiers (except armature)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        eval_obj = self.mesh_obj.evaluated_get(depsgraph)
        eval_mesh = eval_obj.to_mesh()
        
        # Ensure triangulated
        bm = bmesh.new()
        bm.from_mesh(eval_mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        bm.to_mesh(eval_mesh)
        bm.free()
        
        # Get UV layer
        uv_layer = eval_mesh.uv_layers.active.data if eval_mesh.uv_layers.active else None
        
        # Group faces by material
        material_faces: Dict[int, List[int]] = {}
        for poly in eval_mesh.polygons:
            mat_idx = poly.material_index
            if mat_idx not in material_faces:
                material_faces[mat_idx] = []
            material_faces[mat_idx].append(poly.index)
        
        # If no materials, create one default group
        if not material_faces:
            material_faces[0] = list(range(len(eval_mesh.polygons)))
        
        # Create a surface for each material
        for mat_idx in sorted(material_faces.keys()):
            face_indices = material_faces[mat_idx]
            
            # Get material name
            mat_name = "default"
            if mat_idx < len(self.mesh_obj.data.materials):
                mat = self.mesh_obj.data.materials[mat_idx]
                if mat:
                    mat_name = mat.name
            
            # Build vertex and face data for this surface
            surface = self._build_surface(eval_mesh, face_indices, uv_layer, mat_name)
            surfaces.append(surface)
        
        eval_obj.to_mesh_clear()
        
        return surfaces
    
    def _build_surface(self, mesh: bpy.types.Mesh, face_indices: List[int],
                       uv_layer, mat_name: str) -> Dict:
        """Build a single surface from faces"""
        vertices = []
        triangles = []
        
        # Map from (orig_vert_idx, loop_idx) to new surface vertex index
        # We need unique vertices per loop for proper UV handling
        vert_map: Dict[Tuple[int, int], int] = {}
        
        # Collect vertices and triangles
        for face_idx in face_indices:
            poly = mesh.polygons[face_idx]
            
            if len(poly.loop_indices) != 3:
                continue  # Skip non-triangles
            
            tri_indices = []
            for loop_idx in poly.loop_indices:
                orig_vert_idx = mesh.loops[loop_idx].vertex_index
                key = (orig_vert_idx, loop_idx)
                
                # Always create new vertex per loop for correct UVs
                vert = mesh.vertices[orig_vert_idx]
                
                # Get position
                pos = self._transform_position_inverse(vert.co)
                
                # Get normal
                normal = self._transform_normal_inverse(vert.normal)
                
                # Get UV
                uv = (0.0, 0.0)
                if uv_layer:
                    uv = self._transform_uv_inverse(tuple(uv_layer[loop_idx].uv))
                
                # Get vertex weights
                weights = []
                for group in vert.groups:
                    if group.group < len(self.mesh_obj.vertex_groups):
                        group_name = self.mesh_obj.vertex_groups[group.group].name
                        if group_name in self.bone_indices:
                            bone_idx = self.bone_indices[group_name]
                            weights.append({
                                'bone_index': bone_idx,
                                'bone_weight': group.weight,
                                'offset': pos
                            })
                
                # Ensure at least one weight
                if not weights:
                    if self.bone_indices:
                        first_bone_idx = list(self.bone_indices.values())[0]
                    else:
                        first_bone_idx = 0
                    weights.append({
                        'bone_index': first_bone_idx,
                        'bone_weight': 1.0,
                        'offset': pos
                    })
                
                vertex = {
                    'normal': normal,
                    'tex_coords': uv,
                    'weights': weights,
                    'morphs': []
                }
                
                new_idx = len(vertices)
                vert_map[key] = new_idx
                vertices.append(vertex)
                tri_indices.append(new_idx)
            
            triangles.append(tuple(tri_indices))
        
        return {
            'name': mat_name,
            'vertices': vertices,
            'triangles': triangles
        }
    
    def _write_file(self, surfaces: List[Dict], 
                    bones: List[Tuple[str, str, Tuple[float, float, float]]]) -> None:
        """Write all data to binary file"""
        
        model_name = os.path.splitext(os.path.basename(self.filepath))[0]
        
        # Calculate sizes and offsets
        if self.version >= SKD_VERSION_CURRENT:
            header_size = SKD_HEADER_V6_SIZE
        else:
            header_size = SKD_HEADER_V5_SIZE
        
        # Calculate bone data size
        bone_data_size = len(bones) * (SKD_BONE_FILE_DATA_BASE_SIZE + 12)
        
        # --- Pre-build Surface Binary Data ---
        surfaces_binary = []
        
        for surface in surfaces:
            # 1. Build Triangles
            tri_list = []
            tri_struct = struct.Struct('<3i')
            for tri in surface['triangles']:
                tri_list.append(tri_struct.pack(tri[0], tri[1], tri[2]))
            tri_data = b''.join(tri_list)
            
            # 2. Build Vertices
            vert_list = []
            vert_header_struct = struct.Struct('<3f 2f i i')
            morph_struct = struct.Struct('<i 3f')
            weight_struct = struct.Struct('<i f 3f')
            
            for vert in surface['vertices']:
                morphs = vert['morphs']
                # If V5, skip morphs
                if self.version < SKD_VERSION_CURRENT:
                    morphs = []

                num_weights = len(vert['weights'])
                num_morphs = len(morphs)
                
                # Header
                vert_list.append(vert_header_struct.pack(
                    vert['normal'][0], vert['normal'][1], vert['normal'][2],
                    vert['tex_coords'][0], vert['tex_coords'][1],
                    num_weights,
                    num_morphs
                ))
                
                # Morphs
                for morph in morphs:
                    vert_list.append(morph_struct.pack(
                        morph['morph_index'],
                        morph['offset'][0], morph['offset'][1], morph['offset'][2]
                    ))
                
                # Weights
                for weight in vert['weights']:
                    vert_list.append(weight_struct.pack(
                        weight['bone_index'],
                        weight['bone_weight'],
                        weight['offset'][0], weight['offset'][1], weight['offset'][2]
                    ))

            vert_data = b''.join(vert_list)

            # 3. Build Collapse Maps (identity for now)
            num_verts = len(surface['vertices'])
            collapse_struct = struct.Struct('<i')
            # Fast pack for range
            collapse_data = b''.join([collapse_struct.pack(v) for v in range(num_verts)])
            collapse_idx_data = collapse_data # Same identity map

            # Calculate Offsets
            tris_size = len(tri_data)
            verts_size = len(vert_data)
            collapse_size = len(collapse_data)
            collapse_idx_size = len(collapse_idx_data)

            surf_header_size = SKD_SURFACE_SIZE

            ofs_triangles = surf_header_size
            ofs_verts = ofs_triangles + tris_size
            ofs_collapse = ofs_verts + verts_size
            ofs_end = ofs_collapse + collapse_size
            ofs_collapse_idx = ofs_end

            total_surf_size = ofs_end + collapse_idx_size

            # 4. Build Surface Header
            surf_header = struct.pack(
                '<i 64s i i i i i i i i',
                0,  # ident
                surface['name'].encode('latin-1')[:64].ljust(64, b'\x00'),  # name
                len(surface['triangles']),  # numTriangles
                num_verts,  # numVerts
                0,  # staticSurfProcessed
                ofs_triangles,
                ofs_verts,
                ofs_collapse,
                total_surf_size,  # ofsEnd points to end of this block
                ofs_collapse_idx
            )
            
            # Concatenate all parts
            surfaces_binary.append(surf_header + tri_data + vert_data + collapse_data + collapse_idx_data)
            
        # Calculate global offsets
        surface_data_total_size = sum(len(b) for b in surfaces_binary)

        ofs_surfaces = header_size
        ofs_bones = header_size + surface_data_total_size
        ofs_end = ofs_bones + bone_data_size
        
        # --- Build Bone Binary Data ---
        bones_binary_list = []
        for bone_name, parent_name, offset in bones:
            bone_data = struct.pack(
                '<32s 32s i i i i i',
                bone_name.encode('latin-1')[:32].ljust(32, b'\x00'),
                parent_name.encode('latin-1')[:32].ljust(32, b'\x00'),
                SKELBONE_POSROT,
                84, # ofsBaseData (offset to base data relative to bone start)
                0, 0,
                84 + 12 # ofsEnd
            )
            offset_data = struct.pack('<3f', offset[0], offset[1], offset[2])
            bones_binary_list.append(bone_data + offset_data)
            
        bones_binary = b''.join(bones_binary_list)
        
        # --- Write File ---
        with open(self.filepath, 'wb') as f:
            # Write Header
            if self.version >= SKD_VERSION_CURRENT:
                header_data = struct.pack(
                    SKD_HEADER_V6_FORMAT,
                    SKD_IDENT_INT, self.version,
                    model_name.encode('latin-1').ljust(64, b'\x00'),
                    len(surfaces), len(bones),
                    ofs_bones, ofs_surfaces, ofs_end,
                    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, # lodIndex
                    0, 0, 0, 0, # boxes, morphs
                    1.0 / self.scale if self.scale != 0 else 1.0
                )
            else:
                header_data = struct.pack(
                    SKD_HEADER_V5_FORMAT,
                    SKD_IDENT_INT, self.version,
                    model_name.encode('latin-1').ljust(64, b'\x00'),
                    len(surfaces), len(bones),
                    ofs_bones, ofs_surfaces, ofs_end,
                    0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                    0, 0
                )
            f.write(header_data)

            # Write Surfaces
            f.write(b''.join(surfaces_binary))

            # Write Bones
            f.write(bones_binary)


def export_skd(filepath: str,
               mesh_obj: bpy.types.Object,
               armature_obj: Optional[bpy.types.Object] = None,
               flip_uvs: bool = True,
               swap_yz: bool = False,
               scale: float = 1.0,
               version: int = SKD_VERSION_CURRENT) -> bool:
    """
    Export mesh to SKD file.
    
    Args:
        filepath: Output file path
        mesh_obj: Mesh object to export
        armature_obj: Optional armature object
        flip_uvs: Flip V coordinate
        swap_yz: Swap Y and Z axes
        scale: Global scale factor
        version: SKD version (default: 6)
        
    Returns:
        True on success
    """
    exporter = SKDExporter(filepath, mesh_obj, armature_obj, flip_uvs, swap_yz, scale, version)
    return exporter.execute()
