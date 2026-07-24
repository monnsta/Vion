import contextvars
import html
import io
import json
import logging
import re
import traceback
from logging import FileHandler

from rich.console import Console
from rich.logging import RichHandler
from rich.syntax import Syntax
from rich.text import Text


code_log_stream: contextvars.ContextVar[io.StringIO | None] = contextvars.ContextVar('code_log_stream', default=None)

class CodeLogHandler(logging.Handler):
	def emit(self, record):
		stream = code_log_stream.get()
		if stream is not None:
			try:
				msg = self.format(record)
				stream.write(msg + '\n')
			except Exception:
				self.handleError(record)


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
			'<div class="log-entry" onclick="this.classList.toggle(\'active\')">\n'
			'	<div class="log-time-level">\n'
			f'		<span class="log-time">{time_str}</span>\n'
			f'		<span class="log-level" style="color: {color};">{level_letter}</span>\n'
			'	</div>\n'
			'	<div class="log-content">\n'
			f'		<div class="log-msg">{msg}</div>\n'
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
				html_out += f'		<div class="log-traceback" onclick="event.stopPropagation()">\n{snippet}\n		</div>\n'

		html_out += '	</div>\n'

		html_out += (
			'	<div class="log-popup" onclick="event.stopPropagation()">\n'
			f'		<div><span class="meta-label">PID:</span> {record.process}</div>\n'
			f'		<div><span class="meta-label">Thread:</span> {record.threadName}</div>\n'
			f'		<div><span class="meta-label">Location:</span> {record.name}:{record.lineno}</div>\n'
			'	</div>\n'
			'</div>\n'
		)

		return html_out

class TextFormatter(logging.Formatter):
	def __init__(self):
		super().__init__("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S")


class SessionFileHandler(FileHandler):
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
				'			-webkit-text-size-adjust: 100% !important; text-size-adjust: 100% !important; \n'
				'		}\n'
				'		.log-entry { display: flex; flex-direction: row; gap: 12px; padding: 6px 8px; border-bottom: 1px solid #1a1a1a; cursor: pointer; position: relative; transition: background 0.2s; }\n'
				'		.log-entry:hover { background-color: #0a0a0a; }\n'
				'		.log-entry.active { background-color: #0a0a0a; z-index: 20; }\n'
				'		.log-time-level { display: flex; gap: 8px; flex-shrink: 0; font-size: 9.5px; padding-top: 1px; opacity: 0.85; }\n'
				'		.log-time { color: #8be9fd; }\n'
				'		.log-level { font-weight: bold; }\n'
				'		.log-content { display: flex; flex-direction: column; flex-grow: 1; min-width: 0; }\n'
				'		.log-msg { color: #f8f8f2; white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; line-height: 1.4; }\n'
				'		.log-popup { display: none; position: absolute; left: 80px; top: 100%; margin-top: -4px; background: #111; border: 1px solid #333; padding: 8px 12px; border-radius: 4px; box-shadow: 0 4px 10px rgba(0,0,0,0.8); z-index: 10; color: #9c9fa9; flex-direction: column; gap: 4px; }\n'
				'		.log-entry.active .log-popup { display: flex; }\n'
				'		.meta-label { color: #8be9fd; font-weight: bold; margin-right: 4px; }\n'
				'		.log-traceback { margin-top: 6px; background: #050505; padding: 10px; border-radius: 6px; border: 1px solid #1a1a1a; overflow-x: auto; -webkit-text-size-adjust: 100% !important; text-size-adjust: 100% !important; }\n'
				'		.log-traceback pre { margin: 0; display: block; width: max-content; min-width: 100%; }\n'
				'		.log-traceback pre, .log-traceback code, .log-traceback span { font-family: "JetBrains Mono", Consolas, "Courier New", monospace !important; font-size: 11px !important; line-height: 1.25 !important; letter-spacing: 0 !important; word-spacing: 0 !important; white-space: pre !important; font-feature-settings: "tnum" !important; }\n'
				'	</style>\n'
				'</head>\n<body>\n'
			)
			stream.write(header)
			stream.flush()
		return stream

class RichHandlerv2(RichHandler):
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


code_logger = logging.getLogger("code_logger")
code_logger.setLevel(logging.DEBUG)
code_logger.propagate = False
_code_formatter = logging.Formatter("[%(levelname)s] %(message)s")
_code_handler = CodeLogHandler()
_code_handler.setFormatter(_code_formatter)
code_logger.addHandler(_code_handler)
