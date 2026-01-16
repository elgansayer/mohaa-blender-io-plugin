"""
CRITICAL DIAGNOSTIC: Test Blender's bone.matrix behavior

This tests if setting bone.matrix directly works as expected for parent-child relationships.
"""
import bpy
from mathutils import Matrix, Vector, Quaternion
import math

print("="*80)
print("BLENDER BONE.MATRIX BEHAVIOR TEST")
print("="*80)

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Create armature
armature_data = bpy.data.armatures.new("TestArm")
armature_obj = bpy.data.objects.new("TestArmature", armature_data)
bpy.context.collection.objects.link(armature_obj)
bpy.context.view_layer.objects.active = armature_obj

# Enter edit mode and create two bones
bpy.ops.object.mode_set(mode='EDIT')

# Parent bone at origin
parent_bone = armature_data.edit_bones.new("parent")
parent_bone.head = (0, 0, 0)
parent_bone.tail = (0, 0, 1)

# Child bone
child_bone = armature_data.edit_bones.new("child")
child_bone.head = (0, 0, 1)  # At parent's tail
child_bone.tail = (0, 0, 2)
child_bone.parent = parent_bone

# Switch to pose mode
bpy.ops.object.mode_set(mode='POSE')

# Test 1: Set parent matrix directly
print("\n### TEST 1: Parent matrix manipulation ###")
parent_pose = armature_obj.pose.bones["parent"]
child_pose = armature_obj.pose.bones["child"]

# Move parent to (10, 0, 0)
parent_local_matrix = Matrix.Translation((10, 0, 0))
parent_pose.matrix = parent_local_matrix

print(f"Set parent.matrix to translate (10,0,0)")
print(f"Parent bone.location: {parent_pose.location}")
print(f"Parent bone.matrix.translation: {parent_pose.matrix.translation}")

# Test 2: Set child with local offset
print("\n### TEST 2: Child with local offset ###")
# Child should be offset (5,0,0) from parent IN LOCAL SPACE
local_offset = Vector((5, 0, 0))
local_quat = Quaternion((1,0,0,0))  # Identity

local_matrix = local_quat.to_matrix().to_4x4()
local_matrix.translation = local_offset

# Multiply by parent's world matrix
world_matrix = parent_pose.matrix @ local_matrix

child_pose.matrix = world_matrix

print(f"Local offset: {local_offset}")
print(f"Parent world position: {parent_pose.matrix.translation}")
print(f"Child world matrix calculation: parent @ local")
print(f"Child world position (should be 15,0,0): {child_pose.matrix.translation}")
print(f"Child bone.location: {child_pose.location}")

# Test 3: What does bone.location represent?
print("\n### TEST 3: What is bone.location? ###")
parent_pose.location = Vector((20, 0, 0))
parent_pose.rotation_quaternion = Quaternion((1,0,0,0))

print(f"Set parent.location = (20,0,0)")
print(f"Parent.matrix.translation: {parent_pose.matrix.translation}")
print(f"Are they the same? {parent_pose.location == parent_pose.matrix.translation}")

print("\n" + "="*80)
print("KEY FINDINGS:")
print("1. Does bone.matrix work as expected?")
print("2. Is bone.location the same as bone.matrix.translation?")
print("3. Does parent @ local give correct child world matrix?")
print("="*80)
