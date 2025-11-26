"""
Quick helper to send a "NO CREDS" signal to the turret listener server.

Usage:
  python no_creds_helper.py --host 127.0.0.1 --port 9000
"""

import argparse
import socket
import sys
import time


def send_no_creds(host: str, port: int, retries: int = 3, delay: float = 0.5) -> bool:
    """Send a NO CREDS message to the TCP listener; returns True on success."""
    payload = "NO CREDS\n".encode("ascii")
    last_err = None
    for _ in range(max(1, retries)):
        try:
            with socket.create_connection((host, port), timeout=2.0) as sock:
                sock.sendall(payload)
                return True
        except OSError as e:
            last_err = e
            time.sleep(delay)
    if last_err:
        print(f"Failed to send NO CREDS: {last_err}", file=sys.stderr)
    return False


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Send a "NO CREDS" message to the turret listener.')
    p.add_argument("--host", default="127.0.0.1", help="Target host (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=9000, help="Target port (default: 9000)")
    p.add_argument("--retries", type=int, default=3, help="Connection retries (default: 3)")
    p.add_argument("--delay", type=float, default=0.5, help="Delay between retries seconds (default: 0.5)")
    ns = p.parse_args(argv)

    ok = send_no_creds(ns.host, ns.port, retries=ns.retries, delay=ns.delay)
    if ok:
        print(f'Sent "NO CREDS" to {ns.host}:{ns.port}')
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
