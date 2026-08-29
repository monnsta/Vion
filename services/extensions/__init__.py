from .local_ext import Extension, map_command_mentions
from .guild_ext import ServerCogManager, GuildCog


extension = Extension()
server_cog = ServerCogManager()


__all__ = (
	'extension', 'map_command_mentions',
	'server_cog', 'GuildCog'
)
