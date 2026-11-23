"""Item 9: gunicorn is pinned to a fixed release and refuses requests that
carry both Content-Length and Transfer-Encoding."""
import re
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _pinned(name):
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        m = re.match(rf"^{name}==([\d.]+)\s*$", line.strip(), re.I)
        if m:
            return tuple(int(x) for x in m.group(1).split("."))
    return None


def test_versions_pinned():
    assert _pinned("gunicorn") and _pinned("gunicorn") >= (22, 0, 0)
    assert _pinned("Werkzeug") and _pinned("Werkzeug") >= (3, 0, 6)


@pytest.fixture(scope="module")
def gunicorn_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    dockerfile = (ROOT / "Dockerfile").read_text()
    flags = re.search(r"gunicorn app:app --bind \S+ (.*?) --workers", dockerfile).group(1)
    cmd = [sys.executable, "-m", "gunicorn", "tests.security.wsgi_echo:app",
           "--bind", f"127.0.0.1:{port}", "--workers", "1", *shlex.split(flags)]
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield port
    proc.terminate()
    proc.wait(10)


def _raw(port, request):
    with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
        s.sendall(request)
        chunks = []
        while True:
            data = s.recv(4096)
            if not data:
                break
            chunks.append(data)
        return b"".join(chunks).decode("latin-1")


def test_normal_request_works(gunicorn_port):
    res = _raw(gunicorn_port, b"POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 3\r\nConnection: close\r\n\r\nabc")
    assert res.startswith("HTTP/1.1 200") and "len=3" in res


def test_content_length_plus_transfer_encoding_is_400(gunicorn_port):
    req = (b"POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 4\r\nTransfer-Encoding: chunked\r\n"
           b"Connection: close\r\n\r\n0\r\n\r\nGET /admin HTTP/1.1\r\nHost: x\r\n\r\n")
    assert _raw(gunicorn_port, req).startswith("HTTP/1.1 400")


def test_obfuscated_transfer_encoding_is_400(gunicorn_port):
    req = (b"POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 4\r\nTransfer-Encoding: xchunked\r\n"
           b"Connection: close\r\n\r\nabcd")
    res = _raw(gunicorn_port, req)
    assert res.startswith("HTTP/1.1 400") or res.startswith("HTTP/1.1 501")
