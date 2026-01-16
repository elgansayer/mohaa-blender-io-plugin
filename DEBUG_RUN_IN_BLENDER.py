"""
DEBUG SCRIPT - Run this in Blender's Scripting workspace

This will show you exactly what's happening during import.

INSTRUCTIONS:
1. Open Blender
2. Switch to "Scripting" workspace (top menu bar)
3. Click "Open" and select this file
4. Click "Run Script" (or press Alt+P)
5. Check the console output (Window > Toggle System Console)
"""

import bpy

print("\n" + "="*70)
print("TEXTURE LOADING DEBUG")
print("="*70)

# Get addon preferences
from mohaa_skd_skc import get_addon_preferences
prefs = get_addon_preferences()

if prefs:
    game_path = prefs.preferences.game_path
    print(f"\n✓ Addon preferences found")
    print(f"  Game path: '{game_path}'")
else:
    print(f"\n✗ Could not get addon preferences!")
    game_path = ""

# Test file
test_file = "/home/elgan/.local/share/openmohaa/main/EXISTING-DATA/models/furniture/wardrobe/wardrobe.skd"
print(f"\nTest file: {test_file}")

# Check if game path is correct
import os
if game_path:
    scripts_dir = os.path.join(game_path, 'scripts')
    textures_dir = os.path.join(game_path, 'textures')
    existing_data = os.path.join(game_path, 'EXISTING-DATA')
    
    print(f"\nChecking paths:")
    print(f"  {scripts_dir}: {'EXISTS' if os.path.exists(scripts_dir) else 'NOT FOUND'}")
    print(f"  {textures_dir}: {'EXISTS' if os.path.exists(textures_dir) else 'NOT FOUND'}")
    print(f"  {existing_data}: {'EXISTS' if os.path.exists(existing_data) else 'NOT FOUND'}")
    
    if os.path.exists(existing_data):
        print(f"\n⚠️  WARNING: EXISTING-DATA is a subdirectory!")
        print(f"  Your game path should probably be:")
        print(f"  {existing_data}")

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Try import with current settings
print(f"\n{'='*70}")
print("ATTEMPTING IMPORT")
print('='*70)

try:
    result = bpy.ops.import_mesh.skd(
        filepath=test_file,
        use_shaders=True
    )
    print(f"\nImport result: {result}")
except Exception as e:
    print(f"\n✗ Import failed: {e}")
    import traceback
    traceback.print_exc()

# Check what was created
print(f"\n{'='*70}")
print("CHECKING RESULTS")
print('='*70)

meshes = [obj for obj in bpy.data.objects if obj.type == 'MESH']
if meshes:
    mesh = meshes[0]
    print(f"\n✓ Mesh: {mesh.name}")
    print(f"  Materials: {len(mesh.data.materials)}")
    
    for mat in mesh.data.materials:
        print(f"\n  Material: '{mat.name}'")
        has_texture = False
        
        if mat.use_nodes:
            for node in mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE':
                    if node.image:
                        print(f"    ✓ TEXTURE: {node.image.filepath}")
                        has_texture = True
                    else:
                        print(f"    ✗ Texture node but no image")
        
        if not has_texture:
            print(f"    ✗ NO TEXTURE LOADED")
else:
    print("\n✗ No mesh created")

print("\n" + "="*70)
print("DEBUG COMPLETE - Check output above")
print("="*70)
