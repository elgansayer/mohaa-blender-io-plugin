"""
COMPREHENSIVE TEST: Import allied_pilot SKD+SKC and check what actually happens
"""
import bpy
import sys
sys.path.insert(0, "/home/elgan/dev")

print("="*80)
print("ALLIED PILOT IMPORT TEST")
print("="*80)

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Import SKD
SKD = "/home/elgan/.local/share/openmohaa/main/EXISTING-DATA/models/human/allied_pilot/allied_pilot.skd"
SKC = "/home/elgan/.local/share/openmohaa/main/EXISTING-DATA/models/human/allied_pilot/allied_pilot.skc"

print(f"\n1. Importing SKD: {SKD}")
bpy.ops.import_mesh.skd(filepath=SKD, textures_path="/home/elgan/.local/share/openmohaa/main/")

# Find armature
armature_obj = None
for obj in bpy.data.objects:
    if obj.type == 'ARMATURE':
        armature_obj = obj
        break

if not armature_obj:
    print("ERROR: No armature found!")
else:
    print(f"✓ Armature found: {armature_obj.name}")
    print(f"  Bones: {len(armature_obj.data.bones)}")
    
    # Check Bip01 rest position
    if 'Bip01' in armature_obj.data.bones:
        bip01 = armature_obj.data.bones['Bip01']
        print(f"\nBip01 REST POSE:")
        print(f"  head: {bip01.head}")
        print(f"  head_local: {bip01.head_local}")
        print(f"  matrix_local.translation: {bip01.matrix_local.translation}")
    
    # Import SKC
    print(f"\n2. Importing SKC: {SKC}")
    armature_obj.select_set(True)
    bpy.context.view_layer.objects.active = armature_obj
    
    bpy.ops.import_anim.skc(filepath=SKC)
    
    # Check pose after animation
    bpy.context.scene.frame_set(0)
    
    if 'Bip01' in armature_obj.pose.bones:
        pose_bip01 = armature_obj.pose.bones['Bip01']
        print(f"\nBip01 POSE (frame 0):")
        print(f"  location: {pose_bip01.location}")
        print(f"  rotation_quaternion: {pose_bip01.rotation_quaternion}")
        print(f"  matrix.translation: {pose_bip01.matrix.translation}")
        print(f"  matrix_basis.translation: {pose_bip01.matrix_basis.translation}")
    
    # Check mesh position
    mesh_obj = None
    for obj in bpy.data.objects:
        if obj.type == 'MESH':
            mesh_obj = obj
            break
    
    if mesh_obj:
        print(f"\nMesh: {mesh_obj.name}")
        print(f"  Location: {mesh_obj.location}")
        
        # Get evaluated mesh (after armature deformation)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        mesh_eval = mesh_obj.evaluated_get(depsgraph)
        
        # Check vertex positions
        verts = mesh_eval.data.vertices
        if len(verts) > 0:
            z_min = min(v.co.z for v in verts)
            z_max = max(v.co.z for v in verts)
            print(f"  Vertices Z range: {z_min:.2f} to {z_max:.2f}")
            print(f"  Expected: character standing, Z should be around 0-180")

print("\n" + "="*80)
print("Check result in Blender!")
print("="*80)
