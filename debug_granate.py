"""Debug texture loading for steilhandgranate"""
import bpy
import sys
import os

sys.path.insert(0, "/home/elgan/dev")

SKD_FILE = "/home/elgan/.local/share/openmohaa/main/EXISTING-DATA/models/projectiles/STEILHANDGRANATE/steilhandgranate.skd"
GAME_PATH = "/home/elgan/.local/share/openmohaa/main/EXISTING-DATA/"

print("="*60)
print(f"DEBUGGING: {os.path.basename(SKD_FILE)}")
print("="*60)

# 1. Load Shaders
from mohaa_skd_skc.utils.shader_parser import ShaderParser
print(f"Loading shaders from {GAME_PATH}...")
parser = ShaderParser(GAME_PATH)
shaders = parser.parse_all_shaders()
print(f"Loaded {len(shaders)} shaders")

# 2. Read SKD Materials
from mohaa_skd_skc.formats.skd_format import SKDModel
model = SKDModel.read(SKD_FILE)

print("\nSurfaces and Texture Resolution:")
for surf in model.surfaces:
    mat_name = surf.header.name
    print(f"\nSurface Material: '{mat_name}'")
    
    # Check Shader Map
    texture_path = mat_name
    if mat_name in shaders:
        texture_path = shaders[mat_name]
        print(f"  -> Found in shader map: '{texture_path}'")
    else:
        print(f"  -> NOT in shader map")
        
        # Check case-insensitive shader match
        for s_name in shaders:
            if s_name.lower() == mat_name.lower():
                texture_path = shaders[s_name]
                print(f"  -> Found via case-insensitive match: '{s_name}' -> '{texture_path}'")
                break
    
    # Simulate finding the file
    found_path = parser.find_texture(mat_name)
    if found_path:
        print(f"  -> FOUND FILE: {found_path}")
    else:
        print(f"  -> FILE NOT FOUND")
        
        # Debug why it wasn't found - list potential candidates
        base_name = os.path.basename(texture_path)
        base_name_no_ext = os.path.splitext(base_name)[0]
        
        print(f"  Debug: searching for '{base_name}' or '{base_name_no_ext}' in:")
        
        # Check specific directories
        search_dirs = [
            os.path.dirname(SKD_FILE),
            os.path.join(GAME_PATH, "textures"),
            os.path.join(GAME_PATH, "models"),
        ]
        
        for d in search_dirs:
            if os.path.exists(d):
                print(f"    Scanning {d}...")
                # Walk forcing recursive
                matches = []
                for root, _, files in os.walk(d):
                    for f in files:
                        if f.lower().startswith(base_name_no_ext.lower()):
                            matches.append(os.path.join(root, f))
                
                if matches:
                    print(f"    Possible matches found on disk:")
                    for m in matches[:5]:
                        print(f"      - {m}")
                else:
                    print("      No matches")

