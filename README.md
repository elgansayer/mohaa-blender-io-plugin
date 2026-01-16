# MoHAA SKD/SKC Blender Add-on

Import and export Medal of Honor: Allied Assault skeletal models (.skd) and animations (.skc) in Blender 4.x.

## Supported Formats

| Format | Versions | Status |
|--------|----------|--------|
| SKD (Model) | v5, v6 | ✅ Full support |
| SKC (Animation) | v13, v14 | ✅ v13 works, v14 may have compressed files |

## Installation

### Quick Install (Linux)
```bash
ln -sf /home/elgan/dev/mohaa_skd_skc ~/.config/blender/4.3/scripts/addons/mohaa_skd_skc
```

### Manual Install
1. Copy `mohaa_skd_skc` folder to Blender's addons directory:
   - **Linux**: `~/.config/blender/4.x/scripts/addons/`
   - **Windows**: `%APPDATA%\Blender Foundation\Blender\4.x\scripts\addons\`
   - **macOS**: `~/Library/Application Support/Blender/4.x/scripts/addons/`

2. In Blender: **Edit > Preferences > Add-ons**
3. Search for "MoHAA" and enable the add-on

## Usage

### Import
- **File > Import > MoHAA Model (.skd)** - Import model with mesh and armature
- **File > Import > MoHAA Animation (.skc)** - Import animation (select armature first)

### Export  
- **File > Export > MoHAA Model (.skd)** - Export selected mesh/armature
- **File > Export > MoHAA Animation (.skc)** - Export armature animation

### Import Options
| Option | Description |
|--------|-------------|
| Scale | Global scale factor |
| Flip UVs | Flip V coordinate for game textures |
| Swap Y/Z | Alternative coordinate conversion |
| Textures Path | Folder to search for textures (auto-loads into materials) |

## Game Data Locations
```
~/.local/share/openmohaa/main/EXISTING-DATA/models/
~/.local/share/openmohaa/mainta/models/
~/.local/share/openmohaa/maintt/models/
```

## License
GPL-2.0 (same as OpenMoHAA)
