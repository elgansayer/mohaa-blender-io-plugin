# SOLUTION: Fix Your Game Path Setting

## The Problem

Your game path is currently set to:
```
/home/elgan/.local/share/openmohaa/main/
```

But the `scripts/` and `textures/` directories are actually inside `EXISTING-DATA/`:
```
/home/elgan/.local/share/openmohaa/main/EXISTING-DATA/scripts/    ← shaders are here
/home/elgan/.local/share/openmohaa/main/EXISTING-DATA/textures/  ← textures are here
```

Without the correct path, the addon cannot find shaders or textures!

## The Fix

### Method 1: Change Addon Preferences (Recommended)

1. Open Blender
2. Go to: **Edit → Preferences → Add-ons**
3. Search for: **MoHAA**
4. Change **Game Data Path** to:
   ```
   /home/elgan/.local/share/openmohaa/main/EXISTING-DATA/
   ```
5. Click away to save
6. Try importing again

### Method 2: Specify Path on Import

When importing an SKD file:
1. File → Import → MoHAA SKD (.skd)
2. In the import dialog (bottom left), expand the options
3. Set **Textures Path** to:
   ```
   /home/elgan/.local/share/openmohaa/main/EXISTING-DATA/
   ```

## Verify It's Working

Run the debug script I created:
1. Open Blender
2. Switch to "Scripting" workspace
3. Open: `/home/elgan/dev/mohaa_skd_skc/DEBUG_RUN_IN_BLENDER.py`
4. Click "Run Script"
5. Check the console output

It should show:
```
✓ Addon preferences found
  Game path: '/home/elgan/.local/share/openmohaa/main/EXISTING-DATA/'
```

Then when you import, you should see textures load!
