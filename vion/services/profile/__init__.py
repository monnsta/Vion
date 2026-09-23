"""
Profile management package initialization.

Instantiates and exports server and user profile manager singletons.
"""

from .service import Server, User


server = Server()
user = User()


__all__ = ("server", "user")
