"""
Subprocess supervisor and crash monitoring loop for Vion.
"""

import os
import signal
import subprocess
import sys
import time
from rich.console import Console

console = Console()


def run_supervisor(max_crashes: int = 3, crash_window: int = 60, restart_wait: float = 2.0) -> None:
	"""
	Execute bot inside a supervisor loop that monitors exit codes and crash frequencies.
	"""
	crash_timestamps: list[float] = []
	cli_args = [sys.executable, "-m", "vion", "--child"] + [a for a in sys.argv[1:] if a not in ("-s", "--supervise")]

	console.print("[bold cyan]● Supervisor active. Spawning bot runtime...[/bold cyan]\n")

	while True:
		try:
			process = subprocess.Popen(cli_args, start_new_session=True)

			def signal_handler(signum, _):
				console.print("\n[yellow]Supervisor received termination signal. Stopping bot...[/yellow]")
				try:
					os.killpg(os.getpgid(process.pid), signal.SIGTERM)
					process.wait(timeout=5)
				except (subprocess.TimeoutExpired, ProcessLookupError, OSError):
					try:
						os.killpg(os.getpgid(process.pid), signal.SIGKILL)
					except OSError:
						pass
				sys.exit(130 if signum == signal.SIGINT else 143)

			signal.signal(signal.SIGINT, signal_handler)
			signal.signal(signal.SIGTERM, signal_handler)

			code = process.wait()

		except KeyboardInterrupt:
			break

		if code == 0:
			console.print("[green]✓ Clean exit detected. Stopping supervisor.[/green]")
			break
		elif code == 10:
			console.print("[bold red]✗ Critical configuration error (Exit code 10). Halting supervisor.[/bold red]")
			sys.exit(10)
		elif code == 42:
			console.print("[bold yellow]⟳ Immediate restart requested (Exit code 42)...[/bold yellow]")
			time.sleep(1.0)
			continue
		elif code in (130, 143):
			console.print("[yellow]Process interrupted by user signal. Exiting supervisor.[/yellow]")
			break
		else:
			console.print(f"[bold red]! Bot crashed with exit code {code}.[/bold red]")
			now = time.time()
			crash_timestamps = [ts for ts in crash_timestamps if now - ts <= crash_window]
			crash_timestamps.append(now)

			if len(crash_timestamps) > max_crashes:
				console.print(
					f"\n[bold red]FATAL: Reached {len(crash_timestamps)} crashes in {crash_window}s. "
					"Supervisor halting to prevent crash loop.[/bold red]"
				)
				sys.exit(1)

			console.print(
				f"[dim white]Restarting in {restart_wait}s "
				f"(Failure {len(crash_timestamps)}/{max_crashes})...[/dim white]"
			)
			time.sleep(restart_wait)
