import bpy
import math
import time
from mathutils import Vector, Quaternion, Matrix
from bpy.props import EnumProperty
from bpy.types import AddonPreferences
import rna_keymap_ui

# Global state to track across operator instances
g_monitor_running = False
g_last_ortho_time = 0
g_is_orbiting = False
g_last_view_change_time = 0
g_manual_orbit_detected = False

# Store keymap items for cleanup
addon_keymaps = []

# ============================================================================
# PREFERENCES
# ============================================================================

class ViewportAxisSnapPreferences(AddonPreferences):
    bl_idname = __package__
    
    def draw(self, context):
        layout = self.layout
        
        layout.label(text="Fast Viewport Alignment Settings")
        layout.separator()
        
        # Keymap section with proper editable interface
        wm = context.window_manager
        kc = wm.keyconfigs.user
        
        col = layout.column()
        col.label(text="Keymaps:")
        
        # Find our keymap in the addon keyconfigs
        for km, kmi in addon_keymaps:
            # Get the user keymap (this is where user modifications are stored)
            km_user = kc.keymaps.get(km.name)
            if km_user:
                # Find our specific keymap item
                for kmi_user in km_user.keymap_items:
                    if kmi_user.idname == "view3d.snap_to_nearest_axis":
                        # Draw the editable keymap item
                        rna_keymap_ui.draw_kmi(
                            ["ADDON", "USER", "DEFAULT"], 
                            kc, 
                            km_user, 
                            kmi_user, 
                            col, 
                            0
                        )
                        break

# ============================================================================
# CORE FUNCTIONALITY
# ============================================================================

def get_closest_axis_view(context):
    """
    Determine which axis view is closest to the current view.
    Returns a view type string for use with bpy.ops.view3d.view_axis()
    """
    region_3d = context.space_data.region_3d
    view_matrix = region_3d.view_matrix
    
    # Get the view direction (opposite of view matrix Z axis since camera looks down -Z)
    view_dir = -Vector(view_matrix[2][:3])
    
    # Standard view directions in world space
    views = [
        (Vector((0, 0, 1)), "BOTTOM", "TOP"),     # Z axis
        (Vector((0, 1, 0)), "FRONT", "BACK"),     # Y axis  
        (Vector((1, 0, 0)), "LEFT", "RIGHT"),     # X axis
    ]
    
    # Find which axis has the greatest alignment
    max_alignment = -1.0
    closest_view = "TOP"  # Default
    
    for axis, pos_view, neg_view in views:
        # Use abs to find which axis we're most aligned with
        alignment = abs(view_dir.dot(axis))
        
        if alignment > max_alignment:
            max_alignment = alignment
            
            # Now check the sign to determine which side of the axis we're looking from
            dot_product = view_dir.dot(axis)
            
            if dot_product > 0:
                closest_view = pos_view  # Positive side of the axis
            else:
                closest_view = neg_view  # Negative side of the axis
    
    return closest_view

def snap_to_axis_view(context, view_name):
    """
    Snap to a predefined axis view using Blender's built-in view alignment operators
    """
    global g_last_view_change_time
    
    # Record when we're making a view change
    g_last_view_change_time = time.time()
    
    # Use Blender's built-in view align operators
    bpy.ops.view3d.view_axis(type=view_name)
    
    # Switch to orthographic mode
    context.space_data.region_3d.view_perspective = 'ORTHO'
    
    # Update the global time tracker
    global g_last_ortho_time
    g_last_ortho_time = time.time()

# ============================================================================
# OPERATORS
# ============================================================================

class VIEW3D_OT_viewport_rotation_monitor(bpy.types.Operator):
    """Monitor viewport rotation and switch to perspective view"""
    bl_idname = "view3d.viewport_rotation_monitor"
    bl_label = "Viewport Rotation Monitor"
    bl_options = {'INTERNAL'}
    
    _timer = None
    _previous_rotation = None
    _previous_perspective = None
    
    def modal(self, context, event):
        global g_monitor_running, g_last_ortho_time, g_is_orbiting, g_last_view_change_time, g_manual_orbit_detected
        
        # Detect start of orbit operation (middle mouse without modifiers)
        if event.type == 'MIDDLEMOUSE' and event.value == 'PRESS':
            # Check if no modifiers are pressed (pure orbiting, not panning or zooming)
            if not (event.shift or event.ctrl or event.alt or event.oskey):
                g_is_orbiting = True
                g_manual_orbit_detected = False  # Reset manual orbit detection
        
        # Middle mouse button released - end of orbit
        elif event.type == 'MIDDLEMOUSE' and event.value == 'RELEASE':
            g_is_orbiting = False
            # Don't reset g_manual_orbit_detected here - let it persist briefly
        
        # Handle mouse movement ONLY if we're in an orbit operation
        elif event.type == 'MOUSEMOVE' and g_is_orbiting:
            # Mark that we've detected actual manual orbiting (mouse movement while middle mouse is down)
            g_manual_orbit_detected = True
            
            region_3d = context.space_data.region_3d
            
            # If we're in ortho mode and actively orbiting, switch to perspective
            if region_3d.view_perspective == 'ORTHO':
                current_time = time.time()
                # Only switch if we're not within the delay period after setting ortho
                # AND not within delay period after any view change (pie menu, gizmo, etc.)
                if (current_time - g_last_ortho_time > 0.3 and 
                    current_time - g_last_view_change_time > 2.0):  # Even longer delay for view changes
                    region_3d.view_perspective = 'PERSP'
                    g_is_orbiting = False  # Reset orbiting flag
        
        # Regular timer checks for rotation changes
        elif event.type == 'TIMER':
            if context.space_data and context.space_data.type == 'VIEW_3D':
                region_3d = context.space_data.region_3d
                current_rotation = region_3d.view_rotation.copy()
                current_perspective = region_3d.view_perspective
                
                # Detect if perspective mode changed to ortho (from pie menu or gizmo)
                if (self._previous_perspective is not None and 
                    self._previous_perspective == 'PERSP' and 
                    current_perspective == 'ORTHO'):
                    # Update the view change time to prevent interference
                    g_last_view_change_time = time.time()
                    g_manual_orbit_detected = False  # Reset since this is a programmatic change
                
                # Check if rotation has changed
                if self._previous_rotation is not None:
                    # Calculate the difference between quaternions
                    diff = self._previous_rotation.rotation_difference(current_rotation)
                    angle = diff.angle
                    
                    # Only switch to perspective if:
                    # 1. We detected actual manual orbiting (mouse movement during middle mouse drag)
                    # 2. Rotation changed significantly
                    # 3. We're currently orbiting
                    # 4. Enough time has passed since ortho was set
                    # 5. Enough time has passed since any view change
                    if (angle > 0.03 and 
                        g_is_orbiting and 
                        g_manual_orbit_detected):  # Only if we detected actual manual orbiting
                        
                        current_time = time.time()
                        if (region_3d.view_perspective == 'ORTHO' and 
                            current_time - g_last_ortho_time > 0.3 and
                            current_time - g_last_view_change_time > 2.0):  # Longer delay
                            region_3d.view_perspective = 'PERSP'
                            g_is_orbiting = False  # Reset orbiting flag
                            g_manual_orbit_detected = False  # Reset detection
                
                self._previous_rotation = current_rotation
                self._previous_perspective = current_perspective
        
        return {'PASS_THROUGH'}
    
    def execute(self, context):
        global g_monitor_running, g_is_orbiting, g_manual_orbit_detected
        g_monitor_running = True
        g_is_orbiting = False
        g_manual_orbit_detected = False
        
        region_3d = context.space_data.region_3d
        self._previous_rotation = region_3d.view_rotation.copy()
        self._previous_perspective = region_3d.view_perspective
        
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def cancel(self, context):
        global g_monitor_running
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
        g_monitor_running = False

class VIEW3D_OT_snap_to_nearest_axis(bpy.types.Operator):
    """Snap viewport to nearest axis view and switch to orthographic"""
    bl_idname = "view3d.snap_to_nearest_axis"
    bl_label = "Snap to Nearest Axis (Ortho)"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        global g_monitor_running, g_is_orbiting, g_manual_orbit_detected
        
        # Reset orbiting state when snapping
        g_is_orbiting = False
        g_manual_orbit_detected = False
        
        # Start the rotation monitor if it's not running
        if not g_monitor_running:
            bpy.ops.view3d.viewport_rotation_monitor()
        
        # Get the closest standard view
        view_name = get_closest_axis_view(context)
        
        # Snap to the closest axis view
        snap_to_axis_view(context, view_name)
        
        # Log success
        self.report({'INFO'}, f"Snapped to {view_name} view (Orthographic)")
        
        return {'FINISHED'}

# ============================================================================
# KEYMAP REGISTRATION
# ============================================================================

def register_keymaps():
    """Register keymaps"""
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    
    if kc:
        # 3D View keymap
        km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
        kmi = km.keymap_items.new("view3d.snap_to_nearest_axis", 'SPACE', 'PRESS', alt=True)
        addon_keymaps.append((km, kmi))

def unregister_keymaps():
    """Unregister keymaps"""
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

# ============================================================================
# REGISTRATION
# ============================================================================

classes = (
    ViewportAxisSnapPreferences,
    VIEW3D_OT_viewport_rotation_monitor,
    VIEW3D_OT_snap_to_nearest_axis,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
