import asyncio
import atexit
import html
import io
import json
import logging
import os
import re
import shutil
import sys
import time
import traceback
import textwrap
import termios
import tty
import warnings
from logging.handlers import TimedRotatingFileHandler

from rich.console import Console
from rich.logging import RichHandler
from rich.syntax import Syntax
from rich.text import Text

from core.lib.file import json_file
from meta import base, config, load_config, setup_directory


log = logging.getLogger(__name__)


_fd = None
_old_settings = None


class JsonFormatter(logging.Formatter):
	def format(self, record):
		log_data = {
			"timestamp": self.formatTime(record, self.datefmt),
			"level": record.levelname,
			"message": record.getMessage(),
			"logger_name": record.name,
			"file_name": record.filename,
			"path_name": record.pathname,
			"module": record.module,
			"line_number": record.lineno,
			"function_name": record.funcName,
			"process_id": record.process,
			"process_name": record.processName,
			"thread_id": record.thread,
			"thread_name": record.threadName,
			"millisecond_created": record.msecs,
			"epoch_created": record.created
		}

		if record.exc_info:
			log_data["exception"] = self.formatException(record.exc_info)

		return json.dumps(log_data)

class HtmlFormatter(logging.Formatter):
	def __init__(self):
		super().__init__()
		self.console = Console(file=io.StringIO(), record=True, force_terminal=True, width=150, color_system="truecolor")

	def format(self, record):
		time_str = self.formatTime(record, "%H:%M:%S")
		level = record.levelname
		level_letter = level[0] if level else "?"
		msg = html.escape(record.getMessage())

		colors = {
			"DEBUG": "#9c9fa9",
			"INFO": "#a6fff5",
			"WARNING": "#fe9100",
			"ERROR": "#ff5555",
			"CRITICAL": "#f00000",
		}
		color = colors.get(level, "#f8f8f2")

		html_out = (
			f'<div class="log-entry">\n'
			f'	<div class="log-header">\n'
			f'		<span class="log-time">[{time_str}]</span>\n'
			f'		<span class="log-level" style="color: {color};">{level_letter}</span>\n' 
			f'		<span class="log-meta">[PID:{record.process}] [{record.threadName}] [{record.name}:{record.lineno}]</span>\n'
			f'	</div>\n'
			f'	<div class="log-msg">{msg}</div>\n'
		)

		if record.exc_info:
			tb_str = "".join(traceback.format_exception(*record.exc_info))
			syntax = Syntax(tb_str, "pytb", theme="monokai", word_wrap=True)
			self.console.print(syntax)

			rich_html = self.console.export_html(inline_styles=True, clear=True)

			rich_html = re.sub(r'font-family:[^;"]+;?', '', rich_html)
			rich_html = re.sub(r'line-height:[^;"]+;?', '', rich_html)

			start = rich_html.find("<pre")
			end = rich_html.find("</pre>") + 6

			if start != -1:
				snippet = rich_html[start:end]
				html_out += f'	<div class="log-traceback">\n{snippet}\n	</div>\n'

		html_out += '</div>\n'
		return html_out

class HtmlTimedRotatingFileHandler(TimedRotatingFileHandler):
	def _open(self):
		stream = super()._open()
		if stream.tell() == 0 and self.baseFilename.endswith(".html"):
			header = (
				'<!DOCTYPE html>\n<html>\n<head>\n'
				'	<meta charset="utf-8">\n'
				'	<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
				'	<title>Logs</title>\n'
				'	<style>\n'
				'		@import url("https://fonts.googleapis.com/css2?family=JetBrains+Mono&display=swap");\n'
				'		body { \n'
				'			background-color: #000000; color: #f8f8f2; margin: 0; padding: 10px; \n'
				'			font-family: "JetBrains Mono", Consolas, "Courier New", monospace; \n'
				'			font-variant-numeric: tabular-nums; font-size: 11px; \n'
				'			-webkit-text-size-adjust: 100% !important; \n'
				'			text-size-adjust: 100% !important; \n'
				'		}\n'
				'		.log-entry { display: flex; flex-direction: column; gap: 4px; padding: 8px; border-bottom: 1px solid #1a1a1a; transition: background 0.2s; }\n'
				'		.log-entry:hover { background-color: #0a0a0a; }\n'
				'		.log-header { display: flex; gap: 12px; font-family: inherit; }\n'
				'		.log-time { color: #8be9fd; }\n'
				'		.log-level { font-weight: bold; }\n'
				'		.log-meta { color: #9c9fa9; margin-left: auto; }\n'
				'		.log-msg { color: #f8f8f2; white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; font-family: inherit; }\n'
				'		.log-traceback { \n'
				'			margin-top: 8px; background: #050505; padding: 10px; \n'
				'			border-radius: 6px; border: 1px solid #1a1a1a; overflow-x: auto; \n'
				'			-webkit-text-size-adjust: 100% !important; \n'
				'			text-size-adjust: 100% !important; \n'
				'		}\n'
				'		.log-traceback pre {\n'
				'			margin: 0;\n'
				'			display: block;\n'
				'			width: max-content;\n'
				'			min-width: 100%;\n'
				'		}\n'
				'		.log-traceback pre, .log-traceback code, .log-traceback span {\n'
				'			font-family: "JetBrains Mono", Consolas, "Courier New", monospace !important;\n'
				'			font-size: 11px !important;\n'
				'			line-height: 1.25 !important;\n'
				'			letter-spacing: 0 !important;\n'
				'			word-spacing: 0 !important;\n'
				'			white-space: pre !important;\n'
				'			font-feature-settings: "tnum" !important;\n'
				'		}\n'
				'	</style>\n'
				'</head>\n<body>\n'
			)
			stream.write(header)
			stream.flush()
		return stream

class RichHandler(RichHandler):
	def emit(self, record):
		if (
			record.name.startswith("discord")
			and "Attempting a reconnect in" in record.getMessage()
		):
			record.exc_info = None
			record.exc_text = None

		super().emit(record)

	def get_level_text(self, record: logging.LogRecord) -> Text:
		level_map = {
			"DEBUG": "D",
			"INFO": "I",
			"WARNING": "W",
			"ERROR": "E",
			"CRITICAL": "C",
		}
		short_label = level_map.get(record.levelname, record.levelname)
		level_style = f"logging.level.{record.levelname.lower()}"
		return Text.styled(f"{short_label}", level_style)


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

	console_handler = RichHandler(
		level=logging.INFO,
		rich_tracebacks=True,
		tracebacks_show_locals=False,
		markup=True,
		show_path=False,
		log_time_format="%X",
	)
	root_logger.addHandler(console_handler)

	logging.getLogger("discord").setLevel(logging.WARNING)
	logging.getLogger("asyncio").setLevel(logging.WARNING)

def setup_file_logging():
	log_dir = base.logs
	os.makedirs(log_dir, exist_ok=True)

	ext = ".json" if config.logging.use_json else ".html"

	date_str = time.strftime("%Y-%m-%d", time.localtime())
	log_file_path = os.path.join(log_dir, f"{date_str}{ext}")

	root_logger = logging.getLogger()

	file_handler = HtmlTimedRotatingFileHandler(
		filename=log_file_path,
		when='midnight',
		interval=1,
		backupCount=config.logging.cleanup_days,
		encoding='utf-8'
	)

	file_handler.namer = lambda name: (name if name.endswith(ext) else f"{name.split(ext)[0]}{ext}")

	file_handler.setLevel(logging.DEBUG)
	file_handler.setFormatter(
		JsonFormatter() if config.logging.use_json else HtmlFormatter()
	)

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
