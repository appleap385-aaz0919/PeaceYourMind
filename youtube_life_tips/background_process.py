"""Keep automated child processes from opening Windows console windows."""

import os
import subprocess


def hidden_process_options() -> dict[str, int]:
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
