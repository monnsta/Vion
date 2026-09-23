"""
Core object serialization and conversion module.

Provides recursive dictionary, list, and object transformation into JSON-safe dictionaries or YAML.
"""

import asyncio
import datetime
import warnings
from itertools import islice

import discord
import yaml


try:
	DISCORD_MODELS = (
		discord.Member,
		discord.Role,
		discord.Emoji,
		discord.Guild,
		discord.TextChannel,
		discord.VoiceChannel,
		discord.CategoryChannel,
		discord.User,
		discord.Message,
		discord.Asset,
		discord.Client,
		discord.ClientUser,
		discord.app_commands.Command,
	)
	DISCORD_TYPES = (discord.Colour, discord.Permissions)
except ImportError:
	DISCORD_MODELS = ()
	DISCORD_TYPES = ()


class Convert:
	"""
	Configurable recursive serializer for complex Python and Discord objects.

	Attributes:
		filter_attrs: Set of attribute names to ignore during serialization.
		max_depth: Maximum default recursion depth allowed.
		attr_depths: Dictionary mapping specific attribute names to customized depth limits.
		type_depths: Dictionary mapping object types to customized depth limits.
		max_list_len: Maximum number of elements to process per sequence.
		ignore_none: Whether to omit None values from serialized output.
		ignore_empty: Whether to omit empty containers and empty strings.
		ignore_false: Whether to omit False boolean values.
		deduplicate: Whether to substitute repeated Discord ID instances with reference markers.
		flatten: Whether to flatten nested dictionary key structures with underscores.
		output_format: Output format choice ('dict' or 'yaml').
	"""

	def __init__(
		self,
		filter_attrs: list | None = None,
		max_depth: int = 5,
		attr_depths: dict[str, int] | None = None,
		type_depths: dict[type, int] | None = None,
		max_list_len: int = 25,
		ignore_none: bool = True,
		ignore_empty: bool = True,
		ignore_false: bool = True,
		deduplicate: bool = True,
		flatten: bool = False,
		output_format: str = "dict",
	):
		"""
		Initialize Convert serializer instance with target rules and filters.

		Args:
			filter_attrs: Optional list of attribute names to skip.
			max_depth: General recursion depth limit. Defaults to 5.
			attr_depths: Optional depth overrides keyed by attribute name.
			type_depths: Optional depth overrides keyed by object type.
			max_list_len: Maximum list/iterable items to serialize. Defaults to 25.
			ignore_none: Strip None values if True. Defaults to True.
			ignore_empty: Strip empty dictionaries, lists, and strings if True. Defaults to True.
			ignore_false: Strip False values if True. Defaults to True.
			deduplicate: Replace duplicate entity IDs with reference object if True. Defaults to True.
			flatten: Flatten nested dictionary output if True. Defaults to False.
			output_format: String format type ('dict' or 'yaml'). Defaults to "dict".
		"""
		self.filter_attrs = set(filter_attrs or [])
		self.max_depth = max_depth
		self.attr_depths = attr_depths or {}
		self.type_depths = type_depths or {}
		self.max_list_len = max_list_len
		self.ignore_none = ignore_none
		self.ignore_empty = ignore_empty
		self.ignore_false = ignore_false
		self.deduplicate = deduplicate
		self.flatten = flatten
		self.output_format = output_format

	def _flatten_dict(self, d: dict, parent_key: str = "", sep: str = "_") -> dict:
		"""
		Recursively flatten a nested dictionary hierarchy.

		Args:
			d: Input dictionary.
			parent_key: Accumulated parent key prefix.
			sep: Key join separator character. Defaults to '_'.

		Returns:
			Flattened single-level dictionary.
		"""

		def _yield_flat(curr_dict, curr_key):
			for k, v in curr_dict.items():
				new_key = f"{curr_key}{sep}{k}" if curr_key else str(k)
				if isinstance(v, dict):
					yield from _yield_flat(v, new_key)
				else:
					yield new_key, v

		return dict(_yield_flat(d, parent_key))

	async def __call__(self, obj, **kwargs):
		"""
		Asynchronously execute object serialization in a background thread.

		Args:
			obj: Target object or payload to serialize.
			**kwargs: Temporary configuration overrides for this execution run.

		Returns:
			Serialized dictionary structure or formatted YAML string.
		"""
		config = {
			"filter_attrs": kwargs.get("filter_attrs", self.filter_attrs),
			"max_depth": kwargs.get("max_depth", self.max_depth),
			"attr_depths": kwargs.get("attr_depths", self.attr_depths),
			"type_depths": kwargs.get("type_depths", self.type_depths),
			"max_list_len": kwargs.get("max_list_len", self.max_list_len),
			"ignore_none": kwargs.get("ignore_none", self.ignore_none),
			"ignore_empty": kwargs.get("ignore_empty", self.ignore_empty),
			"ignore_false": kwargs.get("ignore_false", self.ignore_false),
			"deduplicate": kwargs.get("deduplicate", self.deduplicate),
			"flatten": kwargs.get("flatten", self.flatten),
			"output_format": kwargs.get("output_format", self.output_format),
		}

		def process():
			seen_mem = set()
			seen_discord_ids = set()

			def _serialize(o, depth, current_max_depth=None):
				effective_max_depth = (
					current_max_depth
					if current_max_depth is not None
					else config["max_depth"]
				)

				# Check type-based depth overrides
				if config["type_depths"]:
					for target_type, target_depth in config["type_depths"].items():
						if isinstance(o, target_type):
							effective_max_depth = max(effective_max_depth, target_depth)
							break

				if config["ignore_none"] and o is None:
					return None

				if isinstance(o, (int, float, bool, str)):
					if config["ignore_empty"] and o == "":
						return None
					if config["ignore_false"] and o is False:
						return None
					return o

				if isinstance(o, datetime.datetime):
					return o.isoformat()

				if DISCORD_TYPES and isinstance(o, DISCORD_TYPES):
					return str(o)

				if config["deduplicate"] and hasattr(o, "id") and isinstance(o.id, int):
					if o.id in seen_discord_ids:
						ref = {"id": o.id, "$ref": True}
						if hasattr(o, "name"):
							try:
								ref["name"] = o.name
							except Exception:
								pass
						return ref
					seen_discord_ids.add(o.id)

				if depth >= effective_max_depth:
					if hasattr(o, "id"):
						return {"id": getattr(o, "id"), "$ref": True}
					if isinstance(o, (list, tuple, set, dict)):
						return "<Max Depth Reached>"
					return str(o) if not callable(o) else None

				mem_id = id(o)
				if mem_id in seen_mem:
					return "<Seen>"

				seen_mem.add(mem_id)
				result = None

				if isinstance(o, dict):
					result = {}
					for k, v in o.items():
						next_depth_limit = config["attr_depths"].get(
							str(k), effective_max_depth
						)
						val = _serialize(v, depth + 1, next_depth_limit)
						if config["ignore_none"] and val is None:
							continue
						if config["ignore_empty"] and val in ({}, [], ""):
							continue
						result[str(k)] = val

				elif not (DISCORD_MODELS and isinstance(o, DISCORD_MODELS)):
					try:
						iterator = iter(o)
						result = []
						for idx, item in enumerate(
							islice(iterator, config["max_list_len"] + 1)
						):
							if idx >= config["max_list_len"]:
								result.append("...<items omitted>")
								break
							val = _serialize(item, depth + 1, effective_max_depth)
							if config["ignore_none"] and val is None:
								continue
							if config["ignore_empty"] and val in ({}, [], ""):
								continue
							result.append(val)
					except TypeError:
						pass

				if result is None:
					result = {}
					for attr_name in dir(o):
						if (
							attr_name.startswith("_")
							or attr_name in config["filter_attrs"]
						):
							continue

						try:
							with warnings.catch_warnings():
								warnings.simplefilter("ignore", DeprecationWarning)
								value = getattr(o, attr_name)

							if callable(value):
								continue

							next_depth_limit = config["attr_depths"].get(
								attr_name, effective_max_depth
							)
							serialized_val = _serialize(
								value, depth + 1, next_depth_limit
							)

							if config["ignore_none"] and serialized_val is None:
								continue
							if config["ignore_empty"] and serialized_val in (
								{},
								[],
								"",
							):
								continue

							result[attr_name] = serialized_val
						except Exception:
							pass

				return result

			raw_dict = _serialize(obj, 0)

			if config["flatten"] and isinstance(raw_dict, dict):
				raw_dict = self._flatten_dict(raw_dict)

			if config["output_format"] == "yaml":
				return yaml.dump(raw_dict, default_flow_style=False, sort_keys=False)  # type: ignore

			return raw_dict

		return await asyncio.to_thread(process)
