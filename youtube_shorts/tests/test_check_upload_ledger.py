from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_upload_ledger.py"


class UploadLedgerCheckTests(unittest.TestCase):
    def test_absent_ledger_allows_run(self) -> None:
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location("check_upload_ledger", SCRIPT)
        module = module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(module.already_uploaded("2026-10-24", Path(directory) / "missing.json"))

    def test_date_in_ledger_skips_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "uploads.json"
            state.write_text(json.dumps({"2026-10-24": {"video_id": "abc"}}), encoding="utf-8")
            result = self.run_check(state, event="schedule")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("already_uploaded=true", result.stdout)

    def test_other_date_allows_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "uploads.json"
            state.write_text(json.dumps({"2026-10-23": {"video_id": "abc"}}), encoding="utf-8")
            result = self.run_check(state, event="schedule")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("already_uploaded=false", result.stdout)

    def test_manual_run_is_not_blocked_by_scheduled_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "uploads.json"
            state.write_text(json.dumps({"2026-10-24": {"video_id": "abc"}}), encoding="utf-8")
            result = self.run_check(state, event="workflow_dispatch")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("already_uploaded=false", result.stdout)

    def test_invalid_ledger_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "uploads.json"
            state.write_text("not json", encoding="utf-8")
            result = self.run_check(state, event="schedule")
            self.assertNotEqual(result.returncode, 0)

    @staticmethod
    def run_check(state: Path, *, event: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "github-output.txt"
            env = os.environ | {"GITHUB_EVENT_NAME": event, "GITHUB_OUTPUT": str(output)}
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--date", "2026-10-24", "--state", str(state)],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            if output.exists():
                result.stdout += output.read_text(encoding="utf-8")
            return result


if __name__ == "__main__":
    unittest.main()
