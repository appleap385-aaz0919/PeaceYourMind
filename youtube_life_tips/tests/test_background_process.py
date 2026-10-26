import os
import subprocess
import sys
import unittest

from background_process import hidden_process_options


class BackgroundProcessTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows console behavior")
    def test_child_has_no_console_and_keeps_captured_output(self):
        result = subprocess.run(
            [sys.executable, "-c",
             "import ctypes, sys; print(int(bool(ctypes.windll.kernel32.GetConsoleWindow()))); "
             "print('diagnostic', file=sys.stderr)"],
            capture_output=True, text=True, check=True, timeout=10,
            **hidden_process_options(),
        )
        self.assertEqual(result.stdout.strip(), "0")
        self.assertEqual(result.stderr.strip(), "diagnostic")
