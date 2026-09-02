"""
Service implementations for specific text and structural file formats.

Provides concrete FileIO handlers for plain text, JSON (via orjson), and YAML files.
"""

from typing import cast, Any

from .base import BaseFileIO

orjson: Any = None
yaml: Any = None
SafeLoader: Any = None
SafeDumper: Any = None

HAS_ORJSON = False
HAS_YAML = False

try:
	import orjson
	HAS_ORJSON = True
except ImportError:
	pass

try:
	import yaml
	HAS_YAML = True
	try:
		from yaml import CSafeLoader as SafeLoader, CSafeDumper as SafeDumper
	except ImportError:
		from yaml import SafeLoader, SafeDumper
except ImportError:
	pass


class TEXT(BaseFileIO[str]):
	"""
	Plain text file I/O handler.
	"""

	def serialize(self, data: str) -> bytes:
		"""
		Serialize string to UTF-8 encoded bytes.

		Args:
			data: Target string payload.

		Returns:
			Encoded UTF-8 byte string.
		"""
		return (data or "").encode("utf-8")

	def deserialize(self, content: bytes) -> str:
		"""
		Decode UTF-8 bytes to plain string.

		Args:
			content: Raw input bytes.

		Returns:
			Decoded text string.
		"""
		return content.decode("utf-8") if content else ""

	def clone(self, data: str) -> str:
		"""
		Return string copy.

		Args:
			data: Input string.

		Returns:
			String value.
		"""
		return data or ""

	@property
	def default_empty(self) -> str:
		"""Default fallback empty string value."""
		return ""


class JSON(BaseFileIO[dict[str, Any]]):
	"""
	JSON file I/O handler powered by orjson.
	"""

	def serialize(self, data: dict[str, Any]) -> bytes:
		"""
		Serialize dictionary into formatted JSON bytes using orjson.

		Args:
			data: Input dictionary object.

		Returns:
			Formatted JSON byte string.
		"""
		return orjson.dumps(data if data is not None else {}, option=orjson.OPT_INDENT_2)

	def deserialize(self, content: bytes) -> dict[str, Any]:
		"""
		Deserialize JSON byte stream into dictionary.

		Args:
			content: JSON byte payload.

		Returns:
			Parsed dictionary structure.
		"""
		if not content or content.strip() == b"":
			return self.default_empty
		return cast(dict[str, Any], orjson.loads(content))

	def clone(self, data: dict[str, Any]) -> dict[str, Any]:
		"""
		Deep copy dictionary payload via orjson dump/load cycle.

		Args:
			data: Input dictionary object.

		Returns:
			Deep-copied dictionary object.
		"""
		if not data:
			return {}
		return cast(dict[str, Any], orjson.loads(orjson.dumps(data)))

	@property
	def default_empty(self) -> dict[str, Any]:
		"""Default fallback empty dictionary."""
		return {}


class YAML(BaseFileIO[dict[str, Any]]):
	"""
	YAML file I/O handler using PyYAML and optimized C-loaders/dumpers if available.
	"""

	def serialize(self, data: dict[str, Any]) -> bytes:
		"""
		Serialize dictionary payload into UTF-8 encoded YAML bytes.

		Args:
			data: Input dictionary object.

		Returns:
			Encoded YAML byte string.
		"""
		return yaml.dump(data if data is not None else {}, Dumper=SafeDumper, sort_keys=False).encode("utf-8")

	def deserialize(self, content: bytes) -> dict[str, Any]:
		"""
		Parse raw YAML bytes into dictionary payload.

		Args:
			content: YAML byte stream.

		Returns:
			Parsed dictionary structure.
		"""
		if not content or content.strip() == b"":
			return self.default_empty
		return cast(dict[str, Any], yaml.load(content.decode("utf-8"), Loader=SafeLoader) or {})

	def clone(self, data: dict[str, Any]) -> dict[str, Any]:
		"""
		Deep copy dictionary payload via orjson dump/load cycle.

		Args:
			data: Input dictionary object.

		Returns:
			Deep-copied dictionary object.
		"""
		if not data:
			return {}
		return cast(dict[str, Any], orjson.loads(orjson.dumps(data)))

	@property
	def default_empty(self) -> dict[str, Any]:
		"""Default fallback empty dictionary."""
		return {}
