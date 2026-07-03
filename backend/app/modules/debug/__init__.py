"""Temporary debug endpoints for verifying the notification pipeline.

Registered only when ``settings.ENABLE_DEBUG_ENDPOINTS`` is true, and each route
additionally requires the project_manager role. Remove before GA if no longer
needed — nothing else in the app depends on this module.
"""
