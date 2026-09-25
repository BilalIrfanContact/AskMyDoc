import os
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


DEV_SCRIPT = Path(__file__).resolve().parents[2] / "dev.sh"
SERVER_STUB = """#!/usr/bin/env python3
import os
import signal
import sys
import time
from pathlib import Path

name = Path(sys.argv[0]).name
Path(os.environ['ASKMYDOC_TEST_PID_DIR'], name + '.pid').write_text(str(os.getpid()))
if name == os.environ.get('ASKMYDOC_TEST_EXIT_SERVER'):
    time.sleep(0.3)
    sys.exit(7)
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
while True:
    time.sleep(0.1)
"""


class DevScriptTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / ".venv/bin").mkdir(parents=True)
        (self.root / "frontend").mkdir()
        (self.root / "bin").mkdir()
        shutil.copy2(DEV_SCRIPT, self.root / "dev.sh")
        for path in (self.root / ".venv/bin/uvicorn", self.root / "bin/npm"):
            path.write_text(SERVER_STUB)
            path.chmod(0o755)

    def start(self, exit_server=None):
        env = os.environ.copy()
        env["PATH"] = str(self.root / "bin") + os.pathsep + env["PATH"]
        env["ASKMYDOC_TEST_PID_DIR"] = str(self.root)
        if exit_server:
            env["ASKMYDOC_TEST_EXIT_SERVER"] = exit_server
        process = subprocess.Popen(
            ["bash", str(self.root / "dev.sh")], cwd=self.root, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=True,
        )
        self.addCleanup(self.stop, process, self.root)
        return process

    @staticmethod
    def stop(process, root):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        # A broken launcher may leave its separately grouped servers alive.
        for name in ("uvicorn", "npm"):
            pid_file = root / (name + ".pid")
            if not pid_file.exists():
                continue
            try:
                os.killpg(os.getpgid(int(pid_file.read_text())), signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            for name in ("uvicorn", "npm"):
                pid_file = root / (name + ".pid")
                if not pid_file.exists():
                    continue
                try:
                    os.killpg(os.getpgid(int(pid_file.read_text())), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)

    def wait_for_servers(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if all((self.root / (name + ".pid")).exists() for name in ("uvicorn", "npm")):
                return
            time.sleep(0.05)
        self.fail("both servers did not start")

    def assert_server_stopped(self, name):
        pid = int((self.root / (name + ".pid")).read_text())
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = subprocess.run(
                ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True,
            ).stdout.strip()
            if not state or state.startswith("Z"):
                return
            time.sleep(0.05)
        self.fail(f"{name} is still running as pid {pid}")

    def test_one_server_exiting_stops_the_other(self):
        process = self.start(exit_server="uvicorn")
        self.wait_for_servers()
        output, _ = process.communicate(timeout=8)
        self.assertEqual(process.returncode, 7, output)
        self.assert_server_stopped("npm")

    def test_frontend_exiting_stops_backend(self):
        process = self.start(exit_server="npm")
        self.wait_for_servers()
        output, _ = process.communicate(timeout=8)
        self.assertEqual(process.returncode, 7, output)
        self.assert_server_stopped("uvicorn")

    def test_interrupt_stops_both_servers(self):
        process = self.start()
        self.wait_for_servers()
        backend_group = os.getpgid(int((self.root / "uvicorn.pid").read_text()))
        frontend_group = os.getpgid(int((self.root / "npm.pid").read_text()))
        self.assertNotEqual(backend_group, os.getpgid(process.pid))
        self.assertNotEqual(frontend_group, os.getpgid(process.pid))
        self.assertNotEqual(backend_group, frontend_group)
        process.send_signal(signal.SIGINT)
        output, _ = process.communicate(timeout=8)
        self.assertEqual(process.returncode, 130, output)
        self.assert_server_stopped("uvicorn")
        self.assert_server_stopped("npm")

    def test_cleanup_stops_servers_if_launcher_dies(self):
        process = self.start()
        self.wait_for_servers()
        process.kill()
        self.stop(process, self.root)
        self.assert_server_stopped("uvicorn")
        self.assert_server_stopped("npm")


if __name__ == "__main__":
    unittest.main()
