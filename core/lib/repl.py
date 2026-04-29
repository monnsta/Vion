import asyncio
import ast
import code
import inspect
import logging
import os
import textwrap
import traceback


log = logging.getLogger(__name__)

try:
	import readline
except ImportError:
	log.warning("Readline doesn't seem to be available on this system, some features may be limited")


class AsyncREPL:
	def __init__(self, env=None):
		self.env = env or {}
		self.buffer = []

	async def start(self):
		loop = asyncio.get_running_loop()
		log.info("Standalone Async REPL session active")

		while True:
			try:
				prompt = "··· " if self.buffer else "</> "
				line = await loop.run_in_executor(None, input, prompt)
			except (EOFError, asyncio.CancelledError):
				break

			if not self.buffer and line.strip().lower() in ("exit", "quit", "stop"):
				break

			if not self.buffer and line.startswith(":"):
				os.system(line[1:])
				continue

			self.buffer.append(line)
			source = "\n".join(self.buffer)

			try:
				compiled = code.compile_command(source, symbol="exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
			except (SyntaxError, OverflowError, ValueError):
				traceback.print_exc()
				self.buffer = []
				continue

			if compiled is None:
				continue

			self.buffer = []
			await self._execute(source)

	async def _execute(self, source):
		try:
			result = eval(source, self.env)
			if inspect.isawaitable(result):
				result = await result
			if result is not None:
				print(result)
		except SyntaxError:
			wrapped_code = f"async def _repl_coro():\n{textwrap.indent(source, '	')}"
			try:
				exec(wrapped_code, self.env)
				result = await self.env['_repl_coro']()
				if result is not None:
					print(result)
			except Exception:
				traceback.print_exc()
		except Exception:
			traceback.print_exc()
