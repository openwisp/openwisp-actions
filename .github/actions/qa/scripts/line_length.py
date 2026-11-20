"""Enforce the repository's shell script line-length limit."""

import os
import re
from pathlib import Path

# Match sh and bash in both direct and env shebangs, including scripts without an extension.
SHELL_SHEBANG = re.compile(r"^#!.*(?:^|[/\s])(?:ba)?sh(?:\s|$)")
EXCLUDED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "env",
    ".tox",
    "node_modules",
    "__pycache__",
}
MAX_LENGTH = 110


def check_shell_lines(root):
    """Check shell files and extensionless shell entry points below root."""
    failed = False
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [d for d in subdirectories if d not in EXCLUDED_DIRECTORIES]
        for name in files:
            path = Path(directory) / name
            with path.open(encoding="utf-8", errors="replace") as stream:
                first_line = stream.readline()
                if path.suffix != ".sh" and not SHELL_SHEBANG.match(first_line):
                    continue
                lines = [first_line, *stream]
            for number, line in enumerate(lines, 1):
                line = line.rstrip("\r\n")
                if len(line) > MAX_LENGTH:
                    print(
                        f"{path}:{number}: line is {len(line)} characters (max {MAX_LENGTH})"
                    )
                    failed = True
    return int(failed)
