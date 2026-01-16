"""
Understanding Blender's bone.matrix_basis
This is the key to animation!
"""
import bpy
from mathutils import Vector, Quaternion, Matrix

print("="*80)
print("UNDERSTANDING matrix_basis")
print("="*80)

# Clear & setup
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

armature_data = bpy.data.armatures.new("TestArm")
armature_obj = bpy.data.objects.new("TestArmature", armature_data)
bpy.context.collection.objects.link(armature_obj)
bpy.context.view_layer.objects.active = armature_obj

bpy.ops.object.mode_set(mode='EDIT')

# Root pointing up
root = armature_data.edit_bones.new("root")
root.head = (0, 0, 0)
root.tail = (0, 0, 10)

bpy.ops.object.mode_set(mode='POSE')
root_pose = armature_obj.pose.bones["root"]

print("\n### Approach 1: Set location directly ###")
root_pose.location = Vector((10, 20, 30))
root_pose.rotation_quaternion = Quaternion((1, 0, 0, 0))

print(f"location: {root_pose.location}")
print(f"rotation_quaternion: {root_pose.rotation_quaternion}")
print(f"matrix_basis:\n{root_pose.matrix_basis}")
print(f"matrix_basis.translation: {root_pose.matrix_basis.translation}")

print("\n### Approach 2: Set matrix_basis directly ###")
new_matrix = Matrix.Translation((50, 60, 70))
root_pose.matrix_basis = new_matrix

print(f"After setting matrix_basis to Translation(50,60,70):")
print(f"location: {root_pose.location}")
print(f"rotation_quaternion: {root_pose.rotation_quaternion}")
print(f"matrix_basis.translation: {root_pose.matrix_basis.translation}")

print("\n### Approach 3: Try using the C++ approach directly ###")
# Simulate: world_matrix from C++ calc
mohaa_quat = (0, 0, -0.707, 0.707)  # -90 degree Z rotation  
mohaa_pos = (0, 100, 0)

quat = Quaternion((mohaa_quat[3], mohaa_quat[0], mohaa_quat[1], mohaa_quat[2]))
pos = Vector(mohaa_pos)

mat = quat.to_matrix().to_4x4()
mat.translation = pos

root_pose.matrix_basis = mat

print(f"Set matrix_basis from MoHAA quat + pos:")
print(f"  Input pos: {mohaa_pos}")
print(f"  Input quat: {mohaa_quat}")
print(f"Result:")
print(f"  location: {root_pose.location}")
print(f"  rotation_quaternion: {root_pose.rotation_quaternion}")

print("\n" + "="*80)
print("CONCLUSION: Should we use matrix_basis directly?")
print("="*80)
