#!/usr/bin/env python3
"""stdio <-> HTTP+SSE MCP bridge (stdlib only).

Holds the upstream SSE stream with Python's HTTP client (no idle body timeout),
forwards client JSON-RPC messages from stdin to the upstream message endpoint,
and forwards server JSON-RPC messages from SSE to stdout.
"""
import json
import sys
import threading
import time
import urllib.parse
from http.client import HTTPConnection

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8002/sse"
U = urllib.parse.urlparse(URL)
HOST = U.hostname or "localhost"
PORT = U.port or 80
PATH = U.path or "/sse"
BASE = f"{U.scheme}://{U.netloc}"

endpoint = None
endpoint_ready = threading.Event()
stdout_lock = threading.Lock()
stop = threading.Event()


def log(*a):
    print("[sse-bridge]", *a, file=sys.stderr, flush=True)


def post(path, payload: bytes):
    conn = HTTPConnection(HOST, PORT, timeout=30)
    try:
        conn.request("POST", path, body=payload,
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        resp.read()
        return resp.status
    finally:
        conn.close()


def sse_loop():
    global endpoint
    while not stop.is_set():
        try:
            conn = HTTPConnection(HOST, PORT, timeout=None)
            conn.request("GET", PATH, headers={"Accept": "text/event-stream"})
            resp = conn.getresponse()
            if resp.status != 200:
                log("SSE status", resp.status)
                time.sleep(1)
                continue
            event = None
            data = []
            while not stop.is_set():
                raw = resp.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if line == "":
                    if event == "endpoint" and data:
                        ep = "".join(data).strip()
                        endpoint = ep
                        endpoint_ready.set()
                        log("endpoint", ep)
                    elif event == "message" and data:
                        payload = "\n".join(data)
                        with stdout_lock:
                            sys.stdout.write(payload + "\n")
                            sys.stdout.flush()
                    event = None
                    data = []
                elif line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data.append(line[5:].lstrip())
        except Exception as e:
            log("SSE error:", repr(e))
        endpoint = None
        endpoint_ready.clear()
        if not stop.is_set():
            time.sleep(1)
    log("SSE loop stopped")


def main():
    threading.Thread(target=sse_loop, daemon=True).start()
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            json.loads(raw)  # validate, forward original bytes
        except Exception as e:
            log("bad JSON from client:", repr(e))
            continue
        if not endpoint_ready.wait(timeout=30):
            log("upstream endpoint not ready")
            continue
        ep = endpoint or ""
        path = urllib.parse.urlparse(ep).path or ep
        query = urllib.parse.urlparse(ep).query
        if query:
            path += "?" + query
        try:
            status = post(path, raw.encode("utf-8"))
            if status >= 400:
                log("POST status", status)
        except Exception as e:
            log("POST error:", repr(e))
    stop.set()
    log("stdin closed")


if __name__ == "__main__":
    main()
