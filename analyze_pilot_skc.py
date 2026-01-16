"""
Analyze allied_pilot.skc animation in detail
"""
import sys
sys.path.insert(0, "/home/elgan/dev/mohaa_skd_skc")

from formats.skc_format import SKCAnimation, get_bone_name_from_channel, CHANNEL_ROTATION, CHANNEL_POSITION

SKC_FILE = "/home/elgan/.local/share/openmohaa/main/EXISTING-DATA/models/human/allied_pilot/allied_pilot.skc"

print("="*80)
print(f"ANALYZING: {SKC_FILE}")
print("="*80)

skc = SKCAnimation.read(SKC_FILE)

print(f"\nFrames: {skc.header.num_frames} @ {skc.header.fps} fps")
print(f"Total channels: {len(skc.channels)}")

# Group by bone
bone_channels = {}
for i, channel in enumerate(skc.channels):
    bone_name = get_bone_name_from_channel(channel.name)
    if bone_name not in bone_channels:
        bone_channels[bone_name] = {'rot': [], 'pos': []}
    
    if channel.channel_type == CHANNEL_ROTATION:
        bone_channels[bone_name]['rot'].append(i)
    elif channel.channel_type == CHANNEL_POSITION:
        bone_channels[bone_name]['pos'].append(i)

print(f"\nUnique bones: {len(bone_channels)}")

# Show Bip01 data specifically
print("\n" + "="*80)
print("BIP01 ANALYSIS (root bone):")
print("="*80)

if 'Bip01' in bone_channels:
    rot_indices = bone_channels['Bip01']['rot']
    pos_indices = bone_channels['Bip01']['pos']
    
    print(f"Rotation channels: {len(rot_indices)} - indices {rot_indices}")
    print(f"Position channels: {len(pos_indices)} - indices {pos_indices}")
    
    if rot_indices:
        print("\nFrame 0 rotation data:")
        for idx in rot_indices:
            quat = skc.channel_data[0][idx].as_quaternion
            print(f"  Channel {idx}: quat=({quat[0]:.4f}, {quat[1]:.4f}, {quat[2]:.4f}, {quat[3]:.4f})")
    
    if pos_indices:
        print("\nFrame 0 position data:")
        for idx in pos_indices:
            pos = skc.channel_data[0][idx].as_position
            print(f"  Channel {idx}: pos=({pos[0]:.4f}, {pos[1]:.4f}, {pos[2]:.4f})")

# Show first 15 bones
print("\n" + "="*80)
print("FIRST 15 BONES (Frame 0):")
print("="*80)

for bone_name in list(bone_channels.keys())[:15]:
    rot_indices = bone_channels[bone_name]['rot']
    pos_indices = bone_channels[bone_name]['pos']
    
    rot_str = "no rotation"
    if rot_indices:
        idx = rot_indices[0]
        quat = skc.channel_data[0][idx].as_quaternion
        rot_str = f"quat=({quat[0]:.3f}, {quat[1]:.3f}, {quat[2]:.3f}, {quat[3]:.3f})"
    
    pos_str = "no position"
    if pos_indices:
        idx = pos_indices[0]
        pos = skc.channel_data[0][idx].as_position
        pos_str = f"pos=({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})"
    
    print(f"{bone_name:25s} | {rot_str:45s} | {pos_str}")

print("\n" + "="*80)
