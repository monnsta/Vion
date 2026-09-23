"""
Dynamic Python code execution sandbox and task orchestration manager.

Provides safe execution contexts, log stream capture, and XML-style block extraction.
"""

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

from vion.infrastructure.utils import create_id
from vion.infrastructure.logging import code_log_stream
from vion.config import config


log = logging.getLogger("exec_code")


ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class status(enum.Enum):
	"""
	Enumeration representing execution state transitions for asynchronous tasks.
	"""

	PENDING = "PENDING"
	RUNNING = "RUNNING"
	COMPLETED = "COMPLETED"
	FAILED = "FAILED"
	CANCELLED = "CANCELLED"
	TIMED_OUT = "TIMED_OUT"

	def __str__(self) -> str:
		"""Return string value of state."""
		return self.value


@dataclass
class ExecutionResult:
	"""
	Container capturing the terminal state, logs, return values, and errors of a code run.

	Attributes:
		status: Current execution status enum state.
		logs: Stripped stdout/logging buffer text output.
		result: Any return value passed back by the executed module's main function.
		error: Traceback string or timeout/cancellation error message if failed.
	"""

	status: status = status.PENDING
	logs: str = ""
	result: Any = None
	error: str | None = None


@dataclass
class ExtractedCode:
	"""
	Container holding code and note blocks extracted from raw markup strings.

	Attributes:
		code: The unescaped Python code string.
		note: Accompanying explanation or note string.
	"""

	code: str
	note: str


def extract(text: str) -> ExtractedCode:
	"""
	Extract Python code and notes wrapped in <code> and <note> XML tag blocks.

	Args:
		text: Raw string containing tagged block elements.

	Returns:
		ExtractedCode dataclass containing unescaped code and note strings.
	"""
	code_match = re.search(r"<code>\s*(.*?)\s*</code>", text, re.DOTALL)
	note_match = re.search(r"<note>\s*(.*?)\s*</note>", text, re.DOTALL)

	code = html.unescape(code_match.group(1).strip()) if code_match else ""
	note = html.unescape(note_match.group(1).strip()) if note_match else ""

	log.debug(f"Extracted Code:\n{code}\n\nExtracted Note:\n{note}")

	return ExtractedCode(code=code, note=note)


class Code:
	"""
	Dynamic execution context manager tracking sandboxed async task runs.

	Attributes:
		tasks: Global register tracking Code instances by unique execution ID.
		code_str: Source Python code string to run.
		execution_id: Unique string tracking identifier for this execution run.
		data: ExecutionResult instance holding current state, logs, and output.
	"""

	tasks: dict[str, "Code"] = {}

	def __init__(self, code_str: str) -> None:
		"""
		Initialize a Code task execution context.

		Args:
			code_str: Raw Python code string containing an async def main(**kwargs) entrypoint.
		"""
		self.code_str = code_str
		self.execution_id = f"EI{str(create_id())}"
		self.data = ExecutionResult()
		self._task: asyncio.Task[None] | None = None
		self._log_buf = io.StringIO()

		Code.tasks[self.execution_id] = self
		log.debug(f"Code task initialized: {self.execution_id}")

	@staticmethod
	def get_task(execution_id: str) -> "Code | None":
		"""
		Retrieve active or past task instance by execution ID.

		Args:
			execution_id: Unique string execution identifier.

		Returns:
			Target Code task instance if found, else None.
		"""
		return Code.tasks.get(execution_id, None)

	async def execute(
		self, timeout: float | None = None, **context_vars: Any
	) -> asyncio.Task[None]:
		"""
		Compile and dispatch code string execution as an asynchronous task inside a sandboxed module.

		Args:
			timeout: Optional execution timeout limit in seconds.
			**context_vars: Keyword arguments passed directly to the main() function context.

		Returns:
			Asyncio task object tracking background execution.

		Raises:
			RuntimeError: If execution is attempted while a task is already running.
			ValueError: If code lacks a valid async main function definition.
		"""
		if self._task and not self._task.done():
			log.warning(
				f"Execution attempt on already running task: {self.execution_id}"
			)
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
				raise ValueError(
					"User code must define an 'async def main(**kwargs)' function."
				)
			if not inspect.iscoroutinefunction(main_func):
				raise ValueError("'main' must be an async function.")

		except Exception as e:
			log.error(f"Setup error for ID {self.execution_id}: {str(e)}")
			self.data.error = f"Compilation/Setup Error:\n{traceback.format_exc()}"
			self.data.status = status.FAILED
			raise

		async def task_wrapper() -> None:
			token = code_log_stream.set(self._log_buf)
			try:
				if timeout:
					log.debug(
						f"Executing ID {self.execution_id} with {timeout}s timeout"
					)
					self.data.result = await asyncio.wait_for(
						main_func(**context_vars), timeout=timeout
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
		"""
		Cancel running execution task safely.

		Returns:
			Tuple containing (success_boolean, status_message_string).
		"""
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
		"""
		Await current execution task completion and return updated results container.

		Returns:
			ExecutionResult dataclass instance.
		"""
		if self._task and not self._task.done():
			log.debug(f"Waiting for task ID: {self.execution_id}")
			await self._task
		self._sync_data()
		return self.data

	def get_output(self) -> ExecutionResult:
		"""
		Fetch execution state and formatted log buffers synchronously without awaiting task.

		Returns:
			ExecutionResult dataclass instance with current captured logs.
		"""
		self._sync_data()
		return self.data

	def _sync_data(self) -> None:
		"""Flush buffer and strip ANSI control sequences from log strings."""
		self.data.logs = ANSI_ESCAPE.sub("", self._log_buf.getvalue())
		log.debug(
			f"Synced buffers for ID: {self.execution_id} (logs: {len(self.data.logs)} bytes)"
		)

	def _reset_state(self) -> None:
		"""Reset state parameters, output payload, and log buffers prior to re-running."""
		log.debug(f"Resetting state for ID: {self.execution_id}")
		self.data = ExecutionResult()
		self._log_buf.seek(0)
		self._log_buf.truncate(0)


__all__ = ("status", "extract", "Code")
