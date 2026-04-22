import json
import traceback
import types
import warnings
from types        import MappingProxyType


# Error Classes
class DataError(Exception):
	pass

class ComputationError(DataError):
	pass

class ImmutableError(DataError):
	pass


# Descriptors & Wrappers
class AntiFreeze:
	__slots__ = ('value',)

	def __init__(self, value):
		self.value = value

class Method:
	__slots__ = ('fn',)

	def __init__(self, fn):
		if not callable(fn):
			raise TypeError("Method expects a callable function.")
		self.fn = fn

class Computed:
	__slots__ = ('fn', 'lazy')

	def __init__(self, fn, lazy=False):
		if not callable(fn):
			raise TypeError("Computed expects a callable function.")
		self.fn = fn
		self.lazy = lazy


# Core Data Object
class BD:
	__slots__ = ('_data', '_watchers', '_frozen', '_anti_freeze')

	def __init__(self, **kwargs):
		super().__setattr__('_data', {})
		super().__setattr__('_watchers', [])
		super().__setattr__('_frozen', False)
		super().__setattr__('_anti_freeze', set())

		for k, v in kwargs.items():
			self.set(k, v)

	def __repr__(self):
		def _format_val(val):
			if isinstance(val, BD):
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

		items = []
		for k, v in self._data.items():
			if isinstance(v, types.MethodType):
				continue
			items.append(f"{k}={_format_val(v)}")

		return f"<{', '.join(items)}>"

	def __len__(self):
		return len(self._data)

	def __iter__(self):
		return iter(self._data)

	def __eq__(self, other):
		if isinstance(other, BD):
			return self.to_dict() == other.to_dict()
		if isinstance(other, dict):
			return self.to_dict() == other
		return False

	def __contains__(self, path):
		return self.has(path)

	def __getitem__(self, path):
		val = self.get(path, default=KeyError)
		if val is KeyError:
			raise KeyError(f"Path '{path}' not found.")
		return val

	def __setitem__(self, path, value):
		self.set(path, value)

	def __delitem__(self, path):
		self.delete(path)

	def __getattr__(self, key):
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
				tb = traceback.format_exc()
				raise ComputationError(f"Lazy computation failed for '{key}': {e}\n{tb}") from e

		return val

	def __setattr__(self, key, value):
		if key in type(self).__slots__:
			super().__setattr__(key, value)
			return
		self.set(key, value)

	def __delattr__(self, key):
		self.delete(key)

	# Core Path Operations
	def set(self, path, value):
		if not isinstance(path, str):
			raise DataError("Path must be a string.")

		if '.' not in path:
			self._set_raw(path, value)
			return self

		parts = path.split('.')
		target = self

		for part in parts[:-1]:
			if part not in target._data or not isinstance(target._data[part], BD):
				target._set_raw(part, BD())
			target = target._data[part]

		target._set_raw(parts[-1], value)
		return self

	def get(self, path, default=None):
		if not isinstance(path, str):
			raise DataError("Path must be a string.")

		if '.' not in path:
			val = self._data.get(path, KeyError)
			if val is KeyError:
				return default
			return getattr(self, path) if type(val) is Computed else val

		parts = path.split('.')
		current = self

		for part in parts:
			if isinstance(current, BD):
				try:
					current = getattr(current, part)
				except AttributeError:
					return default
			elif isinstance(current, dict):
				current = current.get(part, KeyError)
				if current is KeyError:
					return default
			else:
				return default

		return current

	def has(self, path):
		if not isinstance(path, str):
			return False

		if '.' not in path:
			return path in self._data

		return self.get(path, default=KeyError) is not KeyError

	def delete(self, path):
		if not isinstance(path, str):
			raise DataError("Path must be a string.")

		if '.' not in path:
			self._delete_raw(self, path)
			return

		parts = path.split('.')
		target = self

		for part in parts[:-1]:
			if not isinstance(target, BD) or part not in target._data:
				raise KeyError(f"Path '{path}' not found.")
			target = target._data[part]

		self._delete_raw(target, parts[-1])

	@staticmethod
	def _delete_raw(target, key):
		if target._frozen and key not in target._anti_freeze:
			raise ImmutableError(f"Cannot delete '{key}'; the object is frozen.")

		if key in target._data:
			del target._data[key]
			target._anti_freeze.discard(key)
		else:
			raise KeyError(f"Key '{key}' not found.")

	def update(self, payload):
		source = payload.to_dict() if isinstance(payload, BD) else payload
		for k, v in source.items():
			if isinstance(v, dict) and isinstance(self.get(k), BD):
				self.get(k).update(v)
			else:
				self.set(k, v)
		return self

	# Decorators
	def method(self, path):
		def decorator(fn):
			self.set(path, Method(fn))
			return fn
		return decorator

	def computed(self, path):
		def decorator(fn):
			self.set(path, Computed(fn, lazy=False))
			return fn
		return decorator

	def lazy(self, path):
		def decorator(fn):
			self.set(path, Computed(fn, lazy=True))
			return fn
		return decorator

	# Internal Mutability & Reactivity
	def _set_raw(self, key, value):
		if self._frozen and key not in self._anti_freeze:
			raise ImmutableError(f"Cannot modify '{key}'; the object is frozen.")

		old_value = self._data.get(key)

		if type(value) is AntiFreeze:
			self._anti_freeze.add(key)
			value = value.value

		elif type(value) is Method:
			value = types.MethodType(value.fn, self)

		elif type(value) is Computed and not value.lazy:
			try:
				value = value.fn(self)
			except Exception as e:
				tb = traceback.format_exc()
				raise ComputationError(f"Instant computation failed for '{key}': {e}\n{tb}") from e

		self._data[key] = value

		if self._watchers:
			for watcher in self._watchers:
				try:
					watcher(key, old_value, value)
				except Exception as e:
					warnings.warn(f"Watcher callback failed on key '{key}': {e}")

	def watch(self, callback):
		if not callable(callback):
			raise TypeError("Watch expects a callable function.")
		self._watchers.append(callback)

	def freeze(self):
		def _lock(item):
			if isinstance(item, BD):
				return item.freeze()
			if isinstance(item, list):
				return tuple(_lock(i) for i in item)
			if isinstance(item, dict):
				return MappingProxyType({k: _lock(v) for k, v in item.items()})
			if isinstance(item, set):
				return frozenset(_lock(i) for i in item)
			return item

		if not self._frozen:
			for k, v in list(self._data.items()):
				if k in self._anti_freeze:
					continue
				self._data[k] = _lock(v)
			super().__setattr__('_frozen', True)
		return self

	# Serialization & Deserialization
	def to_dict(self, update_self=True):
		def _serialize(item):
			if isinstance(item, BD):
				return item.to_dict(update_self=update_self)
			if isinstance(item, (list, tuple, set, frozenset)):
				return [_serialize(i) for i in item]
			if isinstance(item, (dict, MappingProxyType)):
				return {k: _serialize(v) for k, v in item.items()}
			return item

		out = {}
		for k, v in list(self._data.items()):
			if isinstance(v, types.MethodType):
				continue

			if type(v) is Computed:
				val = getattr(self, k)
			else:
				val = v

			serialized_val = _serialize(val)
			out[k] = serialized_val

			if update_self:
				self._data[k] = serialized_val

		return out

	@classmethod
	def load(cls, payload):
		if isinstance(payload, str):
			try:
				payload = json.loads(payload)
			except json.JSONDecodeError as e:
				raise DataError(f"Failed to parse JSON string: {e}") from e

		if not isinstance(payload, dict):
			raise TypeError("Load requires a dictionary or JSON string representation.")

		def _convert_value(value):
			if isinstance(value, list):
				return [_convert_value(item) for item in value]
			if isinstance(value, dict):
				return BD(**{k: _convert_value(v) for k, v in value.items()})
			return value

		init_kwargs = {key: _convert_value(value) for key, value in payload.items()}
		return cls(**init_kwargs)
