# termai

A local AI-powered terminal assistant that converts natural language into shell commands — safely.

## Features

- **Safe command generation** — preview every command before it runs, with color-coded safety warnings for destructive operations
- **Context-aware** — knows your OS, shell, cwd, git branch, package manager, and recent commands
- **Interactive chat mode** — multi-turn conversation in your terminal with `/help`, `/history`, `/context`, `/clear`
- **Offline operation** — uses a local LLM (GPT4All: Phi-3, Mistral, LLaMA) with automatic fallback
- **Command logging** — full audit trail in `~/.termai/history.jsonl`
- **Plugin system** — extend with custom slash commands and execution hooks
- **Configurable** — TOML config file, CLI flags, and environment variables

## Quick Start

```bash
# Install in editable mode (also installs gpt4all)
pip install -e .

# Or use the install script (adds shell aliases too)
bash scripts/install.sh

# One-shot mode
termai "find all Python files modified today"

# Dry-run (preview only, no execution)
termai --dry-run "delete temp files"

# Interactive chat
termai --chat

# View command history
termai --history
```

## Usage

```
termai "your instruction"          # generate & preview a command
termai --dry-run "instruction"     # preview only
termai --chat                      # interactive mode
termai --history                   # show recent history
termai --history 50                # show last 50 commands
termai --model Mistral-7B-...      # use a specific model
termai --device gpu                # run model on GPU
termai --init-config               # create ~/.termai/config.toml
```

## Interactive Chat

```
$ termai --chat
══════════════════════════════════════════════════
  termai — interactive chat mode
══════════════════════════════════════════════════

ai> find all log files older than 7 days
  ┌─ Command Preview ─────────────────────
  │  find . -name "*.log" -mtime +7
  └───────────────────────────────────────
Execute this command? [y/N] y

ai> /help
ai> /history
ai> /context
ai> exit
```

## Configuration

Create a config file with `termai --init-config`, or manually at `~/.termai/config.toml`:

```toml
[termai]
model = "Phi-3-mini-4k-instruct.Q4_0.gguf"
device = "cpu"
max_tokens = 256
temperature = 0.2
```

Environment variables override config: `TERMAI_MODEL`, `TERMAI_DEVICE`, `TERMAI_MAX_TOKENS`, `TERMAI_PLUGIN_DIR`.

## Plugins

Place Python files in `~/.termai/plugins/`. Each must define a `register(registry)` function:

```python
def register(registry):
    @registry.slash_command("/mycommand")
    def my_handler(args, ctx):
        print("Hello from my plugin!")

    @registry.pre_execute
    def before_run(command, ctx):
        # return modified command or None
        return None
```

See `examples/plugin_example.py` for a full example.

## Project Structure

```
termai/
├── __init__.py      # Package metadata
├── __main__.py      # python -m termai support
├── cli.py           # Argument parsing and entry point
├── config.py        # TOML config and env var management
├── context.py       # Session context (OS, shell, cwd, git, env)
├── model.py         # Local LLM wrapper (GPT4All)
├── generator.py     # Natural language → shell command
├── executor.py      # Command preview, safety checks, execution
├── safety.py        # Destructive command detection & warnings
├── chat.py          # Interactive chat REPL
├── logger.py        # Command history logging (JSONL)
└── plugins.py       # Plugin system (slash commands, hooks)
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
