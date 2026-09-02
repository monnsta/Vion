"""
General utility functions for ID generation, string escaping, formatting, and text deduplication.
"""

import random
import string
import time
import textwrap
from typing import Any


def create_id() -> str:
	"""
	Generate a 10-character Base62 string using the current Unix timestamp and a random offset.

	Returns:
		A 10-character unique string formatted in Base62.
	"""
	BASE62_CHARS = string.digits + string.ascii_lowercase + string.ascii_uppercase

	def base62_encode(number: int, length: int) -> str:
		encoded_string = ""
		base = len(BASE62_CHARS)
		while number > 0:
			remainder = number % base
			number //= base
			encoded_string = BASE62_CHARS[remainder] + encoded_string
		return encoded_string.zfill(length)

	timestamp_s = int(time.time())

	random_part_max = 62 * 62 - 1
	random_value = random.randint(0, random_part_max)

	combined_int = (timestamp_s * (62 * 62)) + random_value
	id_str = base62_encode(combined_int, 10)
	return id_str


def em(*args: Any, chars: str = r"\*_~`|>#-") -> str:
	"""
	Escape Markdown structural symbols and special characters in strings or nested lists.

	Args:
		*args: Strings, numbers, or nested lists/tuples containing sequence components to escape.
		chars: Set of specific characters to escape with a backslash.

	Returns:
		The combined string with all matched Markdown characters backslash-escaped.
	"""
	def flatten(items: Any) -> list[str]:
		flat = []
		for item in items:
			if isinstance(item, (list, tuple)):
				flat.extend(flatten(item))
			else:
				flat.append(str(item))
		return flat

	full_text = "".join(flatten(args))

	result = []
	for ch in full_text:
		if ch in chars:
			result.append("\\" + ch)
		else:
			result.append(ch)
	return "".join(result)


def d(text: str, /) -> str:
	"""
	Short alias for textwrap.dedent. Removes any common leading whitespace from multiline text.

	Args:
		text: Multiline string to dedent.

	Returns:
		The dedented text string.
	"""
	return textwrap.dedent(text)


class F:
	"""
	Dynamic f-string template evaluator that defers formatting execution until invoked.

	Attributes:
		template: Raw f-string template string.
	"""

	def __init__(self, template: str) -> None:
		"""
		Initialize the template instance.

		Args:
			template: Raw template string supporting f-string variable references.
		"""
		self.template = template

	def format(self, **kwargs: object) -> str:
		"""
		Evaluate the raw template string using the provided variable context mapping.

		Args:
			**kwargs: Keyword variables available inside the template evaluation scope.

		Returns:
			The evaluated string output.
		"""
		return eval(
			f"f'''{self.template}'''",
			kwargs,
		)
