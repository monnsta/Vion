"""
Logging infrastructure module.

Provides specialized log handlers, custom formatters (JSON, HTML, Rich),
and context-managed log stream buffers.
"""

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

from vion.infrastructure.utils import d


code_log_stream: contextvars.ContextVar[io.StringIO | None] = contextvars.ContextVar(
	"code_log_stream", default=None
)


class CodeLogHandler(logging.Handler):
	"""
	Log handler that directs log records into a context-managed string stream buffer.
	"""

	def emit(self, record: logging.LogRecord) -> None:
		"""
		Format and write log record to active context log stream buffer.

		Args:
			record: LogRecord object to emit.
		"""
		stream = code_log_stream.get()
		if stream is not None:
			try:
				msg = self.format(record)
				stream.write(msg + "\n")
			except Exception:
				self.handleError(record)


class JsonFormatter(logging.Formatter):
	"""
	Formatter that outputs structured JSON string representations of LogRecords.
	"""

	def format(self, record: logging.LogRecord) -> str:
		"""
		Format log record as a serialized JSON string.

		Args:
			record: LogRecord object to process.

		Returns:
			JSON-formatted string representation of the log event.
		"""
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
			"epoch_created": record.created,
		}

		if record.exc_info:
			log_data["exception"] = self.formatException(record.exc_info)

		return json.dumps(log_data)


class HtmlFormatter(logging.Formatter):
	"""
	Formatter that constructs styled HTML log entry elements with syntax-highlighted tracebacks.

	Attributes:
		console: Rich Console instance configured for rendering HTML elements.
	"""

	def __init__(self) -> None:
		"""Initialize the HtmlFormatter and its underlying Rich console buffer."""
		super().__init__()
		self.console = Console(
			file=io.StringIO(),
			record=True,
			force_terminal=True,
			width=150,
			color_system="truecolor",
		)

	def format(self, record: logging.LogRecord) -> str:
		"""
		Format log record as an interactive HTML snippet with metadata popups.

		Args:
			record: LogRecord object to convert.

		Returns:
			HTML formatted string snippet representing the log event.
		"""
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

		html_out = d(f"""
			<div class="log-entry" onclick="this.classList.toggle(\'active\')">
				<div class="log-time-level">
					<span class="log-time">{time_str}</span>
					<span class="log-level" style="color: {color};">{level_letter}</span>
				</div>
				<div class="log-content">
					<div class="log-msg">{msg}</div>
		""")

		if record.exc_info:
			tb_str = "".join(traceback.format_exception(*record.exc_info))
			syntax = Syntax(tb_str, "pytb", theme="monokai", word_wrap=True)
			self.console.print(syntax)

			rich_html = self.console.export_html(inline_styles=True, clear=True)

			rich_html = re.sub(r'font-family:[^;"]+;?', "", rich_html)
			rich_html = re.sub(r'line-height:[^;"]+;?', "", rich_html)

			start = rich_html.find("<pre")
			end = rich_html.find("</pre>") + 6

			if start != -1:
				snippet = rich_html[start:end]
				html_out += f"""		<div class="log-traceback" onclick="event.stopPropagation()">\n{snippet}\n		</div>\n"""

		html_out += "	</div>\n"

		html_out += d(f"""
				<div class="log-popup" onclick="event.stopPropagation()">
					<div><span class="meta-label">PID:</span> {record.process}</div>
					<div><span class="meta-label">Thread:</span> {record.threadName}</div>
					<div><span class="meta-label">Location:</span> {record.name}:{record.lineno}</div>
				</div>
			</div>
		""")

		return html_out


class TextFormatter(logging.Formatter):
	"""
	Standardized plain text formatter using a bracketed timestamp and metadata layout.
	"""

	def __init__(self) -> None:
		"""Initialize standard text formatting template and timestamp layout."""
		super().__init__(
			"[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S"
		)


class SessionFileHandler(FileHandler):
	"""
	FileHandler subclass that injects structural HTML headers into newly created log files.
	"""

	def __init__(
		self,
		filename: str,
		mode: str = "w",
		encoding: str | None = "utf-8",
		delay: bool = False,
	) -> None:
		"""Initialize SessionFileHandler forcing write mode to truncate log sessions."""
		super().__init__(filename, mode=mode, encoding=encoding, delay=delay)

	def _open(self) -> io.TextIOWrapper:
		"""
		Open target file stream and write document header if destination file is empty HTML.

		Returns:
			Opened text stream handle.
		"""
		stream = super()._open()
		if stream.tell() == 0 and self.baseFilename.endswith(".html"):
			header = d("""
				<!DOCTYPE html><html><head>
					<meta charset="utf-8">
					<meta name="viewport" content="width=device-width, initial-scale=1.0">
					<title>Logs</title>
					<style>
						@import url("https://fonts.googleapis.com/css2?family=JetBrains+Mono&display=swap");
						body {
							background-color: #000000; color: #f8f8f2; margin: 0; padding: 10px;
							font-family: "JetBrains Mono", Consolas, "Courier New", monospace;
							font-variant-numeric: tabular-nums; font-size: 11px;
							-webkit-text-size-adjust: 100% !important; text-size-adjust: 100% !important;
						}
						.log-entry { display: flex; flex-direction: row; gap: 12px; padding: 6px 8px; border-bottom: 1px solid #1a1a1a; cursor: pointer; position: relative; transition: background 0.2s; }
						.log-entry:hover { background-color: #0a0a0a; }
						.log-entry.active { background-color: #0a0a0a; z-index: 20; }
						.log-time-level { display: flex; gap: 8px; flex-shrink: 0; font-size: 9.5px; padding-top: 1px; opacity: 0.85; }
						.log-time { color: #8be9fd; }
						.log-level { font-weight: bold; }
						.log-content { display: flex; flex-direction: column; flex-grow: 1; min-width: 0; }
						.log-msg { color: #f8f8f2; white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; line-height: 1.4; }
						.log-popup { display: none; position: absolute; left: 80px; top: 100%; margin-top: -4px; background: #111; border: 1px solid #333; padding: 8px 12px; border-radius: 4px; box-shadow: 0 4px 10px rgba(0,0,0,0.8); z-index: 10; color: #9c9fa9; flex-direction: column; gap: 4px; }
						.log-entry.active .log-popup { display: flex; }
						.meta-label { color: #8be9fd; font-weight: bold; margin-right: 4px; }
						.log-traceback { margin-top: 6px; background: #050505; padding: 10px; border-radius: 6px; border: 1px solid #1a1a1a; overflow-x: auto; -webkit-text-size-adjust: 100% !important; text-size-adjust: 100% !important; }
						.log-traceback pre { margin: 0; display: block; width: max-content; min-width: 100%; }
						.log-traceback pre, .log-traceback code, .log-traceback span { font-family: "JetBrains Mono", Consolas, "Courier New", monospace !important; font-size: 11px !important; line-height: 1.25 !important; letter-spacing: 0 !important; word-spacing: 0 !important; white-space: pre !important; font-feature-settings: "tnum" !important; }
					</style>
				</head><body>
			""")
			stream.write(header)
			stream.flush()
		return stream


class RichHandlerv2(RichHandler):
	"""
	Customized RichHandler that sanitizes redundant Discord reconnect traces and displays single-letter level indicators.
	"""

	def emit(self, record: logging.LogRecord) -> None:
		"""
		Intercept log emissions to clear unwanted stack traces prior to output rendering.

		Args:
			record: Target LogRecord object.
		"""
		if (
			record.name.startswith("discord")
			and "Attempting a reconnect in" in record.getMessage()
		):
			record.exc_info = None
			record.exc_text = None

		super().emit(record)

	def get_level_text(self, record: logging.LogRecord) -> Text:
		"""
		Format log level label into a single stylized letter representation.

		Args:
			record: Target LogRecord object.

		Returns:
			Styled Rich Text object representing the level string.
		"""
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
