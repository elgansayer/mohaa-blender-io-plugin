"""
Deep diagnostic: Compare our Python parsing vs what C++ expects
Analyze allied pilot SKD and allied pilow SKC
"""
import sys
sys.path.insert(0, "/home/elgan/dev/mohaa_skd_skc")

from formats.skd_format import SKDModel
from formats.skc_format import SKCAnimation, get_bone_name_from_channel, CHANNEL_ROTATION, CHANNEL_POSITION

# Find the files
import glob
skd_files = glob.glob("/home/elgan/.local/share/openmohaa/main/**/*allied*pilot*.skd", recursive=True)
skc_files = glob.glob("/home/elgan/.local/share/openmohaa/main/**/*allied*pilow*.skc", recursive=True)

print("="*80)
print("ALLIED PILOT/PILOW DIAGNOSTIC")
print("="*80)

if skd_files:
    skd_file = skd_files[0]
    print(f"\nSKD: {skd_file}")
    skd = SKDModel.read(skd_file)
    
    print(f"\nBones: {len(skd.bones)}")
    print("First 10 bones:")
    for i, bone in enumerate(skd.bones[:10]):
        print(f"  {i:2d}. {bone.name:25s} parent={bone.parent:15s} offset=({bone.offset[0]:6.2f}, {bone.offset[1]:6.2f}, {bone.offset[2]:6.2f})")
    
    print(f"\nSurfaces: {len(skd.surfaces)}")
    if skd.surfaces:
        surf = skd.surfaces[0]
        print(f"  First surface: {surf.header.name}")
        print(f"  Vertices: {len(surf.vertices)}")
        if surf.vertices:
            v = surf.vertices[0]
            print(f"  First vertex has {len(v.weights)} bone weights:")
            for w in v.weights[:3]:
                if w.bone_index < len(skd.bones):
                    print(f"    Bone {w.bone_index} ({skd.bones[w.bone_index].name}): weight={w.bone_weight:.3f}, offset=({w.offset[0]:.2f}, {w.offset[1]:.2f}, {w.offset[2]:.2f})")

if skc_files:
    skc_file = skc_files[0]
    print(f"\n{'='*80}")
    print(f"SKC: {skc_file}")
    skc = SKCAnimation.read(skc_file)
    
    print(f"\nAnimation: {skc.header.num_frames} frames @ {skc.header.fps} fps")
    print(f"Channels: {len(skc.channels)}")
    
    # Group by bone
    bone_channels = {}
    for i, channel in enumerate(skc.channels):
        bone_name = get_bone_name_from_channel(channel.name)
        if bone_name not in bone_channels:
            bone_channels[bone_name] = {'rot': None, 'pos': None}
        
        if channel.channel_type == CHANNEL_ROTATION:
            bone_channels[bone_name]['rot'] = i
        elif channel.channel_type == CHANNEL_POSITION:
            bone_channels[bone_name]['pos'] = i
    
    print(f"\nBones with animation: {len(bone_channels)}")
    print("First 10 animated bones (frame 0):")
    
    for bone_name in list(bone_channels.keys())[:10]:
        rot_idx = bone_channels[bone_name]['rot']
        pos_idx = bone_channels[bone_name]['pos']
        
        rot_str = "no rotation"
        pos_str = "no position"
        
        if rot_idx is not None:
            quat = skc.channel_data[0][rot_idx].as_quaternion
            rot_str = f"quat=({quat[0]:.3f}, {quat[1]:.3f}, {quat[2]:.3f}, {quat[3]:.3f})"
        
        if pos_idx is not None:
            pos = skc.channel_data[0][pos_idx].as_position
            pos_str = f"pos=({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})"
        
        print(f"  {bone_name:25s} {rot_str:50s} {pos_str}")

print("\n" + "="*80)
print("KEY QUESTIONS:")
print("1. Are bone offsets in SKD all zero?")
print("2. Are vertex weight offsets reasonable?")
print("3. Are SKC quaternions/positions reasonable values?")
print("4. Do SKD bones match SKC bones?")
print("="*80)
