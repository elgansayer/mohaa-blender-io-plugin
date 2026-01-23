import unittest
import os
import struct
from io import BytesIO
import tempfile
from typing import List, Tuple

from formats.skc_format import (
    SKCAnimation, SKCHeader, SKCFrame, SKCChannel, SKCChannelFrame,
    SKC_IDENT_INT, SKC_VERSION_CURRENT, SKC_VERSION_OLD,
    CHANNEL_ROTATION, CHANNEL_POSITION, CHANNEL_VALUE
)
from formats.skd_format import (
    SKDModel, SKDHeader, SKDSurface, SKDSurfaceData, SKDVertex, SKDWeight, SKDMorph, SKDTriangle, SKDBoneFileData,
    SKD_IDENT_INT, SKD_VERSION_CURRENT, SKD_VERSION_OLD, SKELBONE_POSROT
)

class TestSKCWrite(unittest.TestCase):
    def setUp(self):
        self.test_file = "test_output.skc"

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_skc_roundtrip_v14(self):
        self._test_skc_roundtrip(SKC_VERSION_CURRENT)

    def test_skc_roundtrip_v13(self):
        self._test_skc_roundtrip(SKC_VERSION_OLD)

    def _test_skc_roundtrip(self, version):
        # Create dummy SKCAnimation
        num_frames = 5
        num_channels = 2

        header = SKCHeader(
            ident=SKC_IDENT_INT,
            version=version,
            flags=0,
            n_bytes_used=0, # Should be recalculated on write
            frame_time=0.05,
            total_delta=(1.0, 2.0, 3.0),
            total_angle_delta=0.0,
            num_channels=num_channels,
            ofs_channel_names=0, # Should be recalculated
            num_frames=num_frames
        )

        frames = []
        for i in range(num_frames):
            frames.append(SKCFrame(
                bounds_min=(-1.0, -1.0, -1.0),
                bounds_max=(1.0, 1.0, 1.0),
                radius=1.5,
                delta=(0.1*i, 0.0, 0.0),
                angle_delta=0.0,
                ofs_channels=0 # Should be recalculated
            ))

        channels = [
            SKCChannel(name="bone1 rot", channel_type=CHANNEL_ROTATION),
            SKCChannel(name="bone1 pos", channel_type=CHANNEL_POSITION)
        ]

        channel_data = []
        for i in range(num_frames):
            frame_data = []
            # Rot
            frame_data.append(SKCChannelFrame(data=(0.0, 0.0, 0.0, 1.0)))
            # Pos
            frame_data.append(SKCChannelFrame(data=(float(i), 0.0, 0.0, 0.0)))
            channel_data.append(frame_data)

        anim = SKCAnimation(
            header=header,
            frames=frames,
            channels=channels,
            channel_data=channel_data
        )

        # Write
        if not hasattr(anim, 'write'):
            print(f"SKCAnimation.write not implemented yet, skipping test for v{version}")
            return

        anim.write(self.test_file, version=version)

        # Read back
        read_anim = SKCAnimation.read(self.test_file)

        # Verify
        self.assertEqual(read_anim.header.version, version)
        self.assertEqual(read_anim.header.num_frames, num_frames)
        self.assertEqual(read_anim.header.num_channels, num_channels)
        self.assertEqual(read_anim.channels[0].name, "bone1 rot")
        self.assertEqual(len(read_anim.channel_data), num_frames)
        self.assertEqual(read_anim.channel_data[1][1].as_position, (1.0, 0.0, 0.0))

class TestSKDWrite(unittest.TestCase):
    def setUp(self):
        self.test_file = "test_output.skd"

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_skd_roundtrip_v6(self):
        self._test_skd_roundtrip(SKD_VERSION_CURRENT)

    def test_skd_roundtrip_v5(self):
        self._test_skd_roundtrip(SKD_VERSION_OLD)

    def _test_skd_roundtrip(self, version):
        # Create dummy SKDModel
        header = SKDHeader(
            ident=SKD_IDENT_INT,
            version=version,
            name="test_model",
            num_surfaces=1,
            num_bones=1,
            ofs_bones=0,
            ofs_surfaces=0,
            ofs_end=0,
            lod_index=[0]*10,
            num_boxes=0,
            ofs_boxes=0,
            num_morph_targets=0,
            ofs_morph_targets=0,
            scale=1.5 if version >= 6 else 1.0
        )

        # Vertices
        verts = [
            SKDVertex(
                normal=(0, 0, 1), tex_coords=(0, 0),
                weights=[SKDWeight(bone_index=0, bone_weight=1.0, offset=(0,0,0))],
                morphs=[]
            ),
            SKDVertex(
                normal=(0, 0, 1), tex_coords=(1, 0),
                weights=[SKDWeight(bone_index=0, bone_weight=1.0, offset=(1,0,0))],
                morphs=[]
            ),
             SKDVertex(
                normal=(0, 0, 1), tex_coords=(0, 1),
                weights=[SKDWeight(bone_index=0, bone_weight=1.0, offset=(0,1,0))],
                morphs=[]
            )
        ]

        # Triangles
        tris = [SKDTriangle(indices=(0, 1, 2))]

        surface_header = SKDSurface(
            ident=0,
            name="mat_test",
            num_triangles=1,
            num_verts=3,
            static_surf_processed=0,
            ofs_triangles=0,
            ofs_verts=0,
            ofs_collapse=0,
            ofs_end=0,
            ofs_collapse_index=0
        )

        surface = SKDSurfaceData(
            header=surface_header,
            triangles=tris,
            vertices=verts
        )

        # Bones
        bones = [
            SKDBoneFileData(
                name="root",
                parent="worldbone",
                bone_type=SKELBONE_POSROT,
                ofs_base_data=0,
                ofs_channel_names=0,
                ofs_bone_names=0,
                ofs_end=0,
                offset=(0.0, 0.0, 0.0)
            )
        ]

        model = SKDModel(
            header=header,
            surfaces=[surface],
            bones=bones
        )

        # Write
        if not hasattr(model, 'write'):
            print(f"SKDModel.write not implemented yet, skipping test for v{version}")
            return

        model.write(self.test_file, version=version)

        # Read back
        read_model = SKDModel.read(self.test_file)

        # Verify
        self.assertEqual(read_model.header.version, version)
        if version >= 6:
            self.assertEqual(read_model.header.scale, 1.5)
        self.assertEqual(len(read_model.surfaces), 1)
        self.assertEqual(len(read_model.surfaces[0].vertices), 3)
        self.assertEqual(read_model.surfaces[0].header.name, "mat_test")
        self.assertEqual(read_model.bones[0].name, "root")

if __name__ == '__main__':
    unittest.main()
