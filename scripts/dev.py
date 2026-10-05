"""One-command local supervisor. It owns and cleans up only its child processes."""

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]


def available(port):
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", port)) == 0:
            raise SystemExit(f"Port {port} is occupied. Stop the existing ATLAS server first.")


def main():
    for port in (8000, 3000):
        available(port)
    env = {**os.environ, "NEXT_TELEMETRY_DISABLED": "1"}
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    children = []

    def stop(*_):
        for child in reversed(children):
            try:
                root = psutil.Process(child.pid)
                descendants = root.children(recursive=True)
                for process in reversed(descendants):
                    process.terminate()
                root.terminate()
                _, alive = psutil.wait_procs(descendants + [root], timeout=5)
                for process in alive:
                    process.kill()
            except psutil.NoSuchProcess:
                pass
        print("ATLAS stopped.")
        raise SystemExit(0)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    children.append(
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "atlas.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=ROOT,
            env=env,
            creationflags=flags,
        )
    )
    children.append(
        subprocess.Popen(
            [
                "node",
                str(ROOT / "frontend/node_modules/next/dist/bin/next"),
                "dev",
                "--hostname",
                "127.0.0.1",
            ],
            cwd=ROOT / "frontend",
            env=env,
            creationflags=flags,
        )
    )
    print("ATLAS: http://localhost:3000 | API: http://localhost:8000/docs", flush=True)
    while all(child.poll() is None for child in children):
        time.sleep(0.5)
    stop()


if __name__ == "__main__":
    main()
