bl_info = {
    "name": "Fast Viewport Alignment",
    "description": "Instantly snap 3D viewport to the nearest orthographic axis view",
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