from __future__ import annotations

import datetime
import json
from client.core.identity import compute_initials
import os
import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

GIT_PLUMBING_FORMAT = "%H%x1f%P%x1f%an%x1f%ae%x1f%aI%x1f%s%x1e"
GIT_TOPO_FORMAT = "%H%x1f%P%x1f%an%x1f%ae%x1f%at%x1f%ct%x1f%s%x1e"

@dataclass(frozen=True)
class CommitRecord:

    sha: str
    short_sha: str
    author_name: str
    author_login: str
    message: str
    date: datetime.datetime
    avatar_url: str = ""
    parents: Tuple[str, ...] = ()
    is_merge: bool = False

    @property
    def is_root(self) -> bool:
        return len(self.parents) == 0

    @property
    def formatted_date(self) -> str:
        return self.date.strftime("%Y-%m-%d %H:%M")

    @property
    def date_iso(self) -> str:
        return self.date.strftime("%Y-%m-%d")

    @property
    def commit_type(self) -> str:

        msg = self.message.strip().lower()
        for prefix in ("feat", "fix", "docs", "style", "refactor", "test", "chore", "perf", "ci"):
            if msg.startswith(f"{prefix}:") or msg.startswith(f"{prefix}(") or msg.startswith(f"{prefix} "):
                return prefix
        return "commit"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sha": self.sha,
            "short_sha": self.short_sha,
            "author_name": self.author_name,
            "author_login": self.author_login,
            "message": self.message,
            "formatted_date": self.formatted_date,
            "date_iso": self.date_iso,
            "commit_type": self.commit_type,
            "avatar_url": self.avatar_url,
            "parents": list(self.parents),
            "is_merge": self.is_merge,
            "is_root": self.is_root,
        }

@dataclass
class ParticipantStats:

    name: str
    login: str
    avatar_url: str = ""
    commits: List[CommitRecord] = field(default_factory=list)

    @property
    def total_commits(self) -> int:
        return len(self.commits)

    @property
    def last_commit_date(self) -> Optional[datetime.datetime]:
        if not self.commits:
            return None
        return max(c.date for c in self.commits)

    @property
    def status_code(self) -> str:

        if not self.commits or self.last_commit_date is None:
            return "sin_flujo"

        now = datetime.datetime.now(datetime.timezone.utc)
        commit_date = self.last_commit_date
        if commit_date.tzinfo is None:
            commit_date = commit_date.replace(tzinfo=datetime.timezone.utc)

        days_diff = (now - commit_date).total_seconds() / 86400.0

        if days_diff <= 2.0 or self.total_commits >= 6:
            return "al_dia"
        elif days_diff <= 5.0 or self.total_commits >= 2:
            return "en_riesgo"
        else:
            return "sin_flujo"

    @property
    def status_label(self) -> str:
        mapping = {
            "al_dia": "Al día",
            "en_riesgo": "En riesgo",
            "sin_flujo": "Sin flujo activo",
        }
        return mapping.get(self.status_code, "Sin flujo activo")

    def to_dict(self, max_commits_leader: int = 1) -> Dict[str, Any]:
        rel_progress = min(1.0, self.total_commits / max(1, max_commits_leader))
        last_date_str = self.last_commit_date.strftime("%Y-%m-%d %H:%M") if self.last_commit_date else "Sin actividad"

        return {
            "name": self.name,
            "login": self.login,
            "avatar_url": self.avatar_url,
            "total_commits": self.total_commits,
            "relative_progress": round(rel_progress * 100, 1),
            "status_code": self.status_code,
            "status_label": self.status_label,
            "last_commit_date": last_date_str,
            "commits": [c.to_dict() for c in sorted(self.commits, key=lambda x: x.date, reverse=True)],
        }

def check_unresolved_conflicts(repo_path: Path | str) -> bool:

    cmd = ["git", "-C", str(repo_path), "ls-files", "-u"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        return bool(res.stdout.strip())
    except Exception:
        return False

def parse_local_commits(repo_path: Path | str, max_count: int = 250) -> List[CommitRecord]:

    cmd = [
        "git", "-C", str(repo_path),
        "--no-pager", "log",
        f"--max-count={max_count}",
        f"--pretty=format:{GIT_PLUMBING_FORMAT}",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        if res.returncode != 0:
            return []

        commits: List[CommitRecord] = []
        for entry in res.stdout.split("\x1e"):
            clean_entry = entry.strip()
            if not clean_entry:
                continue
            parts = clean_entry.split("\x1f")
            if len(parts) >= 6:
                commit_hash, parents_raw, author, email, date_raw, subject = parts[:6]
                parent_list = tuple(parents_raw.split()) if parents_raw.strip() else ()
                try:
                    if date_raw.isdigit():
                        date_obj = datetime.datetime.fromtimestamp(int(date_raw), tz=datetime.timezone.utc)
                    else:
                        date_obj = datetime.datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
                except Exception:
                    date_obj = datetime.datetime.now(datetime.timezone.utc)

                author_login = email.split("@")[0] if "@" in email else author.lower().replace(" ", "")

                commits.append(
                    CommitRecord(
                        sha=commit_hash,
                        short_sha=commit_hash[:7],
                        author_name=author,
                        author_login=author_login,
                        message=subject,
                        date=date_obj,
                        parents=parent_list,
                        is_merge=len(parent_list) >= 2,
                    )
                )
        return commits
    except Exception:
        return []

def extract_topo_ordered_commits(
    repo_path: str,
    branch: Optional[str] = None,
    max_count: int = 300,
) -> List[Dict[str, Any]]:

    cmd = [
        "git", "-C", repo_path, "--no-pager", "log",
    ]
    if branch and branch.strip().lower() != "all":
        cmd.append(branch.strip())
    else:
        cmd.append("--all")

    cmd.extend([
        "--topo-order",
        f"--max-count={max_count}",
        f"--pretty=format:{GIT_TOPO_FORMAT}",
    ])

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    commits = []
    for entry in res.stdout.split("\x1e"):
        if not entry.strip():
            continue
        parts = entry.strip().split("\x1f")
        if len(parts) >= 7:
            h, parents, author, email, at, ct, subject = parts[:7]
            parent_list = parents.split()
            commits.append({
                "hash": h,
                "short_hash": h[:7],
                "parents": parent_list,
                "is_merge": len(parent_list) >= 2,
                "is_root": len(parent_list) == 0,
                "author": {"name": author, "initials": compute_initials(author)},
                "author_timestamp": int(at) if at.isdigit() else 0,
                "committer_timestamp": int(ct) if ct.isdigit() else 0,
                "subject": subject,
            })
    return commits

def get_repo_git_state(
    repo_path: str | Path,
    branch: Optional[str] = None,
    max_count: int = 300,
) -> Dict[str, Any]:

    repo_str = str(repo_path)
    head_ref = "main"
    refs: Dict[str, Dict[str, str]] = {"heads": {}, "remotes": {}, "tags": {}}
    commits: List[Dict[str, Any]] = []

    try:
        head_cmd = ["git", "-C", repo_str, "rev-parse", "--abbrev-ref", "HEAD"]
        head_res = subprocess.run(head_cmd, capture_output=True, text=True, check=False)
        if head_res.returncode == 0 and head_res.stdout.strip():
            head_ref = head_res.stdout.strip()
    except Exception:
        pass

    try:
        ref_cmd = ["git", "-C", repo_str, "for-each-ref", "--format=%(refname) %(objectname)"]
        ref_res = subprocess.run(ref_cmd, capture_output=True, text=True, check=False)
        if ref_res.returncode == 0:
            for line in ref_res.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) == 2:
                    ref_name, sha = parts
                    if ref_name.startswith("refs/heads/"):
                        branch_name = ref_name.replace("refs/heads/", "")
                        refs["heads"][branch_name] = sha
                    elif ref_name.startswith("refs/remotes/"):
                        remote_name = ref_name.replace("refs/remotes/", "")
                        refs["remotes"][remote_name] = sha
                    elif ref_name.startswith("refs/tags/"):
                        tag_name = ref_name.replace("refs/tags/", "")
                        refs["tags"][tag_name] = sha
    except Exception:
        pass

    branches_list = []
    for b_name, b_sha in refs["heads"].items():
        branches_list.append({
            "name": b_name,
            "sha": b_sha,
            "short_sha": b_sha[:7],
            "is_head": (b_name == head_ref),
            "is_remote": False,
        })
    for r_name, r_sha in refs["remotes"].items():
        if not r_name.endswith("/HEAD"):
            branches_list.append({
                "name": r_name,
                "sha": r_sha,
                "short_sha": r_sha[:7],
                "is_head": False,
                "is_remote": True,
            })

    try:
        commits = extract_topo_ordered_commits(repo_str, branch=branch, max_count=max_count)
    except Exception:
        commits = []

    head_sha = refs["heads"].get(head_ref)
    for c in commits:
        c_hash = c.get("hash", "")
        c["branch_labels"] = [b for b, s in refs["heads"].items() if s == c_hash]
        c["remote_labels"] = [r for r, s in refs["remotes"].items() if s == c_hash]
        c["tag_labels"] = [t for t, s in refs["tags"].items() if s == c_hash]
        c["is_head"] = (c_hash == head_sha)

    merges_count = sum(1 for c in commits if c.get("is_merge", False))

    return {
        "head_ref": head_ref,
        "selected_branch": branch or "all",
        "mode": "local",
        "refs": refs,
        "branches": branches_list,
        "commits": commits,
        "total_commits": len(commits),
        "total_branches": len(branches_list),
        "total_merges": merges_count,
    }

def get_demo_git_state(branch: Optional[str] = None) -> Dict[str, Any]:

    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

    c1 = "1001a1a000000000000000000000000000000001"
    c2 = "2002b2b000000000000000000000000000000002"
    c3 = "3003c3c000000000000000000000000000000003"
    c4 = "4004d4d000000000000000000000000000000004"
    c5 = "5005e5e000000000000000000000000000000005"
    c6 = "6006f6f000000000000000000000000000000006"
    c7 = "7007a7a000000000000000000000000000000007"
    c8 = "8008b8b000000000000000000000000000000008"
    c9 = "9009c9c000000000000000000000000000000009"
    c10 = "a010d0d000000000000000000000000000000010"

    all_commits = [
        {
            "hash": c10,
            "short_hash": c10[:7],
            "parents": [c9],
            "is_merge": False,
            "is_root": False,
            "author": {"name": "Brian La Torre", "initials": "BL"},
            "author_timestamp": now - 300,
            "committer_timestamp": now - 300,
            "subject": "fix(dashboard): corregir reactividad del grafo y sincronización de estado",
            "branch_labels": ["main"],
            "remote_labels": ["origin/main"],
            "tag_labels": ["v1.2.0"],
            "is_head": True,
        },
        {
            "hash": c9,
            "short_hash": c9[:7],
            "parents": [c7, c8],
            "is_merge": True,
            "is_root": False,
            "author": {"name": "Brian La Torre", "initials": "BL"},
            "author_timestamp": now - 1800,
            "committer_timestamp": now - 1800,
            "subject": "Merge branch 'feature/historias' into main",
            "branch_labels": [],
            "remote_labels": [],
            "tag_labels": [],
            "is_head": False,
        },
        {
            "hash": c8,
            "short_hash": c8[:7],
            "parents": [c5],
            "is_merge": False,
            "is_root": False,
            "author": {"name": "Sofia Code", "initials": "SC"},
            "author_timestamp": now - 3600,
            "committer_timestamp": now - 3600,
            "subject": "feat(historias): redactar desenlace en el lago de los patos",
            "branch_labels": ["feature/historias"],
            "remote_labels": ["origin/feature/historias"],
            "tag_labels": [],
            "is_head": False,
        },
        {
            "hash": c7,
            "short_hash": c7[:7],
            "parents": [c6, c4],
            "is_merge": True,
            "is_root": False,
            "author": {"name": "Brian La Torre", "initials": "BL"},
            "author_timestamp": now - 7200,
            "committer_timestamp": now - 7200,
            "subject": "Merge branch 'fix/quiosco' into main",
            "branch_labels": [],
            "remote_labels": [],
            "tag_labels": [],
            "is_head": False,
        },
        {
            "hash": c6,
            "short_hash": c6[:7],
            "parents": [c2],
            "is_merge": False,
            "is_root": False,
            "author": {"name": "Carlos Git", "initials": "CG"},
            "author_timestamp": now - 10800,
            "committer_timestamp": now - 10800,
            "subject": "docs(historias): agregar índice general y tabla de contenidos",
            "branch_labels": [],
            "remote_labels": [],
            "tag_labels": [],
            "is_head": False,
        },
        {
            "hash": c5,
            "short_hash": c5[:7],
            "parents": [c3],
            "is_merge": False,
            "is_root": False,
            "author": {"name": "Sofia Code", "initials": "SC"},
            "author_timestamp": now - 14400,
            "committer_timestamp": now - 14400,
            "subject": "feat(historias): anécdota del ajedrez en las bancas de concreto",
            "branch_labels": [],
            "remote_labels": [],
            "tag_labels": [],
            "is_head": False,
        },
        {
            "hash": c4,
            "short_hash": c4[:7],
            "parents": [c2],
            "is_merge": False,
            "is_root": False,
            "author": {"name": "Lucia Dev", "initials": "LD"},
            "author_timestamp": now - 18000,
            "committer_timestamp": now - 18000,
            "subject": "fix(quiosco): corregir coordenadas históricas y año de construcción",
            "branch_labels": ["fix/quiosco"],
            "remote_labels": [],
            "tag_labels": [],
            "is_head": False,
        },
        {
            "hash": c3,
            "short_hash": c3[:7],
            "parents": [c2],
            "is_merge": False,
            "is_root": False,
            "author": {"name": "Sofia Code", "initials": "SC"},
            "author_timestamp": now - 21600,
            "committer_timestamp": now - 21600,
            "subject": "feat(historias): inicio de redacción de relatos urbanos del parque",
            "branch_labels": [],
            "remote_labels": [],
            "tag_labels": [],
            "is_head": False,
        },
        {
            "hash": c2,
            "short_hash": c2[:7],
            "parents": [c1],
            "is_merge": False,
            "is_root": False,
            "author": {"name": "Brian La Torre", "initials": "BL"},
            "author_timestamp": now - 28800,
            "committer_timestamp": now - 28800,
            "subject": "docs: crear guía de contribución y estructura del proyecto",
            "branch_labels": [],
            "remote_labels": [],
            "tag_labels": [],
            "is_head": False,
        },
        {
            "hash": c1,
            "short_hash": c1[:7],
            "parents": [],
            "is_merge": False,
            "is_root": True,
            "author": {"name": "Brian La Torre", "initials": "BL"},
            "author_timestamp": now - 86400,
            "committer_timestamp": now - 86400,
            "subject": "chore: commit inicial del repositorio bootcamp",
            "branch_labels": [],
            "remote_labels": [],
            "tag_labels": ["v0.1.0"],
            "is_head": False,
        },
    ]

    branches = [
        {"name": "main", "sha": c10, "short_sha": c10[:7], "is_head": True, "is_remote": False},
        {"name": "feature/historias", "sha": c8, "short_sha": c8[:7], "is_head": False, "is_remote": False},
        {"name": "fix/quiosco", "sha": c4, "short_sha": c4[:7], "is_head": False, "is_remote": False},
        {"name": "origin/main", "sha": c10, "short_sha": c10[:7], "is_head": False, "is_remote": True},
    ]

    filtered = all_commits
    if branch and branch != "all":
        branch_tip = next((b["sha"] for b in branches if b["name"] == branch), None)
        if branch_tip:
            reachable = set()
            queue = [branch_tip]
            commit_lookup = {c["hash"]: c for c in all_commits}
            while queue:
                curr = queue.pop(0)
                if curr not in reachable:
                    reachable.add(curr)
                    c_obj = commit_lookup.get(curr)
                    if c_obj:
                        queue.extend(c_obj.get("parents", []))
            filtered = [c for c in all_commits if c["hash"] in reachable]

    return {
        "head_ref": "main",
        "selected_branch": branch or "all",
        "mode": "demo",
        "refs": {
            "heads": {"main": c10, "feature/historias": c8, "fix/quiosco": c4},
            "remotes": {"origin/main": c10},
            "tags": {"v1.2.0": c10, "v0.1.0": c1},
        },
        "branches": branches,
        "commits": filtered,
        "total_commits": len(filtered),
        "total_branches": len(branches),
        "total_merges": sum(1 for c in filtered if c.get("is_merge")),
    }

class ICommitProvider(ABC):

    @abstractmethod
    def fetch_commits(self) -> Tuple[List[CommitRecord], Optional[str], str]:

        pass

class DemoCommitProvider(ICommitProvider):

    def fetch_commits(self) -> Tuple[List[CommitRecord], Optional[str], str]:
        now = datetime.datetime.now(datetime.timezone.utc)

        participants_data = [
            {
                "name": "Sofia Code",
                "login": "sofiacode",
                "messages": [
                    "docs: corregir ortografia en historias del parque central",
                    "feat: agregar anecdota sobre el lago de los patos",
                    "style: formato markdown y sangrias en seccion 2",
                    "fix: ajustar encabezados de nivel dos ##",
                    "docs: redactar guia de primeros auxilios en git",
                    "test: validar longitud minima de 50 palabras",
                    "refactor: dividir anecdota 1 en parrafos legibles",
                    "chore: actualizar notas de reflexion semana 1",
                ],
                "hours_offsets": [2, 6, 14, 24, 32, 48, 60, 72],
            },
            {
                "name": "Carlos Git",
                "login": "carlosgit",
                "messages": [
                    "docs: solucionar error tipografico en historia 1",
                    "feat: anadir relato del club de ajedrez",
                    "fix: corregir palabra bolador por volador",
                    "docs: ampliar guia de git blame",
                    "chore: agregar enlace a recursos colaborativos",
                ],
                "hours_offsets": [8, 18, 36, 52, 80],
            },
            {
                "name": "Lucia Tester",
                "login": "luciatester",
                "messages": [
                    "docs: primer commit de prueba en historias",
                    "fix: reparar error en palabra zielo por cielo",
                    "docs: actualizar lista de verificacion local",
                ],
                "hours_offsets": [70, 96, 120],
            },
            {
                "name": "Mateo Rookie",
                "login": "mateorookie",
                "messages": [
                    "docs: saludo inicial y configuracion de perfil",
                ],
                "hours_offsets": [168],
            },
        ]

        commits: List[CommitRecord] = []
        counter = 1000

        for p in participants_data:
            for idx, msg in enumerate(p["messages"]):
                counter += 1
                fake_sha = f"e{counter:04x}a1b2c3d4e5f6a7b8c9d0e1"
                commit_time = now - datetime.timedelta(hours=p["hours_offsets"][idx])

                commits.append(
                    CommitRecord(
                        sha=fake_sha,
                        short_sha=fake_sha[:7],
                        author_name=p["name"],
                        author_login=p["login"],
                        message=msg,
                        date=commit_time,
                    )
                )

        return commits, None, "Modo Demostración (Offline)"

class LocalGitCommitProvider(ICommitProvider):

    def __init__(self, repo_dir: Path | str) -> None:
        self.repo_dir = Path(repo_dir)

    def fetch_commits(self) -> Tuple[List[CommitRecord], Optional[str], str]:
        if not self.repo_dir.exists():
            return [], f"Directorio local '{self.repo_dir}' no existe.", "Git Local"

        git_dir = self.repo_dir / ".git"
        if not git_dir.exists() and not (self.repo_dir / "HEAD").exists():
            return [], f"No es un repositorio Git válido en '{self.repo_dir}'.", "Git Local"

        records = parse_local_commits(self.repo_dir, max_count=150)
        if not records:
            return [], "El repositorio local no contiene commits aún.", "Git Local"

        has_conflicts = check_unresolved_conflicts(self.repo_dir)
        provider_label = f"Git Local ({self.repo_dir.name})"
        if has_conflicts:
            provider_label += " [Conflictos Detectados]"

        return records, None, provider_label

class GitHubApiCommitProvider(ICommitProvider):

    def __init__(
        self,
        repo_slug: str,
        token: Optional[str] = None,
        storage: Optional[Any] = None,
    ) -> None:
        self.repo_slug = repo_slug.strip().strip("/")
        self.token = token.strip() if token else ""
        self.storage = storage
        self.url = f"https://api.github.com/repos/{self.repo_slug}/commits?per_page=100"

    def _get_storage(self) -> Optional[Any]:
        if self.storage is not None:
            return self.storage
        try:
            from .storage import SQLiteStudentStorage
            self.storage = SQLiteStudentStorage()
            return self.storage
        except Exception:
            return None

    def _parse_github_commits(self, raw_data: List[Dict[str, Any]]) -> List[CommitRecord]:
        records: List[CommitRecord] = []
        for item in raw_data:
            sha = item.get("sha", "")
            commit_info = item.get("commit", {})
            author_info = item.get("author") or {}
            committer_raw = commit_info.get("author") or {}

            author_name = committer_raw.get("name") or "Anónimo"
            author_login = author_info.get("login") or author_name.lower().replace(" ", "")
            avatar_url = author_info.get("avatar_url") or ""

            parents_list = tuple(p.get("sha", "") for p in item.get("parents", []) if p.get("sha"))

            raw_date = committer_raw.get("date")
            if raw_date:
                try:
                    date_obj = datetime.datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                except Exception:
                    date_obj = datetime.datetime.now(datetime.timezone.utc)
            else:
                date_obj = datetime.datetime.now(datetime.timezone.utc)

            message = commit_info.get("message", "").split("\n")[0]

            records.append(
                CommitRecord(
                    sha=sha,
                    short_sha=sha[:7] if sha else "unknown",
                    author_name=author_name,
                    author_login=author_login,
                    message=message,
                    date=date_obj,
                    avatar_url=avatar_url,
                    parents=parents_list,
                    is_merge=len(parents_list) >= 2,
                )
            )
        return records

    def fetch_commits(self) -> Tuple[List[CommitRecord], Optional[str], str]:
        if not self.repo_slug or "/" not in self.repo_slug:
            return [], "Slug de GitHub inválido. Usa 'owner/repo' (ej: 'octocat/Hello-World').", "GitHub API"

        storage = self._get_storage()
        cache_entry = storage.get_http_cache(self.url) if storage else None

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Course-Git-Leaderboard",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        if cache_entry and cache_entry.get("etag"):
            headers["If-None-Match"] = cache_entry["etag"]

        try:
            res = requests.get(self.url, headers=headers, timeout=10)
            remaining = int(res.headers.get("x-ratelimit-remaining", 1))

            if res.status_code == 304 and cache_entry:
                try:
                    cached_raw = json.loads(cache_entry["payload_json"])
                    return self._parse_github_commits(cached_raw), None, f"GitHub ({self.repo_slug}) [Cache 304]"
                except Exception:
                    pass

            if res.status_code == 200:
                raw_data = res.json()
                if isinstance(raw_data, list):
                    etag = res.headers.get("ETag")
                    if etag and storage:
                        try:
                            storage.save_http_cache(self.url, etag, json.dumps(raw_data))
                        except Exception:
                            pass
                    return self._parse_github_commits(raw_data), None, f"GitHub ({self.repo_slug})"
                return [], "Respuesta inesperada de GitHub API.", "GitHub API"

            if remaining == 0 or res.status_code in (403, 429):
                if cache_entry:
                    try:
                        cached_raw = json.loads(cache_entry["payload_json"])
                        return self._parse_github_commits(cached_raw), "Límite de API de GitHub alcanzado. Mostrando versión en caché.", f"GitHub ({self.repo_slug}) [Cache Offline]"
                    except Exception:
                        pass
                msg = res.json().get("message", "Límite de tasa de GitHub API excedido.") if res.text else "Rate limit excedido"
                return [], f"GitHub Rate Limit ({res.status_code}): {msg}", "GitHub API"

            if res.status_code == 404:
                return [], f"El repositorio '{self.repo_slug}' no fue encontrado (404).", "GitHub API"

            return [], f"Error en GitHub API ({res.status_code}): {res.text[:100]}", "GitHub API"

        except requests.exceptions.RequestException as exc:
            if cache_entry:
                try:
                    cached_raw = json.loads(cache_entry["payload_json"])
                    return self._parse_github_commits(cached_raw), f"Error de conexión ({exc}). Mostrando versión en caché.", f"GitHub ({self.repo_slug}) [Cache Offline]"
                except Exception:
                    pass
            return [], f"Error de conexión con GitHub: {exc}", "GitHub API"

OptimizedGitHubCommitProvider = GitHubApiCommitProvider

class RepoConfigManager:

    CONFIG_FILENAME = "repo_config.json"

    @classmethod
    def get_config_path(cls) -> Path:
        current_dir = Path(__file__).resolve().parent.parent
        cfg_dir = current_dir / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        return cfg_dir / cls.CONFIG_FILENAME

    @classmethod
    def load_config(cls) -> Dict[str, Any]:
        path = cls.get_config_path()
        defaults = {
            "mode": "auto",            # 'auto', 'local', 'github', 'demo'
            "repo_path": ".",
            "github_repo": "",         # ej: 'owner/repo'
            "github_token": "",
            "last_updated": None,
        }

        if not path.exists():
            try:
                path.write_text(json.dumps(defaults, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
            return defaults

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {**defaults, **data}
        except Exception:
            return defaults

    @classmethod
    def save_config(cls, new_config: Dict[str, Any]) -> bool:
        path = cls.get_config_path()
        try:
            current = cls.load_config()
            merged = {**current, **new_config, "last_updated": datetime.datetime.now().isoformat()}
            path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception:
            return False

class RepoAnalyticsService:

    @classmethod
    def get_provider(
        cls,
        config: Dict[str, Any],
        storage: Optional[Any] = None,
    ) -> ICommitProvider:
        mode = (config.get("mode") or "auto").strip().lower()
        github_repo = (config.get("github_repo") or "").strip()
        repo_path_str = (config.get("repo_path") or ".").strip()

        if mode == "demo":
            return DemoCommitProvider()

        if mode == "github" or (mode == "auto" and github_repo):
            return GitHubApiCommitProvider(
                repo_slug=github_repo,
                token=config.get("github_token"),
                storage=storage,
            )

        repo_dir = Path(repo_path_str)
        if not repo_dir.is_absolute():
            repo_root = Path(__file__).resolve().parent.parent.parent
            repo_dir = (repo_root / repo_path_str).resolve()

        if (repo_dir / ".git").exists():
            return LocalGitCommitProvider(repo_dir=repo_dir)

        return DemoCommitProvider()

    @classmethod
    def get_leaderboard_data(
        cls,
        storage: Optional[Any] = None,
    ) -> Dict[str, Any]:
        config = RepoConfigManager.load_config()
        provider = cls.get_provider(config, storage=storage)
        commits, error_msg, provider_label = provider.fetch_commits()

        if error_msg and not isinstance(provider, DemoCommitProvider):
            fallback_provider = DemoCommitProvider()
            commits, _, fallback_label = fallback_provider.fetch_commits()
            provider_label = f"{fallback_label} (Aviso: {error_msg})"
            error_msg = None

        grouped: Dict[str, ParticipantStats] = {}
        daily_counts: Dict[str, Dict[str, int]] = {}

        for c in commits:
            key = c.author_login.lower()
            if key not in grouped:
                avatar_url = c.avatar_url
                if not avatar_url and storage and hasattr(storage, "get_avatar_hash"):
                    h = storage.get_avatar_hash(key) or storage.get_avatar_hash(c.author_name.lower())
                    if not h:
                        try:
                            from server.core.avatar_processor import auto_load_and_store_repo_avatar
                            disc = auto_load_and_store_repo_avatar(storage, student_keys=[key, c.author_name.lower()])
                            if disc:
                                h = disc.get("avatar_hash")
                        except Exception:
                            pass
                    if not h:
                        h = storage.get_avatar_hash("default")
                    if h:
                        avatar_url = f"/api/avatar/{key}?v={h[:8]}"

                grouped[key] = ParticipantStats(
                    name=c.author_name,
                    login=c.author_login,
                    avatar_url=avatar_url,
                    commits=[],
                )
            if not c.avatar_url and grouped[key].avatar_url:
                c.avatar_url = grouped[key].avatar_url

            grouped[key].commits.append(c)

            day = c.date_iso
            if day not in daily_counts:
                daily_counts[day] = {}
            daily_counts[day][c.author_name] = daily_counts[day].get(c.author_name, 0) + 1

        participants = list(grouped.values())
        participants.sort(key=lambda p: (p.total_commits, p.last_commit_date or datetime.datetime.min), reverse=True)

        max_commits = max((p.total_commits for p in participants), default=1)

        sorted_days = sorted(daily_counts.keys())[-14:]
        daily_activity_series = []
        for day in sorted_days:
            day_data = {"date": day, "total": sum(daily_counts[day].values()), "by_participant": daily_counts[day]}
            daily_activity_series.append(day_data)

        top1 = participants[0].to_dict(max_commits) if len(participants) > 0 else None
        top2 = participants[1].to_dict(max_commits) if len(participants) > 1 else None
        top3 = participants[2].to_dict(max_commits) if len(participants) > 2 else None

        has_conflicts = False
        repo_path_str = (config.get("repo_path") or ".").strip()
        repo_dir = Path(repo_path_str)
        if not repo_dir.is_absolute():
            repo_root = Path(__file__).resolve().parent.parent.parent
            repo_dir = (repo_root / repo_path_str).resolve()
        if (repo_dir / ".git").exists():
            has_conflicts = check_unresolved_conflicts(repo_dir)

        return {
            "provider_label": provider_label,
            "error_msg": error_msg,
            "has_unresolved_conflicts": has_conflicts,
            "total_commits": len(commits),
            "total_participants": len(participants),
            "top_podium": {
                "top1": top1,
                "top2": top2,
                "top3": top3,
            },
            "participants": [p.to_dict(max_commits) for p in participants],
            "daily_activity": daily_activity_series,
            "config": config,
        }
