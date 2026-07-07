<div align="center">
    <img src="icon.png" alt="Vion Logo" width="120" height="120" />
    <h1>Vion: The Unrestricted AI Discord Agent</h1>
    <p><em>An advanced AI agent designed with robust modularity and sandboxed execution capabilities, capable of doing ANYTHING within Discord.</em></p>
</div>

---

## Table of Contents
1. [Getting Started](#getting-started)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Features](#features)
5. [Project Architecture](#project-architecture)
6. [Contributing](#contributing)
7. [License](#license)

---

## Getting Started

Vion is designed for robust operation with built-in fail-safes and a streamlined setup. The primary way to manage and run the application is through the provided shell script: `init/env`.

**Quick Start:**

1. **Prepare your `.env` file**: Copy `.env.template` to `.env` in the project root and fill in your Discord, Gemini, and AssemblyAI API keys.
2. **Install Dependencies**: Run `init/env --install`. This will create a Python virtual environment (if it doesn't exist) and install all required packages.
3. **Run the Bot**:
   * **Standard Run**: `source init/env; bot_run`
   * **Supervised Run (with auto-restart)**: `source init/env; bot_supervise`

For more detailed help on the available commands within the sourced environment, type `bot_help` after sourcing `init/env`.

```bash
# Example for a fresh setup and running in supervised mode
cp .env.template .env
# Edit .env file here to add your API keys
init/env --install --supervise
```

---

## Installation

### Prerequisites

* Python 3.11 or higher
* `venv` module for Python (usually included, but may need to be installed separately on some Linux distributions, e.g., `sudo apt-get install python3.11-venv`)
* `git` (to clone the repository)

### Steps

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/monnsta/Vion.git
   cd Vion
   ```

2. **Configure API Secrets:**
   Copy the environment template file and populate it with your API keys.
   ```bash
   cp .env.template .env
   ```
   Open the newly created `.env` file and replace the placeholder values with your actual `discord_api_key`, `assemblyai_api_key`, and `gemini_api_key`. Multiple Gemini keys can be provided for fallback.

3. **Install Dependencies:**
   Use the `env` script to set up the virtual environment and install Python packages.
   ```bash
   # This command creates a .venv if it doesn't exist and installs dependencies
   init/env --install
   ```
   *(Optional: If you prefer to manually source the script and use its functions)*
   ```bash
   source init/env
   bot_check     # Verifies or creates the virtual environment
   bot_install   # Installs dependencies
   ```

---

## Configuration

Vion's behavior is primarily driven by configuration files, ensuring a clear separation between logic and dynamic settings.

* **`config.ial`**: This file, located in the project root, is the brain of Vion. It defines the bot's identity, personality (via `system_instructions`), operational parameters, AI models, constraints (e.g., `max_memory`), and default settings for servers and users. It allows for fine-grained control over how the AI perceives itself and interacts with the world.

* **`.env`**: Contains sensitive API keys (Discord, Gemini, AssemblyAI) that should *never* be committed to version control. This file is loaded at runtime to securely access external services. Make sure to populate it as described in [Installation](#installation).

---

## Features

Vion is designed to be a highly capable and adaptable AI agent, offering:

* **Advanced AI Persona**: Defined by comprehensive `system_instructions`, Vion exhibits an "Unhinged, predictably cooperative mind assisting on own twisted terms. Interprets rules via wild autonomy and mild psychosis."
* **Dynamic AI Capabilities**: The bot can execute AI-generated Python code within a secure sandbox environment, enabling it to perform complex actions and respond intelligently to various Discord events.
* **Secure Sandboxed Code Execution**: To prevent malicious code or unintended side effects, AI-generated code runs in a carefully controlled sandbox with a strict whitelist of allowed modules and built-in functions.
* **Modular Data Management**: Dedicated systems manage user and server profiles, settings, AI memory (conversations, previous responses), and audit logs, allowing for personalized and context-aware interactions.
* **Global Blacklisting**: A built-in system allows developers to blacklist problematic users or servers, ensuring a safe and controlled environment.
* **Customizable Discord Experience**: Users and server administrators can configure custom command prefixes, manage AI API keys (for Gemini), and set specific AI instructions and behavioral toggles (e.g., `freewill`, `chatbot_only`).
* **Rich Interactive UI**: Leverages Discord's UI components (buttons, modals, pagination) for intuitive command interaction and data management.
* **Robust Error Handling & Supervision**: The `init/env` scripts include crash monitoring and auto-restart capabilities, along with detailed logging via `bootstrap.py` to ensure high availability and easy debugging.
* **Extensible Architecture**: The cog-based system allows for easy addition and removal of features, making Vion highly adaptable to new requirements and functionalities.

---

## Project Architecture

The repository is highly modular, ensuring clear separation between core logic, UI generation, and runtime execution.

```
.
├── core/                  # Core Application Logic
│   ├── cog/               # Discord commands and event extensions (cogs)
│   │   ├── dev/           # Developer-only commands (blacklist, extensions, code execution)
│   │   ├── fun/           # Fun mini-games and interactive commands
│   │   ├── root/          # Core bot commands (help, ping, data management)
│   │   ├── setting/       # User/server configurable settings (prefixes, AI keys, instructions)
│   │   └── ui_template.py # Reusable Discord UI components (views, modals)
│   ├── lib/               # Low-Level Utilities (Code Sandbox, File I/O, LLM Engine, Data Conversion)
│   └── wrp/               # High-Level Wrappers (AI orchestration, Profile, Memory, Blacklist)
├── data/                  # Dynamic User and Server runtime memory & configs (user/server-specific data)
│   ├── global/            # Global persistent data (e.g., blacklist)
│   ├── servers/           # Data specific to each Discord server
│   ├── trash/             # Temporarily stores deleted user/server data
│   └── users/             # Data specific to each Discord user
├── init/                  # Environment setup and execution scripts
├── logs/                  # System runtime logs and rotating archives
├── meta/                  # Configuration Setup & Path Mapping (loads config.ial, .env)
├── .env                   # Environment variables and API secrets (ignored by Git)
├── .env.template          # Template for .env file
├── bootstrap.py           # Initialization script (Logging setup, early config loading)
├── bot.py                 # Main application entry point
├── config.ial             # Primary bot configuration and behavior settings (IAL language)
├── icon.png               # Bot's icon
└── requirements.txt       # Python dependencies
```

---

## Contributing

This project is currently closed to external contributions due to its proprietary nature and active development. However, we welcome feedback and bug reports.

---

## License

Copyright (C) 2026 monnsta
This software is proprietary and confidential.
Unauthorized copying, modification, or distribution is strictly prohibited.
