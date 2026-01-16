"""
Understanding Blender's bone transform spaces

PoseBone has several matrix properties:
- bone.matrix: Pose space matrix (relative to rest pose?) 
- bone.matrix_basis: Local transform in parent space
- bone.matrix_channel: Animation data matrix

Let's understand these properly.
"""
import bpy
from mathutils import Matrix, Vector, Quaternion

print("="*80)
print("BLENDER BONE TRANSFORM SPACES")
print("="*80)

# Clear & create armature
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

armature_data = bpy.data.armatures.new("TestArm")
armature_obj = bpy.data.objects.new("TestArmature", armature_data)
bpy.context.collection.objects.link(armature_obj)
bpy.context.view_layer.objects.active = armature_obj

bpy.ops.object.mode_set(mode='EDIT')

# Create bone at (0,0,5) with length 1
bone = armature_data.edit_bones.new("test")
bone.head = (0, 0, 5)
bone.tail = (0, 0, 6)

bpy.ops.object.mode_set(mode='POSE')
pose_bone = armature_obj.pose.bones["test"]

print("\n### REST POSE ###")
print(f"Edit bone head: (0, 0, 5)")
print(f"PoseBone.bone.head_local: {pose_bone.bone.head_local}")
print(f"PoseBone.bone.matrix_local:\n{pose_bone.bone.matrix_local}")

print("\n### APPLYING ANIMATION ###")
# Try to move bone to world position (10, 0, 0)
target_world_pos = Vector((10, 0, 0))

print(f"\nGoal: Move bone to world position {target_world_pos}")

# Method 1: Set location directly
pose_bone.location = target_world_pos
print(f"\nMethod 1: Set location = {target_world_pos}")
print(f"  bone.location: {pose_bone.location}")
print(f"  bone.matrix.translation: {pose_bone.matrix.translation}")
print(f"  bone.matrix_basis.translation: {pose_bone.matrix_basis.translation}")

# Reset
pose_bone.location = (0,0,0)

# Method 2: Use matrix_basis
local_matrix = Matrix.Translation(target_world_pos)
pose_bone.matrix_basis = local_matrix
print(f"\nMethod 2: Set matrix_basis to translation matrix")
print(f"  bone.location: {pose_bone.location}")
print(f"  bone.matrix.translation: {pose_bone.matrix.translation}")

print("\n" + "="*80)
print("CONCLUSION: Which property should we set for animation?")
print("  - bone.location/rotation_quaternion")  
print("  - bone.matrix_basis")
print("  - Something else?")
print("="*80)
