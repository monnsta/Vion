# Bot Documentation & Manual
> This is the internal documentation and manual for the AI Discord Bot framework. It covers startup procedures, configuration requirements, and the underlying directory architecture.

---

## Table of Contents
 1. [Getting Started](#getting-started)
 2. [Configuration](#configuration)
 3. [Project Architecture](#project-architecture)

---

## Getting Started
The application is designed to run robustly with built-in fail-safes. There are two primary methods for starting the bot depending on your environment (Production vs. Development).

### Production Environment (Recommended)
Execute the provided bash script. This acts as a lightweight process manager that installs dependencies, provides security over the process, automatically restarts the bot in the event of a crash, and detects crash loops to prevent system overload.
```bash
./exec.sh
```

### Development Environment
For testing or debugging, you can bypass the bash script and run the bot script directly.
```bash
python bot.py
```

---

## Configuration
The bot's identity, behavior, limits, and AI parameters are entirely driven by the configure.yml file located in the project root.

---

## Project Architecture
The repository is modularized to separate core logic, configuration, and runtime execution smoothly.
```
.
├── core/                   # Core Application Logic
│   ├── cog/                # Discord commands and events extensions
│   ├── lib/                # Low-Level Utilities
│   │   ├── bttrdict.py     # A dataclass-like utility helpfull for making structured objects with less code
│   │   ├── code.py         # Code execution and sandbox managers
│   │   ├── converter.py    # Object-to-JSON and type converters
│   │   ├── file.py         # File system managers
│   │   ├── llm.py          # LLM content generation
│   │   └── utils.py        # Miscellaneous helpers
│   └── wrp/                # High-Level Wrappers
│       ├── blacklist.py    # Access control
│       ├── extension.py    # Cog loading utilities
│       ├── memory.py       # Conversational and state memory
│       └── profile.py      # Handles settings and info of users or servers
├── meta/                   # Configuration Setup
│   ├── .env                # Environment variables (Credentials)
│   ├── .env.template       # Template for .env file
│   ├── __init__.py
│   ├── paths.py            # File paths used everywhere
│   └── settings.py         # Global settings variables
├── .dockerignore
├── .gitignore
├── bootstrap.py            # Initialization script (Logging, early setup)
├── bot.py                  # Main application entry point
├── configure.yml           # Primary bot configuration and behavior settings
├── docker-compose.yml
├── dockerfile
├── exec.sh                 # Process manager script (Keeps bot alive)
├── LICENSE
├── README.md               # You are here
└── requirements.txt        # Python dependencies
```

### Directory Breakdown
 * **core/**: The brain of the bot. This holds all executable logic.
   * **cog/**: The command and event handlers loaded into the bot instance.
   * **lib/**: Foundational utilities handling file IO, isolated code execution, and data formatting.
   * **ui/**: Pre-built interface structures (like embeds or views) used across commands.
   * **wrp/**: Simple APIs built over complex systems (wrappers). This allows the cogs to easily interact with memory, data, and blacklists without writing boilerplate.
 * **meta/**: Handles the ingestion of environmental variables and parsing configure.yml upon initialization.
 * **Root Scripts (bot.py, bootstrap.py, exec.sh)**: The structural layers that boot up the logging environment, establish the Discord connection, and manage the operating system process.
