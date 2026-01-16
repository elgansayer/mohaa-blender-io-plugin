#!/usr/bin/env python3
"""
DEEP ANALYSIS: Understand SKD/SKC Data Format

This script analyzes the actual data to understand:
1. What coordinate space are bone offsets in?
2. What coordinate space are vertex weight offsets in?
3. How do SKC animation positions relate to SKD structure?
4. What is the correct vertex position calculation?

Run with: python3 deep_analysis.py
"""

import sys
import os
sys.path.insert(0, '/home/elgan/dev/mohaa_skd_skc')

from formats.skd_format import SKDModel
from formats.skc_format import SKCAnimation, CHANNEL_POSITION, CHANNEL_ROTATION, get_bone_name_from_channel

# Test files
SKD_PATH = "/home/elgan/.local/share/openmohaa/main/EXISTING-DATA/models/human/allied_pilot/allied_pilot.skd"
SKC_PATH = "/home/elgan/.local/share/openmohaa/main/EXISTING-DATA/models/human/allied_pilot/allied_pilot.skc"

print("="*80)
print("DEEP ANALYSIS: SKD/SKC Data Format")
print("="*80)

# Load files
skd = SKDModel.read(SKD_PATH)
skc = SKCAnimation.read(SKC_PATH)

print(f"\n--- SKD: {os.path.basename(SKD_PATH)} ---")
print(f"Bones: {len(skd.bones)}")
print(f"Surfaces: {len(skd.surfaces)}")

# Analyze bones
print("\n--- BONE ANALYSIS ---")
print(f"{'Index':<5} {'Name':<25} {'Parent':<25} {'Offset (X,Y,Z)':<40}")
print("-"*95)

bone_world_positions = {}
def calc_bone_world(bone_name):
    if bone_name in bone_world_positions:
        return bone_world_positions[bone_name]
    
    for idx, b in enumerate(skd.bones):
        if b.name == bone_name:
            if not b.parent or b.parent.lower() == 'worldbone':
                world = b.offset
            else:
                parent_world = calc_bone_world(b.parent)
                world = (
                    parent_world[0] + b.offset[0],
                    parent_world[1] + b.offset[1],
                    parent_world[2] + b.offset[2]
                )
            bone_world_positions[bone_name] = world
            return world
    return (0, 0, 0)

for idx, bone in enumerate(skd.bones[:15]):  # First 15 bones
    world = calc_bone_world(bone.name)
    print(f"{idx:<5} {bone.name:<25} {bone.parent or 'None':<25} L:({bone.offset[0]:>7.2f}, {bone.offset[1]:>7.2f}, {bone.offset[2]:>7.2f}) W:({world[0]:>7.2f}, {world[1]:>7.2f}, {world[2]:>7.2f})")

# Analyze SKC Frame 0
print("\n--- SKC FRAME 0 ANALYSIS ---")
skc_channels = {}
for i, ch in enumerate(skc.channels):
    bone_name = get_bone_name_from_channel(ch.name)
    if bone_name not in skc_channels:
        skc_channels[bone_name] = {'pos': None, 'rot': None}
    if ch.channel_type == CHANNEL_POSITION:
        skc_channels[bone_name]['pos'] = i
    elif ch.channel_type == CHANNEL_ROTATION:
        skc_channels[bone_name]['rot'] = i

print(f"{'Bone Name':<25} {'SKC Pos (X,Y,Z)':<40} {'SKC Rot (X,Y,Z,W)':<45}")
print("-"*110)
for bone_name in list(skc_channels.keys())[:15]:
    data = skc_channels[bone_name]
    pos_str = "N/A"
    rot_str = "N/A"
    if data['pos'] is not None:
        pos = skc.channel_data[0][data['pos']].as_position
        pos_str = f"({pos[0]:>7.2f}, {pos[1]:>7.2f}, {pos[2]:>7.2f})"
    if data['rot'] is not None:
        rot = skc.channel_data[0][data['rot']].as_quaternion
        rot_str = f"({rot[0]:>6.3f}, {rot[1]:>6.3f}, {rot[2]:>6.3f}, {rot[3]:>6.3f})"
    print(f"{bone_name:<25} {pos_str:<40} {rot_str:<45}")

# Compare SKD vs SKC for key bones
print("\n--- SKD vs SKC BONE COMPARISON ---")
print(f"{'Bone':<25} {'SKD World':<35} {'SKC Frame0':<35} {'Match?':<10}")
print("-"*105)
for bone_name in ['Bip01', 'Bip01 Pelvis', 'Bip01 Spine', 'Bip01 Head', 'Bip01 L Calf', 'Bip01 R Calf']:
    skd_world = bone_world_positions.get(bone_name, (0,0,0))
    skd_str = f"({skd_world[0]:>7.2f}, {skd_world[1]:>7.2f}, {skd_world[2]:>7.2f})"
    
    skc_pos = "N/A"
    if bone_name in skc_channels and skc_channels[bone_name]['pos'] is not None:
        pos = skc.channel_data[0][skc_channels[bone_name]['pos']].as_position
        skc_pos = f"({pos[0]:>7.2f}, {pos[1]:>7.2f}, {pos[2]:>7.2f})"
    
    match = "SAME" if skd_str == skc_pos else "DIFF"
    print(f"{bone_name:<25} {skd_str:<35} {skc_pos:<35} {match:<10}")

# Analyze vertex weights
print("\n--- VERTEX WEIGHT ANALYSIS ---")
print("Looking at first surface, first 5 vertices:")
if skd.surfaces:
    surface = skd.surfaces[0]
    print(f"Surface: {surface.header.name}, Vertices: {len(surface.vertices)}")
    
    for v_idx, vert in enumerate(surface.vertices[:5]):
        print(f"\n  Vertex {v_idx}: {len(vert.weights)} weights")
        for w in vert.weights:
            bone_name = skd.bones[w.bone_index].name if w.bone_index < len(skd.bones) else "INVALID"
            bone_world = bone_world_positions.get(bone_name, (0,0,0))
            print(f"    Bone: {bone_name:<20} Weight: {w.bone_weight:.3f}")
            print(f"      Offset (Local): ({w.offset[0]:>8.3f}, {w.offset[1]:>8.3f}, {w.offset[2]:>8.3f})")
            print(f"      Bone World:     ({bone_world[0]:>8.3f}, {bone_world[1]:>8.3f}, {bone_world[2]:>8.3f})")
            
            # Calculate vertex world position two ways
            way1 = (w.offset[0], w.offset[1], w.offset[2])  # Just offset
            way2 = (bone_world[0] + w.offset[0], bone_world[1] + w.offset[1], bone_world[2] + w.offset[2])  # Bone + offset
            print(f"      Vertex if offset-only:    ({way1[0]:>8.3f}, {way1[1]:>8.3f}, {way1[2]:>8.3f})")
            print(f"      Vertex if bone+offset:    ({way2[0]:>8.3f}, {way2[1]:>8.3f}, {way2[2]:>8.3f})")

# Check bounding box of vertices using different methods
print("\n--- VERTEX BOUNDING BOX ANALYSIS ---")
all_verts_offset_only = []
all_verts_bone_plus_offset = []

for surface in skd.surfaces:
    for vert in surface.vertices:
        pos_offset = [0.0, 0.0, 0.0]
        pos_bone_plus = [0.0, 0.0, 0.0]
        
        for w in vert.weights:
            if w.bone_index < len(skd.bones):
                bone_name = skd.bones[w.bone_index].name
                bone_world = bone_world_positions.get(bone_name, (0,0,0))
                
                # Method 1: Offset only
                pos_offset[0] += w.bone_weight * w.offset[0]
                pos_offset[1] += w.bone_weight * w.offset[1]
                pos_offset[2] += w.bone_weight * w.offset[2]
                
                # Method 2: Bone + Offset
                pos_bone_plus[0] += w.bone_weight * (bone_world[0] + w.offset[0])
                pos_bone_plus[1] += w.bone_weight * (bone_world[1] + w.offset[1])
                pos_bone_plus[2] += w.bone_weight * (bone_world[2] + w.offset[2])
        
        all_verts_offset_only.append(tuple(pos_offset))
        all_verts_bone_plus_offset.append(tuple(pos_bone_plus))

def get_bounds(verts):
    if not verts:
        return None
    min_x = min(v[0] for v in verts)
    max_x = max(v[0] for v in verts)
    min_y = min(v[1] for v in verts)
    max_y = max(v[1] for v in verts)
    min_z = min(v[2] for v in verts)
    max_z = max(v[2] for v in verts)
    return (min_x, max_x, min_y, max_y, min_z, max_z)

bounds1 = get_bounds(all_verts_offset_only)
bounds2 = get_bounds(all_verts_bone_plus_offset)

print("Method 1 (Offset Only):")
print(f"  X: {bounds1[0]:>8.2f} to {bounds1[1]:>8.2f}  (range: {bounds1[1]-bounds1[0]:.2f})")
print(f"  Y: {bounds1[2]:>8.2f} to {bounds1[3]:>8.2f}  (range: {bounds1[3]-bounds1[2]:.2f})")
print(f"  Z: {bounds1[4]:>8.2f} to {bounds1[5]:>8.2f}  (range: {bounds1[5]-bounds1[4]:.2f})")

print("\nMethod 2 (Bone World + Offset):")
print(f"  X: {bounds2[0]:>8.2f} to {bounds2[1]:>8.2f}  (range: {bounds2[1]-bounds2[0]:.2f})")
print(f"  Y: {bounds2[2]:>8.2f} to {bounds2[3]:>8.2f}  (range: {bounds2[3]-bounds2[2]:.2f})")
print(f"  Z: {bounds2[4]:>8.2f} to {bounds2[5]:>8.2f}  (range: {bounds2[5]-bounds2[4]:.2f})")

print("\n" + "="*80)
print("CONCLUSIONS:")
print("="*80)
print("""
If the model is a human approximately 70 inches (178cm) tall:
- In game units, we expect a Z range of roughly 0-70 (or 0-180 in cm)
- The method that gives a Z range matching human height is likely CORRECT

Based on the bounds above, determine which method is correct.
""")
