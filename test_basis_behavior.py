"""
TEST: Is matrix_basis Absolute or Relative to Rest Pose?
"""
import bpy
from mathutils import Vector, Matrix

print("="*80)
print("MATRIX BASIS TEST")
print("="*80)

# Clear
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Create armature with bone at Y=10
armature_data = bpy.data.armatures.new("TestArm")
obj = bpy.data.objects.new("TestObj", armature_data)
bpy.context.collection.objects.link(obj)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode='EDIT')

bone = armature_data.edit_bones.new("Bone")
bone.head = (0, 10, 0)
bone.tail = (0, 11, 0)
# Rest pos: (0, 10, 0)

bpy.ops.object.mode_set(mode='POSE')
pb = obj.pose.bones["Bone"]

print(f"Initial Rest Pose Location (World): {pb.head}")
print(f"Initial matrix_basis: {pb.matrix_basis}")
print(f"Initial location: {pb.location}")

print("\n--- TEST 1: set location = (0, 5, 0) ---")
pb.location = Vector((0, 5, 0))
print(f"matrix_basis.translation: {pb.matrix_basis.translation}")
print(f"Actual Head Location (World): {pb.head}")
# If absolute, Head should be (0, 5, 0).
# If relative, Head should be (0, 15, 0).

print("\n--- TEST 2: set matrix_basis translation = (0, 20, 0) ---")
mat = Matrix.Identity(4)
mat.translation = (0, 20, 0)
pb.matrix_basis = mat
print(f"Actual Head Location (World): {pb.head}")

print("="*80)
