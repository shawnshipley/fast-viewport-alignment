bl_info = {
    "name": "Fast Viewport Alignment",
    "description": "Quickly snap viewport to nearest aligned axis with a single shortcut",
    "author": "Shawn Shipley",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "category": "3D View",
    "doc_url": "https://github.com/shawnshipley/fast-viewport-alignment",
    "support": "Community"
}

from . import viewport

def register():
    viewport.register()
    viewport.register_keymaps()

def unregister():
    viewport.unregister_keymaps()
    viewport.unregister()

if __name__ == "__main__":
    register()