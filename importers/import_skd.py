"""
SKD (Skeletal Model) Importer for Blender

Imports MoHAA .skd files to create:
- Armature with bone hierarchy
- Mesh with vertex weights and UV maps
- Materials with textures (when texture path is provided)

Coordinate System Notes:
- MoHAA uses Quake-style: X=right, Y=forward, Z=up
- Blender uses: X=right, Y=forward, Z=up
- Apply transformation: (x, y, z) -> (x, -y, z) for correct orientation
"""

import bpy
import bmesh
from mathutils import Vector, Matrix, Quaternion
from typing import Dict, List, Tuple, Optional
import os
import glob

# Relative imports
from ..utils.tik_parser import TikParser, find_tik_for_skd
from ..formats.skd_format import (
    SKDModel, SKDHeader, SKDSurfaceData, SKDVertex, 
    SKDWeight, SKDBoneFileData, SKELBONE_POSROT
)
# Patch Helper
from ..formats.skc_format import SKCAnimation
from .skd_patcher import apply_skc_rest_pose



class SKDImporter:
    """Imports SKD models into Blender"""
    
    # Common texture extensions to search for
    TEXTURE_EXTENSIONS = ['.tga', '.dds', '.jpg', '.jpeg', '.png', '.bmp']
    
    def __init__(self, filepath: str, 
                 flip_uvs: bool = True,
                 swap_yz: bool = False,
                 scale: float = 1.0,
                 textures_path: str = "",
                 shader_map: Optional[Dict[str, str]] = None,
                 skc_filepath: str = None):
        """
        Initialize importer.
        
        Args:
            filepath: Path to .skd file
            flip_uvs: Flip V coordinate (1.0 - v)
            swap_yz: Swap Y and Z axes
            scale: Global scale factor
            textures_path: Base path to search for textures (e.g., game's main folder)
            shader_map: Dictionary mapping shader names to texture paths
            skc_filepath: Optional path to matching SKC file for rest pose correction
        """
        self.filepath = filepath
        self.flip_uvs = flip_uvs
        self.swap_yz = swap_yz
        self.scale = scale
        self.textures_path = textures_path
        self.shader_map = shader_map or {}
        self.skc_filepath = skc_filepath
        self.surface_lookup = {}  # Map surface_name -> shader_name from TIK
        
        self.model: Optional[SKDModel] = None
        self.armature_obj: Optional[bpy.types.Object] = None
        self.mesh_obj: Optional[bpy.types.Object] = None
        self.bone_name_map: Dict[str, str] = {}  # Original name -> Blender name
    
    def execute(self) -> Tuple[Optional[bpy.types.Object], Optional[bpy.types.Object]]:
        """
        Execute import.
        
        Returns:
            Tuple of (armature_object, mesh_object) or (None, None) on failure
        """
        # Load SKD file
        try:
            self.model = SKDModel.read(self.filepath)
        except Exception as e:
            print(f"Error loading SKD file: {e}")
            return None, None
        
        # Get model name from file
        model_name = os.path.splitext(os.path.basename(self.filepath))[0]
        
        # Try to load TIK file for surface mapping
        if self.filepath:
            tik_path = find_tik_for_skd(self.filepath)
            if tik_path:
                print(f"Found associated TIK: {tik_path}")
                try:
                    # Use textures_path as game_path if available
                    game_path = self.textures_path
                    tik_parser = TikParser(game_path)
                    tik_parser.parse_file(tik_path)
                    self.surface_lookup = tik_parser.get_mapping()
                    if self.surface_lookup:
                        print(f"Loaded {len(self.surface_lookup)} surface mappings from TIK")
                except Exception as e:
                    print(f"Warning: Failed to parse TIK: {e}")

        # Create armature first
        if self.model.bones:
            self.armature_obj = self._create_armature(model_name)
        
        # Create mesh
        if self.model.surfaces:
            self.mesh_obj = self._create_mesh(model_name)
            
            # Parent mesh to armature
            if self.armature_obj and self.mesh_obj:
                self.mesh_obj.parent = self.armature_obj
                
                # Add Armature modifier so mesh deforms with bones
                armature_mod = self.mesh_obj.modifiers.new(name="Armature", type='ARMATURE')
                armature_mod.object = self.armature_obj
                
        
        return self.armature_obj, self.mesh_obj
    
    def _transform_position(self, pos: Tuple[float, float, float]) -> Vector:
        """Transform position from MoHAA to Blender coordinates"""
        # MoHAA: Y-forward, Z-up
        # Blender: Y-back, Z-up  
        # Transform: (X, Y, Z) -> (X, -Z, Y)
        x, y, z = pos
        if self.swap_yz:
            return Vector((x * self.scale, -z * self.scale, y * self.scale))
        else:
            return Vector((x * self.scale, y * self.scale, z * self.scale))
    
    def _transform_normal(self, normal: Tuple[float, float, float]) -> Vector:
        """Transform normal vector from MoHAA to Blender coordinates"""
        x, y, z = normal
        
        if self.swap_yz:
            return Vector((x, -z, y)).normalized()
        else:
            return Vector((x, y, z)).normalized()
    
    def _transform_uv(self, uv: Tuple[float, float]) -> Tuple[float, float]:
        """Transform UV coordinates for Blender"""
        u, v = uv
        
        if self.flip_uvs:
            return (u, 1.0 - v)
        return (u, v)
    
    def _find_texture(self, shader_name: str) -> Optional[str]:
        """
        Find texture file from shader/material name.
        
        Args:
            shader_name: Material/shader name from SKD surface
            
        Returns:
            Full path to texture file, or None if not found
        """
        if not shader_name:
            return None
        
        # First check TIK mapping (Surface -> Shader)
        resolved_shader = shader_name
        if self.surface_lookup and shader_name in self.surface_lookup:
            resolved_shader = self.surface_lookup[shader_name]
            # print(f"  Surface '{shader_name}' -> Shader '{resolved_shader}'")
        
        # Then check shader map for texture path (Shader -> Texture)
        texture_path = resolved_shader
        if self.shader_map and resolved_shader in self.shader_map:
            texture_path = self.shader_map[resolved_shader]
            print(f"  Shader '{resolved_shader}' -> '{texture_path}'")
        
        if not self.textures_path:
            return None
        
        # Clean up the shader name - remove any path prefix like "models/..."
        # and try to find matching texture files
        base_name = texture_path.replace('\\', '/').split('/')[-1]
        
        # Search paths to try
        search_paths = [
            self.textures_path,
            os.path.dirname(self.filepath),
        ]
        
        # Add common texture subdirectories
        for base_path in list(search_paths):
            search_paths.extend([
                os.path.join(base_path, 'textures'),
                os.path.join(base_path, 'models'),
                os.path.join(base_path, 'skins'),
                # Support for EXISTING-DATA subdirectory structure
                os.path.join(base_path, 'EXISTING-DATA'),
                os.path.join(base_path, 'EXISTING-DATA', 'textures'),
                os.path.join(base_path, 'EXISTING-DATA', 'models'),
            ])
        
        # Check if texture_path already has an extension
        _, existing_ext = os.path.splitext(texture_path)
        extensions_to_try = [''] if existing_ext else self.TEXTURE_EXTENSIONS
        
        for base_path in search_paths:
            # Try full texture path (from shader or original name)
            for ext in extensions_to_try:
                full_path = os.path.join(base_path, texture_path.replace('/', os.sep) + ext)
                if os.path.exists(full_path):
                    return full_path
            
            # Try just the base name
            _, base_ext = os.path.splitext(base_name)
            base_extensions = [''] if base_ext else self.TEXTURE_EXTENSIONS
            for ext in base_extensions:
                full_path = os.path.join(base_path, base_name + ext)
                if os.path.exists(full_path):
                    return full_path
        
        # Search recursively as last resort
        for base_path in search_paths[:2]:  # Only search main paths
            if os.path.isdir(base_path):
                for ext in self.TEXTURE_EXTENSIONS:
                    pattern = os.path.join(base_path, '**', base_name + ext)
                    matches = glob.glob(pattern, recursive=True)
                    if matches:
                        return matches[0]
        
        return None
    
    def _create_material_with_texture(self, mat_name: str, texture_path: Optional[str]) -> bpy.types.Material:
        """
        Create a material with optional texture.
        
        Args:
            mat_name: Material name
            texture_path: Path to texture file, or None
            
        Returns:
            Created material
        """
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        # Clear default nodes
        nodes.clear()
        
        # Create output node
        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (400, 0)
        
        # Create principled BSDF
        bsdf_node = nodes.new(type='ShaderNodeBsdfPrincipled')
        bsdf_node.location = (0, 0)
        
        # Link BSDF to output
        links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])
        
        # Load and connect texture if available
        if texture_path and os.path.exists(texture_path):
            try:
                # Load image
                image = bpy.data.images.load(texture_path)
                
                # Create image texture node
                tex_node = nodes.new(type='ShaderNodeTexImage')
                tex_node.location = (-300, 0)
                tex_node.image = image
                
                # Connect to base color
                links.new(tex_node.outputs['Color'], bsdf_node.inputs['Base Color'])
                
                # If image has alpha, connect it
                if image.channels == 4:
                    links.new(tex_node.outputs['Alpha'], bsdf_node.inputs['Alpha'])
                    mat.blend_method = 'CLIP'
                
                print(f"  Loaded texture: {texture_path}")
            except Exception as e:
                print(f"  Warning: Failed to load texture {texture_path}: {e}")
        
        return mat
    
    def _create_armature(self, name: str) -> bpy.types.Object:
        """Create armature from bone data"""
        # Create armature data
        armature_data = bpy.data.armatures.new(name=f"{name}_Armature")
        armature_data.display_type = 'STICK'
        
        # Create armature object
        armature_obj = bpy.data.objects.new(f"{name}_Armature", armature_data)
        bpy.context.collection.objects.link(armature_obj)
        
        # Make armature active and enter edit mode
        bpy.context.view_layer.objects.active = armature_obj
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Build bone hierarchy
        bone_indices: Dict[str, int] = {}
        for i, bone_data in enumerate(self.model.bones):
            bone_indices[bone_data.name] = i
        
        # Create edit bones
        edit_bones = armature_data.edit_bones
        created_bones: Dict[str, bpy.types.EditBone] = {}
        
        for bone_data in self.model.bones:
            bone_name = bone_data.name
            
            # Skip worldbone (it's the root reference)
            if bone_name.lower() == 'worldbone':
                continue
            
            # Create bone
            edit_bone = edit_bones.new(bone_name)
            created_bones[bone_name] = edit_bone
            self.bone_name_map[bone_name] = bone_name
            
            # Set bone position from offset
            head_pos = self._transform_position(bone_data.offset)
            edit_bone.head = head_pos
            
            # Set tail slightly offset (bones need length)
            tail_offset = Vector((0, 0, 0.1 * self.scale))
            edit_bone.tail = head_pos + tail_offset
            
            # Set parent
            parent_name = bone_data.parent
            if parent_name and parent_name.lower() != 'worldbone':
                if parent_name in created_bones:
                    edit_bone.parent = created_bones[parent_name]
                    # Connect to parent if close enough
                    parent_tail = created_bones[parent_name].tail
                    if (head_pos - parent_tail).length < 0.01:
                        edit_bone.use_connect = True
        
        # Exit edit mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # NOTE: WE DO NOT ROTATE OBJECT ANYMORE
        # Data is transformed during import.
        
        return armature_obj
    
    def _create_mesh(self, name: str) -> bpy.types.Object:
        """Create mesh from surface data"""
        # Create mesh data
        mesh_data = bpy.data.meshes.new(name=f"{name}_Mesh")
        
        # Collect all geometry from surfaces
        all_verts: List[Vector] = []
        all_faces: List[Tuple[int, int, int]] = []
        all_uvs: List[Tuple[float, float]] = []
        all_normals: List[Vector] = []
        all_weights: List[List[Tuple[str, float]]] = []  # Per-vertex bone weights
        face_materials: List[int] = []  # Material index per face
        
        vertex_offset = 0
        
        for surf_idx, surface in enumerate(self.model.surfaces):
            # Process vertices
            for vertex in surface.vertices:
                # Calculate position from weighted bone offsets
                # Formula: vertex_world = sum(weight * (bone_pos + weight_offset))
                pos = [0.0, 0.0, 0.0]
                for weight in vertex.weights:
                    bone_idx = weight.bone_index
                    if bone_idx < len(self.model.bones):
                        bone = self.model.bones[bone_idx]
                        bone_offset = bone.offset  # Bone's world position
                        # Vertex world = bone_world + weight_local (weighted)
                        pos[0] += weight.bone_weight * (bone_offset[0] + weight.offset[0])
                        pos[1] += weight.bone_weight * (bone_offset[1] + weight.offset[1])
                        pos[2] += weight.bone_weight * (bone_offset[2] + weight.offset[2])
                    else:
                        # Fallback: just use weight offset
                        pos[0] += weight.bone_weight * weight.offset[0]
                        pos[1] += weight.bone_weight * weight.offset[1]
                        pos[2] += weight.bone_weight * weight.offset[2]
                
                all_verts.append(self._transform_position(tuple(pos)))
                all_normals.append(self._transform_normal(vertex.normal))
                all_uvs.append(self._transform_uv(vertex.tex_coords))
                
                # Collect bone weights
                vert_weights = []
                for weight in vertex.weights:
                    if weight.bone_index < len(self.model.bones):
                        bone_name = self.model.bones[weight.bone_index].name
                        if bone_name.lower() != 'worldbone':
                            vert_weights.append((bone_name, weight.bone_weight))
                all_weights.append(vert_weights)
            
            # Process triangles (offset by current vertex count)
            for triangle in surface.triangles:
                face = (
                    triangle.indices[0] + vertex_offset,
                    triangle.indices[1] + vertex_offset,
                    triangle.indices[2] + vertex_offset
                )
                all_faces.append(face)
                face_materials.append(surf_idx)
            
            vertex_offset += len(surface.vertices)
        
        # Create mesh geometry
        mesh_data.from_pydata([v.to_tuple() for v in all_verts], [], all_faces)
        mesh_data.update()
        
        # Create UV layer
        if all_uvs:
            uv_layer = mesh_data.uv_layers.new(name="UVMap")
            
            for poly in mesh_data.polygons:
                for loop_idx in poly.loop_indices:
                    vert_idx = mesh_data.loops[loop_idx].vertex_index
                    if vert_idx < len(all_uvs):
                        uv_layer.data[loop_idx].uv = all_uvs[vert_idx]
        
        # Set custom normals
        if all_normals:
            mesh_data.normals_split_custom_set_from_vertices(
                [n.to_tuple() for n in all_normals]
            )
        
        # Create mesh object
        mesh_obj = bpy.data.objects.new(f"{name}_Mesh", mesh_data)
        bpy.context.collection.objects.link(mesh_obj)
        
        # Create vertex groups for bone weights
        if self.model.bones and all_weights:
            # Create vertex groups for each bone
            bone_groups: Dict[str, bpy.types.VertexGroup] = {}
            
            for bone_data in self.model.bones:
                if bone_data.name.lower() != 'worldbone':
                    group = mesh_obj.vertex_groups.new(name=bone_data.name)
                    bone_groups[bone_data.name] = group
            
            # Assign weights
            for vert_idx, weights in enumerate(all_weights):
                for bone_name, weight in weights:
                    if bone_name in bone_groups and weight > 0.0:
                        bone_groups[bone_name].add([vert_idx], weight, 'REPLACE')
        
        # Create materials for surfaces WITH textures
        for i, surface in enumerate(self.model.surfaces):
            mat_name = surface.header.name if surface.header.name else f"Surface_{i}"
            print(f"Creating material: {mat_name}")
            
            # Try to find texture
            texture_path = self._find_texture(mat_name)
            
            # Create material with texture
            mat = self._create_material_with_texture(mat_name, texture_path)
            mesh_data.materials.append(mat)
        
        # Assign material indices to faces
        for poly_idx, mat_idx in enumerate(face_materials):
            if poly_idx < len(mesh_data.polygons):
                mesh_data.polygons[poly_idx].material_index = mat_idx
        
        return mesh_obj


def import_skd(filepath: str, 
               flip_uvs: bool = True,
               swap_yz: bool = False,
               scale: float = 1.0,
               textures_path: str = "",
               shader_map: Optional[Dict[str, str]] = None,
               skc_filepath: str = None) -> Tuple[Optional[bpy.types.Object], Optional[bpy.types.Object]]:
    """
    Import an SKD file.
    
    Args:
        filepath: Path to .skd file
        flip_uvs: Flip V coordinate
        swap_yz: Swap Y and Z axes
        scale: Global scale factor
        textures_path: Base path to search for textures
        shader_map: Dictionary mapping shader names to texture paths
        skc_filepath: Optional path to matching SKC file for rest pose correction
        
    Returns:
        Tuple of (armature_object, mesh_object)
    """
    importer = SKDImporter(filepath, flip_uvs, swap_yz, scale, textures_path, shader_map, skc_filepath)
    return importer.execute()
