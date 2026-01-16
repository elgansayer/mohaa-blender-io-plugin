"""
Shader Parser for MoHAA/Quake3 shader files

Parses .shader files to build a mapping from shader names to texture paths.
Supports reading shaders from directories and .pk3 (ZIP) files.
"""

import os
import re
import zipfile
from typing import Dict, List, Optional, Tuple


class ShaderParser:
    """Parses Quake3/MoHAA shader files to extract shader->texture mappings"""
    
    def __init__(self, game_path: str):
        """
        Initialize parser with game data path.
        
        Args:
            game_path: Path to game data directory (e.g., .../main/EXISTING-DATA/)
        """
        self.game_path = game_path
        self.shaders: Dict[str, str] = {}  # shader_name -> texture_path
        self._texture_cache: Dict[str, str] = {}  # texture_path -> full_path
    
    def parse_all_shaders(self) -> Dict[str, str]:
        """
        Parse all shader files in the game path.
        
        Returns:
            Dictionary mapping shader names to texture paths
        """
        if not self.game_path or not os.path.isdir(self.game_path):
            return {}
        
        # Parse shaders from scripts/ directory
        scripts_dir = os.path.join(self.game_path, 'scripts')
        if os.path.isdir(scripts_dir):
            self._parse_shader_directory(scripts_dir)
        
        # Parse shaders from .pk3 files
        for filename in os.listdir(self.game_path):
            if filename.endswith('.pk3'):
                pk3_path = os.path.join(self.game_path, filename)
                self._parse_pk3_shaders(pk3_path)
        
        return self.shaders
    
    def _parse_shader_directory(self, scripts_dir: str) -> None:
        """Parse all .shader files in a directory"""
        for filename in os.listdir(scripts_dir):
            if filename.endswith('.shader'):
                filepath = os.path.join(scripts_dir, filename)
                try:
                    with open(filepath, 'r', encoding='latin-1') as f:
                        content = f.read()
                    self._parse_shader_content(content)
                except Exception as e:
                    print(f"Warning: Could not parse shader file {filepath}: {e}")
    
    def _parse_pk3_shaders(self, pk3_path: str) -> None:
        """Parse shader files from inside a .pk3 (ZIP) file"""
        try:
            with zipfile.ZipFile(pk3_path, 'r') as pk3:
                for name in pk3.namelist():
                    if name.startswith('scripts/') and name.endswith('.shader'):
                        try:
                            content = pk3.read(name).decode('latin-1')
                            self._parse_shader_content(content)
                        except Exception as e:
                            print(f"Warning: Could not parse shader {name} in {pk3_path}: {e}")
        except Exception as e:
            print(f"Warning: Could not open pk3 file {pk3_path}: {e}")
    
    def _parse_shader_content(self, content: str) -> None:
        """
        Parse shader file content and extract shader->texture mappings.
        
        Shader format:
        shader_name
        {
            qer_editorimage textures/path/to/texture.tga
            {
                map textures/path/to/texture.tga
            }
        }
        """
        # Remove comments
        content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
        
        # State machine parsing
        current_shader = None
        brace_depth = 0
        current_texture = None
        
        lines = content.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                i += 1
                continue
            
            # Check for opening brace
            if line == '{':
                brace_depth += 1
                i += 1
                continue
            
            # Check for closing brace
            if line == '}':
                if brace_depth == 1 and current_shader and current_texture:
                    # End of shader definition
                    self.shaders[current_shader] = current_texture
                brace_depth -= 1
                if brace_depth == 0:
                    current_shader = None
                    current_texture = None
                i += 1
                continue
            
            # Outside any shader - this is a shader name
            if brace_depth == 0 and not line.startswith('{'):
                current_shader = line.split()[0] if line.split() else None
                current_texture = None
                i += 1
                continue
            
            # Inside shader definition
            if brace_depth >= 1 and current_shader:
                # Look for qer_editorimage (preferred)
                if line.lower().startswith('qer_editorimage'):
                    parts = line.split(None, 1)
                    if len(parts) > 1:
                        current_texture = parts[1].strip()
                
                # Fallback to first 'map' directive
                elif line.lower().startswith('map ') and not current_texture:
                    parts = line.split(None, 1)
                    if len(parts) > 1:
                        tex = parts[1].strip()
                        # Ignore special maps
                        if not tex.startswith('$') and tex not in ['*white', '*black']:
                            current_texture = tex
            
            i += 1
    
    def find_texture(self, shader_or_texture: str) -> Optional[str]:
        """
        Find the actual texture file path for a shader name or texture path.
        
        Args:
            shader_or_texture: Shader name or direct texture path
            
        Returns:
            Full path to texture file, or None if not found
        """
        # Check cache first
        if shader_or_texture in self._texture_cache:
            return self._texture_cache[shader_or_texture]
        
        # Resolve shader to texture path
        texture_path = self.shaders.get(shader_or_texture, shader_or_texture)
        
        # Remove any leading slashes
        texture_path = texture_path.lstrip('/')
        
        # Try to find the actual file
        full_path = self._find_texture_file(texture_path)
        
        if full_path:
            self._texture_cache[shader_or_texture] = full_path
        
        return full_path
    
    def _find_texture_file(self, texture_path: str) -> Optional[str]:
        """Find texture file in game directories or pk3 files"""
        if not self.game_path:
            return None
        
        # Extensions to try
        extensions = ['', '.tga', '.dds', '.jpg', '.jpeg', '.png', '.bmp']
        
        # First try direct path in game directory
        for ext in extensions:
            full_path = os.path.join(self.game_path, texture_path + ext)
            if os.path.isfile(full_path):
                return full_path
        
        # Try without extension if path already has one
        base, existing_ext = os.path.splitext(texture_path)
        if existing_ext:
            full_path = os.path.join(self.game_path, texture_path)
            if os.path.isfile(full_path):
                return full_path
        
        # Search in pk3 files
        result = self._extract_from_pk3(texture_path)
        if result:
            return result
        
        return None
    
    def _extract_from_pk3(self, texture_path: str) -> Optional[str]:
        """
        Extract texture from pk3 file to temp directory and return path.
        
        Returns the path to the extracted file, or None if not found.
        """
        import tempfile
        
        if not os.path.isdir(self.game_path):
            return None
        
        # Normalize path
        texture_path = texture_path.replace('\\', '/')
        base, ext = os.path.splitext(texture_path)
        
        # File patterns to search for
        search_patterns = [texture_path]
        if not ext:
            search_patterns.extend([
                texture_path + '.tga',
                texture_path + '.dds',
                texture_path + '.jpg',
                texture_path + '.png'
            ])
        
        # Search pk3 files
        for filename in os.listdir(self.game_path):
            if filename.endswith('.pk3'):
                pk3_path = os.path.join(self.game_path, filename)
                try:
                    with zipfile.ZipFile(pk3_path, 'r') as pk3:
                        for pattern in search_patterns:
                            # Try exact match
                            if pattern in pk3.namelist():
                                # Extract to temp
                                temp_dir = tempfile.mkdtemp(prefix='mohaa_tex_')
                                pk3.extract(pattern, temp_dir)
                                return os.path.join(temp_dir, pattern)
                            
                            # Try case-insensitive
                            pattern_lower = pattern.lower()
                            for name in pk3.namelist():
                                if name.lower() == pattern_lower:
                                    temp_dir = tempfile.mkdtemp(prefix='mohaa_tex_')
                                    pk3.extract(name, temp_dir)
                                    return os.path.join(temp_dir, name)
                except Exception:
                    continue
        
        return None


def get_shader_texture_map(game_path: str) -> Dict[str, str]:
    """
    Convenience function to parse all shaders and return the mapping.
    
    Args:
        game_path: Path to game data directory
        
    Returns:
        Dictionary mapping shader names to texture paths
    """
    parser = ShaderParser(game_path)
    return parser.parse_all_shaders()
