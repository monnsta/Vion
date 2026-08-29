import random
import string
import time
import textwrap
from typing import Any


def create_id() -> str:
	BASE62_CHARS = string.digits + string.ascii_lowercase + string.ascii_uppercase

	def base62_encode(number, length):
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
	return textwrap.dedent(text)

class F:
	def __init__(self, template: str):
		self.template = template

	def format(self, **kwargs: object) -> str:
		return eval(
			f"f'''{self.template}'''",
			kwargs,
		)
