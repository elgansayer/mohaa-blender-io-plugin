"""
MINIMAL TEST: What coordinate conversion do we actually need?

Test if position data needs Y/Z swap for MoHAA -> Blender
"""
import bpy
from mathutils import Vector, Quaternion, Matrix

print("="*80)
print("MINIMAL COORDINATE SPACE TEST")
print("="*80)

# Clear
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Create simple armature with 2 bones
armature_data = bpy.data.armatures.new("TestArm")
armature_obj = bpy.data.objects.new("TestArmature", armature_data)
bpy.context.collection.objects.link(armature_obj)
bpy.context.view_layer.objects.active = armature_obj

bpy.ops.object.mode_set(mode='EDIT')

# Root bone at origin, pointing up (Z+)
root = armature_data.edit_bones.new("root")
root.head = (0, 0, 0)
root.tail = (0, 0, 10)  # Points in +Z

# Child bone
child = armature_data.edit_bones.new("child")
child.head = (0, 0, 10)
child.tail = (0, 0, 20)
child.parent = root

bpy.ops.object.mode_set(mode='POSE')

print("\n### TEST 1: Set root location to (0, 100, 0) - should move forward in Y ###")
root_pose = armature_obj.pose.bones["root"]
root_pose.location = Vector((0, 100, 0))

print(f"Set location: (0, 100, 0)")
print(f"bone.location: {root_pose.location}")  
print(f"bone.matrix.translation: {root_pose.matrix.translation}")

print("\n### TEST 2: Set root location to (0, 0, 100) - should move up in Z ###")
root_pose.location = Vector((0, 0, 100))

print(f"Set location: (0, 0, 100)")
print(f"bone.location: {root_pose.location}")
print(f"bone.matrix.translation: {root_pose.matrix.translation}")

print("\n### TEST 3: What if we need Y->-Y conversion? ###")
# MoHAA position (0, 100, 0) means +Y forward
# Blender needs -Y for forward
# So convert: (X, Y, Z) -> (X, -Y, Z)

mohaa_pos = Vector((0, 100, 0))
blender_pos = Vector((mohaa_pos.x, -mohaa_pos.y, mohaa_pos.z))

root_pose.location = blender_pos
print(f"MoHAA position: {mohaa_pos}")
print(f"Converted to: {blender_pos}")
print(f"bone.matrix.translation: {root_pose.matrix.translation}")

print("\n" + "="*80)
print("KEY: Does bone.matrix.translation match what we expect?")
print("="*80)
