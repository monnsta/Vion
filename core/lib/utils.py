# Copyright (c) 2026 monnsta. All rights reserved.

import random
import string
import time
from typing import Iterable, Any

from discord.ext import commands


def is_dev(devs: Iterable[int]):
	async def predicate(ctx: commands.Context) -> bool:
		return any(dev_id == ctx.author.id for dev_id in devs)
	return commands.check(predicate)

def is_admin(devs: Iterable[int], compare: tuple[str, str] | None = None):
	async def predicate(ctx: commands.Context) -> bool:
		if compare and ctx.kwargs.get(compare[0]) == compare[1]:
			return True

		perms = getattr(ctx.author, "guild_permissions", None)
		is_owner = (ctx.author.id == ctx.guild.owner_id if ctx.guild else True)
		is_dev = any(ctx.author.id == dev_id for dev_id in devs)
		is_admin = (
			perms.manage_guild or
			perms.administrator
			if perms else False
		)
		return is_owner or is_dev or is_admin
	return commands.check(predicate)

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

def em(*args: Any, chars: str = r"\*_~`|>#-.()[]{}!") -> str:
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

def mt(*args: str | int, sep: str = "\n") -> str:
	joined = sep.join(map(str, args))
	return joined

class F:
	def __init__(self, template: str):
		self.template = template

	def format(self, **kwargs: object) -> str:
		return eval(
			f"f'''{self.template}'''",
			kwargs,
		)
