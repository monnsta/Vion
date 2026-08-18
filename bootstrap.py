import asyncio
import atexit
import logging
import os
import sys
import time
import termios
import warnings
import glob

from core.lib.file import json_file
from core.lib.logging import JsonFormatter, HtmlFormatter, TextFormatter, SessionFileHandler, RichHandlerv2
from meta import base, config, load_config, setup_directory


log = logging.getLogger(__name__)


_fd = None
_old_settings = None


def disable_echoctl():
	global _fd, _old_settings
	try:
		_fd = sys.stdin.fileno()
		_old_settings = termios.tcgetattr(_fd)
		new_settings = termios.tcgetattr(_fd)
		new_settings[3] = new_settings[3] & ~termios.ECHOCTL

		termios.tcsetattr(_fd, termios.TCSADRAIN, new_settings)
	except Exception:
		_fd = None
		_old_settings = None

def setup_console_logging():
	root_logger = logging.getLogger()
	root_logger.setLevel(logging.DEBUG)
	root_logger.handlers.clear()

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
	logging.getLogger("core.wrp.memory").setLevel(logging.INFO)
	logging.getLogger("core.wrp.profile").setLevel(logging.INFO)
	logging.getLogger("core.wrp.blacklist").setLevel(logging.INFO)

def setup_file_logging():
	if not config.logging.file:
		return

	log_dir = base.logs
	os.makedirs(log_dir, exist_ok=True)

	now = time.time()
	retention = config.logging.cleanup_days * 86400
	for log_file in glob.glob(os.path.join(log_dir, "*.*")):
		if os.path.isfile(log_file) and os.stat(log_file).st_mtime < (now - retention):
			try:
				os.remove(log_file)
			except OSError:
				pass

	ext = f".{config.logging.type}"
	date_str = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
	log_file_path = os.path.join(log_dir, f"{date_str}{ext}")

	root_logger = logging.getLogger()

	file_handler = SessionFileHandler(
		filename=log_file_path,
		encoding='utf-8'
	)
	file_handler.setLevel(logging.DEBUG)

	if config.logging.type == "json":
		file_handler.setFormatter(JsonFormatter())
	elif config.logging.type == "html":
		file_handler.setFormatter(HtmlFormatter())
	else:
		file_handler.setFormatter(TextFormatter())

	root_logger.addHandler(file_handler)


def cleanup():
	if json_file:
		json_file.cache.stop_gc()
	if _fd is not None and _old_settings is not None:
		termios.tcsetattr(_fd, termios.TCSADRAIN, _old_settings)
	log.info("Shutting down...")


if __name__ != "__main__":
	warnings.filterwarnings("ignore", category=DeprecationWarning)
	warnings.simplefilter("ignore", DeprecationWarning)
	atexit.register(cleanup)
	disable_echoctl()

	setup_console_logging()

	asyncio.run(load_config())
	asyncio.run(setup_directory())

	setup_file_logging()

	if json_file:
		json_file.cache.start_gc()
