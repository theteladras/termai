"""Example termai plugin.

Copy this file to ~/.termai/plugins/example.py to activate it.
It adds a /sysinfo slash command to interactive chat mode.
"""


def register(registry):
    @registry.slash_command("/sysinfo")
    def sysinfo_cmd(args, ctx):
        """Print detailed system information."""
        import platform
        import shutil

        print(f"  OS:       {platform.system()} {platform.release()}")
        print(f"  Arch:     {platform.machine()}")
        print(f"  Python:   {platform.python_version()}")
        print(f"  Shell:    {ctx.shell}")
        print(f"  CWD:      {ctx.cwd}")
        cols, rows = shutil.get_terminal_size()
        print(f"  Terminal: {cols}x{rows}")
        print()

    @registry.pre_execute
    def log_pre(command, ctx):
        """Example pre-execution hook — just logs to stderr."""
        import sys
        print(f"  \033[2m[plugin] About to run: {command}\033[0m", file=sys.stderr)
        return None  # returning None keeps command unchanged
