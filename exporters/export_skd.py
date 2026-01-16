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
    SKD_HEADER_V6_SIZE, SKD_SURFACE_SIZE, SKD_VERTEX_SIZE,
    SKD_WEIGHT_SIZE, SKD_MORPH_SIZE, SKD_TRIANGLE_SIZE,
    SKD_BONE_NAME_SIZE, SKD_BONE_FILE_DATA_BASE_SIZE
)


class SKDExporter:
    """Exports Blender models to SKD format"""
    
    def __init__(self, filepath: str,
                 mesh_obj: bpy.types.Object,
                 armature_obj: Optional[bpy.types.Object] = None,
                 flip_uvs: bool = True,
                 swap_yz: bool = False,
                 scale: float = 1.0):
        """
        Initialize exporter.
        
        Args:
            filepath: Output .skd file path
            mesh_obj: Mesh object to export
            armature_obj: Optional armature object
            flip_uvs: Flip V coordinate (reverse of import)
            swap_yz: Swap Y and Z axes (reverse of import)
            scale: Global scale factor (inverse applied)
        """
        self.filepath = filepath
        self.mesh_obj = mesh_obj
        self.armature_obj = armature_obj
        self.flip_uvs = flip_uvs
        self.swap_yz = swap_yz
        self.scale = scale
        
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
        header_size = SKD_HEADER_V6_SIZE  # 144 bytes
        
        # Calculate bone data size (using boneFileData_t format: 84 bytes base + 12 bytes offset)
        bone_data_size = len(bones) * (SKD_BONE_FILE_DATA_BASE_SIZE + 12)
        
        # Calculate surface data size
        surface_data_size = 0
        surface_infos = []
        
        for surface in surfaces:
            num_verts = len(surface['vertices'])
            num_tris = len(surface['triangles'])
            
            # Surface header: 84 bytes
            surf_header_size = SKD_SURFACE_SIZE
            
            # Triangles: 12 bytes each (3 ints)
            tris_size = num_tris * SKD_TRIANGLE_SIZE
            
            # Vertices: variable size
            # Each vertex: 24 bytes header + morphs + weights
            verts_size = 0
            for vert in surface['vertices']:
                verts_size += SKD_VERTEX_SIZE  # 24 bytes
                verts_size += len(vert['morphs']) * SKD_MORPH_SIZE  # 16 bytes each
                verts_size += len(vert['weights']) * SKD_WEIGHT_SIZE  # 20 bytes each
            
            # Collapse map: 4 bytes per vertex (int)
            collapse_size = num_verts * 4
            
            # Collapse index: 4 bytes per vertex (int)  
            collapse_idx_size = num_verts * 4
            
            total_surf_size = surf_header_size + tris_size + verts_size + collapse_size + collapse_idx_size
            
            surface_infos.append({
                'name': surface['name'],
                'vertices': surface['vertices'],
                'triangles': surface['triangles'],
                'header_size': surf_header_size,
                'tris_offset': surf_header_size,
                'tris_size': tris_size,
                'verts_offset': surf_header_size + tris_size,
                'verts_size': verts_size,
                'collapse_offset': surf_header_size + tris_size + verts_size,
                'collapse_size': collapse_size,
                'collapse_idx_offset': surf_header_size + tris_size + verts_size + collapse_size,
                'total_size': total_surf_size
            })
            
            surface_data_size += total_surf_size
        
        # Calculate offsets
        ofs_surfaces = header_size
        ofs_bones = header_size + surface_data_size
        ofs_end = ofs_bones + bone_data_size
        
        # Build binary data
        output = BytesIO()
        
        # Write header
        header_data = struct.pack(
            '<i i 64s i i i i i 10i i i i i f',
            SKD_IDENT_INT,  # ident
            SKD_VERSION_CURRENT,  # version (6)
            model_name.encode('latin-1').ljust(64, b'\x00'),  # name
            len(surfaces),  # numSurfaces
            len(bones),  # numBones
            ofs_bones,  # ofsBones
            ofs_surfaces,  # ofsSurfaces
            ofs_end,  # ofsEnd
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0,  # lodIndex[10]
            0,  # numBoxes
            0,  # ofsBoxes
            0,  # numMorphTargets
            0,  # ofsMorphTargets
            1.0 / self.scale if self.scale != 0 else 1.0  # scale
        )
        output.write(header_data)
        
        # Write surfaces
        for i, surf_info in enumerate(surface_infos):
            surf_start = output.tell()
            
            num_verts = len(surf_info['vertices'])
            num_tris = len(surf_info['triangles'])
            
            # Calculate offsets relative to surface start
            ofs_triangles = surf_info['tris_offset']
            ofs_verts = surf_info['verts_offset']
            ofs_collapse = surf_info['collapse_offset']
            ofs_end = surf_info['total_size']
            ofs_collapse_idx = surf_info['collapse_idx_offset']
            
            # Write surface header (84 bytes)
            surf_header = struct.pack(
                '<i 64s i i i i i i i i',
                0,  # ident
                surf_info['name'].encode('latin-1')[:64].ljust(64, b'\x00'),  # name
                num_tris,  # numTriangles
                num_verts,  # numVerts
                0,  # staticSurfProcessed
                ofs_triangles,  # ofsTriangles
                ofs_verts,  # ofsVerts
                ofs_collapse,  # ofsCollapse
                ofs_end,  # ofsEnd
                ofs_collapse_idx  # ofsCollapseIndex
            )
            output.write(surf_header)
            
            # Write triangles (3 ints each = 12 bytes)
            for tri in surf_info['triangles']:
                output.write(struct.pack('<3i', tri[0], tri[1], tri[2]))
            
            # Write vertices
            for vert in surf_info['vertices']:
                # Vertex header (24 bytes)
                num_weights = len(vert['weights'])
                num_morphs = len(vert['morphs'])
                
                vert_data = struct.pack(
                    '<3f 2f i i',
                    vert['normal'][0], vert['normal'][1], vert['normal'][2],
                    vert['tex_coords'][0], vert['tex_coords'][1],
                    num_weights,
                    num_morphs
                )
                output.write(vert_data)
                
                # Write morphs (16 bytes each)
                for morph in vert['morphs']:
                    morph_data = struct.pack(
                        '<i 3f',
                        morph['morph_index'],
                        morph['offset'][0], morph['offset'][1], morph['offset'][2]
                    )
                    output.write(morph_data)
                
                # Write weights (20 bytes each)
                for weight in vert['weights']:
                    weight_data = struct.pack(
                        '<i f 3f',
                        weight['bone_index'],
                        weight['bone_weight'],
                        weight['offset'][0], weight['offset'][1], weight['offset'][2]
                    )
                    output.write(weight_data)
            
            # Write collapse map (identity for now)
            for v in range(num_verts):
                output.write(struct.pack('<i', v))
            
            # Write collapse index (identity for now)
            for v in range(num_verts):
                output.write(struct.pack('<i', v))
        
        # Write bones (using boneFileData_t format: 84 bytes each)
        for bone_name, parent_name, offset in bones:
            # We don't have separate base data or channel names, so offsets are 0
            
            bone_data = struct.pack(
                '<32s 32s i i i i i',
                bone_name.encode('latin-1')[:32].ljust(32, b'\x00'),    # name
                parent_name.encode('latin-1')[:32].ljust(32, b'\x00'),  # parent
                SKELBONE_POSROT,  # boneType
                84,  # ofsBaseData (point to immediate data?) 
                     # Actually standard files have ofsBaseData=84 (relative to bone start)
                     # if there is extra data. We just write the base struct. 
                     # Wait, if we use SKELBONE_POSROT, do we need extra data?
                     # Standard files usually have boneType 1 (POSROT) and no extra data?
                     # Let's check phone_roundbase again. 
                     # It had ofsBaseData: 84.
                     # And boneType: 1.
                     # If ofsBaseData is 84, it points to strictly AFTER the bone struct.
                     # But ofsEnd is 116. So 116-84 = 32 bytes of extra data?
                     # Let's look closer at phone_roundbase.
                     # It had offsets: base=84, channels=96, names=116, end=116.
                     # So base data at 84..96 (12 bytes). 
                     # Channel names at 96..116 (20 bytes).
                     # Bone names at 116..116 (0 bytes).
                     # 12 bytes = 3 floats (offset).
                     # So yes, POSROT has an offset.
                     
                0,   # ofsChannelNames (we skip for now)
                0,   # ofsBoneNames
                84 + 12  # ofsEnd (84 + 12 bytes for offset)
            )
            output.write(bone_data)
            
            # Write the offset (12 bytes)
            output.write(struct.pack('<3f', offset[0], offset[1], offset[2]))

        
        # Write to file
        with open(self.filepath, 'wb') as f:
            f.write(output.getvalue())


def export_skd(filepath: str,
               mesh_obj: bpy.types.Object,
               armature_obj: Optional[bpy.types.Object] = None,
               flip_uvs: bool = True,
               swap_yz: bool = False,
               scale: float = 1.0) -> bool:
    """
    Export mesh to SKD file.
    
    Args:
        filepath: Output file path
        mesh_obj: Mesh object to export
        armature_obj: Optional armature object
        flip_uvs: Flip V coordinate
        swap_yz: Swap Y and Z axes
        scale: Global scale factor
        
    Returns:
        True on success
    """
    exporter = SKDExporter(filepath, mesh_obj, armature_obj, flip_uvs, swap_yz, scale)
    return exporter.execute()
