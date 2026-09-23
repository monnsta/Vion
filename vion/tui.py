"""
Interactive Terminal User Interface (TUI) for Vion initialization and secrets setup.
"""

import secrets

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from vion.config import storage


console = Console()


def render_banner() -> None:
	"""
	Display minimalist monocromatic startup banner.
	"""
	banner = Text()
	banner.append("██┐   ██┐██┐ ██████┐ ███┐   ██┐\n", style="bold cyan")
	banner.append("██│   ██│██│██┌───██┐████┐  ██│\n", style="bold cyan")
	banner.append("██│   ██│██│██│   ██│██┌██┐ ██│\n", style="bold cyan")
	banner.append("└██┐ ██┌┘██│██│   ██│██│└██┐██│\n", style="bold blue")
	banner.append(" └████┌┘ ██│└██████┌┘██│ └████│\n", style="bold blue")
	banner.append("  └───┘  └─┘ └─────┘ └─┘  └───┘\n", style="bold blue")

	panel = Panel(
		banner,
		subtitle="[bold dim white]First-Run Setup Wizard[/bold dim white]",
		border_style="bold blue",
		expand=False,
	)
	console.print("\n", panel)


def run_setup_wizard(force: bool = False) -> bool:
	"""
	Launch guided setup wizard to configure .env and runtime files.

	Args:
		root_dir: Path to project root.
		force: Re-run setup even if .env already exists.

	Returns:
		True if setup was completed or skipped successfully, False if aborted.
	"""
	render_banner()

	try:
		if storage.env.exists() and not force:
			console.print(
				"[dim white]Configuration file (.env) already exists.[/dim white]"
			)
			if not Confirm.ask(
				"[bold cyan]Would you like to reconfigure environment secrets?[/bold cyan]",
				default=False,
			):
				return True

		console.print(
			"\n[bold cyan]=== Step 1: Environment & Secrets Configuration ===[/bold cyan]\n"
		)

		existing_discord = ""
		existing_gemini = ""
		existing_assembly = ""
		existing_hmac = ""

		if storage.env.exists():
			try:
				with open(storage.env, "r", encoding="utf-8") as f:
					data = yaml.safe_load(f) or {}
					existing_discord = data.get("discord", "")
					existing_gemini = data.get("gemini", "")
					existing_assembly = data.get("assemblyai", "")
					existing_hmac = data.get("hmac", "")
			except Exception:
				pass

		discord_token = Prompt.ask(
			"[bold cyan]Discord Bot Token[/bold cyan]",
			password=True,
			default=existing_discord if existing_discord else None,
		)

		gemini_key = Prompt.ask(
			"[bold cyan]Gemini API Key[/bold cyan] [dim](optional)[/dim]",
			password=True,
			default=existing_gemini if existing_gemini else "",
		)

		assembly_key = Prompt.ask(
			"[bold cyan]AssemblyAI API Key[/bold cyan] [dim](optional)[/dim]",
			password=True,
			default=existing_assembly if existing_assembly else "",
		)

		default_hmac = existing_hmac if existing_hmac else secrets.token_hex(32)
		hmac_secret = Prompt.ask(
			"[bold cyan]HMAC Secret Key[/bold cyan] [dim](auto-generated)[/dim]",
			default=default_hmac,
		)

	except (KeyboardInterrupt, EOFError):
		console.print("\n\n[bold yellow]Setup cancelled by user.[/bold yellow]")
		return False

	env_content = (
		f'discord: "{discord_token.strip() if discord_token else discord_token}"\n'
		f'gemini: "{gemini_key.strip()}"\n'
		f'assemblyai: "{assembly_key.strip()}"\n'
		f'hmac: "{hmac_secret.strip()}"\n'
	)

	try:
		with open(storage.env, "w", encoding="utf-8") as f:
			f.write(env_content)
		console.print("\n[bold green]✓ Saved secrets to .env[/bold green]")
	except Exception as e:
		console.print(f"\n[bold red]✗ Failed to write .env file: {e}[/bold red]")
		return False

	console.print("\n[bold cyan]=== Step 2: System Configuration ===[/bold cyan]\n")
	if not storage.config.exists():
		console.print(
			f"[bold red]✗ {storage.config} missing. Please restore the file or pull from repo.[/bold red]"
		)

	table = Table(title="Setup Summary", border_style="dim")
	table.add_column("Parameter", style="cyan")
	table.add_column("Status", style="bold")

	table.add_row(
		"Discord Token",
		"[green]Configured[/green]" if discord_token else "[red]Missing[/red]",
	)
	table.add_row(
		"Gemini API Key",
		"[green]Configured[/green]"
		if gemini_key
		else "[dim yellow]Not Set[/dim yellow]",
	)
	table.add_row(
		"AssemblyAI Key",
		"[green]Configured[/green]"
		if assembly_key
		else "[dim yellow]Not Set[/dim yellow]",
	)
	table.add_row("HMAC Secret", "[green]Generated[/green]")
	table.add_row(
		f"{storage.config.name} File",
		"[green]Present[/green]" if storage.config.exists() else "[red]Missing[/red]",
	)

	console.print("\n", table, "\n")
	return True
