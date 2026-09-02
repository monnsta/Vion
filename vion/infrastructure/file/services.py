from typing import cast, Any

from .base import BaseFileIO

orjson: Any = None
yaml: Any = None
SafeLoader: Any = None
SafeDumper: Any = None

try:
	import orjson

	try:
		import yaml
		try:
			from yaml import CSafeLoader as SafeLoader, CSafeDumper as SafeDumper
		except ImportError:
			from yaml import SafeLoader, SafeDumper
	except ImportError:
		pass
except ImportError:
	pass


class TEXT(BaseFileIO[str]):
	"""Plain text implementation."""
	def serialize(self, data: str) -> bytes:
		return (data or "").encode("utf-8")

	def deserialize(self, content: bytes) -> str:
		return content.decode("utf-8") if content else ""

	def clone(self, data: str) -> str:
		return data or ""

	@property
	def default_empty(self) -> str:
		return ""

class JSON(BaseFileIO[dict[str, Any]]):
	"""JSON implementation."""
	def serialize(self, data: dict[str, Any]) -> bytes:
		return orjson.dumps(data if data is not None else {}, option=orjson.OPT_INDENT_2)

	def deserialize(self, content: bytes) -> dict[str, Any]:
		if not content or content.strip() == b"":
			return self.default_empty
		return cast(dict[str, Any], orjson.loads(content))

	def clone(self, data: dict[str, Any]) -> dict[str, Any]:
		if not data: return {}
		return cast(dict[str, Any], orjson.loads(orjson.dumps(data)))

	@property
	def default_empty(self) -> dict[str, Any]:
		return {}

class YAML(BaseFileIO[dict[str, Any]]):
	"""YAML implementation."""
	def serialize(self, data: dict[str, Any]) -> bytes:
		return yaml.dump(data if data is not None else {}, Dumper=SafeDumper, sort_keys=False).encode("utf-8")

	def deserialize(self, content: bytes) -> dict[str, Any]:
		if not content or content.strip() == b"":
			return self.default_empty
		return cast(dict[str, Any], yaml.load(content.decode("utf-8"), Loader=SafeLoader) or {})

	def clone(self, data: dict[str, Any]) -> dict[str, Any]:
		if not data: return {}
		return cast(dict[str, Any], orjson.loads(orjson.dumps(data)))

	@property
	def default_empty(self) -> dict[str, Any]:
		return {}
