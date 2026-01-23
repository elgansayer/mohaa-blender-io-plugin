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
            version: SKD format version (5 or 6)
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
            print(f"  Version: {self.version}")
            
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
    
    def _write_file(self, surfaces_data: List[Dict],
                    bones_data: List[Tuple[str, str, Tuple[float, float, float]]]) -> None:
        """Write all data to binary file using SKDModel"""
        
        model_name = os.path.splitext(os.path.basename(self.filepath))[0]
        
        # Convert bones
        bones = []
        for name, parent, offset in bones_data:
            bones.append(SKDBoneFileData(
                name=name,
                parent=parent,
                bone_type=SKELBONE_POSROT,
                ofs_base_data=84, # Calculated in write() anyway but good to be explicit
                ofs_channel_names=0,
                ofs_bone_names=0,
                ofs_end=96,
                offset=offset
            ))
            
        # Convert surfaces
        surfaces = []
        for surf_data in surfaces_data:
            # Convert triangles
            triangles = [SKDTriangle(indices=t) for t in surf_data['triangles']]
            
            # Convert vertices
            vertices = []
            for v_data in surf_data['vertices']:
                weights = [SKDWeight(
                    bone_index=w['bone_index'],
                    bone_weight=w['bone_weight'],
                    offset=w['offset']
                ) for w in v_data['weights']]
                
                morphs = [SKDMorph(
                    morph_index=m['morph_index'],
                    offset=m['offset']
                ) for m in v_data['morphs']]
                
                vertices.append(SKDVertex(
                    normal=v_data['normal'],
                    tex_coords=v_data['tex_coords'],
                    weights=weights,
                    morphs=morphs
                ))
            
            # Create surface header
            header = SKDSurface(
                ident=0,
                name=surf_data['name'],
                num_triangles=len(triangles),
                num_verts=len(vertices),
                static_surf_processed=0,
                ofs_triangles=0, # Calculated in write()
                ofs_verts=0,
                ofs_collapse=0,
                ofs_end=0,
                ofs_collapse_index=0
            )
            
            surfaces.append(SKDSurfaceData(
                header=header,
                triangles=triangles,
                vertices=vertices
            ))

        # Create Header
        header = SKDHeader(
            ident=SKD_IDENT_INT,
            version=self.version,
            name=model_name,
            num_surfaces=len(surfaces),
            num_bones=len(bones),
            ofs_bones=0, # Calculated in write()
            ofs_surfaces=0,
            ofs_end=0,
            lod_index=[0]*10,
            num_boxes=0,
            ofs_boxes=0,
            num_morph_targets=0,
            ofs_morph_targets=0,
            scale=1.0 / self.scale if self.scale != 0 else 1.0
        )

        # Create Model
        model = SKDModel(
            header=header,
            surfaces=surfaces,
            bones=bones
        )
        
        # Write
        model.write(self.filepath, version=self.version)


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
        version: SKD format version (5 or 6)
        
    Returns:
        True on success
    """
    exporter = SKDExporter(filepath, mesh_obj, armature_obj, flip_uvs, swap_yz, scale, version)
    return exporter.execute()
