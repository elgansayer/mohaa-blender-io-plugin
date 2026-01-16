#!/usr/bin/env python3
"""
FINAL TEST: Full vertex calculation with corrected quaternion convention
"""

import sys
import numpy as np
sys.path.insert(0, '/home/elgan/dev/mohaa_skd_skc')

from formats.skd_format import SKDModel
from formats.skc_format import SKCAnimation, CHANNEL_POSITION, CHANNEL_ROTATION, get_bone_name_from_channel

SKD_PATH = "/home/elgan/.local/share/openmohaa/main/EXISTING-DATA/models/human/allied_pilot/allied_pilot.skd"
SKC_PATH = "/home/elgan/.local/share/openmohaa/main/EXISTING-DATA/models/human/allied_pilot/allied_pilot.skc"

def quat_to_matrix_quake(w, x, y, z):
    """Quake-engine style quaternion to rotation matrix"""
    n = np.sqrt(w*w + x*x + y*y + z*z)
    if n > 0: w, x, y, z = w/n, x/n, y/n, z/n
    return np.array([
        [1-2*(y*y+z*z), 2*(x*y+z*w), 2*(x*z-y*w)],
        [2*(x*y-z*w), 1-2*(x*x+z*z), 2*(y*z+x*w)],
        [2*(x*z+y*w), 2*(y*z-x*w), 1-2*(x*x+y*y)]
    ])

print("="*80)
print("FINAL TEST: Corrected Quaternion Convention")
print("="*80)

skd = SKDModel.read(SKD_PATH)
skc = SKCAnimation.read(SKC_PATH)

# Parse SKC channels
skc_channels = {}
for i, ch in enumerate(skc.channels):
    bone_name = get_bone_name_from_channel(ch.name)
    if bone_name not in skc_channels:
        skc_channels[bone_name] = {'pos': None, 'rot': None}
    if ch.channel_type == CHANNEL_POSITION:
        skc_channels[bone_name]['pos'] = i
    elif ch.channel_type == CHANNEL_ROTATION:
        skc_channels[bone_name]['rot'] = i

bone_idx_map = {bone.name: idx for idx, bone in enumerate(skd.bones)}
bone_world_matrices = {}

def get_local_transform(bone_name):
    """Get local (pos, rot) using SKD offset + SKC rotation"""
    bone = skd.bones[bone_idx_map[bone_name]] if bone_name in bone_idx_map else None
    
    # Default: SKD offset, identity rotation
    pos = np.array(bone.offset) if bone else np.array([0.0, 0.0, 0.0])
    rot = np.eye(3)
    
    # Override with SKC data if available
    if bone_name in skc_channels:
        data = skc_channels[bone_name]
        if data['pos'] is not None:
            raw_pos = skc.channel_data[0][data['pos']].as_position
            pos = np.array(raw_pos)
        if data['rot'] is not None:
            raw_rot = skc.channel_data[0][data['rot']].as_quaternion
            x, y, z, w = raw_rot
            rot = quat_to_matrix_quake(w, x, y, z)  # Use Quake-style!
    
    return pos, rot

def calc_world(bone_name):
    if bone_name in bone_world_matrices:
        return bone_world_matrices[bone_name]
    
    if bone_name not in bone_idx_map:
        return np.array([0.0, 0.0, 0.0]), np.eye(3)
    
    bone = skd.bones[bone_idx_map[bone_name]]
    local_pos, local_rot = get_local_transform(bone_name)
    
    if not bone.parent or bone.parent.lower() == 'worldbone':
        world_pos = local_pos
        world_rot = local_rot
    else:
        parent_pos, parent_rot = calc_world(bone.parent)
        world_rot = parent_rot @ local_rot
        world_pos = parent_pos + parent_rot @ local_pos
    
    bone_world_matrices[bone_name] = (world_pos, world_rot)
    return world_pos, world_rot

# Calculate all world transforms
for bone in skd.bones:
    calc_world(bone.name)

print("\n--- BONE WORLD POSITIONS (Corrected) ---")
for bn in ['Bip01', 'Bip01 Pelvis', 'Bip01 Spine', 'Bip01 Spine1', 'Bip01 Spine2', 
           'Bip01 Neck', 'Bip01 Head', 'Bip01 R Thigh', 'Bip01 R Calf', 'Bip01 R Foot']:
    if bn in bone_world_matrices:
        pos, rot = bone_world_matrices[bn]
        print(f"{bn:<25} ({pos[0]:>8.2f}, {pos[1]:>8.2f}, {pos[2]:>8.2f})")

# Calculate vertices
all_verts = []
for surface in skd.surfaces:
    for vert in surface.vertices:
        final_pos = np.array([0.0, 0.0, 0.0])
        for w in vert.weights:
            if w.bone_index < len(skd.bones):
                bone_name = skd.bones[w.bone_index].name
                if bone_name in bone_world_matrices:
                    world_pos, world_rot = bone_world_matrices[bone_name]
                    offset = np.array(w.offset)
                    vertex_pos = world_rot @ offset + world_pos
                    final_pos += vertex_pos * w.bone_weight
        all_verts.append(final_pos)

all_verts = np.array(all_verts)
min_x, min_y, min_z = all_verts.min(axis=0)
max_x, max_y, max_z = all_verts.max(axis=0)

print(f"\n--- VERTEX BOUNDING BOX ---")
print(f"  X: {min_x:>8.2f} to {max_x:>8.2f}  (range: {max_x-min_x:.2f})")
print(f"  Y: {min_y:>8.2f} to {max_y:>8.2f}  (range: {max_y-min_y:.2f})")
print(f"  Z: {min_z:>8.2f} to {max_z:>8.2f}  (range: {max_z-min_z:.2f})")

height = max_z - min_z
print(f"\n  Model Height: {height:.2f} units")

if 60 < height < 85:
    print("  ✓ SUCCESS! Human-sized model (~70 inches)!")
    print("\n  This confirms the Quake-style quaternion convention is correct!")
elif 150 < height < 200:
    print("  ✓ SUCCESS! Human-sized model (~175 cm)!")
else:
    print(f"  Height still unexpected. Checking feet Z: {min_z:.2f}")

print("\n" + "="*80)
