import json
import logging
import time
from pathlib           import Path
from logging.handlers  import TimedRotatingFileHandler

from rich.logging      import RichHandler

from core.lib.file     import json_file
from meta              import base, load_config, setup_directory


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


# 1. Setup the log directory and dynamic naming
log_dir = Path(base.logs)
log_dir.mkdir(parents=True, exist_ok=True)
log_date_format = f"%B-%-d-%Y.log"
log_file_path = str(log_dir / time.strftime(log_date_format))


# 2. Configure the Root Logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.handlers.clear()


# 3. Setup TimedRotatingFileHandler
file_handler = TimedRotatingFileHandler(
	filename=log_file_path,
	when='midnight',
	interval=1,
	backupCount=7,
	encoding='utf-8'
)

def namer(_): return str(log_dir / time.strftime(log_date_format))

file_handler.namer = namer
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(JsonFormatter())
root_logger.addHandler(file_handler)


# 4. Setup Console Handler
console_handler = RichHandler(
	level=logging.INFO,
	rich_tracebacks=True,
	tracebacks_show_locals=True,
	markup=True
)
root_logger.addHandler(console_handler)


# 5. Other setup
if json_file: json_file.cache.start_gc()
setup_directory()
load_config()


def stop():
	if json_file: json_file.cache.stop_gc()
