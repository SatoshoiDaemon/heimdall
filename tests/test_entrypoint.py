import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX SIGTERM lifecycle test")
def test_sigterm_stops_python_process_cleanly(tmp_path):
    ready = tmp_path / "ready"
    script = """
import asyncio, os
from pathlib import Path
import run
import src.core.bot
class FakeBot:
    failure = None
    def __init__(self):
        self.stopped = asyncio.Event()
    async def __aenter__(self): return self
    async def __aexit__(self, *args): await self.close()
    async def start(self, token, reconnect=True):
        Path(os.environ['TEST_READY']).write_text('ready')
        await self.stopped.wait()
    async def close(self):
        if not self.stopped.is_set():
            print('CLOSED', flush=True)
            self.stopped.set()
src.core.bot.ModBot = FakeBot
raise SystemExit(run.main())
"""
    env = {
        **os.environ,
        "BOT_TOKEN": "test-token",
        "MONGO_URI": "mongodb://localhost:27017",
        "MONGO_DB_NAME": "test",
        "TEST_READY": str(ready),
    }
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 8
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists(), "test entrypoint did not start"
        process.send_signal(signal.SIGTERM)
        output, _ = process.communicate(timeout=5)
        assert process.returncode == 0, output
        assert output.count("CLOSED") == 1
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)


def test_missing_token_exits_with_configuration_error(monkeypatch):
    import run
    from src.core.config import Config

    fake = Config({"MONGO_URI": "mongodb://localhost:27017", "MONGO_DB_NAME": "test"})
    monkeypatch.setattr(run, "config", fake)
    assert run.main() == 1
