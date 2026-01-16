"""
DIAGNOSTIC: Import SKD and Dump Rest Pose
"""
import bpy
import sys
import os

# Ensure we can find our modules
sys.path.insert(0, "/home/elgan/dev/mohaa_skd_skc")

# Import directly from file to skip addon registration issues in cli
from importers.import_skd import import_skd

SKD_PATH = "/home/elgan/.local/share/openmohaa/main/EXISTING-DATA/models/human/allied_pilot/allied_pilot.skd"

print("="*80)
print("IMPORTING SKD FOR DIAGNOSTIC")
print("="*80)

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Import
armature, mesh = import_skd(SKD_PATH, flip_uvs=True, swap_yz=False, scale=1.0, textures_path="", use_shaders=False)

print("\n" + "="*80)
print(f"REST POSE FOR: {armature.name}")
print("="*80)

for bone in armature.data.bones:
    print(f"\nBone: {bone.name}")
    print(f"  Head: {bone.head}")
    
    if bone.parent:
        # Calculate Local to Parent Rest transform
        parent_inv = bone.parent.matrix_local.inverted()
        local_rest = parent_inv @ bone.matrix_local
        print(f"  Local2Parent Trans: {local_rest.translation}")
    else:
        print(f"  Local2Parent Trans: {bone.head}")

print("="*80)
