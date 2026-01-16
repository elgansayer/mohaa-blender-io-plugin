"""
DIAGNOSTIC: Dump Blender's Rest Pose
"""
import bpy
import mathutils

obj = bpy.context.active_object
if obj and obj.type == 'ARMATURE':
    print("="*80)
    print(f"REST POSE FOR: {obj.name}")
    print("="*80)
    
    for bone in obj.data.bones:
        print(f"Bone: {bone.name}")
        print(f"  Head (Armature Space): {bone.head}")
        print(f"  Tail (Armature Space): {bone.tail}")
        print(f"  Matrix Local (Armature Space):\n{bone.matrix_local}")
        
        if bone.parent:
            print(f"  Parent: {bone.parent.name}")
            # Calculate Local to Parent Rest transform
            parent_inv = bone.parent.matrix_local.inverted()
            local_rest = parent_inv @ bone.matrix_local
            print(f"  Local to Parent Rest Translation: {local_rest.translation}")
            print(f"  Local to Parent Rest Rotation: {local_rest.to_quaternion()}")
        else:
            print(f"  Parent: None")
            print(f"  Local Rest Translation: {bone.head}")
            
    print("="*80)
else:
    print("Please select the armature object")
