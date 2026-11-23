"""Loopback-only virtual Hoson controller transport (experimental).

This accepts TCP/UDP traffic for a disconnected PrintExp test installation.
A live machine's replies cannot be inferred merely from a successful socket
connection. Unsupported packets are logged, never invented or sent onward.

Response profiles use verified captures only and must be reviewed before use.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import socketserver
import threading
import time

HOST = "127.0.0.1"
PORT = 5001
MAX_PACKET = 65536


def load_rules(path: Path | None) -> list[dict]:
    if path is None:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rules = data.get("rules", [])
    if not isinstance(rules, list):
        raise ValueError("Simulation rules must be an array")
    cleaned = []
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("transport") not in ("tcp", "udp"):
            raise ValueError("Invalid rule transport")
        prefix = bytes.fromhex(rule["request_prefix_hex"])
        reply = bytes.fromhex(rule["response_hex"])
        if not prefix or len(prefix) > MAX_PACKET or len(reply) > MAX_PACKET:
            raise ValueError("Response rules require bounded nonempty request prefixes")
        cleaned.append({"transport": rule["transport"], "prefix": prefix, "response": reply})
    return cleaned


class EventLog:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.Lock()

    def put(self, transport: str, event: str, payload: bytes = b"") -> None:
        item = {"timestamp": datetime.now(timezone.utc).isoformat(),
                "transport": transport, "event": event, "hex": payload.hex()}
        with self.lock:
            with self.path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(item, separators=(",", ":")) + "\n")


class VirtualController:
    def __init__(self, logfile: Path, rules: list[dict]):
        self.logger = EventLog(logfile)
        self.rules = rules
        self.tcp = None
        self.udp = None
        self.threads = []

    def response(self, transport: str, message: bytes) -> bytes | None:
        for rule in self.rules:
            if rule["transport"] == transport and message.startswith(rule["prefix"]):
                return rule["response"]
        return None

    def start(self) -> None:
        owner = self
        class TcpHandler(socketserver.BaseRequestHandler):
            def handle(self):
                owner.logger.put("tcp", "local_client_connected")
                self.request.settimeout(1.0)
                while True:
                    try:
                        data = self.request.recv(MAX_PACKET)
                    except socket.timeout:
                        continue
                    except OSError:
                        break
                    if not data:
                        break
                    owner.logger.put("tcp", "received", data)
                    response = owner.response("tcp", data)
                    if response is not None:
                        self.request.sendall(response)
                        owner.logger.put("tcp", "replayed_verified_response", response)
                    else:
                        owner.logger.put("tcp", "unsupported_request_no_response", data)
                owner.logger.put("tcp", "local_client_closed")

        class TcpServer(socketserver.ThreadingTCPServer):
            allow_reuse_address = False
            daemon_threads = True

        class UdpServer(socketserver.ThreadingUDPServer):
            allow_reuse_address = False
            daemon_threads = True

        class UdpHandler(socketserver.BaseRequestHandler):
            def handle(self):
                data, sock = self.request
                owner.logger.put("udp", "received", data)
                response = owner.response("udp", data)
                if response is not None:
                    sock.sendto(response, self.client_address)
                    owner.logger.put("udp", "replayed_verified_response", response)
                else:
                    owner.logger.put("udp", "unsupported_request_no_response", data)
        try:
            self.tcp = TcpServer((HOST, PORT), TcpHandler)
            self.udp = UdpServer((HOST, PORT), UdpHandler)
            for server in (self.tcp, self.udp):
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                self.threads.append(thread)
            self.logger.put("server", "listening_loopback_only_on_127.0.0.1_5001")
        except Exception:
            self.stop()
            raise

    def stop(self) -> None:
        for server in (self.tcp, self.udp):
            if server is not None:
                try:
                    server.shutdown()
                    server.server_close()
                except OSError:
                    pass
        self.tcp = self.udp = None


def _printexp_running() -> bool:
    import subprocess
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq PrintExp_X64.exe", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    return result.returncode == 0 and '"printexp_x64.exe"' in result.stdout.lower()


def supervise(logfile: Path, rules: list[dict], launcher: Path, host_exe: Path) -> int:
    import subprocess
    controller = VirtualController(logfile, rules)
    controller.start()  # Must bind both loopback sockets before PrintExp starts.
    try:
        controller.logger.put("server", "launcher_started")
        started = subprocess.Popen(
            [str(launcher), str(host_exe)],
            cwd=str(host_exe.parent),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        # Launcher can exit while PrintExp continues; track the vendor process.
        observed = False
        for tick in range(3600 * 8):
            if _printexp_running():
                observed = True
            if observed and not _printexp_running():
                controller.logger.put("server", "printexp_exited")
                return 0
            if not observed and tick >= 60 and started.poll() is not None:
                controller.logger.put("server", "printexp_did_not_start")
                return 2
            time.sleep(1)
        controller.logger.put("server", "supervisor_timeout")
        return 3
    finally:
        controller.stop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--rules", type=Path)
    parser.add_argument("--launcher", type=Path, required=True)
    parser.add_argument("--host", type=Path, required=True)
    args = parser.parse_args()
    if args.host.name.lower() != "printexp_x64.exe":
        parser.error("The selected host is not PrintExp_X64.exe")
    if not args.host.is_file() or not args.launcher.is_file():
        parser.error("Expected PrintExp and native launcher executables are missing")
    try:
        return supervise(args.log, load_rules(args.rules), args.launcher, args.host)
    except Exception as exc:
        try:
            EventLog(args.log).put("server", "fatal_error_" + str(exc))
        except OSError:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
