import os
import subprocess
import tempfile
import unittest

SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
SCRIPT = os.path.join(SCRIPTS, "prepare-test-environment.sh")
FAKE_TOOL = """#!/usr/bin/env bash
{ printf '%s' "$(basename "$0") cwd=$PWD"; printf '|%s' "$@"; echo; } >>"$STATE/log"
"""
FAKE_SUDO = """#!/usr/bin/env bash
{ printf 'sudo'; printf '|%s' "$@"; echo; } >>"$STATE/log"
if [ "$1" = -n ]; then
  shift 5
fi
exec "$@"
"""
GIS = "sqlite3 gdal-bin libspatialite-dev"


class TestPrepareTestEnvironment(unittest.TestCase):
    def run_script(self, packages="", services="", pip=""):
        with tempfile.TemporaryDirectory() as state:
            tools = {"sudo": FAKE_SUDO, "apt-get": FAKE_TOOL}
            tools.update({"docker": FAKE_TOOL, "pip": FAKE_TOOL})
            for name, content in tools.items():
                path = os.path.join(state, name)
                with open(path, "w") as f:
                    f.write(content)
                os.chmod(path, 0o755)
            workspace = os.path.join(state, "workspace")
            pr_dir = os.path.join(state, "pr")
            os.makedirs(workspace)
            os.makedirs(pr_dir)
            env = {
                "PATH": f"{state}:{os.environ['PATH']}",
                "STATE": state,
                "GITHUB_WORKSPACE": workspace,
                "PR_DIR": pr_dir,
                "APT_PACKAGES": packages,
                "COMPOSE_SERVICES": services,
                "PIP_INSTALL": pip,
            }
            result = subprocess.run([SCRIPT], env=env, capture_output=True, text=True)
            log_path = os.path.join(state, "log")
            log = []
            if os.path.exists(log_path):
                with open(log_path) as f:
                    log = f.read().replace(state, "STATE").splitlines()
            return result, log

    def test_does_nothing_without_inputs(self):
        result, log = self.run_script()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(log, [])

    def test_installs_the_listed_packages(self):
        result, log = self.run_script(packages=GIS)
        self.assertEqual(result.returncode, 0)
        installs = [line for line in log if line.startswith("apt-get")]
        self.assertEqual(len(installs), 2)
        self.assertTrue(installs[0].endswith("|update|-qq"))
        self.assertTrue(
            installs[1].endswith(
                "|install|-qq|-y|--no-install-recommends"
                "|sqlite3|gdal-bin|libspatialite-dev"
            )
        )

    def test_starts_services_from_the_trusted_checkout(self):
        result, log = self.run_script(services="redis influxdb")
        self.assertEqual(result.returncode, 0)
        compose = [line for line in log if line.startswith("docker")]
        self.assertEqual(len(compose), 1)
        self.assertTrue(
            compose[0].endswith(
                "|compose|-f|STATE/workspace/docker-compose.yml"
                "|up|-d|--wait|redis|influxdb"
            )
        )

    def test_installs_python_dependencies_as_reviewer_in_the_pr_copy(self):
        result, log = self.run_script(pip="-r requirements-test.txt -e .[rest]")
        self.assertEqual(result.returncode, 0)
        self.assertTrue(
            any(line.startswith("sudo|-n|-H|-u|reviewer|--|bash|-c") for line in log)
        )
        self.assertIn(
            "pip cwd=STATE/pr|install|-r|requirements-test.txt|-e|.[rest]", log
        )

    def test_rejects_invalid_names_before_running_anything(self):
        cases = [
            {"packages": "gdal;rm"},
            {"packages": "--allow-unauthenticated"},
            {"services": "redis&"},
            {"services": "$(id)"},
        ]
        for inputs in cases:
            with self.subTest(inputs=inputs):
                result, log = self.run_script(**inputs, pip="-e .")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Invalid package or service name", result.stdout)
                self.assertEqual(log, [])


if __name__ == "__main__":
    unittest.main()
