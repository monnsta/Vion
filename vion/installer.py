"""
Runtime dependency and platform environment manager.

The installer is intentionally self-bootstrapping:

- detects the host platform
- discovers the project root
- creates/configures Vion's virtual environment
- prefers native packages where appropriate
- installs Python dependencies
- verifies imports before allowing the application to start
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import os
import platform
import re
import shutil
import subprocess
import sys
import tomllib
import venv

from pathlib import Path


# Platform detection
def is_termux() -> bool:
	"""Return whether Vion is running inside Termux."""
	prefix = os.environ.get("PREFIX", "")

	return (
		"com.termux" in prefix
		or Path("/data/data/com.termux").exists()
	)


def is_windows() -> bool:
	"""Return whether Vion is running on Windows."""
	return platform.system().lower() == "windows"


def is_linux() -> bool:
	"""Return whether Vion is running on Linux."""
	return platform.system().lower() == "linux"


def is_macos() -> bool:
	"""Return whether Vion is running on macOS."""
	return platform.system().lower() == "darwin"


def architecture() -> str:
	"""Return a normalized host architecture name."""
	machine = platform.machine().lower()

	return {
		"x86_64": "x86_64",
		"amd64": "x86_64",
		"aarch64": "aarch64",
		"arm64": "aarch64",
		"armv7l": "armv7",
		"armv7": "armv7",
		"i386": "x86",
		"i686": "x86",
	}.get(machine, machine)


# Generic process helpers
def run(
	command: list[str],
	*,
	check: bool = True,
	quiet: bool = False,
	env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
	"""Run a subprocess while preserving the current environment."""
	if not quiet:
		print(f"[*] {' '.join(command)}")

	return subprocess.run(
		command,
		check=check,
		env=env,
		text=True,
	)


def command_exists(name: str) -> bool:
	"""Return whether an executable exists in PATH."""
	return shutil.which(name) is not None


# Project discovery
def find_project_root(start: Path | None = None) -> Path:
	"""
	Find the project root by walking upwards until pyproject.toml is found.
	"""
	current = (start or Path(__file__)).resolve()

	if current.is_file():
		current = current.parent

	for directory in (current, *current.parents):
		if (directory / "pyproject.toml").is_file():
			return directory

	raise RuntimeError(
		"Could not locate pyproject.toml. "
		"Vion must be run from a source tree containing pyproject.toml."
	)


# Python environment
def in_virtualenv() -> bool:
	"""Return whether the current interpreter is running inside a venv."""
	return sys.prefix != sys.base_prefix


def venv_dir(root_dir: Path) -> Path:
	"""Return Vion's virtual environment directory."""
	return root_dir / ".venv"


def venv_python(root_dir: Path) -> Path:
	"""Return the Python executable belonging to Vion's venv."""
	env_dir = venv_dir(root_dir)

	if is_windows():
		return env_dir / "Scripts" / "python.exe"

	return env_dir / "bin" / "python"


def read_pyvenv_config(env_dir: Path) -> dict[str, str]:
	"""Read pyvenv.cfg into a normalized dictionary."""
	config_file = env_dir / "pyvenv.cfg"

	if not config_file.exists():
		return {}

	values: dict[str, str] = {}

	try:
		for line in config_file.read_text(encoding="utf-8").splitlines():
			if "=" not in line:
				continue

			key, value = line.split("=", 1)
			values[key.strip().lower()] = value.strip()

	except OSError:
		return {}

	return values


def enable_system_site_packages(env_dir: Path) -> bool:
	"""
	Enable access to the base interpreter's site-packages.

	This is required on Termux when Vion uses Termux-provided native
	Python packages from inside the virtual environment.
	"""
	config_file = env_dir / "pyvenv.cfg"

	if not config_file.exists():
		return False

	try:
		lines = config_file.read_text(encoding="utf-8").splitlines()
		new_lines: list[str] = []
		found = False

		for line in lines:
			if line.lower().startswith("include-system-site-packages"):
				new_lines.append("include-system-site-packages = true")
				found = True
			else:
				new_lines.append(line)

		if not found:
			new_lines.append("include-system-site-packages = true")

		config_file.write_text(
			"\n".join(new_lines) + "\n",
			encoding="utf-8",
		)

		return True

	except OSError:
		return False


def create_virtualenv(root_dir: Path) -> None:
	"""Create Vion's virtual environment."""
	env_dir = venv_dir(root_dir)

	print(f"[*] Creating Vion virtual environment at {env_dir}")

	builder = venv.EnvBuilder(
		system_site_packages=is_termux(),
		clear=False,
		with_pip=True,
	)

	builder.create(env_dir)


def ensure_virtualenv(root_dir: Path) -> bool:
	"""
	Ensure Vion has a functional virtual environment.

	Returns True when the current process must restart inside the venv.
	"""
	env_dir = venv_dir(root_dir)

	if not env_dir.exists():
		create_virtualenv(root_dir)
		return True

	if not venv_python(root_dir).exists():
		print("[!] Existing .venv is incomplete. Rebuilding it...")

		shutil.rmtree(env_dir, ignore_errors=True)
		create_virtualenv(root_dir)

		return True

	if is_termux():
		config = read_pyvenv_config(env_dir)

		if config.get("include-system-site-packages", "").lower() != "true":
			print(
				"[*] Configuring Termux venv to use native Termux packages..."
			)

			if not enable_system_site_packages(env_dir):
				raise RuntimeError(
					"Could not enable system-site-packages in .venv."
				)

			return True

	return False


def restart_inside_venv(root_dir: Path) -> None:
	"""Replace the current process with Vion's venv interpreter."""
	python = venv_python(root_dir)

	if not python.exists():
		raise RuntimeError(
			f"Vion Python interpreter does not exist: {python}"
		)

	print(f"[*] Restarting Vion using {python}")

	os.execv(
		str(python),
		[
			str(python),
			"-m",
			"vion",
			*sys.argv[1:],
		],
	)


# Termux package management
def termux_package_available(package: str) -> bool:
	"""
	Return whether an exact package name is available to Termux.

	pkg search is used rather than assuming a package exists.
	"""
	if not command_exists("pkg"):
		return False

	result = subprocess.run(
		["pkg", "search", f"^{re.escape(package)}$"],
		stdout=subprocess.PIPE,
		stderr=subprocess.DEVNULL,
		text=True,
	)

	if result.returncode != 0:
		return False

	for line in result.stdout.splitlines():
		name = line.split("/", 1)[0].strip()

		if name == package:
			return True

	return False


def termux_package_installed(package: str) -> bool:
	"""Return whether a Termux package is already installed."""
	if not command_exists("pkg"):
		return False

	result = subprocess.run(
		["pkg", "list-installed"],
		stdout=subprocess.PIPE,
		stderr=subprocess.DEVNULL,
		text=True,
	)

	if result.returncode != 0:
		return False

	for line in result.stdout.splitlines():
		if line.startswith(package + "/"):
			return True

	return False


def install_termux_packages(
	packages: list[str],
	*,
	required: bool = False,
) -> list[str]:
	"""
	Install only packages actually available from Termux.

	Returns the packages that were successfully selected.
	"""
	if not packages:
		return []

	available: list[str] = []
	unavailable: list[str] = []

	for package in packages:
		if termux_package_available(package):
			available.append(package)
		else:
			unavailable.append(package)

	if unavailable:
		print(
			"[i] Termux packages unavailable on this installation: "
			+ ", ".join(unavailable)
		)

	if not available:
		if required:
			raise RuntimeError(
				"No required Termux packages are available: "
				+ ", ".join(packages)
			)

		return []

	missing = [
		package
		for package in available
		if not termux_package_installed(package)
	]

	if not missing:
		return available

	try:
		run(["pkg", "install", "-y", *missing])

	except subprocess.CalledProcessError:
		print(
			"[!] Termux package installation failed. "
			"Attempting to repair the package database..."
		)

		run(["pkg", "upgrade", "-y"])

		run(["pkg", "install", "-y", *missing])

	return available


def ensure_termux_repo(name: str) -> None:
	"""Install a Termux repository package if it is available."""
	if termux_package_installed(name):
		return

	if termux_package_available(name):
		install_termux_packages([name])


# Termux native Python dependencies
TERMUX_NATIVE_PACKAGES: dict[str, tuple[str, ...]] = {
	"numpy": (
		"python-numpy",
	),
	"matplotlib": (
		"matplotlib",
		"python-matplotlib",
	),
	"pillow": (
		"python-pillow",
	),
	"cryptography": (
		"python-cryptography",
	),
	"pynacl": (
		"python-pynacl",
	),
	"pyyaml": (
		"python-pyyaml",
	),
	"orjson": (
		"python-orjson",
	),
}


def normalized_name(name: str) -> str:
	"""Normalize a Python distribution name."""
	return name.lower().replace("_", "-")


def native_package_candidates(requirement: str) -> tuple[str, ...]:
	"""Return possible Termux package names for a Python dependency."""
	name = normalized_name(package_name(requirement))

	return TERMUX_NATIVE_PACKAGES.get(name, ())


def install_native_python_dependencies(dependencies: list[str]) -> set[str]:
	"""
	Install native Python dependencies through Termux when available.

	Returns the distributions successfully delegated to Termux.
	"""
	if not is_termux():
		return set()

	needs_native_repo = False

	for dependency in dependencies:
		if native_package_candidates(dependency):
			candidates = native_package_candidates(dependency)

			if not any(
				termux_package_available(candidate)
				for candidate in candidates
			):
				needs_native_repo = True

	if needs_native_repo:
		print("[*] Checking TUR for additional native Python packages...")
		ensure_termux_repo("tur-repo")

		run(["pkg", "update", "-y"])

	installed: set[str] = set()

	for dependency in dependencies:
		candidates = native_package_candidates(dependency)

		if not candidates:
			continue

		selected = next(
			(
				candidate
				for candidate in candidates
				if termux_package_available(candidate)
			),
			None,
		)

		if selected is None:
			continue

		install_termux_packages([selected])
		installed.add(normalized_name(package_name(dependency)))

	return installed


# Termux build environment
TERMUX_BUILD_PACKAGES: dict[str, tuple[str, ...]] = {
	"rust": (
		"rust",
	),
	"c": (
		"clang",
		"llvm",
		"binutils",
		"make",
		"pkg-config",
	),
	"cmake": (
		"cmake",
		"ninja",
	),
	"crypto": (
		"openssl",
		"libffi",
		"libsodium",
	),
	"image": (
		"zlib",
		"libjpeg-turbo",
		"freetype",
		"libpng",
	),
}


def setup_termux_build_environment(dependencies: list[str]) -> None:
	"""
	Install only the build tools required by unresolved native dependencies.
	"""
	if not is_termux():
		return

	missing_names = {
		normalized_name(package_name(dependency))
		for dependency in dependencies
	}

	build_groups: set[str] = set()

	if "orjson" in missing_names:
		build_groups.update(("rust", "c"))

	if "pynacl" in missing_names:
		build_groups.update(("c", "crypto"))

	if "cryptography" in missing_names:
		build_groups.update(("c", "crypto"))

	if "pyyaml" in missing_names:
		build_groups.add("c")

	if "matplotlib" in missing_names:
		build_groups.update(("c", "cmake", "image"))

	if not build_groups:
		return

	packages: list[str] = []

	for group in sorted(build_groups):
		packages.extend(TERMUX_BUILD_PACKAGES[group])

	install_termux_packages(list(dict.fromkeys(packages)))


def configure_termux_build_environment() -> None:
	"""Configure compiler/build environment for Termux."""
	if not is_termux():
		return

	os.environ.setdefault("MATHLIB", "m")
	os.environ.setdefault("LDFLAGS", "-lm")

	if command_exists("rustc"):
		result = subprocess.run(
			["rustc", "-vV"],
			stdout=subprocess.PIPE,
			stderr=subprocess.DEVNULL,
			text=True,
		)

		for line in result.stdout.splitlines():
			if line.startswith("host: "):
				os.environ.setdefault(
					"CARGO_BUILD_TARGET",
					line.removeprefix("host: ").strip(),
				)
				break

	if "CARGO_BUILD_JOBS" not in os.environ:
		try:
			cpu_count = len(os.sched_getaffinity(0))
		except (AttributeError, OSError):
			cpu_count = os.cpu_count() or 4

		os.environ["CARGO_BUILD_JOBS"] = str(cpu_count)

	# Needed by some PyO3-based packages when the installed Python
	# is newer than the version explicitly supported by their build config.
	os.environ.setdefault(
		"PYO3_USE_ABI3_FORWARD_COMPATIBILITY",
		"1",
	)


def setup_termux() -> None:
	"""
	Prepare the Termux environment without blindly installing a toolchain.
	"""
	if not is_termux():
		return

	if not command_exists("pkg"):
		raise RuntimeError(
			"Termux was detected, but the 'pkg' command is unavailable."
		)

	print("[*] Termux environment detected.")

	# Refresh repository metadata, but do NOT upgrade the entire system.
	run(["pkg", "update", "-y"])

	# ffmpeg is a runtime dependency for Vion's voice functionality.
	install_termux_packages(["ffmpeg"])

	configure_termux_build_environment()


# Python dependency management
def load_dependencies(root_dir: Path) -> list[str]:
	"""Load project dependencies from pyproject.toml."""
	pyproject_path = root_dir / "pyproject.toml"

	with pyproject_path.open("rb") as file:
		data = tomllib.load(file)

	return list(
		data.get("project", {}).get("dependencies", [])
	)


def package_name(requirement: str) -> str:
	"""
	Extract a distribution name from a PEP 508 requirement.
	"""
	name = requirement.split(";", 1)[0].strip()
	name = name.split("[", 1)[0].strip()

	for operator in (
		">=",
		"<=",
		"==",
		"!=",
		"~=",
		">",
		"<",
	):
		if operator in name:
			name = name.split(operator, 1)[0].strip()
			break

	return name


def import_name_for_distribution(distribution: str) -> str | None:
	"""Return Vion's known import name for a distribution."""
	aliases = {
		"discord.py": "discord",
		"discord-ext-voice-recv": "discord.ext.voice_recv",
		"google-genai": "google.genai",
		"pynacl": "nacl",
		"pyyaml": "yaml",
		"yt-dlp": "yt_dlp",
		"matplotlib": "matplotlib",
		"orjson": "orjson",
		"httpx": "httpx",
		"pytz": "pytz",
		"rich": "rich",
		"davey": "davey",
	}

	return aliases.get(normalized_name(distribution))


def distribution_available(requirement: str) -> bool:
	"""Return whether a distribution is installed."""
	try:
		importlib.metadata.version(
			package_name(requirement)
		)

		return True

	except importlib.metadata.PackageNotFoundError:
		return False


def dependency_importable(requirement: str) -> bool:
	"""
	Return whether a dependency is actually importable.
	"""
	distribution = package_name(requirement)
	module = import_name_for_distribution(distribution)

	if module is None:
		return distribution_available(requirement)

	try:
		importlib.import_module(module)
		return True

	except Exception:
		return False


def ensure_pip() -> None:
	"""Ensure pip exists in the current interpreter."""
	if importlib.util.find_spec("pip") is not None:
		return

	print("[*] pip is missing. Bootstrapping pip...")

	run([
		sys.executable,
		"-m",
		"ensurepip",
		"--upgrade",
	])


def uv_available() -> bool:
	"""Return whether uv is available."""
	return command_exists("uv")


def install_with_uv(root_dir: Path) -> None:
	"""Install Vion itself without re-resolving dependencies."""
	run([
		"uv",
		"pip",
		"install",
		"--no-deps",
		"-e",
		str(root_dir),
	])


def install_with_pip(root_dir: Path) -> None:
	"""Install the project using pip."""
	args = [
		sys.executable,
		"-m",
		"pip",
		"install",
		"-e",
		str(root_dir),
	]

	if not is_termux():
		args.insert(-2, "--prefer-binary")

	run(args)


def install_python_dependencies(root_dir: Path) -> None:
	"""
	Install unresolved Python dependencies and verify every import.

	On Termux, native dependencies are supplied by Termux whenever possible.
	"""
	dependencies = load_dependencies(root_dir)

	missing = [
		dependency
		for dependency in dependencies
		if not dependency_importable(dependency)
	]

	if not missing:
		print("[✓] Python dependencies are already satisfied.")

		if uv_available():
			install_with_uv(root_dir)

		return

	print(
		"[!] Missing or broken Python dependencies detected:\n"
		+ "\n".join(f"    {dependency}" for dependency in missing)
	)

	if is_termux():
		install_native_python_dependencies(missing)

		missing = [
			dependency
			for dependency in missing
			if not dependency_importable(dependency)
		]

		if missing:
			setup_termux_build_environment(missing)
			configure_termux_build_environment()

			missing = [
				dependency
				for dependency in missing
				if not dependency_importable(dependency)
			]

	if missing:
		print("[*] Installing remaining Python dependencies...")

		if uv_available():
			for dependency in missing:
				run([
					"uv",
					"pip",
					"install",
					dependency,
				])
		else:
			ensure_pip()

			run([
				sys.executable,
				"-m",
				"pip",
				"install",
				*missing,
			])

	if uv_available():
		install_with_uv(root_dir)
	else:
		run([
			sys.executable,
			"-m",
			"pip",
			"install",
			"--no-deps",
			"-e",
			str(root_dir),
		])

	broken = [
		dependency
		for dependency in dependencies
		if not dependency_importable(dependency)
	]

	if broken:
		raise RuntimeError(
			"Dependency installation completed, but these dependencies "
			"are still not importable:\n"
			+ "\n".join(f" - {dependency}" for dependency in broken)
		)

	print("[✓] All Python dependencies are installed and importable.")


# Public entry point
def setup_platform_env() -> None:
	"""Apply platform-specific environment configuration."""
	if is_termux():
		setup_termux()
		return

	if is_linux() or is_macos():
		os.environ.setdefault(
			"PYO3_USE_ABI3_FORWARD_COMPATIBILITY",
			"1",
		)

		os.environ.setdefault(
			"CARGO_BUILD_JOBS",
			str(os.cpu_count() or 4),
		)


def ensure_dependencies(root_dir: Path) -> None:
	"""
	Ensure Vion's complete runtime environment exists.

	This may replace the current process when switching into the venv.
	"""
	root_dir = root_dir.resolve()

	needs_restart = ensure_virtualenv(root_dir)

	if needs_restart:
		restart_inside_venv(root_dir)

	setup_platform_env()

	install_python_dependencies(root_dir)


# Maintenance
def clean_cache(root_dir: Path) -> None:
	"""Remove Python bytecode and __pycache__ directories."""
	try:
		from rich.console import Console

		console = Console()
		console.print(
			"[dim white]Cleaning cache files...[/dim white]"
		)

	except ImportError:
		print("Cleaning cache files...")

	count = 0

	for path in root_dir.rglob("__pycache__"):
		if path.is_dir():
			shutil.rmtree(path, ignore_errors=True)
			count += 1

	for path in root_dir.rglob("*.pyc"):
		if path.is_file():
			try:
				path.unlink()
				count += 1
			except OSError:
				pass

	print(f"✓ Cleaned {count} cache locations.")
