import asyncio
import datetime

import discord

try:
	DISCORD_MODELS = (
		discord.Member, discord.Role, discord.Emoji, discord.Guild,
		discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel,
		discord.User, discord.Message, discord.Asset, discord.Client,
		discord.ClientUser
	)
	DISCORD_TYPES = (discord.Colour, discord.Permissions)
except ImportError:
	DISCORD_MODELS = ()
	DISCORD_TYPES = ()


class Convert:
	def __init__(self, filter_attrs: list = None, max_depth: int = 5):
		self.filter_attrs = filter_attrs or []
		self.max_depth = max_depth
	
	async def __call__(self, obj, filter_attrs=None, max_depth=None):
		current_max_depth = max_depth if max_depth is not None else self.max_depth
		current_filter_attrs = filter_attrs if filter_attrs is not None else self.filter_attrs
		
		def _serialize(obj, seen_stack, depth):
			# Base type checks
			if obj is None or isinstance(obj, (int, float, bool, str)):
				return obj
			
			if isinstance(obj, datetime.datetime):
				return obj.isoformat()
			
			if DISCORD_TYPES and isinstance(obj, DISCORD_TYPES):
				return str(obj)
			
			# Depth limit
			if depth >= current_max_depth:
				return str(obj) if not callable(obj) else "[Callable]"
			
			# Circular reference check
			obj_id = id(obj)
			if obj_id in seen_stack:
				return "<Circular Reference>"
			
			seen_stack.add(obj_id)
			result = None
			
			try:
				# Dict serialization
				if isinstance(obj, dict):
					result = {
						str(k): _serialize(v, seen_stack, depth + 1)
						for k, v in obj.items()
					}
				# List/iterable serialization
				elif not (DISCORD_MODELS and isinstance(obj, DISCORD_MODELS)):
					try:
						result = [_serialize(item, seen_stack, depth + 1) for item in obj]
					except TypeError:
						pass
				
				# Object attribute serialization
				if result is None:
					result = {}
					for attr_name in dir(obj):
						if attr_name.startswith('_') or attr_name in current_filter_attrs:
							continue
						if depth > 1 and attr_name in ('members', 'roles', 'channels'):
							continue
						
						try:
							value = getattr(obj, attr_name)
							if not callable(value):
								result[attr_name] = _serialize(value, seen_stack, depth + 1)
						except Exception:
							pass
			finally:
				seen_stack.discard(obj_id)
			
			return result
		
		return await asyncio.to_thread(_serialize, obj, set(), 0)

# object for messages
convert1 = Convert(
	filter_attrs = [
		'guild', 'channel', 'mutual_guilds',
		'call', 'jump_url', 'colour',
		'accent_colour', 'DEFAULT_VALUE', 'VALID_FLAGS',
		'BASE', 'key', 'role_subscription',
		'clean_content', 'value', 'raw_role_mentions',
		'failed_to_mention_some_roles_in_thread',
		'role_mentions', 'raw_mentions',
		'message_snapshots', 'nonce', 'system_content',
		'purchase_notification', 'tts', 'application',
		'application_id', 'accent_color',
		'avatar_decoration_sku_id', 'top_role',
		'client_status', 'default_avatar', 'category',
		'discriminator', 'dm_settings_upsell_acknowledged',
		'identity_enabled', 'roles', 'channel_mentions',
		'mention_everyone', 'pinned_at', 'pinned',
		'desktop_status', 'pending', 'web_status', 'channels',
		'activity', 'flags', 'public_flags'
	],
	max_depth = 5
)

# object for servers
convert2 = Convert(
	filter_attrs = [
		'me', 'BASE', 'key', 'DEFAULT_VALUE',
		'VALID_FLAGS', 'jump_url', 'categories',
		'voice_channels', 'text_channels'
	],
	max_depth = 5
)

# object for lists of servers
convert3 = Convert(
	filter_attrs = [
		'me', 'BASE', 'key', 'DEFAULT_VALUE',
		'VALID_FLAGS', 'jump_url', 'categories',
		'voice_channels', 'text_channels'
	],
	max_depth = 3
)

# object for users
convert4 = Convert(
	filter_attrs = [
		'BASE', 'key', 'DEFAULT_VALUE', 'VALID_FLAGS',
		'guild', 'mutual_guilds', 'status', 'web_status',
		'mobile_status', 'desktop_status', 'client_status',
		'colour'
	],
	max_depth = 5
)

# object for bot
convert5 = Convert(
	filter_attrs = [
		'cached_messages', 'cogs', 'extra_events',
		'users', 'user', 'token', 'soundboard_sounds',
		'help_command', 'command_mentions', 'commands',
		'stickers'
	],
	max_depth = 3
)
