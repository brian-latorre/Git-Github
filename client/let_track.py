#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import queue
import requests
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from pynput import keyboard
    import socketio
except ModuleNotFoundError as e:
    missing_pkg = e.name
    print("=" * 65)
    print(" [!] FALTA INSTALAR DEPENDENCIAS EN TU ENTORNO PYTHON")
    print("=" * 65)
    print(f" No se encontro el paquete: '{missing_pkg}'")
    print("\n Para solucionarlo rapidamente en tu terminal activa, ejecuta:")
    print("   pip install -r client/requirements.txt")
    print(" o bien:")
    print("   pip install pynput python-socketio websocket-client Pillow")
    print("=" * 65)
    sys.exit(1)

from client.core.identity import DynamicPathResolver, StudentIdentityWatcher, resolve_or_create_student_id
from client.core.keyboard_state import KeyboardStateManager, sanitize_and_validate_command
from client.core.models import InputType, NormalizedInputEvent
from client.core.repo_analyzer import get_repo_git_state

DEFAULT_PORT = 5000
DEFAULT_HOST = "localhost"
UDP_LISTEN_HOST = "127.0.0.1"
UDP_LISTEN_PORT = 51234

DEFAULT_PLACEHOLDER_NAMES = (
    "alumno sin nombre",
    "alumno pendiente",
    "escribe tu nombre completo",
    "tu nombre",
    "el sistema de seguimiento de clase leerá automáticamente este archivo.",
    "el sistema de seguimiento",
)


def load_client_config_url() -> Optional[str]:
    try:
        config_path = DynamicPathResolver.find_repo_root() / "client" / "config" / "client_config.json"
        if config_path.is_file():
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                env_key = data.get("default_env", "production")
                envs = data.get("environments", {})
                if env_key in envs:
                    return envs[env_key]
    except Exception:
        pass
    return None


def resolve_default_git_username() -> Optional[str]:
    try:
        res = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if res.returncode == 0:
            name = res.stdout.strip()
            if name and name.lower() not in DEFAULT_PLACEHOLDER_NAMES:
                return name
    except Exception:
        pass
    return None


class StudentTrackerClient:
    def __init__(
        self,
        server_host: str = DEFAULT_HOST,
        server_port: int = DEFAULT_PORT,
        explicit_name: str | None = None,
        server_url: str | None = None,
    ) -> None:
        if server_url:
            self.server_url = server_url.rstrip("/")
        else:
            self.server_url = f"http://{server_host}:{server_port}"

        self.sio = socketio.Client(
            reconnection=True,
            reconnection_attempts=30,
            reconnection_delay=2,
        )

        self.repo_root = DynamicPathResolver.find_repo_root()
        self.student_id = resolve_or_create_student_id()
        self.identity_watcher = StudentIdentityWatcher(explicit_name=explicit_name)
        self.identity_file_path = self.identity_watcher.file_path

        current_name = self.identity_watcher.current_name
        is_placeholder = (not current_name) or (current_name.strip().lower() in DEFAULT_PLACEHOLDER_NAMES)

        if is_placeholder:
            print(f"[*] Archivo de identidad : {self.identity_file_path.name}")
            print(f"[*] Estado actual        : '{current_name}' (Pendiente de personalizar)")
            print("    -> Abre 'mi_nombre.md' en tu editor, escribe tu nombre y guarda los cambios.")

        self.keyboard_state = KeyboardStateManager(enforce_whitelist=True)

        self._last_synced_head: Optional[str] = None
        self._last_commits_count: int = -1
        self._debounce_timer: Optional[threading.Timer] = None
        self._git_sync_lock = threading.Lock()

        self._event_queue: queue.Queue[NormalizedInputEvent] = queue.Queue(maxsize=1000)
        self._worker_running = True

        self._worker_thread = threading.Thread(
            target=self._dispatch_worker,
            daemon=True,
            name="KeyboardEventDispatcherThread",
        )
        self._worker_thread.start()

        self._udp_thread = threading.Thread(
            target=self._udp_listener_worker,
            daemon=True,
            name="UDPTerminalListenerThread",
        )
        self._udp_thread.start()

        self._git_watcher_thread = threading.Thread(
            target=self._git_head_watcher_worker,
            daemon=True,
            name="GitHeadWatcherThread",
        )
        self._git_watcher_thread.start()

        self._setup_socket_handlers()

    def _discover_local_avatar(self) -> tuple[Optional[str], Optional[bytes]]:
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            path = self.repo_root / f"avatar{ext}"
            if path.is_file():
                try:
                    if path.stat().st_size > 5 * 1024 * 1024:
                        print("[!] avatar.* supera los 5MB; omitiendo...")
                        continue
                    content = path.read_bytes()
                    h = hashlib.sha256(content).hexdigest()
                    return h, content
                except Exception:
                    pass
        return None, None

    def _setup_socket_handlers(self) -> None:
        @self.sio.event
        def connect():
            print(f"[+] Conectado exitosamente al servidor en {self.server_url}")
            self._announce_identity()

        @self.sio.on("solicitar_avatar")
        def on_solicitar_avatar(data):
            h, content = self._discover_local_avatar()
            if content and h:
                try:
                    payload = {
                        "student_key": self.identity_watcher.current_name,
                        "student_id": self.student_id,
                        "avatar_hash": h,
                        "image_base64": base64.b64encode(content).decode("ascii"),
                    }
                    requests.post(f"{self.server_url}/api/student/avatar", json=payload, timeout=15)
                    print(f"[*] Foto de perfil local '{h[:6]}' sincronizada con exito.")
                except Exception as exc:
                    print(f"[!] No se pudo subir el avatar al servidor: {exc}")

        @self.sio.event
        def disconnect():
            if self._worker_running:
                print("[-] Desconectado del servidor. Intentando reconectar...")
            else:
                print("[-] Desconectado del servidor.")

        @self.sio.event
        def connect_error(data):
            pass

    def _announce_identity(self) -> None:
        if self.sio.connected:
            try:
                name = self.identity_watcher.current_name
                avatar_hash, _ = self._discover_local_avatar()
                payload = {
                    "student_id": self.student_id,
                    "nombre": name,
                    "identity_file": str(self.identity_file_path.name),
                }
                if avatar_hash:
                    payload["avatar_hash"] = avatar_hash

                self.sio.emit("conectar", payload)
                print(f"[*] Identidad sincronizada con el panel: '{name}'")
                self.sync_git_graph(force=True)
            except Exception:
                pass

    def _schedule_git_sync(self, delay: float = 0.35) -> None:
        with self._git_sync_lock:
            if self._debounce_timer and self._debounce_timer.is_alive():
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(delay, self.sync_git_graph)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def sync_git_graph(self, force: bool = False) -> None:
        if not self.sio.connected:
            return

        try:
            git_state = get_repo_git_state(self.repo_root)
            if not git_state or not isinstance(git_state, dict):
                return

            head_ref = git_state.get("head_ref", "main")
            head_sha = git_state.get("refs", {}).get("heads", {}).get(head_ref, "")
            total_commits = git_state.get("total_commits", len(git_state.get("commits", [])))

            if not force and head_sha == self._last_synced_head and total_commits == self._last_commits_count:
                return

            self._last_synced_head = head_sha
            self._last_commits_count = total_commits

            display_name = self.identity_watcher.current_name
            payload = {
                "student_id": self.student_id,
                "display_name": display_name,
                "git_state": git_state,
            }
            self.sio.emit("sync_student_graph", payload)
            print(f"[*] Grafo Git local sincronizado ({head_ref} @ {total_commits} commits)")
        except Exception:
            pass

    def _git_head_watcher_worker(self) -> None:
        git_dir = self.repo_root / ".git"
        head_file = git_dir / "HEAD"
        refs_dir = git_dir / "refs" / "heads"

        def _get_mtimes() -> tuple[float, float]:
            h_mtime = head_file.stat().st_mtime if head_file.exists() else 0.0
            r_mtime = refs_dir.stat().st_mtime if refs_dir.exists() else 0.0
            return (h_mtime, r_mtime)

        last_mtimes = _get_mtimes()

        while self._worker_running:
            try:
                time.sleep(1.2)
                curr_mtimes = _get_mtimes()
                if curr_mtimes != last_mtimes:
                    last_mtimes = curr_mtimes
                    self._schedule_git_sync(delay=0.15)
            except Exception:
                pass

    def _on_identity_changed(self, new_name: str) -> None:
        print(f"[*] Cambio detectado en {self.identity_file_path.name}: nuevo nombre '{new_name}'")
        self._announce_identity()

    def _dispatch_worker(self) -> None:
        while self._worker_running:
            try:
                event = self._event_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if not self.sio.connected:
                continue

            try:
                name = self.identity_watcher.current_name
                payload = {
                    "nombre": name,
                    "student_id": self.student_id,
                    "canonical_repr": event.canonical_repr,
                    "input_type": event.input_type.value,
                    "raw_key": event.raw_key,
                    "modifiers": list(event.modifiers),
                    "tecla": event.canonical_repr,
                }
                self.sio.emit("tecla", payload)

                prefix = "[CMD]" if event.input_type.value == "command" else "[KEY]"
                print(f"    {prefix} {event.canonical_repr}")

                if event.input_type == InputType.COMMAND:
                    GIT_MUTATING_KEYWORDS = (
                        "commit", "branch", "checkout", "switch", "merge",
                        "rebase", "reset", "cherry-pick", "pull", "tag", "stash"
                    )
                    cmd_str = (event.canonical_repr or "").strip().lower()
                    if "git" in cmd_str and any(kw in cmd_str for kw in GIT_MUTATING_KEYWORDS):
                        self._schedule_git_sync(delay=0.35)
            except Exception:
                pass

    def _udp_listener_worker(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((UDP_LISTEN_HOST, UDP_LISTEN_PORT))
            sock.settimeout(0.5)
        except Exception:
            return

        while self._worker_running:
            try:
                data, _ = sock.recvfrom(4096)
                if not data:
                    continue
                raw_line = data.decode("utf-8", errors="replace").strip()
                valid_cmd = sanitize_and_validate_command(raw_line)
                if valid_cmd:
                    event = NormalizedInputEvent(
                        input_type=InputType.COMMAND,
                        canonical_repr=valid_cmd,
                        raw_key="enter",
                        modifiers=set(),
                    )
                    try:
                        self._event_queue.put_nowait(event)
                    except queue.Full:
                        pass
            except socket.timeout:
                continue
            except Exception:
                break

        try:
            sock.close()
        except Exception:
            pass

    def on_press(self, key: keyboard.Key | keyboard.KeyCode) -> bool | None:
        try:
            event = self.keyboard_state.on_key_down(key)
            if event:
                try:
                    self._event_queue.put_nowait(event)
                except queue.Full:
                    pass
        except Exception:
            pass

        return None

    def on_release(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        try:
            self.keyboard_state.on_key_up(key)
        except Exception:
            pass

    def run(self) -> None:
        self.identity_watcher.subscribe(self._on_identity_changed)
        self.identity_watcher.start_watching(poll_interval=1.0)

        student_name = self.identity_watcher.current_name

        print("=" * 65)
        print("  TRACKER DE CLASE EN VIVO - CLIENTE DE ALUMNO")
        print("=" * 65)
        print(f"[*] Alumno detectado : {student_name}")
        print(f"[*] ID Estudiante    : {self.student_id}")
        print(f"[*] Archivo origen   : {self.identity_file_path}")
        print(f"[*] Servidor destino : {self.server_url}")
        print("[*] Privacidad       : Lista blanca de comandos de clase activada")
        print("[*] Salir            : Presiona Ctrl+C en esta terminal para finalizar")
        print("=" * 65)
        print("[*] Conectando al servidor...")

        try:
            self.sio.connect(self.server_url, wait_timeout=5)
            self._announce_identity()
        except Exception as e:
            print(f"[!] No se pudo conectar de inmediato a {self.server_url}: {e}")
            print("[*] El cliente intentara reconectar en segundo plano mientras captura eventos locales...")

        print("[*] Escuchando teclas y comandos de terminal...\n")
        try:
            with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as listener:
                while listener.is_alive():
                    listener.join(timeout=0.5)
        except KeyboardInterrupt:
            print("\n[!] Finalizado por el usuario.")
        finally:
            self._worker_running = False
            self.identity_watcher.stop_watching()
            if self.sio.connected:
                self.sio.disconnect()


def main() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="Cliente Tracker de Teclado y Comandos de Clase")
    parser.add_argument(
        "server",
        nargs="?",
        default=None,
        help=f"IP o dominio del servidor (default: client_config.json o {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Puerto del servidor (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--nombre",
        "-n",
        type=str,
        default=None,
        help="Especificar o actualizar tu nombre en mi_nombre.md",
    )
    args = parser.parse_args()

    if args.server:
        if args.server.startswith("http://") or args.server.startswith("https://"):
            resolved_url = args.server
        else:
            resolved_url = f"http://{args.server}:{args.port}"
    else:
        resolved_url = load_client_config_url() or f"http://{DEFAULT_HOST}:{args.port}"

    client = StudentTrackerClient(server_url=resolved_url, explicit_name=args.nombre)
    client.run()


if __name__ == "__main__":
    main()
