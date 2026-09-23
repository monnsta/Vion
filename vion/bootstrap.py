"""
Runtime environment bootstrapper.

Handles terminal setup, console/file logging registration, path initialization, and shutdown.
"""

import asyncio
import atexit
import logging
import os
import signal
import sys
import termios
import warnings

from vion.infrastructure.file import json_file
from vion.infrastructure.logging import (
	HtmlFormatter,
	JsonFormatter,
	RichHandlerv2,
	SessionFileHandler,
	TextFormatter,
)
from vion.config import config, storage, load_config, setup_directory


log = logging.getLogger("startup")

_fd = None
_old_settings = None


def disable_console_logging() -> None:
	"""
	Instantly remove stdout logging handlers to prevent terminal log spam during exit.
	"""
	root_logger = logging.getLogger()
	for handler in list(root_logger.handlers):
		if isinstance(handler, RichHandlerv2) or not isinstance(
			handler, SessionFileHandler
		):
			root_logger.removeHandler(handler)


def disable_echoctl() -> None:
	"""
	Disable ECHOCTL in terminal settings to prevent printing control characters like ^C.
	"""
	global _fd, _old_settings

	try:
		if not sys.stdin.isatty():
			return
		_fd = sys.stdin.fileno()
		_old_settings = termios.tcgetattr(_fd)

		new_settings = termios.tcgetattr(_fd)
		new_settings[3] = new_settings[3] & ~termios.ECHOCTL

		termios.tcsetattr(_fd, termios.TCSADRAIN, new_settings)
	except Exception:
		_fd = None
		_old_settings = None


def setup_console_logging() -> None:
	"""
	Configure stdout console logging handler using Rich text rendering.
	"""
	root_logger = logging.getLogger()
	root_logger.setLevel(logging.DEBUG)

	console_handler = RichHandlerv2(
		level=logging.INFO,
		rich_tracebacks=True,
		tracebacks_show_locals=False,
		markup=True,
		show_path=False,
		log_time_format="%X",
	)

	root_logger.addHandler(console_handler)

	logging.getLogger("discord").setLevel(logging.INFO)
	logging.getLogger("asyncio").setLevel(logging.WARNING)

	logging.getLogger("memory").setLevel(logging.INFO)
	logging.getLogger("profile").setLevel(logging.INFO)
	logging.getLogger("blacklist").setLevel(logging.INFO)


def setup_file_logging() -> None:
	"""
	Initialize file-based session log handler and perform two-file log rotation.
	"""
	if not config.logging.file:
		return

	log_dir = storage.dirs.logs
	os.makedirs(log_dir, exist_ok=True)

	ext = f".{config.logging.type}"
	current_log = os.path.join(log_dir, f"current{ext}")
	previous_log = os.path.join(log_dir, f"previous{ext}")

	if os.path.exists(current_log):
		try:
			if os.path.exists(previous_log):
				os.remove(previous_log)

			os.rename(current_log, previous_log)
		except OSError:
			pass

	root_logger = logging.getLogger()

	file_handler = SessionFileHandler(filename=current_log, mode="w", encoding="utf-8")

	file_handler.setLevel(logging.DEBUG)

	if config.logging.type == "json":
		file_handler.setFormatter(JsonFormatter())
	elif config.logging.type == "html":
		file_handler.setFormatter(HtmlFormatter())
	else:
		file_handler.setFormatter(TextFormatter())

	root_logger.addHandler(file_handler)


def cleanup() -> None:
	"""
	Restore original terminal settings and terminate internal garbage collection routines.
	"""
	disable_console_logging()

	if json_file:
		try:
			json_file.cache.stop_gc()
		except Exception:
			pass

	if _fd is not None and _old_settings is not None:
		try:
			if sys.stdin.isatty():
				termios.tcsetattr(_fd, termios.TCSADRAIN, _old_settings)
		except Exception:
			pass


def setup_signal_handlers() -> None:
	"""
	Intercept termination signals to immediately mute stdout output.
	"""

	def handle_exit_signal(signum, frame):
		_ = signum, frame
		disable_console_logging()

	try:
		signal.signal(signal.SIGINT, handle_exit_signal)
		signal.signal(signal.SIGTERM, handle_exit_signal)
	except (ValueError, OSError):
		pass


async def bootstrap() -> None:
	"""
	Execute async application startup sequence including configuration and filesystem validation.
	"""
	warnings.filterwarnings("ignore", category=DeprecationWarning)
	warnings.simplefilter("ignore", DeprecationWarning)

	atexit.register(cleanup)
	setup_signal_handlers()
	disable_echoctl()

	setup_console_logging()

	await setup_directory()
	await load_config()

	setup_file_logging()

	if json_file:
		json_file.cache.start_gc()


if __name__ != "__main__":
	asyncio.run(bootstrap())
