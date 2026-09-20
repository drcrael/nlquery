"""Bounded readiness check for disposable CI services."""

import socket
import time

for port in (5432, 27017, 6379, 7687):
    deadline = time.monotonic() + 90
    while True:
        try:
            with socket.create_connection(("localhost", port), timeout=2):
                break
        except OSError:
            if time.monotonic() > deadline:
                raise RuntimeError("Test service did not become ready") from None
            time.sleep(1)
