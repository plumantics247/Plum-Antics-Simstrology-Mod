"""Big 3 private script runtime package."""

try:
    from .integration.bridge import register_debug_commands
    from .integration.mode_lock import sync_mode_lock_traits

    register_debug_commands()
    sync_mode_lock_traits()
except Exception:
    pass
