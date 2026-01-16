"""
SKC Standalone Importer for Blender

Imports SKC animation files and creates a skeleton armature from the animation data,
without requiring an SKD model file.
"""

import bpy
from mathutils import Vector, Quaternion
from typing import Dict, List, Tuple, Optional, Set
import os

from ..formats.skc_format import (
    SKCAnimation, CHANNEL_ROTATION, CHANNEL_POSITION,
    get_bone_name_from_channel
)


class SKCStandaloneImporter:
    """Imports SKC animations and generates skeleton from animation data"""
    
    def __init__(self, filepath: str, scale: float = 1.0):
        """
        Initialize importer.
        
        Args:
            filepath: Path to .skc file
            scale: Global scale factor
        """
        self.filepath = filepath
        self.scale = scale
        
        self.animation: Optional[SKCAnimation] = None
        self.bone_hierarchy: Dict[str, Optional[str]] = {}  # {bone_name: parent_name}
        self.bone_positions: Dict[str, Vector] = {}  # {bone_name: position}
        
    def execute(self) -> Optional[bpy.types.Object]:
        """
        Execute import.
        
        Returns:
            Created armature object or None on failure
        """
        # Load SKC file
        try:
            self.animation = SKCAnimation.read(self.filepath)
        except Exception as e:
            print(f"Error loading SKC file: {e}")
            return None
        
        # Parse bone hierarchy from channel names
        self._build_bone_hierarchy()
        
        # Create armature
        armature_obj = self._create_armature()
        
        if not armature_obj:
            return None
        
        # Apply animation to armature
        self._apply_animation(armature_obj)
        
        return armature_obj
    
    def _build_bone_hierarchy(self):
        """Parse bone names from channels and infer parent-child relationships"""
        # Extract unique bone names
        bone_names: Set[str] = set()
        
        for channel in self.animation.channels:
            bone_name = get_bone_name_from_channel(channel.name)
            bone_names.add(bone_name)
            
            # Get position from first frame if available
            if channel.channel_type == CHANNEL_POSITION:
                if 0 < len(self.animation.channel_data):
                    channel_idx = self.animation.channels.index(channel)
                    pos_data = self.animation.channel_data[0][channel_idx]
                    # Store position (will be transformed later)
                    self.bone_positions[bone_name] = Vector(pos_data.as_position)
        
        # Sort bones by name length (process shorter names first)
        sorted_bones = sorted(bone_names, key=len)
        
        # Infer hierarchy by finding longest matching prefix
        for bone_name in sorted_bones:
            parent = self._find_parent_bone(bone_name, sorted_bones)
            self.bone_hierarchy[bone_name] = parent
    
    def _find_parent_bone(self, bone_name: str, all_bones: List[str]) -> Optional[str]:
        """
        Find parent bone by longest matching prefix.
        
        Args:
            bone_name: Name of bone to find parent for
            all_bones: List of all bone names
            
        Returns:
            Parent bone name or None if root
        """
        best_parent = None
        best_length = 0
        
        for candidate in all_bones:
            if candidate == bone_name:
                continue
            
            # Check if candidate is a prefix of bone_name
            # Example: "Bip01" is parent of "Bip01 Spine"
            if bone_name.startswith(candidate + " "):
                if len(candidate) > best_length:
                    best_parent = candidate
                    best_length = len(candidate)
        
        return best_parent
    
    def _create_armature(self) -> Optional[bpy.types.Object]:
        """Create Blender armature from bone hierarchy"""
        # Get action name from file
        anim_name = os.path.splitext(os.path.basename(self.filepath))[0]
        armature_name = f"{anim_name}_Skeleton"
        
        # Create armature data
        armature_data = bpy.data.armatures.new(name=armature_name)
        armature_obj = bpy.data.objects.new(armature_name, armature_data)
        
        # Link to scene
        bpy.context.collection.objects.link(armature_obj)
        bpy.context.view_layer.objects.active = armature_obj
        
        # Enter edit mode to create bones
        bpy.ops.object.mode_set(mode='EDIT')
        
        # Create bones in hierarchical order (roots first)
        bones_to_create = list(self.bone_hierarchy.keys())
        created_bones = set()
        
        while bones_to_create:
            progress = False
            
            for bone_name in list(bones_to_create):
                parent_name = self.bone_hierarchy[bone_name]
                
                # Can only create if parent is already created (or is root)
                if parent_name is None or parent_name in created_bones:
                    self._create_bone(armature_data, bone_name, parent_name)
                    created_bones.add(bone_name)
                    bones_to_create.remove(bone_name)
                    progress = True
            
            # Safety check to avoid infinite loop
            if not progress:
                print(f"Warning: Could not create bones: {bones_to_create}")
                break
        
        # Exit edit mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        return armature_obj
    
    def _create_bone(self, armature_data: bpy.types.Armature, 
                     bone_name: str, parent_name: Optional[str]):
        """
        Create a single bone in the armature.
        
        Args:
            armature_data: Armature data
            bone_name: Name of bone to create
            parent_name: Name of parent bone or None for root
        """
        edit_bone = armature_data.edit_bones.new(bone_name)
        
        # Get bone position from animation data
        if bone_name in self.bone_positions:
            # Transform from MoHAA to Blender coordinates
            pos = self.bone_positions[bone_name]
            # Apply coordinate transform: Y-forward to Y-back
            head_pos = Vector((pos[0] * self.scale, -pos[1] * self.scale, pos[2] * self.scale))
        else:
            # No position data, use (0,0,0) relative to parent
            head_pos = Vector((0, 0, 0))
        
        # Set parent
        if parent_name and parent_name in armature_data.edit_bones:
            edit_bone.parent = armature_data.edit_bones[parent_name]
            # Position relative to parent
            if edit_bone.parent:
                head_pos = edit_bone.parent.tail + head_pos
        
        edit_bone.head = head_pos
        
        # Set tail (bone end point)
        # Try to find a child bone to point towards
        child_names = [name for name, parent in self.bone_hierarchy.items() if parent == bone_name]
        
        if child_names:
            # Point towards first child
            child_name = child_names[0]
            if child_name in self.bone_positions:
                child_pos = self.bone_positions[child_name]
                child_head = Vector((child_pos[0] * self.scale, -child_pos[1] * self.scale, child_pos[2] * self.scale))
                edit_bone.tail = child_head
            else:
                # Default length
                edit_bone.tail = head_pos + Vector((0, 0, 5.0))
        else:
            # No children, use default length
            edit_bone.tail = head_pos + Vector((0, 0, 5.0))
        
        # Ensure minimum bone length
        if (edit_bone.tail - edit_bone.head).length < 1.0:
            edit_bone.tail = edit_bone.head + Vector((0, 0, 5.0))
    
    def _apply_animation(self, armature_obj: bpy.types.Object):
        """Apply animation to created armature"""
        from .import_skc import SKCImporter
        
        # Create SKC importer and reuse animation application logic
        skc_importer = SKCImporter(
            filepath=self.filepath,
            armature_obj=armature_obj,
            swap_yz=False,
            scale=self.scale
        )
        
        # Reuse the loaded animation data
        skc_importer.animation = self.animation
        
        # Create action and apply animation
        skc_importer._create_action(os.path.splitext(os.path.basename(self.filepath))[0])


def import_skc_standalone(filepath: str, scale: float = 1.0) -> Optional[bpy.types.Object]:
    """
    Import an SKC animation file as a standalone skeleton.
    
    Args:
        filepath: Path to .skc file
        scale: Global scale factor
        
    Returns:
        Created armature object or None on failure
    """
    importer = SKCStandaloneImporter(filepath, scale)
    return importer.execute()
