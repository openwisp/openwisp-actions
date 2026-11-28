"""Remove cached archives that do not match current package metadata.

APT may accept an existing archive based only on its size. Check SHA-256
before a cached package can run its installation scripts as root.
"""

import hashlib
import os
import re
import stat
import subprocess
import sys
import tempfile
from email.parser import Parser
from pathlib import Path
from urllib.parse import unquote


def package_metadata(package):
    result = subprocess.run(
        ["/usr/bin/apt-cache", "show", "--no-all-versions", package],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
    )
    return result.stdout if result.returncode == 0 else ""


def admit_archive(path, active):
    # Do not follow cache-provided symlinks or accept names as command options.
    if not stat.S_ISREG(path.lstat().st_mode):
        return False
    parts = path.name.split("_")
    if len(parts) != 3 or not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", parts[0]):
        return False
    metadata = package_metadata(parts[0])
    for record in metadata.split("\n\n"):
        fields = Parser().parsestr(record)
        filename = fields.get("Filename", "").rsplit("/", 1)[-1]
        digest = fields.get("SHA256", "")
        size = fields.get("Size", "")
        if (
            unquote(filename) != unquote(path.name)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not size.isdecimal()
        ):
            continue
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except OSError:
            return False
        with os.fdopen(fd, "rb") as archive:
            info = os.fstat(archive.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != int(size):
                return False
            actual = hashlib.sha256()
            with tempfile.NamedTemporaryFile(dir=active, delete=False) as verified:
                try:
                    for chunk in iter(lambda: archive.read(1024 * 1024), b""):
                        actual.update(chunk)
                        verified.write(chunk)
                    if actual.hexdigest() != digest:
                        return False
                    verified.flush()
                    os.fchmod(verified.fileno(), 0o644)
                    os.replace(verified.name, active / path.name)
                    return True
                finally:
                    Path(verified.name).unlink(missing_ok=True)
    return False


def verify_archives(staging, active):
    for path in staging.glob("*.deb"):
        if not admit_archive(path, active):
            os.unlink(path)


if __name__ == "__main__":
    verify_archives(Path(sys.argv[1]), Path(sys.argv[2]))
