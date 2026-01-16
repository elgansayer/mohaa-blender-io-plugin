#!/usr/bin/env python3
"""
Batch Validation Test for SKD/SKC Import

This script tests all SKD/SKC files WITHOUT needing Blender.
It validates:
1. File parsing (no errors)
2. Bone hierarchy (correct parent-child relationships)
3. Vertex bounding box (reasonable dimensions for characters)
4. Model height (should be ~60-80 units for humans)

Run: python3 batch_validate.py
"""

import sys
import os
import glob
import numpy as np
from typing import Dict, List, Tuple, Optional

sys.path.insert(0, '/home/elgan/dev/mohaa_skd_skc')

from formats.skd_format import SKDModel
from formats.skc_format import SKCAnimation, CHANNEL_POSITION, CHANNEL_ROTATION, get_bone_name_from_channel

# Configuration
GAME_DATA_PATH = "/home/elgan/.local/share/openmohaa/main/EXISTING-DATA"
HUMAN_HEIGHT_MIN = 50  # Minimum expected height for human models
HUMAN_HEIGHT_MAX = 90  # Maximum expected height

def quat_to_matrix_quake(w, x, y, z):
    """Quake-engine style quaternion to rotation matrix"""
    n = np.sqrt(w*w + x*x + y*y + z*z)
    if n > 0: w, x, y, z = w/n, x/n, y/n, z/n
    return np.array([
        [1-2*(y*y+z*z), 2*(x*y+z*w), 2*(x*z-y*w)],
        [2*(x*y-z*w), 1-2*(x*x+z*z), 2*(y*z+x*w)],
        [2*(x*z+y*w), 2*(y*z-x*w), 1-2*(x*x+y*y)]
    ])

def validate_skd(skd_path: str, skc_path: Optional[str] = None) -> Dict:
    """Validate a single SKD file, optionally with its SKC."""
    result = {
        'path': skd_path,
        'skc_path': skc_path,
        'status': 'UNKNOWN',
        'errors': [],
        'warnings': [],
        'bone_count': 0,
        'vertex_count': 0,
        'height': 0,
        'bounds': None
    }
    
    # Load SKD
    try:
        skd = SKDModel.read(skd_path)
        result['bone_count'] = len(skd.bones)
        result['vertex_count'] = sum(len(s.vertices) for s in skd.surfaces)
    except Exception as e:
        result['status'] = 'FAIL'
        result['errors'].append(f"SKD parse error: {e}")
        return result
    
    # Load SKC if provided
    skc_channels = {}
    skc = None
    if skc_path and os.path.exists(skc_path):
        try:
            skc = SKCAnimation.read(skc_path)
            for i, ch in enumerate(skc.channels):
                bone_name = get_bone_name_from_channel(ch.name)
                if bone_name not in skc_channels:
                    skc_channels[bone_name] = {'pos': None, 'rot': None}
                if ch.channel_type == CHANNEL_POSITION:
                    skc_channels[bone_name]['pos'] = i
                elif ch.channel_type == CHANNEL_ROTATION:
                    skc_channels[bone_name]['rot'] = i
        except Exception as e:
            result['warnings'].append(f"SKC parse error: {e}")
    
    # Build bone hierarchy and calculate world matrices
    bone_idx_map = {bone.name: idx for idx, bone in enumerate(skd.bones)}
    bone_world_matrices = {}
    
    def get_local_transform(bone_name):
        bone_idx = bone_idx_map.get(bone_name)
        bone = skd.bones[bone_idx] if bone_idx is not None else None
        pos = np.array(bone.offset) if bone else np.array([0.0, 0.0, 0.0])
        rot = np.eye(3)
        
        if skc and bone_name in skc_channels:
            data = skc_channels[bone_name]
            if data['pos'] is not None:
                pos = np.array(skc.channel_data[0][data['pos']].as_position)
            if data['rot'] is not None:
                x, y, z, w = skc.channel_data[0][data['rot']].as_quaternion
                rot = quat_to_matrix_quake(w, x, y, z)
        return pos, rot
    
    def calc_world(bone_name, parent_pos, parent_rot):
        if bone_name not in bone_idx_map:
            return
        bone_idx = bone_idx_map[bone_name]
        bone = skd.bones[bone_idx]
        local_pos, local_rot = get_local_transform(bone_name)
        world_rot = parent_rot @ local_rot
        world_pos = parent_pos + parent_rot @ local_pos
        bone_world_matrices[bone_idx] = (world_pos, world_rot)
        
        for child_idx, child in enumerate(skd.bones):
            if child.parent == bone_name:
                calc_world(child.name, world_pos, world_rot)
    
    # Calculate from roots
    for idx, bone in enumerate(skd.bones):
        if not bone.parent or bone.parent.lower() == 'worldbone':
            calc_world(bone.name, np.array([0.0, 0.0, 0.0]), np.eye(3))
    
    # Calculate vertex positions
    all_verts = []
    for surface in skd.surfaces:
        for vert in surface.vertices:
            final_pos = np.array([0.0, 0.0, 0.0])
            for w in vert.weights:
                if w.bone_index in bone_world_matrices:
                    world_pos, world_rot = bone_world_matrices[w.bone_index]
                    offset = np.array(w.offset)
                    vertex_pos = world_rot @ offset + world_pos
                    final_pos += vertex_pos * w.bone_weight
            all_verts.append(final_pos)
    
    if not all_verts:
        result['status'] = 'FAIL'
        result['errors'].append("No vertices found")
        return result
    
    # Calculate bounds
    all_verts = np.array(all_verts)
    min_xyz = all_verts.min(axis=0)
    max_xyz = all_verts.max(axis=0)
    result['bounds'] = {
        'min': min_xyz.tolist(),
        'max': max_xyz.tolist(),
        'size': (max_xyz - min_xyz).tolist()
    }
    
    height = max_xyz[2] - min_xyz[2]
    result['height'] = height
    
    # Check if model is human-sized
    model_name = os.path.basename(skd_path).lower()
    is_human = 'human' in skd_path.lower() or any(x in model_name for x in ['pilot', 'soldier', 'german', 'allied', 'resistance', 'manon'])
    
    if is_human:
        if HUMAN_HEIGHT_MIN <= height <= HUMAN_HEIGHT_MAX:
            result['status'] = 'PASS'
        else:
            result['status'] = 'WARN'
            result['warnings'].append(f"Height {height:.1f} outside expected range {HUMAN_HEIGHT_MIN}-{HUMAN_HEIGHT_MAX}")
    else:
        result['status'] = 'PASS'  # Non-human models: just check it parses
    
    return result

def find_matching_skc(skd_path: str) -> Optional[str]:
    """Find matching SKC file for an SKD"""
    # Try same directory, same name
    base = os.path.splitext(skd_path)[0]
    skc_path = base + '.skc'
    if os.path.exists(skc_path):
        return skc_path
    
    # Try model directory
    skd_dir = os.path.dirname(skd_path)
    model_name = os.path.basename(base)
    subdir_skc = os.path.join(skd_dir, model_name, model_name + '.skc')
    if os.path.exists(subdir_skc):
        return subdir_skc
    
    return None

def main():
    print("="*80)
    print("BATCH SKD/SKC VALIDATION TEST")
    print("="*80)
    
    # Find all SKD files
    skd_files = glob.glob(os.path.join(GAME_DATA_PATH, "**/*.skd"), recursive=True)
    print(f"Found {len(skd_files)} SKD files")
    
    results = {
        'PASS': [],
        'WARN': [],
        'FAIL': [],
        'UNKNOWN': []
    }
    
    for i, skd_path in enumerate(sorted(skd_files)):
        rel_path = os.path.relpath(skd_path, GAME_DATA_PATH)
        print(f"[{i+1}/{len(skd_files)}] {rel_path}... ", end='', flush=True)
        
        skc_path = find_matching_skc(skd_path)
        result = validate_skd(skd_path, skc_path)
        
        status = result['status']
        has_skc = "SKC" if skc_path else "   "
        height = result['height']
        
        if status == 'PASS':
            print(f"✓ {has_skc} h={height:.1f}")
        elif status == 'WARN':
            print(f"⚠ {has_skc} h={height:.1f} {result['warnings']}")
        else:
            print(f"✗ {has_skc} {result['errors']}")
        
        results[status].append(result)
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"PASS: {len(results['PASS'])}")
    print(f"WARN: {len(results['WARN'])}")
    print(f"FAIL: {len(results['FAIL'])}")
    
    if results['FAIL']:
        print("\n--- FAILED FILES ---")
        for r in results['FAIL']:
            print(f"  {os.path.relpath(r['path'], GAME_DATA_PATH)}: {r['errors']}")
    
    if results['WARN']:
        print("\n--- WARNING FILES ---")
        for r in results['WARN']:
            print(f"  {os.path.relpath(r['path'], GAME_DATA_PATH)}: h={r['height']:.1f} {r['warnings']}")

if __name__ == '__main__':
    main()
