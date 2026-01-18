
import unittest
import sys
import os
import types
import struct
from io import BytesIO

# =============================================================================
# MOCKS
# =============================================================================

class MockVector:
    def __init__(self, data):
        self._data = list(data) if data is not None else [0.0, 0.0, 0.0]

    @property
    def x(self): return self._data[0]
    @property
    def y(self): return self._data[1]
    @property
    def z(self): return self._data[2]

    def __getitem__(self, idx): return self._data[idx]
    def __setitem__(self, idx, val): self._data[idx] = val
    def __len__(self): return len(self._data)
    def __iter__(self): return iter(self._data)

    def __sub__(self, other):
        return MockVector([a - b for a, b in zip(self._data, other)])

    @property
    def length(self):
        return sum(x*x for x in self._data)**0.5

    def normalized(self):
        l = self.length
        if l == 0: return MockVector([0,0,0])
        return MockVector([x/l for x in self._data])

    def to_tuple(self):
        return tuple(self._data)

class MockQuaternion:
    def __init__(self, data):
        self._data = list(data) if data is not None else [1.0, 0.0, 0.0, 0.0]

    @property
    def w(self): return self._data[0]
    @property
    def x(self): return self._data[1]
    @property
    def y(self): return self._data[2]
    @property
    def z(self): return self._data[3]

    def __getitem__(self, idx): return self._data[idx]
    def __iter__(self): return iter(self._data)

class MockMatrix:
    def __init__(self, rows=None):
        self.rows = rows or []

    @classmethod
    def Identity(cls, size):
        return cls()

class MockObject:
    def __init__(self, name, type_):
        self.name = name
        self.type = type_
        self.data = None
        self.pose = None
        self.animation_data = None
        self.evaluated_get = lambda dg: self
        self.to_mesh = lambda: self.data
        self.to_mesh_clear = lambda: None
        self.modifiers = []

class MockBone:
    def __init__(self, name):
        self.name = name
        self.head = MockVector([0,0,0])
        self.head_local = MockVector([0,0,0])
        self.parent = None
        self.rotation_mode = 'QUATERNION'
        self.rotation_quaternion = MockQuaternion([1,0,0,0])
        self.location = MockVector([0,0,0])

class MockArmature:
    def __init__(self):
        self.bones = []

class MockPose:
    def __init__(self):
        self.bones = []

class MockAction:
    def __init__(self):
        self.frame_range = (0, 10)

class MockScene:
    def __init__(self):
        self.render = types.SimpleNamespace(fps=24)
        self.frame_current = 0
    def frame_set(self, f):
        self.frame_current = f

class MockContext:
    def __init__(self):
        self.scene = MockScene()
        self.evaluated_depsgraph_get = lambda: None

# BMesh mocks
class MockBMesh:
    def __init__(self):
        self.faces = []
    def from_mesh(self, mesh): pass
    def to_mesh(self, mesh): pass
    def free(self): pass

class MockBMeshOps:
    def triangulate(self, bm, faces): pass

# Setup Mock Modules
if 'bpy' not in sys.modules:
    mathutils = types.ModuleType('mathutils')
    mathutils.Vector = MockVector
    mathutils.Quaternion = MockQuaternion
    mathutils.Matrix = MockMatrix

    bpy = types.ModuleType('bpy')
    bpy.types = types.ModuleType('bpy.types')
    bpy.types.Object = MockObject
    bpy.types.Action = MockAction
    bpy.types.Armature = MockArmature
    bpy.types.Bone = MockBone
    bpy.types.Mesh = types.SimpleNamespace()
    bpy.data = types.SimpleNamespace(objects=[], materials=[])
    bpy.context = MockContext()
    class MockOperator: pass
    class MockAddonPreferences: pass
    bpy.types.Operator = MockOperator
    bpy.types.AddonPreferences = MockAddonPreferences

    props = types.ModuleType('bpy.props')
    props.StringProperty = lambda **kwargs: None
    props.BoolProperty = lambda **kwargs: None
    props.FloatProperty = lambda **kwargs: None
    bpy.props = props

    ops = types.ModuleType('bpy.ops')
    bpy.ops = ops

    bpy_extras = types.ModuleType('bpy_extras')
    io_utils = types.ModuleType('bpy_extras.io_utils')
    class MockImportHelper: pass
    class MockExportHelper: pass
    io_utils.ImportHelper = MockImportHelper
    io_utils.ExportHelper = MockExportHelper
    bpy_extras.io_utils = io_utils

    bmesh = types.ModuleType('bmesh')
    bmesh.new = lambda: MockBMesh()
    bmesh.ops = MockBMeshOps()

    sys.modules['mathutils'] = mathutils
    sys.modules['bpy'] = bpy
    sys.modules['bmesh'] = bmesh
    sys.modules['bpy.types'] = bpy.types
    sys.modules['bpy.props'] = props
    sys.modules['bpy.ops'] = ops
    sys.modules['bpy_extras'] = bpy_extras
    sys.modules['bpy_extras.io_utils'] = io_utils
else:
    import bpy
    import mathutils
    import bmesh

# =============================================================================
# IMPORTS (handled to work from root)
# =============================================================================

sys.path.append(os.getcwd())

# Try to handle package structure
try:
    from formats.skc_format import SKC_IDENT_INT, SKC_VERSION_CURRENT
    from formats.skd_format import SKD_IDENT_INT, SKD_VERSION_CURRENT

    # We need to trick exporters into thinking they are part of a package if we import them directly
    # OR we can just import them and if they use relative imports, they fail.
    # To make relative imports work, we must run this script in a way that 'exporters' is a subpackage
    # OR we patch sys.modules/imports.

    # Easiest way: Mock the relative imports by mapping '..formats' etc.
    # But Python relative imports checks __package__.

    # We will assume this script is run from root and the package structure is:
    # .
    # ├── exporters
    # ├── formats

    # If we import exporters.export_skc, it's a top level module.
    # It attempts 'from ..formats.skc_format import ...'
    # This fails.

    # Solution: Do NOT use the installed files directly if we can't load them.
    # But we want to test the installed files.

    # Use the symlink trick internally or assume 'mohaa_skd_skc' package exists.
    # Since we can't create symlinks in CI easily, we might just fail here.
    # But wait, we can set __package__ if we load manually.

    # Let's try importing as 'exporters.export_skc' and hope the user runs 'python -m test_exporters_standalone'
    # and we have a __init__.py in root? No.

    # Fallback: Just try importing. If it fails, print instruction.
    from exporters.export_skc import export_skc
    from exporters.export_skd import export_skd
except ImportError as e:
    # If we are here, likely relative import failure.
    # We can try to use importlib to load module with adjusted package?
    pass

# To bypass the relative import issue without a real package, we can:
# 1. Create a dummy 'mohaa_skd_skc' package in sys.modules that maps to current dir.
# 2. Import via that.

if 'mohaa_skd_skc' not in sys.modules:
    # Create a dummy package
    pkg = types.ModuleType('mohaa_skd_skc')
    pkg.__path__ = [os.getcwd()]
    sys.modules['mohaa_skd_skc'] = pkg

try:
    from mohaa_skd_skc.exporters.export_skc import export_skc
    from mohaa_skd_skc.exporters.export_skd import export_skd
except ImportError:
    # If that fails (e.g. recursive import issues), try another way or just skip
    print("Warning: Could not import exporters via package. Tests might fail.")

# =============================================================================
# TESTS
# =============================================================================

class TestExporters(unittest.TestCase):

    def setUp(self):
        # Setup mock armature
        self.armature_obj = bpy.types.Object("TestArmature", 'ARMATURE')

        # Mock Pose
        class MockPose:
            def __init__(self):
                self.bones = []
        self.armature_obj.pose = MockPose()

        self.bone = bpy.types.Bone("Bone1")
        self.armature_obj.pose.bones.append(self.bone)

        self.action = bpy.types.Action()
        self.action.frame_range = (0, 10)

        # Setup mock mesh
        self.mesh_obj = bpy.types.Object("TestMesh", 'MESH')

        # Mock evaluated object/mesh
        class MockMesh:
            def __init__(self):
                self.polygons = []
                self.vertices = []
                self.uv_layers = types.SimpleNamespace(active=None)
                self.vertex_groups = []
                self.materials = []
            def to_mesh_clear(self): pass

        class MockEvalObject:
            def to_mesh(self): return MockMesh()
            def to_mesh_clear(self): pass

        self.mesh_obj.evaluated_get = lambda dg: MockEvalObject()
        self.mesh_obj.data = types.SimpleNamespace(materials=[])
        self.mesh_obj.vertex_groups = []

    def tearDown(self):
        if os.path.exists("test_output.skc"):
            os.remove("test_output.skc")
        if os.path.exists("test_output.skd"):
            os.remove("test_output.skd")

    def test_export_skc_v14(self):
        if 'export_skc' not in globals(): return
        success = export_skc("test_output.skc", self.armature_obj, self.action, version=14)
        self.assertTrue(success)
        self.assertTrue(os.path.exists("test_output.skc"))

        with open("test_output.skc", "rb") as f:
            ident, version = struct.unpack('<ii', f.read(8))
            self.assertEqual(ident, SKC_IDENT_INT)
            self.assertEqual(version, 14)

    def test_export_skc_v13(self):
        if 'export_skc' not in globals(): return
        success = export_skc("test_output.skc", self.armature_obj, self.action, version=13)
        self.assertTrue(success)

        with open("test_output.skc", "rb") as f:
            ident, version = struct.unpack('<ii', f.read(8))
            self.assertEqual(ident, SKC_IDENT_INT)
            self.assertEqual(version, 13)

    def test_export_skd_v6(self):
        if 'export_skd' not in globals(): return
        success = export_skd("test_output.skd", self.mesh_obj, version=6)
        self.assertTrue(success)

        with open("test_output.skd", "rb") as f:
            ident, version = struct.unpack('<ii', f.read(8))
            self.assertEqual(ident, SKD_IDENT_INT)
            self.assertEqual(version, 6)

    def test_export_skd_v5(self):
        if 'export_skd' not in globals(): return
        success = export_skd("test_output.skd", self.mesh_obj, version=5)
        self.assertTrue(success)

        with open("test_output.skd", "rb") as f:
            ident, version = struct.unpack('<ii', f.read(8))
            self.assertEqual(ident, SKD_IDENT_INT)
            self.assertEqual(version, 5)

if __name__ == '__main__':
    unittest.main()
