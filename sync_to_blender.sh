#!/bin/bash
# Sync dev version to Blender's installed addon directory

DEV_DIR="/home/elgan/dev/mohaa_skd_skc"
BLENDER_ADDON_DIR="/home/elgan/.config/blender/4.3/scripts/addons/mohaa_skd_skc"

echo "=========================================="
echo "SYNCING DEV VERSION TO BLENDER"
echo "=========================================="
echo ""
echo "From: $DEV_DIR"
echo "To:   $BLENDER_ADDON_DIR"
echo ""

if [ ! -d "$BLENDER_ADDON_DIR" ]; then
    echo "ERROR: Blender addon directory not found!"
    echo "The addon may not be installed."
    exit 1
fi

echo "Copying files..."
rsync -av --exclude='*.pyc' --exclude='__pycache__' --exclude='.git' \
    --exclude='debug_*.py' --exclude='test_*.py' --exclude='*.sh' \
    "$DEV_DIR/" "$BLENDER_ADDON_DIR/"

echo ""
echo "✓ Files synced successfully!"
echo ""
echo "=========================================="
echo "NEXT STEPS:"
echo "=========================================="
echo "1. Restart Blender (if it's open)"
echo "2. The addon will now use the updated code"
echo "=========================================="
