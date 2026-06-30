# Copyright (c) 2026 monnsta. All rights reserved.

import builtins
import ial
import json
import logging
import sys

import pytz

from core.lib.dataclass import Data, Computed, Method, AntiFreeze
from core.lib.utils import F, mt
from core.lib.file import ial_file
from meta.paths import file


log = logging.getLogger(__name__)

real_import = builtins.__import__


config = Data()
emoji  = Data()


async def load_config():
	global config, emoji
	log.info("Setting up config...")
	if ial_file == None:
		log.critical("ial parser not found, please install the required dependencies")
		sys.exit(10)
	try:
		success, data = await ial_file.load(file.conf, update_cache=False, use_cache=False)
	except ial.MultiError as e:
		for i, error in enumerate(e.errors):
			log.error(f"{i}. {error}", exc_info=True)

	if not success: # type: ignore
		log.critical(f"Failed to load {file.conf}")
		sys.exit(10)

	try:
		config.update(Data.load(data)) # type: ignore
	except Exception:
		log.critical("An error occurred while parsing config into Data object", exc_info=True)
		sys.exit(10)

	log.debug(json.dumps({k: v for k, v in data.items() if k != "system_instructions"})) #type: ignore

	allowed_prefixes = tuple(f"{m}." for m in config.sandbox.allowed_modules)
	allowed_exact = set(config.sandbox.allowed_modules)

	def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
		if name in allowed_exact or name.startswith(allowed_prefixes):
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

	emoji.update(Data.load(config.emoji.to_dict(update_self=False)))
	config.delete("emoji")

	config.activity.range = tuple(config.activity.range)
	config.timezone = pytz.timezone(config.timezone)

	_, secrets_data = await ial_file.load(file.env)
	config.secrets = Data.load(secrets_data)

	config.sandbox.allowed_builtins = {name: getattr(builtins, name) for name in config.sandbox.allowed_builtins}
	config.sandbox.allowed_builtins["__import__"] = safe_import

	config.system_instructions = Computed(lambda self: F(self.system_instructions).format())
	log.debug(config.system_instructions)

	config.event_inst = Data(
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
	config.cmd = Data()


__all__ = ('load_config', 'emoji', 'config')
