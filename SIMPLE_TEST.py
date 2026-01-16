"""
SIMPLE TEST - This will definitely produce output

Run this in Blender's Scripting workspace
"""

import bpy

# This should ALWAYS print
print("="*70)
print("SIMPLE TEST STARTING")
print("="*70)

# Test 1: Basic Blender functionality
print("\n1. Blender version:", bpy.app.version_string)
print("2. Current objects:", len(bpy.data.objects))

# Test 2: Try to import the addon
print("\n3. Testing addon import...")
try:
    import mohaa_skd_skc
    print("   ✓ Addon package imported")
    print("   Location:", mohaa_skd_skc.__file__)
except ImportError as e:
    print("   ✗ FAILED to import addon:", e)
    print("\n   PROBLEM: The addon is not loaded!")
    print("   SOLUTION: Enable it in Edit → Preferences → Add-ons")
except Exception as e:
    print("   ✗ ERROR:", e)

# Test 3: Check if operator exists
print("\n4. Testing SKD import operator...")
if hasattr(bpy.ops.import_mesh, 'skd'):
    print("   ✓ Operator 'import_mesh.skd' exists")
else:
    print("   ✗ Operator NOT found")
    print("   Available operators:", [x for x in dir(bpy.ops.import_mesh) if not x.startswith('_')][:5])

print("\n" + "="*70)
print("TEST COMPLETE")
print("="*70)
print("\nIf you can see this, the console is working!")
print("If you saw errors above, the addon isn't loading properly.")
