"""
Application execution entry point.

Triggers dependency checks, environment setup, CLI parsing,
setup wizard, and bot execution.
"""

import argparse
import os
import sys

from vion.installer import (
	clean_cache,
	ensure_dependencies,
	find_project_root,
	setup_platform_env,
)


def main() -> None:
	"""
	Main CLI entry point for python -m vion or vion execution.
	"""
	root_dir = find_project_root()
	root_dir.mkdir(parents=True, exist_ok=True)

	os.environ["VION_ROOT_DIR"] = str(root_dir)

	setup_platform_env()
	ensure_dependencies(root_dir)

	parser = argparse.ArgumentParser(
		prog="vion",
		description="Vion AI Discord Bot Execution Engine",
		add_help=True,
	)

	parser.add_argument(
		"-s",
		"--supervise",
		action="store_true",
		help="Run with supervisor and crash restart loop",
	)

	parser.add_argument(
		"-c",
		"--setup",
		action="store_true",
		help="Force interactive TUI setup wizard",
	)

	parser.add_argument(
		"-x",
		"--clean",
		action="store_true",
		help="Clean __pycache__ and compiled python files",
	)

	parser.add_argument(
		"--check",
		action="store_true",
		help="Check runtime environment without launching bot",
	)

	parser.add_argument(
		"--child",
		action="store_true",
		help=argparse.SUPPRESS,
	)

	args, _ = parser.parse_known_args()

	if args.clean:
		clean_cache(root_dir)

		if (
			not args.supervise
			and not args.setup
			and not args.check
			and len(sys.argv) == 2
		):
			return

	env_file = root_dir / ".env"

	needs_setup = (
		args.setup
		or not env_file.exists()
	)

	if needs_setup and not args.child:
		from vion.tui import run_setup_wizard

		success = run_setup_wizard(force=args.setup)

		if not success:
			sys.exit(130)

	if args.check:
		from rich.console import Console

		console = Console()
		console.print(
			"[bold green]✓ Environment check passed.[/bold green]"
		)
		return

	if args.supervise and not args.child:
		from vion.supervisor import run_supervisor

		run_supervisor()
		return

	from vion.bot import run

	run()


if __name__ == "__main__":
	try:
		main()
	except KeyboardInterrupt:
		sys.exit(130)
