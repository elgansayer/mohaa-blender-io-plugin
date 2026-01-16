"""
Test if auto-import code path works
"""
import os

skd_path = "/home/elgan/.local/share/openmohaa/main/EXISTING-DATA/models/human/allied_pilot/allied_pilot.skd"
skd_dir = os.path.dirname(skd_path)
skd_basename = os.path.splitext(os.path.basename(skd_path))[0]
skc_path = os.path.join(skd_dir, skd_basename + ".skc")

print(f"SKD path: {skd_path}")
print(f"SKD dir: {skd_dir}")
print(f"SKD basename: {skd_basename}")
print(f"Checking for: {skc_path}")
print(f"Exists: {os.path.exists(skc_path)}")

if os.path.exists(skc_path):
    print(f"✓ SKC file found, auto-import should trigger")
else:
    print(f"✗ SKC file NOT found")
