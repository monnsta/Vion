import asyncio
import inspect
import io
import logging
import re
import traceback
import types
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Callable, Optional

from core.lib.dataclass import Data, Repr
from core.lib.utils import create_id
from meta import config


log = logging.getLogger(__name__)


ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

status = Data(
	PENDING   = Repr("PENDING", 1),
	RUNNING   = Repr("RUNNING", 2),
	COMPLETED = Repr("COMPLETED", 3),
	FAILED    = Repr("FAILED", 4),
	CANCELLED = Repr("CANCELLED", 5),
	TIMED_OUT = Repr("TIMED_OUT", 6)
)

def extract(text: str) -> Data:
	log.debug("Extracting code and monologue from text")
	py = re.search(
		r"<code>\s*(.*?)\s*</code>",
		text, re.DOTALL
	)
	mo = re.search(
		r"<monologue>\s*(.*?)\s*</monologue>",
		text, re.DOTALL
	)
	log.debug(f"Extracted Code:\n{py}\n\nExtracted Monologue:\n{mo}")

	return Data(
		code = py.group(1).strip() if py else "",
		monologue = mo.group(1).strip() if mo else ""
	)

class StreamInterceptor(io.StringIO):
	def __init__(self, callback: Optional[Callable[[str], None]] = None):
		super().__init__()
		self._callback = callback

	def write(self, s: str) -> int:
		res = super().write(s)
		if self._callback:
			self._callback(s)
		return res

class Code:
	tasks = Data()

	def __init__(self, code_str: str, on_stdout: Optional[Callable[[str], None]] = None, on_stderr: Optional[Callable[[str], None]] = None):
		self.code_str = code_str
		self.execution_id = f"EI{str(create_id())}"
		self.data = Data(
			status = status.PENDING,
			stdout = "",
			stderr  = "",
			result = None,
			error = None
		)
		self._task: Optional[asyncio.Task] = None

		self._stdout_buf = StreamInterceptor(on_stdout)
		self._stderr_buf = StreamInterceptor(on_stderr)

		Code.tasks.set(self.execution_id, self)
		log.debug(f"Code task initialized: {self.execution_id}")

	@staticmethod
	def get_task(execution_id: str) -> Optional['Code']:
		return getattr(Code.tasks, execution_id, None)

	async def execute(self, timeout: Optional[float] = None, **context_vars: Any) -> asyncio.Task:
		if self._task and not self._task.done():
			log.warning(f"Execution attempt on already running task: {self.execution_id}")
			raise RuntimeError("This code block is already running. Call stop() first.")

		self._reset_state()
		self.data.status = status.RUNNING
		log.info(f"Starting execution for ID: {self.execution_id}")

		user_module = types.ModuleType(self.execution_id)
		safe_builtins = dict(config.sandbox.allowed_builtins)
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
			try:
				if timeout:
					log.debug(f"Executing ID {self.execution_id} with {timeout}s timeout")
					with redirect_stdout(self._stdout_buf), redirect_stderr(self._stderr_buf):
						self.data.result = await asyncio.wait_for(
							main_func(**context_vars),
							timeout=timeout
						)
				else:
					with redirect_stdout(self._stdout_buf), redirect_stderr(self._stderr_buf):
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

	async def wait(self) -> Data:
		if self._task and not self._task.done():
			log.debug(f"Waiting for task ID: {self.execution_id}")
			await self._task
		self._sync_data()
		return self.data

	def get_output(self) -> Data:
		self._sync_data()
		return self.data

	def _sync_data(self):
		self.data.stdout = ANSI_ESCAPE.sub('', self._stdout_buf.getvalue())
		self.data.stderr = ANSI_ESCAPE.sub('', self._stderr_buf.getvalue())
		log.debug(f"Synced buffers for ID: {self.execution_id} (stdout: {len(self.data.stdout)} bytes)")

	def _reset_state(self):
		log.debug(f"Resetting state for ID: {self.execution_id}")
		self.data = Data(
			status = status.PENDING,
			stdout = "",
			stderr  = "",
			result = None,
			error = None
		)
		self._stdout_buf.seek(0)
		self._stdout_buf.truncate(0)
		self._stderr_buf.seek(0)
		self._stderr_buf.truncate(0)


__all__ = ('status', 'extract', 'Code')
