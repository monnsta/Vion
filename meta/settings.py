import asyncio
import builtins
import json
import logging

import discord
import pytz

from meta.file          import file, sub
from core.lib.bttrdict  import BD, Computed, Method, AntiFreeze
from core.lib.etc       import F, mt
from core.lib.file      import json_file, text_file, yaml_file


log = logging.getLogger(__name__)

real_import = builtins.__import__


log.info("Setting up config...")
success, data = asyncio.run(yaml_file.load("configure.yml"))

try:
	config = BD.load(data)
	log.debug(json.dumps(data, indent=4))
except Exception:
	log.error("An error accured while setting up config", exc_info=True)


def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
	if any(name == m or name.startswith(m + ".") for m in config.sandbox.allowed_modules):
		return real_import(name, globals, locals, fromlist, level)
	raise ImportError(f"Module '{name}' is not allowed in sandbox")
for parent in [config.settings, config.ai_data]:
	for attr in ['server', 'user']:
		val = getattr(parent, attr)
		setattr(parent, attr, AntiFreeze(val.to_dict()))
for i in range(len(config.devs)): config.devs[i] = tuple(config.devs[i])
for i in range(len(config.dev_servers)): config.dev_servers[i] = tuple(config.dev_servers[i])

emoji = BD.load(config.emoji.to_dict(False))
config.delete("emoji")

config.timezone = pytz.timezone(config.timezone)
config.system_instructions = F(config.system_instructions)
config.secrets = BD.load(asyncio.run(json_file.load(sub.env))[1]).freeze()
config.allowed_builtins = {
	"print": print,
	"range": range,
	"len": len,
	"int": int,
	"float": float,
	"str": str,
	"bool": bool,
	"dict": dict,
	"list": list,
	"set": set,
	"tuple": tuple,
	"enumerate": enumerate,
	"abs": abs,
	"min": min,
	"max": max,
	"sum": sum,
	"any": any,
	"all": all,
	"filter": filter,
	"map": map,
	"reversed": reversed,
	"sorted": sorted,
	"round": round,
	"divmod": divmod,
	"ord": ord,
	"chr": chr,
	"slice": slice,
	"zip": zip,
	"pow": pow,
	"isinstance": isinstance,
	"issubclass": issubclass,
	"format": format,
	"repr": repr,
	"frozenset": frozenset,
	"bytearray": bytearray,
	"bytes": bytes,
	"__import__": safe_import
}
config.event_inst = BD( #{
	_template = lambda event, objects, extra_text: mt(
		f"You're triggered by the `{event}` event.",
		f"You have these objects to work with:\n * {f'{char[10]} * '.join(objects)}",
		f"{extra_text}"
	),

	freewill = Method(lambda self: self._template(
		"freewill",
		["guild", "bot"],
		"You can do anything you want in this event, get a channel to message in or just ignore. upto you."
	)),

	inactivity = Method(lambda self: self._template(
		"inactivity",
		["guild", "bot"],
		"You can send a message to increase activity in a channel of your choice or ignore"
	)),

	on_message = Method(lambda self, message_id: self._template(
		"on_message",
		["message", "bot"],
		f"This is the message ID you were triggered by: {message_id}"
	)),

	on_member_join = Method(lambda self: self._template(
		"on_member_join",
		["member", "guild", "bot"],
		"A member joined, you can welcome them or do anything you want."
	)),

	on_member_remove = Method(lambda self: self._template(
		"on_member_remove",
		["member", "guild", "bot"],
		"A member left, you can say goodbye to them or do anything you want."
	))
) #}
config.freeze()


__all__ = ('emoji', 'config')
