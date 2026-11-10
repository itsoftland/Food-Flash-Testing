"""Run Node harness and static checks for Dine Flash blue-dot recovery."""
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


STATIC_ROOT = Path(__file__).resolve().parent / "static/orders/js"
HARNESS = (
    Path(__file__).resolve().parent
    / "static/orders/js/dineflash/services/test/chatSyncUnseenRecovery.harness.mjs"
)


class DineFlashBlueDotRecoveryClientTests(unittest.TestCase):
    def test_chat_sync_splits_booking_guard_from_unseen_recovery(self):
        sync = (STATIC_ROOT / "services/chatSyncService.js").read_text(encoding="utf-8")
        restore = (STATIC_ROOT / "services/chatRestoreService.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("booking_guard: bookingGuard", sync)
        self.assertIn("deferDineMultiBookingSyncSeed", restore)
        self.assertIn("paintedForSyncSeed", restore)
        self.assertNotIn("if (!recoveryGuard) continue;", sync)

    @unittest.skipUnless(_resolve_node_executable(), "Node.js executable not found")
    def test_blue_dot_recovery_harness_passes(self):
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
