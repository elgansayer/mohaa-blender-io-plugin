"""
DIAGNOSTIC SCRIPT - Run this in Blender's Scripting workspace

This will show you EXACTLY what's happening during import.

HOW TO RUN:
1. Open Blender
2. Switch to "Scripting" workspace (top menu)
3. Click "Text" → "Open" → Select this file
4. Click "Run Script" button (▶) or press Alt+P
5. Watch the output in the System Console (Window → Toggle System Console)
"""

import bpy
import os

print("\n" + "="*70)
print("TEXTURE LOADING DIAGNOSTIC")
print("="*70)

# Step 1: Check addon is loaded
try:
    from mohaa_skd_skc import get_addon_preferences
    from mohaa_skd_skc.importers.import_skd import SKDImporter
    from mohaa_skd_skc.utils.shader_parser import ShaderParser
    print("\n✓ Addon modules loaded successfully")
except Exception as e:
    print(f"\n✗ ERROR loading addon: {e}")
    import traceback
    traceback.print_exc()

# Step 2: Check preferences
try:
    prefs = get_addon_preferences()
    if prefs:
        game_path = prefs.preferences.game_path
        print(f"\n✓ Game path from preferences: '{game_path}'")
    else:
        game_path = ""
        print(f"\n⚠ No addon preferences found")
except Exception as e:
    game_path = ""
    print(f"\n✗ Error getting preferences: {e}")

# Use main path if not set
if not game_path:
    game_path = "/home/elgan/.local/share/openmohaa/main/"
    print(f"  Using default: {game_path}")

# Step 3: Test shader parsing
print(f"\n{'='*70}")
print("SHADER PARSING TEST")
print('='*70)
try:
    parser = ShaderParser(game_path)
    shader_map = parser.parse_all_shaders()
    print(f"✓ Loaded {len(shader_map)} shaders")
    
    if 'wardrobe' in shader_map:
        print(f"✓ 'wardrobe' shader found: {shader_map['wardrobe']}")
    else:
        print(f"✗ 'wardrobe' shader NOT found")
except Exception as e:
    print(f"✗ Shader parsing failed: {e}")
    shader_map = {}

# Step 4: Test texture file existence
print(f"\n{'='*70}")
print("TEXTURE FILE CHECK")
print('='*70)

texture_paths_to_check = [
    os.path.join(game_path, "textures/models/items/wardrobe.tga"),
    os.path.join(game_path, "EXISTING-DATA/textures/models/items/wardrobe.tga"),
]

for path in texture_paths_to_check:
    exists = os.path.exists(path)
    print(f"{'✓' if exists else '✗'} {path}")

# Step 5: Do actual import
print(f"\n{'='*70}")
print("IMPORT TEST")
print('='*70)

test_file = "/home/elgan/.local/share/openmohaa/main/EXISTING-DATA/models/furniture/wardrobe/wardrobe.skd"

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

print(f"Importing: {test_file}")
print(f"With game path: {game_path}")

try:
    # Create importer directly so we can see what's happening
    importer = SKDImporter(
        filepath=test_file,
        textures_path=game_path,
        shader_map=shader_map
    )
    
    arm, mesh = importer.execute()
    
    if mesh:
        print(f"\n✓ Mesh created: {mesh.name}")
        print(f"  Materials: {len(mesh.data.materials)}")
        
        for mat in mesh.data.materials:
            print(f"\n  Material: '{mat.name}'")
            
            if mat.use_nodes:
                for node in mat.node_tree.nodes:
                    print(f"    Node: {node.type}")
                    if node.type == 'TEX_IMAGE':
                        if node.image:
                            print(f"    ✓✓✓ TEXTURE: {node.image.filepath}")
                        else:
                            print(f"    ✗ Texture node but NO image!")
            else:
                print(f"    ✗ Material doesn't use nodes")
    else:
        print(f"\n✗ No mesh created")
        
except Exception as e:
    print(f"\n✗ Import failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*70)
print("DIAGNOSTIC COMPLETE")
print("="*70)
print("\nIf you see '✓✓✓ TEXTURE:' above, textures ARE loading.")
print("If not, send me the output above so I can diagnose further.")
