"""Start Insights Buddy on this computer and open it in the browser.

    python run.py                 port 8000, or the next free one
    python run.py --port 8010     another port
    python run.py --no-browser    don't open the browser
    python run.py --data FOLDER   keep cases in another folder (tests, spare servers)

It listens on 127.0.0.1 only, so nothing outside this computer can reach it.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser

HOST = "127.0.0.1"


def _in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((HOST, port)) == 0


def _bind(port: int) -> socket.socket | None:
    if _in_use(port):
        return None
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if os.name != "nt":
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((HOST, port))
    except OSError:
        s.close()
        return None
    return s


def bind_free_port(first: int, tries: int = 50) -> tuple[socket.socket, int]:
    """A socket bound to the first free port from `first` on."""
    for port in range(first, first + tries):
        s = _bind(port)
        if s is not None:
            return s, port
    raise SystemExit(f"Ports {first} to {first + tries - 1} are all busy. Close another program, or use --port.")


def _open_when_ready(url: str, port: int) -> None:
    deadline = time.time() + 20
    while time.time() < deadline:
        if _in_use(port):
            webbrowser.open(url)
            return
        time.sleep(0.25)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Start Insights Buddy on this computer.")
    ap.add_argument("--port", type=int, default=None, help="the port to use (default 8000, or IB_PORT)")
    ap.add_argument("--no-browser", action="store_true", help="don't open the browser")
    ap.add_argument("--data", default=None, help="the data folder (default: data/ next to run.py)")
    args = ap.parse_args(argv)

    if args.data:
        os.environ["IB_DATA_DIR"] = os.path.abspath(args.data)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ib import config  # read settings after --data is applied
    import uvicorn

    sock, port = bind_free_port(args.port or config.DEFAULT_PORT)
    url = f"http://{HOST}:{port}"
    if args.port and port != args.port:
        print(f"Port {args.port} is busy, so Insights Buddy uses port {port}.", flush=True)
    print(f"Insights Buddy is running at {url} (on this computer only). Data folder: {config.data_dir()}")
    print("Press Ctrl+C to stop.", flush=True)
    if not args.no_browser:
        threading.Thread(target=_open_when_ready, args=(url, port), daemon=True).start()

    server = uvicorn.Server(uvicorn.Config("ib.api:app", host=HOST, port=port, log_level="info"))
    try:
        server.run(sockets=[sock])
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
