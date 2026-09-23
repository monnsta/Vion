"""
Tracking and analytics initialization module.

Instantiates and exports global singletons for activity logging, notifications,
and runtime metric tracking.
"""

from .ai_activity import Activity
from .notification import Notification
from .runtime import Runtime


activity = Activity()
notif = Notification()
runtime = Runtime()


__all__ = ("activity", "notif", "runtime")
