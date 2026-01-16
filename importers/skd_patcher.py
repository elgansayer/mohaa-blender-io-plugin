"""
SKD/SKC Data Patcher for Rest Pose Fix
"""
from mathutils import Vector, Matrix, Quaternion

def apply_skc_rest_pose(skd_model, skc_animation, scale=1.0):
    """
    Modifies SKD model data in-place to use SKC Frame 0 as rest pose.
    Adjusts bone offsets and vertex weight offsets.
    """
    print("Patching SKD model with SKC Frame 0 data...")
    
    # 1. Calculate new bone positions from SKC Frame 0
    # SKC data is local to parent.
    # SKD bones store 'offset' which is local to parent.
    # But SKD 'offset' is often (0,0,0) (collapsed).
    
    # We need to compute the SHIFT for each bone (New - Old).
    # Shift is in Object Space? Or Parent Space?
    # Vertex offsets are typically Object Space relative to Bone Head?
    # Or Bone Local Space?
    # Most likely Object Space relative to Bone Head (if rotation is Identity).
    
    # Let's assume bones have IDENTITY rotation in SKD Rest Pose.
    # SKC Frame 0 might introduce rotation.
    
    # Map channels
    from .skc_format import CHANNEL_POSITION, CHANNEL_ROTATION, get_bone_name_from_channel
    
    bone_channels = {}
    for i, channel in enumerate(skc_animation.channels):
        bone_name = get_bone_name_from_channel(channel.name)
        if bone_name not in bone_channels:
            bone_channels[bone_name] = {'pos': None}
        if channel.channel_type == CHANNEL_POSITION:
            bone_channels[bone_name]['pos'] = i

    # Current Bone World Positions (SKD)
    # We need to traverse hierarchy.
    skd_bones_dict = {b.name: b for b in skd_model.bones}
    
    # Helper to get world pos
    def get_skd_world(bone_name, bones_dict):
        bone = bones_dict.get(bone_name)
        if not bone: return Vector((0,0,0))
        local = Vector(bone.offset) * scale
        parent_world = get_skd_world(bone.parent, bones_dict) if bone.parent != 'worldbone' else Vector((0,0,0))
        return parent_world + local

    old_world_positions = {}
    for bond_data in skd_model.bones:
        old_world_positions[bond_data.name] = get_skd_world(bond_data.name, skd_bones_dict)

    # New Bone World Positions (SKC Frame 0)
    # This requires full hierarchy traversal combining SKC local data.
    new_world_positions = {}
    
    def calculate_new_world(bone_name, parent_world):
        # Start with SKD offset (base)
        skd_bone = skd_bones_dict.get(bone_name)
        base_local = Vector(skd_bone.offset) * scale if skd_bone else Vector((0,0,0))
        
        # Override with SKC data if present
        # SKC stores Absolute Local Position usually?
        if bone_name in bone_channels and bone_channels[bone_name]['pos'] is not None:
            idx = bone_channels[bone_name]['pos']
            raw_pos = skc_animation.channel_data[0][idx].as_position
            # Convert coordinate system if needed?
            # Assuming raw data for now, consistent with importer.
            local_pos = Vector(raw_pos) * scale
        else:
            local_pos = base_local
            
        world_pos = parent_world + local_pos
        new_world_positions[bone_name] = world_pos
        
        # Recurse children
        children = [b for b in skd_model.bones if b.parent == bone_name]
        for child in children:
            calculate_new_world(child.name, world_pos)
            
    # Start with roots
    roots = [b for b in skd_model.bones if b.parent == 'worldbone' or not b.parent]
    for root in roots:
        calculate_new_world(root.name, Vector((0,0,0)))

    # 2. Update Vertex Weights
    # Vertex_World = Old_Bone_World + Old_Weight_Offset
    # We want Vertex_World to stay constant.
    # New_Weight_Offset = Vertex_World - New_Bone_World
    #                   = (Old_Bone_World + Old_Weight_Offset) - New_Bone_World
    #                   = Old_Weight_Offset - (New_Bone_World - Old_Bone_World)
    #                   = Old_Weight_Offset - Shift
    
    # Calculate shifts
    shifts = {}
    for name, old_pos in old_world_positions.items():
        if name in new_world_positions:
            shifts[name] = new_world_positions[name] - old_pos
        else:
            shifts[name] = Vector((0,0,0))
            
    # Apply to mesh
    for surf in skd_model.surfaces:
        for vert in surf.verts:
            for w in vert.weights:
                bone_name = skd_model.bones[w.bone_index].name
                shift = shifts.get(bone_name, Vector((0,0,0)))
                # Update offset
                # w.offset is a tuple/list in raw format, need to update it
                # Assuming SKDVertexWeight structure has mutable offset
                cur_offset = Vector(w.offset) * scale
                new_offset = cur_offset - shift
                w.offset = (new_offset.x / scale, new_offset.y / scale, new_offset.z / scale)
                
    # 3. Update Bone Offsets in SKD Model
    # We need to update the SKD 'offset' field to match the new structure.
    # New_Local = New_World - New_Parent_World.
    
    for bone in skd_model.bones:
        new_world = new_world_positions.get(bone.name, Vector((0,0,0)))
        if bone.parent and bone.parent != 'worldbone':
            parent_new_world = new_world_positions.get(bone.parent, Vector((0,0,0)))
        else:
            parent_new_world = Vector((0,0,0))
            
        new_local = new_world - parent_new_world
        bone.offset = (new_local.x / scale, new_local.y / scale, new_local.z / scale)

    print("SKD Model patched successfully.")
    return skd_model
