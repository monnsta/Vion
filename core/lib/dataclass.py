import json
import traceback
import types
import warnings
from typing import Any, Callable, Dict, List, Optional, Set, Union, Type, TypeVar, Iterator
from types import MappingProxyType


T = TypeVar("T", bound="Data")


# Error Classes
class DataError(Exception):
	"""Base exception for Data data operations."""
	pass

class ComputationError(DataError):
	"""Raised when a Computed or Lazy value fails to evaluate."""
	pass

class ImmutableError(DataError):
	"""Raised when attempting to modify a frozen Data object."""
	pass


# Wrappers
class Repr:
	"""
	A proxy wrapper that returns a specific string representation
	while delegating all attribute access and comparisons to an 
	underlying value.
	"""
	__slots__ = ("_repr_val", "_actual_val")

	def __init__(self, repr_val: str, actual_val: Any):
		self._repr_val = repr_val
		self._actual_val = actual_val

	def __getattr__(self, key: str) -> Any:
		return getattr(self._actual_val, key)

	def __getitem__(self, key: Any) -> Any:
		return self._actual_val[key]

	# Comparison Operators
	def __lt__(self, other: Any) -> bool:
		return self._actual_val < (other._actual_val if isinstance(other, Repr) else other)

	def __le__(self, other: Any) -> bool:
		return self._actual_val <= (other._actual_val if isinstance(other, Repr) else other)

	def __eq__(self, other: Any) -> bool:
		return self._actual_val == (other._actual_val if isinstance(other, Repr) else other)

	def __gt__(self, other: Any) -> bool:
		return self._actual_val > (other._actual_val if isinstance(other, Repr) else other)

	def __ge__(self, other: Any) -> bool:
		return self._actual_val >= (other._actual_val if isinstance(other, Repr) else other)

	def __str__(self) -> str:
		return self._repr_val

	def __repr__(self) -> str:
		return self._repr_val

class AntiFreeze:
	"""Wrapper to protect specific keys from being frozen."""
	__slots__ = ("value",)
	def __init__(self, value: Any):
		self.value = value

class Method:
	"""Wrapper to mark a function as an instance method."""
	__slots__ = ("fn",)
	def __init__(self, fn: Callable):
		if not callable(fn):
			raise TypeError("Method expects a callable function.")
		self.fn = fn

class Computed:
	"""Wrapper for values calculated dynamically from the Data state."""
	__slots__ = ("fn", "lazy")
	def __init__(self, fn: Callable[["Data"], Any], lazy: bool = False):
		if not callable(fn):
			raise TypeError("Computed expects a callable function.")
		self.fn = fn
		self.lazy = lazy

class Secret:
	"""Wrapper to hide sensitive data in logs/repr while keeping it accessible."""
	__slots__ = ("value",)
	def __init__(self, value: Any):
		self.value = value

	def __repr__(self) -> str:
		return "********"

	def __str__(self) -> str:
		return "********"

class Validated:
	"""Wrapper that enforces a validation function before setting a value."""
	__slots__ = ("validator", "value")
	def __init__(self, validator: Callable[[Any], bool], value: Any):
		if not validator(value):
			raise DataError(f"Initial value failed validation: {value}")
		self.validator = validator
		self.value = value

class Alias:
	"""Wrapper that redirects access to another path in the Data tree."""
	__slots__ = ("path",)
	def __init__(self, path: str):
		self.path = path

class Observed:
	"""Wrapper that triggers a callback only when this specific key changes."""
	__slots__ = ("callback", "value")
	def __init__(self, callback: Callable[[Any, Any], None], value: Any):
		self.callback = callback
		self.value = value


# Core Data Object
class Data:
	"""
	BttrDict (Data): A nested, observable, and freezable data container
	supporting dot-notation, computed properties, and custom representations.
	"""
	__slots__ = ("_data", "_watchers", "_frozen", "_anti_freeze")

	def __init__(self, **kwargs: Any):
		super().__setattr__("_data", {})
		super().__setattr__("_watchers", [])
		super().__setattr__("_frozen", False)
		super().__setattr__("_anti_freeze", set())

		for k, v in kwargs.items():
			self.set(k, v)

	@classmethod
	def load(cls: Type[T], data: Union[str, Dict[str, Any]]) -> T:
		"""Loads a dictionary or JSON string, recursively converting nested dicts to Data instances."""
		if isinstance(data, str):
			try:
				parsed_data = json.loads(data)
			except json.JSONDecodeError as e:
				raise DataError(f"Failed to parse JSON string: {e}")
		elif isinstance(data, dict):
			parsed_data = data
		else:
			raise TypeError("load() expects a JSON string or a dictionary.")

		if not isinstance(parsed_data, dict):
			raise DataError("Root structure must be a dictionary/object.")

		def _convert(item: Any) -> Any:
			if isinstance(item, dict):
				return cls(**{k: _convert(v) for k, v in item.items()})
			if isinstance(item, list):
				return [_convert(i) for i in item]
			if isinstance(item, set):
				return {_convert(i) for i in item}
			if isinstance(item, tuple):
				return tuple(_convert(i) for i in item)
			return item

		return _convert(parsed_data)

	def __repr__(self) -> str:
		def _format_val(val: Any) -> str:
			if isinstance(val, (Data, Repr)):
				return repr(val)
			if isinstance(val, (dict, MappingProxyType)):
				inner = ", ".join(f"{repr(k)}: {_format_val(v)}" for k, v in val.items())
				return "{" + inner + "}"
			if isinstance(val, (list, tuple, set, frozenset)):
				brackets = {list: "[]", tuple: "()", set: "{}", frozenset: "{}"}
				b = brackets.get(type(val), "[]")
				inner = ", ".join(_format_val(i) for i in val)
				return f"{b[0]}{inner}{b[1]}"
			if type(val) is Computed:
				return "<computed>"
			return repr(val)

		items = [f"{k}={_format_val(v)}" for k, v in self._data.items() 
				 if not isinstance(v, types.MethodType)]
		return f"<{', '.join(items)}>"

	def __len__(self) -> int:
		return len(self._data)

	def __iter__(self) -> Iterator[str]:
		return iter(self._data)

	def __contains__(self, key: str) -> bool:
		return key in self._data

	def __eq__(self, other: Any) -> bool:
		if isinstance(other, Data):
			return self.to_dict() == other.to_dict()
		if isinstance(other, dict):
			return self.to_dict() == other
		return False

	def __getitem__(self, path: str) -> Any:
		val = self.get(path, default=KeyError)
		if val is KeyError:
			raise KeyError(f"Path '{path}' not found.")
		return val

	def __setitem__(self, path: str, value: Any) -> None:
		self.set(path, value)

	def __delitem__(self, path: str) -> None:
		self.delete(path)

	def __getattr__(self, key: str) -> Any:
		try:
			val = self._data[key]
		except KeyError:
			raise AttributeError(f"'{type(self).__name__}' object has no attribute '{key}'")

		if type(val) is Computed:
			try:
				result = val.fn(self)
				self._data[key] = result
				return result
			except Exception as e:
				raise ComputationError(f"Lazy computation failed for '{key}': {e}") from e

		if type(val) is Alias:
			return self.get(val.path)

		if type(val) is Secret:
			return val.value

		return val

	def __setattr__(self, key: str, value: Any) -> None:
		if key in type(self).__slots__:
			super().__setattr__(key, value)
			return
		self.set(key, value)

	def keys(self) -> Iterator[str]:
		return self._data.keys()

	def values(self) -> Iterator[Any]:
		return (getattr(self, k) for k in self._data)

	def items(self) -> Iterator[tuple[str, Any]]:
		return ((k, getattr(self, k)) for k in self._data)

	def update(self, data: Union[Dict[str, Any], "Data"]) -> "Data":
		"""Updates the Data instance with another dictionary or Data instance."""
		iterable = data._data.items() if isinstance(data, Data) else data.items()
		for k, v in iterable:
			self.set(k, v)
		return self

	def pop(self, key: str, default: Any = KeyError) -> Any:
		"""Removes a key and returns its value."""
		if key in self._data:
			val = getattr(self, key)
			self.delete(key)
			return val
		if default is not KeyError:
			return default
		raise KeyError(f"Key '{key}' not found.")

	def clear(self) -> None:
		"""Removes all items from the Data instance, respecting anti-freeze/frozen limits."""
		if self._frozen:
			raise ImmutableError("Cannot clear; the object is frozen.")
		for key in list(self._data.keys()):
			if key not in self._anti_freeze:
				self.delete(key)

	def set(self, path: str, value: Any) -> "Data":
		"""Sets a value at a potentially nested path (e.g., 'user.profile.name')."""
		if not isinstance(path, str):
			raise DataError("Path must be a string.")

		if "." not in path:
			self._set_raw(path, value)
			return self

		parts = path.split(".")
		target = self

		for part in parts[:-1]:
			if part not in target._data or not isinstance(target._data[part], Data):
				target._set_raw(part, Data())
			target = target._data[part]

		target._set_raw(parts[-1], value)
		return self

	def get(self, path: str, default: Any = None) -> Any:
		"""Retrieves a value from a nested path."""
		if "." not in path:
			val = self._data.get(path, KeyError)
			if val is KeyError: return default
			return getattr(self, path) if type(val) is Computed else val

		parts = path.split(".")
		current = self
		for part in parts:
			try:
				current = getattr(current, part) if isinstance(current, (Data, Repr)) else current[part]
			except (AttributeError, KeyError, TypeError):
				return default
		return current

	def delete(self, path: str) -> None:
		"""Deletes a key at a nested path."""
		if "." not in path:
			self._delete_raw(self, path)
			return

		parts = path.split(".")
		target = self
		for part in parts[:-1]:
			target = target._data[part]
		self._delete_raw(target, parts[-1])

	@staticmethod
	def _delete_raw(target: "Data", key: str) -> None:
		if target._frozen and key not in target._anti_freeze:
			raise ImmutableError(f"Cannot delete '{key}'; the object is frozen.")
		if key in target._data:
			del target._data[key]
			target._anti_freeze.discard(key)
		else:
			raise KeyError(f"Key '{key}' not found.")

	def _set_raw(self, key: str, value: Any) -> None:
		if self._frozen and key not in self._anti_freeze:
			raise ImmutableError(f"Cannot modify '{key}'; the object is frozen.")

		old_value = self._data.get(key)

		if type(value) is Validated:
			if not value.validator(value.value):
				raise DataError(f"Validation failed for key '{key}'")
			value = value.value

		if type(value) is Secret:
			pass 
		elif type(value) is AntiFreeze:
			self._anti_freeze.add(key)
			value = value.value

		elif type(value) is Method:
			value = types.MethodType(value.fn, self)
		elif type(value) is Computed and not value.lazy:
			value = value.fn(self)
		elif type(value) is Alias:
			pass
		elif type(value) is Observed:
			callback = value.callback
			value = value.value
			self._watchers.append(lambda k, o, n: callback(o, n) if k == key else None)

		self._data[key] = value

		for watcher in self._watchers:
			try:
				watcher(key, old_value, value)
			except Exception as e:
				warnings.warn(f"Watcher callback failed: {e}")

	def to_dict(self, update_self: bool = True) -> Dict[str, Any]:
		"""Converts the Data structure into a standard Python dictionary."""
		def _serialize(item: Any) -> Any:
			if isinstance(item, Repr):
				return _serialize(item._actual_val)
			if isinstance(item, Data):
				return item.to_dict(update_self=update_self)
			if isinstance(item, (list, tuple, set, frozenset)):
				return [_serialize(i) for i in item]
			if isinstance(item, (dict, MappingProxyType)):
				return {k: _serialize(v) for k, v in item.items()}
			return item

		out = {}
		for k, v in list(self._data.items()):
			if isinstance(v, types.MethodType): continue
			val = getattr(self, k) if type(v) is Computed else v
			serialized_val = _serialize(val)
			out[k] = serialized_val
			if update_self: self._data[k] = serialized_val
		return out

	def freeze(self) -> "Data":
		"""
		Recursively freezes the object, nested Data instances, and converts 
		mutable collections (list, set, dict) into immutable types.
		"""
		super().__setattr__("_frozen", True)

		def _deep_freeze(item: Any) -> Any:
			if isinstance(item, Data):
				return item.freeze()

			if isinstance(item, list):
				return tuple(_deep_freeze(i) for i in item)
			
			if isinstance(item, set):
				return frozenset(_deep_freeze(i) for i in item)

			if isinstance(item, dict):
				return MappingProxyType({k: _deep_freeze(v) for k, v in item.items()})

			return item

		for key, val in list(self._data.items()):
			if key in self._anti_freeze:
				continue

			if not isinstance(val, (types.MethodType, Computed, Alias)):
				self._data[key] = _deep_freeze(val)

		return self


__all__ = (
	'DataError', 'ComputationError', 'ImmutableError',
	'Repr', 'AntiFreeze', 'Method', 'Computed', 'Secret', 'Validated', 'Alias', 'Observed',
	'Data'
)