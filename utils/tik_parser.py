"""
Parser for MoHAA .tik files (Tiki entity definitions)

Used to extract surface->shader mappings often defined in .tik files.
"""

import os
import re
from typing import Dict, Set, Optional

class TikParser:
    """Parses .tik files to extract surface shader mappings"""
    
    def __init__(self, game_path: str):
        self.game_path = game_path
        self.surface_map: Dict[str, str] = {}
        self._processed_files: Set[str] = set()
        
    def parse_file(self, filepath: str) -> None:
        """Parse a .tik or included .txt file"""
        # Normalize path
        filepath = os.path.abspath(filepath)
        
        if filepath in self._processed_files:
            return
            
        self._processed_files.add(filepath)
        
        if not os.path.exists(filepath):
            return

        try:
            with open(filepath, 'r', encoding='latin-1') as f:
                content = f.read()
            self._parse_content(content)
        except Exception as e:
            print(f"Warning: Could not parse TIK file {filepath}: {e}")

    def _parse_content(self, content: str) -> None:
        # Remove comments //
        content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
        
        lines = content.splitlines()
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # Handle surface command
            # Syntax: surface <name> shader <shader>
            # Regex handles optional quotes
            m_surf = re.search(r'surface\s+"?([^"\s]+)"?\s+shader\s+"?([^"\s]+)"?', line, re.IGNORECASE)
            if m_surf:
                surf_name = m_surf.group(1)
                shader_name = m_surf.group(2)
                self.surface_map[surf_name] = shader_name
                continue
                
            # Handle include
            # Syntax: $include path/to/file
            m_inc = re.search(r'\$include\s+"?([^"\s]+)"?', line, re.IGNORECASE)
            if m_inc and self.game_path:
                include_rel_path = m_inc.group(1)
                # Handle potential windows data
                include_rel_path = include_rel_path.replace('\\', '/')
                # Includes are usually relative to game root
                full_path = os.path.join(self.game_path, include_rel_path)
                if os.path.isfile(full_path):
                    self.parse_file(full_path)

    def get_mapping(self) -> Dict[str, str]:
        return self.surface_map


def find_tik_for_skd(skd_path: str) -> Optional[str]:
    """
    Find associated .tik file for an SKD model.
    Searches in the same directory and parent directory.
    """
    skd_dir = os.path.dirname(skd_path)
    skd_basename = os.path.basename(skd_path)
    base_name = os.path.splitext(skd_basename)[0]
    
    # Names to check (case variants for robustness)
    names_to_check = [base_name, base_name.lower()]
    
    # 1. Check same directory: model.tik
    for name in names_to_check:
        tik_name = name + ".tik"
        path = os.path.join(skd_dir, tik_name)
        if os.path.exists(path):
            return path
        
    # 2. Check parent directory
    # Often SKD is in models/type/modelname/modelname.skd
    # And TIK is in models/type/modelname.tik
    parent_dir = os.path.dirname(skd_dir)
    for name in names_to_check:
        tik_name = name + ".tik"
        path = os.path.join(parent_dir, tik_name)
        if os.path.exists(path):
            return path
        
    return None
