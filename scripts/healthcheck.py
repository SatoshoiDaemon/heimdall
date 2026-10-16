"""Check gateway and dependency heartbeat without opening a public port."""

import json
import sys
import time
from pathlib import Path

try:
    state = json.loads(Path("/tmp/heimdall-health.json").read_text())
    sys.exit(0 if time.time() - state["at"] < 90 else 1)
except (OSError, ValueError, KeyError):
    sys.exit(1)
