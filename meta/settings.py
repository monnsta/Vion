import asyncio
import builtins
import json
import logging
import sys

import discord
import pytz

from core.lib.bttrdict  import BD, Computed, Method, AntiFreeze
from core.lib.utils     import F, mt
from core.lib.file      import json_file, text_file, yaml_file
from meta.file          import file, sub


log = logging.getLogger(__name__)

real_import = builtins.__import__


config = BD()
emoji  = BD()

def load_config():
	global config, emoji
	log.info("Setting up config...")
	success, data = asyncio.run(yaml_file.load("configure.yml"))

	if not success:
		log.critical("Failed to load configure.yml")
		sys.exit(10)

	try:
		config.update(BD.load(data))
		log.debug(json.dumps(data, indent=4))
	except Exception:
		log.critical("An error occurred while parsing config into BD object", exc_info=True)
		sys.exit(10)

	def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
		if any(name == m or name.startswith(m + ".") for m in config.sandbox.allowed_modules):
			return real_import(name, globals, locals, fromlist, level)
		raise ImportError(f"Module '{name}' is not allowed in sandbox")

	for parent in [config.settings, config.ai_data]:
		for attr in ['server', 'user']:
			val = getattr(parent, attr)
			setattr(parent, attr, AntiFreeze(val.to_dict()))

	for obj in [config.devs, config.dev_servers]:
		for i in range(len(obj)):
			obj[i] = tuple(obj[i])

	config.dev_server_ids = [dsid for _, dsid, _ in config.dev_servers]
	config.dev_ids = [did for _, did in config.devs]

	emoji.update(BD.load(config.emoji.to_dict(update_self=False)))
	config.delete("emoji")

	config.status.range = tuple(config.status.range)
	config.timezone = pytz.timezone(config.timezone)

	_, secrets_data = asyncio.run(yaml_file.load(sub.env))
	config.secrets = BD.load(secrets_data).freeze()

	allowed_names = [
		"print", "range", "len", "int", "float", "str", "bool", "dict", "list", 
		"set", "tuple", "enumerate", "abs", "min", "max", "sum", "any", "all", 
		"filter", "map", "reversed", "sorted", "round", "divmod", "ord", "chr", 
		"slice", "zip", "pow", "isinstance", "issubclass", "format", "repr", 
		"frozenset", "bytearray", "bytes"
	]

	config.sandbox.allowed_builtins = {name: getattr(builtins, name) for name in allowed_names}
	config.sandbox.allowed_builtins["__import__"] = safe_import

	config.system_instructions = Computed(lambda self: F(self.system_instructions).format(config=self))

	config.event_inst = BD(
		_template = lambda event, objects, extra_text: mt(
			f"You're triggered by the `{event}` event.",
			f"You have these objects to work with: {', '.join(objects)}",
			f"{extra_text}"
		),

		freewill = Method(lambda self: self._template(
			"freewill",
			["guild", "bot"],
			"You can do anything you want in this event, get a channel to message in or just ignore. Upto you."
		)),

		inactivity = Method(lambda self: self._template(
			"inactivity",
			["guild", "bot"],
			"You can send a message to increase activity in a channel of your choice or ignore."
		)),

		error_notify = Method(lambda self, traceback: self._template(
			"error_notify",
			["guild", "bot"],
			f"You had error_notify on a code block, and it hit an error, this is the traceback:\n\n{traceback}"
		))

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
		)),

		on_channel_create = Method(lambda self: self._template(
			"on_channel_create",
			["channel", "bot"],
			"A new channel was created, you can comment on it by sending a message to the channel or a different one if it's readonly."
		)),

		on_channel_remove = Method(lambda self: self._template(
			"on_channel_remove",
			["guild", "bot"],
			"A channel was deleted, you can comment on it by sending a message in a general place people talk."
		))
	)
	config.cmd = AntiFreeze(BD())

	config.freeze()
	emoji.freeze()


__all__ = ('load_config', 'emoji', 'config')
