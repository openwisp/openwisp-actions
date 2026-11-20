"""Run repository-specific quality checks."""

import sys
from pathlib import Path

from inline_run import check_inline_runs
from line_length import check_shell_lines
from source_formats import check_source_formats

if __name__ == "__main__":
    checks = {
        "line-length": check_shell_lines,
        "inline-run": check_inline_runs,
        "source-formats": check_source_formats,
    }
    if len(sys.argv) not in (2, 3) or sys.argv[1] not in checks:
        sys.exit(
            "Usage: python __main__.py {line-length|inline-run|source-formats} [root]"
        )
    root = Path(sys.argv[2]) if len(sys.argv) == 3 else Path.cwd()
    sys.exit(checks[sys.argv[1]](root))
