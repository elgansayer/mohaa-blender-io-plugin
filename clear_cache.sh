#!/bin/bash
# Clear Python bytecode cache for the addon

killall -9 blender
pkill -f blender
echo "Clearing Python cache files..."
find /home/elgan/dev/mohaa_skd_skc -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find /home/elgan/dev/mohaa_skd_skc -name "*.pyc" -delete 2>/dev/null
echo "✓ Cache cleared!"
echo ""
echo "Now restart Blender for changes to take effect."
xclip -selection clipboard -i < /home/elgan/.local/share/openmohaa/main/EXISTING-DATA/models/furniture/wardrobe/wardrobe.skd
blender
# copy /home/elgan/.local/share/openmohaa/main/EXISTING-DATA/models/furniture/wardrobe/wardrobe.skd to clipboard
