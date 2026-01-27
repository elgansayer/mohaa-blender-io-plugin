"""
SKD/SKC Data Patcher for Rest Pose Fix
"""
from mathutils import Vector, Matrix, Quaternion

def apply_skc_rest_pose(skd_model, skc_animation, scale=1.0):
    """
    Modifies SKD model data in-place to use SKC Frame 0 as rest pose.
    Adjusts bone offsets and vertex weight offsets.
    CRITICAL FIX: Now respects Rotations in the SKC data to ensure correct hierarchy reconstruction.
    """
    print("Patching SKD model with SKC Frame 0 data (Rotation Aware)...")
    
    from ..formats.skc_format import CHANNEL_POSITION, CHANNEL_ROTATION, get_bone_name_from_channel
    
    # 1. Map Channels
    bone_channels = {}
    for i, channel in enumerate(skc_animation.channels):
        bone_name = get_bone_name_from_channel(channel.name)
        if bone_name not in bone_channels:
            bone_channels[bone_name] = {'pos': None, 'rot': None}
        if channel.channel_type == CHANNEL_POSITION:
            bone_channels[bone_name]['pos'] = i
        elif channel.channel_type == CHANNEL_ROTATION:
            bone_channels[bone_name]['rot'] = i

    # 2. Calculate OLD World Positions (SKD Base)
    # Assumption: SKD Base Pose has Identity Rotation for all bones (since SKD only stores offset).
    skd_bones_dict = {b.name: b for b in skd_model.bones}
    
    old_world_positions = {}
    
    def calculate_old_world(bone_name, parent_pos):
        bone = skd_bones_dict.get(bone_name)
        if not bone: 
            return Vector((0,0,0)) # Should not happen
            
        local_pos = Vector(bone.offset) * scale
        world_pos = parent_pos + local_pos
        old_world_positions[bone_name] = world_pos
        
        children = [b for b in skd_model.bones if b.parent == bone_name]
        for child in children:
            calculate_old_world(child.name, world_pos)
            
    # Start roots for OLD world
    roots = [b for b in skd_model.bones if b.parent == 'worldbone' or not b.parent]
    for root in roots:
        calculate_old_world(root.name, Vector((0,0,0)))


    # 3. Calculate NEW World Positions (SKC Frame 0)
    # MUST Use Matrix Hierarchy to respect rotations!
    new_world_positions = {}
    # We also need NEW LOCAL positions to update the bone structure later
    new_local_positions = {}
    
    def calculate_new_world_matrix(bone_name, parent_matrix):
        skd_bone = skd_bones_dict.get(bone_name)
        
        # Default Local Transform (from SKD)
        # Pos = Offset, Rot = Identity
        if skd_bone:
            base_pos = Vector(skd_bone.offset) * scale
        else:
            base_pos = Vector((0,0,0))
        base_rot = Quaternion((1,0,0,0)) # Identity
        
        # Override with SKC Data
        final_pos = base_pos
        final_rot = base_rot
        
        if bone_name in bone_channels:
            # Position
            idx_pos = bone_channels[bone_name]['pos']
            if idx_pos is not None:
                raw_pos = skc_animation.channel_data[0][idx_pos].as_position
                final_pos = Vector(raw_pos) * scale
                
            # Rotation
            idx_rot = bone_channels[bone_name]['rot']
            if idx_rot is not None:
                raw_quat = skc_animation.channel_data[0][idx_rot].as_quaternion
                # SKC Quat is (x,y,z,w). Blender Quat is (w,x,y,z).
                x, y, z, w = raw_quat
                final_rot = Quaternion((w, x, y, z))
        
        # Build Local Matrix
        local_matrix = final_rot.to_matrix().to_4x4()
        local_matrix.translation = final_pos
        
        # Calculate World Matrix
        world_matrix = parent_matrix @ local_matrix
        
        # Store Position
        new_world_positions[bone_name] = world_matrix.translation
        
        # Calculate resulting Local Pos for the SKD structure update?
        # Actually, SKD 'offset' is Parent-Relative Position (Local Position).
        # But is it defined in Parent's Coordinate Frame?
        # SKD standard seems to be: Offset is just translation from parent.
        # IF SKD bones implicitly inherit rotation, then yes.
        # BUT SKD bones have NO rotation field.
        # This implies SKD format assumes pure translation hierarchy?
        # OR it assumes the game engine applying animation handles the rotation?
        
        # IF we want to bake the SKC pose into the "Rest Pose", we are saying:
        # "This bone is now at Location X relative to Parent".
        # But if Parent is Rotated... does SKD format support "Rotated Parent"?
        # SKD format doesn't care about rotation because it only stores the OFFSET.
        # Blender, however, needs to know where the bone TAIL is, which depends on rotation?
        # No, Blender `edit_bone.head` is strictly spatial.
        
        # HOWEVER, the `offset` we write back to `skd_model.bones` must be compatible with SKD format.
        # SKD `offset` is `Position_Relative_To_Parent`.
        # Is this Position in World Axis? Or Parent Axis?
        # Standard skeletal systems: Local Position is in Parent's Local Space.
        # Since SKD parents have no rotation, Parent Axis == World Axis (OLD).
        # BUT NEW skeleton has rotations.
        # If we bake rotation into the "Rest Pose", can we store it in SKD?
        # SKD HAS NO ROTATION FIELD.
        
        # CRITICAL REALIZATION:
        # We can update the BONE POSITIONS in the Importer (Blender Object).
        # But we technically cannot "save" a Rotated Rest Pose into an SKD file structure if it doesn't support rotation.
        # BUT we are just patching the IN-MEMORY SKDModel to feed the importer.
        # The Importer uses `bone.offset` to calculate `head`.
        # `head = parent_head + offset`.
        # This implies standard Vector Addition (ignoring parent rotation).
        # This means SKD format IS purely translational for base pose.
        
        # So, if we use SKC (Rotated) hierarchy to calculate World Positions...
        # We get the correct World Positions for the "Expanded" skeleton.
        # To feed this back into SKD `offset` logic (which ignores rotation):
        # We must calculate `virtual_offset = child_world - parent_world`.
        # This `virtual_offset` simply places the child at the correct spot in World Space.
        # It ignores the fact that the parent is rotated.
        # But that's fine! Because SKD format ignores rotation anyway!
        # When Blender imports it, it will simply place bones at `parent + offset`.
        # So `child` will be at `parent + (child_world - parent_world) = child_world`.
        # Accurate!
        
        # Recurse
        children = [b for b in skd_model.bones if b.parent == bone_name]
        for child in children:
            calculate_new_world_matrix(child.name, world_matrix)

    # Start roots for NEW world
    for root in roots:
        calculate_new_world_matrix(root.name, Matrix.Identity(4))


    # 4. Update Vertex Weights (Shift logic)
    # Shift = New_World - Old_World  (Correct logic for updating offset to keep vertex world pos constant)
    shifts = {}
    for name, old_pos in old_world_positions.items():
        if name in new_world_positions:
            shifts[name] = new_world_positions[name] - old_pos
        else:
            shifts[name] = Vector((0,0,0))

    # Optimization: Pre-calculate shifts list for O(1) access by bone index
    # instead of repeated dictionary lookups inside the tight vertex/weight loop.
    num_bones = len(skd_model.bones)
    shifts_list = [Vector((0,0,0))] * num_bones
    for i, bone in enumerate(skd_model.bones):
        shifts_list[i] = shifts.get(bone.name, Vector((0,0,0)))

    # Apply to Mesh
    for surf in skd_model.surfaces:
        for vert in surf.vertices:
            for w in vert.weights:
                if w.bone_index < num_bones:
                    shift = shifts_list[w.bone_index]

                    cur_offset = Vector(w.offset) * scale
                    new_offset = cur_offset - shift
                    w.offset = (new_offset.x / scale, new_offset.y / scale, new_offset.z / scale)

    # 5. Update SKD Bone Offsets (Virtual Offsets)
    # As discussed: New_Offset = New_World - Parent_New_World.
    
    for bone in skd_model.bones:
        new_world = new_world_positions.get(bone.name, Vector((0,0,0)))
        if bone.parent and bone.parent != 'worldbone':
            parent_new_world = new_world_positions.get(bone.parent, Vector((0,0,0)))
        else:
            parent_new_world = Vector((0,0,0))
            
        new_local = new_world - parent_new_world
        bone.offset = (new_local.x / scale, new_local.y / scale, new_local.z / scale)

    print("SKD Model patched successfully (Rotation Aware).")
    return skd_model
