"""Run Node harness for classic Dine Flash create-user duplicate error UI mapping."""
import os
import shutil
import subprocess
import unittest
from pathlib import Path


def _resolve_node_executable() -> str | None:
    for candidate in (
        shutil.which("node"),
        "/usr/share/cursor/resources/app/resources/helpers/node",
    ):
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


HARNESS = (
    Path(__file__).resolve().parent
    / "static/company/js/users/test/createUserErrorMessage.harness.mjs"
)


class DineFlashCreateUserErrorMessageClientTests(unittest.TestCase):
    @unittest.skipUnless(_resolve_node_executable(), "Node.js executable not found")
    def test_create_user_error_message_harness_passes(self):
        node = _resolve_node_executable()
        proc = subprocess.run(
            [node, str(HARNESS)],
            capture_output=True,
            text=True,
            cwd=str(HARNESS.parent),
            timeout=60,
            check=False,
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}",
        )
        self.assertIn("all assertions passed", proc.stdout)
