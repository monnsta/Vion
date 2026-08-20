import asyncio
import inspect
import io
import logging
import re
import html
import traceback
import types
import enum
from typing import Any
from dataclasses import dataclass

from core.lib.utils import create_id
from core.lib.logging import code_log_stream
from meta import config


log = logging.getLogger(__name__)


ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


class status(enum.Enum):
	PENDING   = "PENDING"
	RUNNING   = "RUNNING"
	COMPLETED = "COMPLETED"
	FAILED    = "FAILED"
	CANCELLED = "CANCELLED"
	TIMED_OUT = "TIMED_OUT"

	def __str__(self) -> str:
		return self.value


@dataclass
class ExecutionResult:
	status: status = status.PENDING
	logs: str = ""
	result: Any = None
	error: str | None = None


@dataclass
class ExtractedCode:
	code: str
	note: str


def extract(text: str) -> ExtractedCode:
	code_match = re.search(r"<code>\s*(.*?)\s*</code>", text, re.DOTALL)
	note_match = re.search(r"<note>\s*(.*?)\s*</note>", text, re.DOTALL)

	code = html.unescape(code_match.group(1).strip()) if code_match else ""
	note = html.unescape(note_match.group(1).strip()) if note_match else ""

	log.debug(f"Extracted Code:\n{code}\n\nExtracted Note:\n{note}")

	return ExtractedCode(code=code, note=note)


class Code:
	tasks: dict[str, 'Code'] = {}

	def __init__(self, code_str: str):
		self.code_str = code_str
		self.execution_id = f"EI{str(create_id())}"
		self.data = ExecutionResult()
		self._task: asyncio.Task | None = None
		self._log_buf = io.StringIO()

		Code.tasks[self.execution_id] = self
		log.debug(f"Code task initialized: {self.execution_id}")

	@staticmethod
	def get_task(execution_id: str) -> 'Code | None':
		return Code.tasks.get(execution_id, None)

	async def execute(self, timeout: float | None = None, **context_vars: Any) -> asyncio.Task:
		if self._task and not self._task.done():
			log.warning(f"Execution attempt on already running task: {self.execution_id}")
			raise RuntimeError("This code block is already running. Call stop() first.")

		self._reset_state()
		self.data.status = status.RUNNING
		log.info(f"Starting execution for ID: {self.execution_id}")

		user_module = types.ModuleType(self.execution_id)
		safe_builtins = config.sandbox.allowed_builtins.copy()
		setattr(user_module, "__builtins__", safe_builtins)

		try:
			exec(self.code_str, user_module.__dict__)
			main_func = getattr(user_module, "main", None)

			if not main_func:
				raise ValueError("User code must define an 'async def main(**kwargs)' function.")
			if not inspect.iscoroutinefunction(main_func):
				raise ValueError("'main' must be an async function.")

		except Exception as e:
			log.error(f"Setup error for ID {self.execution_id}: {str(e)}")
			self.data.error = f"Compilation/Setup Error:\n{traceback.format_exc()}"
			self.data.status = status.FAILED
			raise

		async def task_wrapper():
			token = code_log_stream.set(self._log_buf)
			try:
				if timeout:
					log.debug(f"Executing ID {self.execution_id} with {timeout}s timeout")
					self.data.result = await asyncio.wait_for(
						main_func(**context_vars),
						timeout=timeout
					)
				else:
					self.data.result = await main_func(**context_vars)

				self.data.status = status.COMPLETED
				log.info(f"Execution completed for ID: {self.execution_id}")

			except asyncio.TimeoutError:
				log.warning(f"Execution timed out for ID: {self.execution_id}")
				self.data.error = f"Execution timed out after {timeout} seconds."
				self.data.status = status.TIMED_OUT

			except asyncio.CancelledError:
				log.info(f"Execution cancelled for ID: {self.execution_id}")
				self.data.status = status.CANCELLED

			except Exception as e:
				err_msg = traceback.format_exc()
				log.error(f"Runtime error for ID {self.execution_id}:\n{e}")
				self.data.error = str(err_msg)
				self.data.status = status.FAILED

			finally:
				code_log_stream.reset(token)
				self._sync_data()

		self._task = asyncio.create_task(task_wrapper())
		return self._task

	async def stop(self) -> tuple[bool, str]:
		if not self._task:
			log.debug(f"Stop called on null task: {self.execution_id}")
			return False, "No active task to stop."
		if self._task.done():
			log.debug(f"Stop called on finished task: {self.execution_id}")
			return False, f"Task already finished with status: {self.data.status}."

		log.info(f"Cancelling task ID: {self.execution_id}")
		self._task.cancel()
		try:
			await self._task
		except asyncio.CancelledError:
			pass

		return True, "Task stopped successfully."

	async def wait(self) -> ExecutionResult:
		if self._task and not self._task.done():
			log.debug(f"Waiting for task ID: {self.execution_id}")
			await self._task
		self._sync_data()
		return self.data

	def get_output(self) -> ExecutionResult:
		self._sync_data()
		return self.data

	def _sync_data(self):
		self.data.logs = ANSI_ESCAPE.sub('', self._log_buf.getvalue())
		log.debug(f"Synced buffers for ID: {self.execution_id} (logs: {len(self.data.logs)} bytes)")

	def _reset_state(self):
		log.debug(f"Resetting state for ID: {self.execution_id}")
		self.data = ExecutionResult()
		self._log_buf.seek(0)
		self._log_buf.truncate(0)


__all__ = ('status', 'extract', 'Code')
