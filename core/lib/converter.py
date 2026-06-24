import asyncio
import datetime
import yaml
import json

import discord


try:
	DISCORD_MODELS = (
		discord.Member, discord.Role, discord.Emoji, discord.Guild,
		discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel,
		discord.User, discord.Message, discord.Asset, discord.Client,
		discord.ClientUser, discord.app_commands.Command
	)
	DISCORD_TYPES = (discord.Colour, discord.Permissions)
except ImportError:
	DISCORD_MODELS = ()
	DISCORD_TYPES = ()


class Convert:
	def __init__(
		self, 
		filter_attrs: list = None, 
		max_depth: int = 5,
		ignore_none: bool = True,
		ignore_empty: bool = True,
		flatten: bool = False,
		output_format: str = "dict"
	):
		self.filter_attrs = set(filter_attrs or [])
		self.max_depth = max_depth
		self.ignore_none = ignore_none
		self.ignore_empty = ignore_empty
		self.flatten = flatten
		self.output_format = output_format

	def _flatten_dict(self, d: dict, parent_key: str = '', sep: str = '_') -> dict:
		items = []
		for k, v in d.items():
			new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)
			if isinstance(v, dict):
				items.extend(self._flatten_dict(v, new_key, sep=sep).items())
			else:
				items.append((new_key, v))
		return dict(items)

	def _serialize(self, obj, seen_stack, depth):
		if self.ignore_none and obj is None:
			return None

		if isinstance(obj, (int, float, bool, str)):
			if self.ignore_empty and obj == "":
				return None
			return obj

		if isinstance(obj, datetime.datetime):
			return obj.isoformat()

		if DISCORD_TYPES and isinstance(obj, DISCORD_TYPES):
			return str(obj)

		if hasattr(obj, 'url') and isinstance(getattr(obj, 'url'), str):
			return getattr(obj, 'url')

		if depth >= self.max_depth:
			return str(obj) if not callable(obj) else None

		obj_id = id(obj)
		if obj_id in seen_stack:
			return "<Circular>"

		seen_stack.add(obj_id)
		result = None

		try:
			if isinstance(obj, dict):
				result = {}
				for k, v in obj.items():
					val = self._serialize(v, seen_stack, depth + 1)
					if self.ignore_none and val is None: continue
					if self.ignore_empty and val in ({}, []): continue
					result[str(k)] = val

			elif not (DISCORD_MODELS and isinstance(obj, DISCORD_MODELS)):
				try:
					result = []
					for item in obj:
						val = self._serialize(item, seen_stack, depth + 1)
						if self.ignore_none and val is None: continue
						if self.ignore_empty and val in ({}, []): continue
						result.append(val)
				except TypeError:
					pass

			if result is None:
				result = {}
				for attr_name in dir(obj):
					if attr_name.startswith('_') or attr_name in self.filter_attrs:
						continue

					if depth > 1 and attr_name in ('members', 'roles', 'channels', 'guilds'):
						continue

					try:
						value = getattr(obj, attr_name)
						if callable(value):
							continue

						serialized_val = self._serialize(value, seen_stack, depth + 1)

						if self.ignore_none and serialized_val is None:
							continue
						if self.ignore_empty and serialized_val in ({}, [], ""):
							continue

						result[attr_name] = serialized_val
					except Exception:
						pass
		finally:
			seen_stack.discard(obj_id)

		return result

	async def __call__(self, obj, **kwargs):
		original_state = {k: getattr(self, k) for k in kwargs if hasattr(self, k)}
		for k, v in kwargs.items():
			if hasattr(self, k):
				setattr(self, k, v)

		def process():
			raw_dict = self._serialize(obj, set(), 0)

			if self.flatten and isinstance(raw_dict, dict):
				raw_dict = self._flatten_dict(raw_dict)

			if self.output_format == "yaml":
				return yaml.dump(raw_dict, default_flow_style=False, sort_keys=False)
			elif self.output_format == "json":
				return json.dumps(raw_dict)

			return raw_dict

		result = await asyncio.to_thread(process)

		for k, v in original_state.items():
			setattr(self, k, v)

		return result


convert_message = Convert(
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
	max_depth = 5,
	output_format = "yaml"
)

convert_guild = Convert(
	filter_attrs = [
		'me', 'BASE', 'key', 'DEFAULT_VALUE',
		'VALID_FLAGS', 'jump_url', 'categories',
		'voice_channels', 'text_channels'
	],
	max_depth = 5,
	output_format = "yaml"
)

convert_user = Convert(
	filter_attrs = [
		'BASE', 'key', 'DEFAULT_VALUE', 'VALID_FLAGS',
		'guild', 'mutual_guilds', 'status', 'web_status',
		'mobile_status', 'desktop_status', 'client_status',
		'colour'
	],
	max_depth = 5,
	output_format = "yaml"
)

convert_bot = Convert(
	filter_attrs = [
		'cached_messages', 'cogs', 'extra_events',
		'users', 'user', 'token', 'soundboard_sounds',
		'help_command', 'command_mentions', 'commands',
		'stickers'
	],
	max_depth = 3,
	output_format = "yaml"
)
