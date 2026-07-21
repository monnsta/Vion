import asyncio
import datetime
import logging
import sys
import warnings

import discord

try:
	import yaml
except ImportError:
	yaml = None


log = logging.getLogger(__name__)


if not yaml:
	log.critical("yaml is not installed, please install the required dependencies")
	sys.exit(10)

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
		filter_attrs: list | None = None,
		max_depth: int = 5,
		max_list_len: int = 25,
		ignore_none: bool = True,
		ignore_empty: bool = True,
		ignore_false: bool = True,
		deduplicate: bool = True,
		flatten: bool = False,
		output_format: str = "dict"
	):
		self.filter_attrs = set(filter_attrs or [])
		self.max_depth = max_depth
		self.max_list_len = max_list_len
		self.ignore_none = ignore_none
		self.ignore_empty = ignore_empty
		self.ignore_false = ignore_false
		self.deduplicate = deduplicate
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

	def _deduplicate_dict(self, data, seen_ids: set | None = None):
		if seen_ids is None:
			seen_ids = set()

		if isinstance(data, dict):
			obj_id = data.get("id")
			if obj_id is not None and isinstance(obj_id, int):
				if obj_id in seen_ids:
					ref = {"id": obj_id, "$ref": True}
					if "name" in data:
						ref["name"] = data["name"]
					return ref
				seen_ids.add(obj_id)

			return {k: self._deduplicate_dict(v, seen_ids) for k, v in data.items()}

		elif isinstance(data, list):
			return [self._deduplicate_dict(item, seen_ids) for item in data]

		return data

	def _serialize(self, obj, seen_stack, depth):
		if self.ignore_none and obj is None:
			return None

		if isinstance(obj, (int, float, bool, str)):
			if self.ignore_empty and obj == "":
				return None
			if self.ignore_false and obj is False:
				return None
			return obj

		if isinstance(obj, datetime.datetime):
			return obj.isoformat()

		if DISCORD_TYPES and isinstance(obj, DISCORD_TYPES):
			return str(obj)

		if depth >= self.max_depth:
			if hasattr(obj, 'id'):
				return {"id": getattr(obj, 'id'), "$ref": True}
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
					for idx, item in enumerate(obj):
						if idx >= self.max_list_len:
							result.append(f"...<{len(obj) - self.max_list_len} items omitted>")
							break
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

					try:
						with warnings.catch_warnings():
							warnings.simplefilter("ignore", DeprecationWarning)
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

			if self.deduplicate and isinstance(raw_dict, (dict, list)):
				raw_dict = self._deduplicate_dict(raw_dict)

			if self.flatten and isinstance(raw_dict, dict):
				raw_dict = self._flatten_dict(raw_dict)

			if self.output_format == "yaml":
				return yaml.dump(raw_dict, default_flow_style=False, sort_keys=False) # type: ignore
			elif self.output_format == "json":
				return raw_dict

			return raw_dict

		result = await asyncio.to_thread(process)

		for k, v in original_state.items():
			setattr(self, k, v)

		return result


COMMON_FILTERS = [
	'BASE', 'key', 'DEFAULT_VALUE', 'VALID_FLAGS', 'jump_url', 'colour',
	'accent_colour', 'accent_color', 'avatar_decoration_sku_id', 'client_status',
	'desktop_status', 'web_status', 'mobile_status', 'mutual_guilds', 'flags',
	'public_flags', 'interaction', 'raw_mentions', 'raw_role_mentions', 'clean_content'
]

convert_message = Convert(
	filter_attrs=COMMON_FILTERS + ['call', 'role_subscription', 'value', 'nonce'],
	max_depth=5,
	output_format="json"
)

convert_guild = Convert(
	filter_attrs=COMMON_FILTERS + ['me'],
	max_depth=5,
	output_format="json"
)

convert_user = Convert(
	filter_attrs=COMMON_FILTERS + ['status', 'default_avatar', 'discriminator'],
	max_depth=3,
	output_format="json"
)

convert_bot = Convert(
	filter_attrs=COMMON_FILTERS + ['cached_messages', 'cogs', 'extra_events', 'token'],
	max_depth=4,
	output_format="json"
)
