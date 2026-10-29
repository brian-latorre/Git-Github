from __future__ import annotations

import os
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, List, Optional

def compute_initials(name: Optional[str]) -> str:

    if not name:
        return "??"
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "??"
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return parts[0][:2].upper()

class DynamicPathResolver:

    @staticmethod
    def find_repo_root(start_path: Optional[Path] = None) -> Path:

        current = (start_path or Path(__file__)).resolve()
        if current.is_file():
            current = current.parent

        for parent in [current] + list(current.parents):
            if (parent / ".git").exists() or (parent / "historias").exists() or (parent / "client").exists() :
                return parent

        return Path(__file__).resolve().parent.parent.parent

    @classmethod
    def resolve_identity_file(cls, repo_root: Optional[Path] = None) -> Path:
        cwd_candidate = Path.cwd() / "mi_nombre.md"
        if cwd_candidate.exists():
            return cwd_candidate

        cwd_parent_candidate = Path.cwd().parent / "mi_nombre.md"
        if cwd_parent_candidate.exists():
            return cwd_parent_candidate

        root = repo_root or cls.find_repo_root()
        candidate = root / "mi_nombre.md"
        if candidate.exists():
            return candidate

        sibling_candidate = Path(__file__).resolve().parent.parent.parent / "mi_nombre.md"
        if sibling_candidate.exists():
            return sibling_candidate

        return candidate

class FlexibleIdentityParser:

    @staticmethod
    def parse_name_from_content(content: str) -> str:
        if not content:
            return ""

        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines:
            return ""

        for line in lines:
            if line == "---":
                continue

            cleaned = line

            kv_match = re.match(r"^(?:nombre|alumno|name|student|estudiante)\s*[:=]\s*(.+)$", cleaned, re.IGNORECASE)
            if kv_match:
                cleaned = kv_match.group(1).strip()

            cleaned = re.sub(r"^#+\s*", "", cleaned).strip()

            cleaned = re.sub(r"^[-*+]\s+", "", cleaned).strip()

            cleaned = re.sub(r"^(\*\*|__|\*|_)(.*?)\1$", r"\2", cleaned).strip()

            cleaned = cleaned.strip("\"'").strip()

            lower_line = cleaned.lower()
            if (
                cleaned
                and not lower_line.startswith("escribe tu nombre")
                and not lower_line.startswith("reemplaza este")
                and not lower_line.startswith("el sistema de seguimiento")
                and not lower_line.startswith("el sistema")
                and "seguimiento de clase" not in lower_line
                and "ejemplo: sofia code" not in lower_line
            ):
                return cleaned

        return ""

class StudentIdentityWatcher:

    def __init__(self, target_file: Optional[Path] = None, explicit_name: Optional[str] = None) -> None:
        self.file_path: Path = target_file or DynamicPathResolver.resolve_identity_file()

        if explicit_name:
            self.set_name(explicit_name)

        self._current_name: str = self._read_name_from_disk()
        self._listeners: List[Callable[[str], None]] = []
        self._last_mtime: float = self._get_file_mtime()
        self._running: bool = False
        self._watch_thread: Optional[threading.Thread] = None

    def _get_file_mtime(self) -> float:
        try:
            return self.file_path.stat().st_mtime if self.file_path.exists() else 0.0
        except OSError:
            return 0.0

    @staticmethod
    def _resolve_git_username() -> Optional[str]:
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
                if name and name.lower() not in (
                    "alumno sin nombre",
                    "alumno pendiente",
                    "escribe tu nombre completo",
                    "tu nombre",
                ):
                    return name
        except Exception:
            pass
        return None

    def _read_name_from_disk(self) -> str:
        if self.file_path.exists():
            try:
                content = self.file_path.read_text(encoding="utf-8")
                name = FlexibleIdentityParser.parse_name_from_content(content)
                if name:
                    return name
            except Exception:
                pass

        git_name = self._resolve_git_username()
        if git_name:
            return git_name

        return "Alumno Pendiente"

    def set_name(self, new_name: str) -> None:

        clean = new_name.strip()
        if clean:
            self._current_name = clean
            try:
                self.file_path.write_text(f"# {clean}\n", encoding="utf-8")
                self._last_mtime = self._get_file_mtime()
                self._notify(clean)
            except Exception:
                pass

    @property
    def current_name(self) -> str:
        return self._current_name

    def subscribe(self, listener: Callable[[str], None]) -> None:
        self._listeners.append(listener)

    def _notify(self, new_name: str) -> None:
        for listener in self._listeners:
            try:
                listener(new_name)
            except Exception:
                pass

    def check_updates(self) -> bool:
        current_mtime = self._get_file_mtime()
        if current_mtime != self._last_mtime:
            self._last_mtime = current_mtime
            new_name = self._read_name_from_disk()
            if new_name != self._current_name:
                self._current_name = new_name
                self._notify(new_name)
                return True
        return False

    def start_watching(self, poll_interval: float = 1.0) -> None:
        if self._running:
            return

        self._running = True

        def _loop():
            while self._running:
                self.check_updates()
                time.sleep(poll_interval)

        self._watch_thread = threading.Thread(target=_loop, daemon=True, name="IdentityWatchThread")
        self._watch_thread.start()

    def stop_watching(self) -> None:
        self._running = False

def resolve_or_create_student_id(config_dir: Optional[Path] = None) -> str:

    target_dir = config_dir or (Path(__file__).resolve().parent.parent / "config")
    target_dir.mkdir(parents=True, exist_ok=True)
    id_file = target_dir / ".student_id"

    if id_file.exists():
        try:
            val = id_file.read_text(encoding="utf-8").strip()
            if val and val.startswith("stu_") and len(val) >= 8:
                return val
        except Exception:
            pass

    new_id = f"stu_{uuid.uuid4().hex[:12]}"
    try:
        id_file.write_text(new_id, encoding="utf-8")
    except Exception:
        pass
    return new_id
