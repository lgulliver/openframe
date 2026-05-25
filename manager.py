#!/usr/bin/env python3

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


APP_ROOT = Path(os.environ.get("OPENFRAME_APP_ROOT", "/opt/openframe")).resolve()
REPOS_ROOT = Path(os.environ.get("REPOS_ROOT", "/repos")).resolve()
DATA_ROOT = Path(os.environ.get("OPENFRAME_DATA_ROOT", "/data")).resolve()
SETTINGS_PATH = DATA_ROOT / "manager-settings.json"
SHARED_GITCONFIG_PATH = DATA_ROOT / "gitconfig"
GENERATED_OPENCODE_CONFIG_PATH = DATA_ROOT / "opencode.generated.json"
MANAGER_HOST = os.environ.get("OPENCODE_HOSTNAME", "0.0.0.0")
MANAGER_PORT = int(os.environ.get("OPENCODE_PORT", "4096"))
INSTANCE_HOST = os.environ.get("INSTANCE_HOST", "0.0.0.0")
INSTANCE_PORT_START = int(os.environ.get("INSTANCE_PORT_START", "4300"))
INSTANCE_PORT_END = int(os.environ.get("INSTANCE_PORT_END", "4399"))
IDLE_TIMEOUT_SECONDS = int(os.environ.get("INSTANCE_IDLE_TIMEOUT_SECONDS", "1800"))
USERNAME = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode")
PASSWORD = os.environ["OPENCODE_SERVER_PASSWORD"]
CONFIG_PATH = os.environ.get("OPENCODE_CONFIG", str(APP_ROOT / "opencode.json"))
OPEN_IN_BROWSER = os.environ.get("MANAGER_OPEN_INSTANCES_IN_NEW_TAB", "1")

TOOL_ENV_KEYS = (
    "OPENCODE_SERVER_PASSWORD",
    "OPENCODE_SERVER_USERNAME",
    "BROWSER",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", name.strip()).strip("-").lower()
    return slug or "repo"


def basic_auth_header() -> str:
    token = base64.b64encode(f"{USERNAME}:{PASSWORD}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def host_without_port(host: str) -> str:
    value = host.strip()
    if not value:
        return "localhost"
    if value.startswith("["):
        end = value.find("]")
        if end != -1:
            return value[1:end]
        return value
    if value.count(":") == 1:
        name, port = value.rsplit(":", 1)
        if port.isdigit():
            return name
    return value


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    body = json.dumps(payload, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler: BaseHTTPRequestHandler, status: int, body: str, content_type: str = "text/plain; charset=utf-8") -> None:
    encoded = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


class SettingsStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
        self._settings = self._load()
        self._ensure_defaults()
        self._write_gitconfig()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._settings))

    def git_settings(self) -> dict[str, str]:
        with self._lock:
            git_settings = self._settings.setdefault("git", {})
            return {
                "userName": str(git_settings.get("userName", "")),
                "userEmail": str(git_settings.get("userEmail", "")),
                "defaultBranch": str(git_settings.get("defaultBranch", "main")),
                "coreEditor": str(git_settings.get("coreEditor", "")),
            }

    def runtime_settings(self) -> dict[str, str]:
        with self._lock:
            runtime = self._settings.setdefault("runtime", {})
            return {
                "opencodeApiKey": str(runtime.get("opencodeApiKey", "")),
                "openaiApiKey": str(runtime.get("openaiApiKey", "")),
                "anthropicApiKey": str(runtime.get("anthropicApiKey", "")),
                "googleGenerativeAiApiKey": str(runtime.get("googleGenerativeAiApiKey", "")),
                "opencodeModel": str(runtime.get("opencodeModel", "")),
                "opencodeSmallModel": str(runtime.get("opencodeSmallModel", "")),
                "extraConfigJson": str(runtime.get("extraConfigJson", "")),
            }

    def update_git_settings(self, payload: dict[str, Any]) -> dict[str, str]:
        with self._lock:
            git_settings = self._settings.setdefault("git", {})
            git_settings["userName"] = str(payload.get("userName", "")).strip()
            git_settings["userEmail"] = str(payload.get("userEmail", "")).strip()
            git_settings["defaultBranch"] = str(payload.get("defaultBranch", "main")).strip() or "main"
            git_settings["coreEditor"] = str(payload.get("coreEditor", "")).strip()
            self._persist()
            self._write_gitconfig()
            return self.git_settings()

    def update_runtime_settings(self, payload: dict[str, Any]) -> dict[str, str]:
        with self._lock:
            runtime = self._settings.setdefault("runtime", {})
            runtime["opencodeApiKey"] = str(payload.get("opencodeApiKey", "")).strip()
            runtime["openaiApiKey"] = str(payload.get("openaiApiKey", "")).strip()
            runtime["anthropicApiKey"] = str(payload.get("anthropicApiKey", "")).strip()
            runtime["googleGenerativeAiApiKey"] = str(payload.get("googleGenerativeAiApiKey", "")).strip()
            runtime["opencodeModel"] = str(payload.get("opencodeModel", "")).strip()
            runtime["opencodeSmallModel"] = str(payload.get("opencodeSmallModel", "")).strip()
            runtime["extraConfigJson"] = str(payload.get("extraConfigJson", "")).strip()
            self._validate_extra_config(runtime["extraConfigJson"])
            self._persist()
            self._write_opencode_config()
            return self.runtime_settings()

    def runtime_env(self) -> dict[str, str]:
        runtime = self.runtime_settings()
        env: dict[str, str] = {
            "OPENCODE_CONFIG": str(GENERATED_OPENCODE_CONFIG_PATH),
        }
        mapping = {
            "opencodeApiKey": "OPENCODE_API_KEY",
            "openaiApiKey": "OPENAI_API_KEY",
            "anthropicApiKey": "ANTHROPIC_API_KEY",
            "googleGenerativeAiApiKey": "GOOGLE_GENERATIVE_AI_API_KEY",
            "opencodeModel": "OPENCODE_MODEL",
            "opencodeSmallModel": "OPENCODE_SMALL_MODEL",
        }
        for key, env_name in mapping.items():
            if runtime.get(key):
                env[env_name] = runtime[key]
        return env

    def _load(self) -> dict[str, Any]:
        if not SETTINGS_PATH.exists():
            return {}
        try:
            return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _ensure_defaults(self) -> None:
        git_settings = self._settings.setdefault("git", {})
        git_settings.setdefault("userName", os.environ.get("GIT_USER_NAME", ""))
        git_settings.setdefault("userEmail", os.environ.get("GIT_USER_EMAIL", ""))
        git_settings.setdefault("defaultBranch", os.environ.get("GIT_DEFAULT_BRANCH", "main") or "main")
        git_settings.setdefault("coreEditor", os.environ.get("GIT_CORE_EDITOR", ""))
        runtime = self._settings.setdefault("runtime", {})
        runtime.setdefault("opencodeApiKey", os.environ.get("OPENCODE_API_KEY", ""))
        runtime.setdefault("openaiApiKey", os.environ.get("OPENAI_API_KEY", ""))
        runtime.setdefault("anthropicApiKey", os.environ.get("ANTHROPIC_API_KEY", ""))
        runtime.setdefault("googleGenerativeAiApiKey", os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY", ""))
        runtime.setdefault("opencodeModel", os.environ.get("OPENCODE_MODEL", ""))
        runtime.setdefault("opencodeSmallModel", os.environ.get("OPENCODE_SMALL_MODEL", ""))
        runtime.setdefault("extraConfigJson", "")
        self._persist()
        self._write_opencode_config()

    def _persist(self) -> None:
        SETTINGS_PATH.write_text(json.dumps(self._settings, indent=2), encoding="utf-8")

    def _write_gitconfig(self) -> None:
        git_settings = self._settings.get("git", {})
        lines = [
            "[init]",
            f"\tdefaultBranch = {git_settings.get('defaultBranch', 'main') or 'main'}",
        ]
        user_name = str(git_settings.get("userName", "")).strip()
        user_email = str(git_settings.get("userEmail", "")).strip()
        if user_name or user_email:
            lines.append("[user]")
            if user_name:
                lines.append(f"\tname = {user_name}")
            if user_email:
                lines.append(f"\temail = {user_email}")
        core_editor = str(git_settings.get("coreEditor", "")).strip()
        if core_editor:
            lines.append("[core]")
            lines.append(f"\teditor = {core_editor}")
        SHARED_GITCONFIG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_opencode_config(self) -> None:
        base_config: dict[str, Any] = {}
        if Path(CONFIG_PATH).exists():
            try:
                loaded = json.loads(Path(CONFIG_PATH).read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    base_config = loaded
            except json.JSONDecodeError:
                base_config = {}
        runtime = self._settings.get("runtime", {})
        extra_config_json = str(runtime.get("extraConfigJson", "")).strip()
        merged = dict(base_config)
        if extra_config_json:
            extra_loaded = json.loads(extra_config_json)
            if not isinstance(extra_loaded, dict):
                raise ValueError("Extra OpenCode config must be a JSON object")
            merged = deep_merge(merged, extra_loaded)
        GENERATED_OPENCODE_CONFIG_PATH.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")

    def _validate_extra_config(self, value: str) -> None:
        if not value:
            return
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError("Extra OpenCode config must be a JSON object")


SETTINGS = SettingsStore()


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@dataclass
class RepoRecord:
    slug: str
    name: str
    path: Path
    git: bool


@dataclass
class InstanceRecord:
    repo: RepoRecord
    port: int
    process: subprocess.Popen[str]
    started_at: datetime
    last_access_at: datetime
    last_health_at: datetime | None = None
    state_dir: Path | None = None
    log_path: Path | None = None
    stop_reason: str | None = None
    last_error: str | None = None
    last_session_count: int | None = None
    last_session_titles: list[str] = field(default_factory=list)
    session_fingerprint: str | None = None

    def is_running(self) -> bool:
        return self.process.poll() is None

    def url(self, host: str) -> str:
        return f"http://{host}:{self.port}"


class InstanceManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._instances: dict[str, InstanceRecord] = {}
        self._stop_event = threading.Event()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True, name="instance-cleanup")
        self._cleanup_thread.start()

    def list_repos(self) -> list[RepoRecord]:
        repos: list[RepoRecord] = []
        if not REPOS_ROOT.exists():
            return repos
        for child in sorted(REPOS_ROOT.iterdir(), key=lambda item: item.name.lower()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            repos.append(
                RepoRecord(
                    slug=slugify(child.name),
                    name=child.name,
                    path=child.resolve(),
                    git=(child / ".git").exists(),
                )
            )
        return repos

    def repo_by_slug(self, slug: str) -> RepoRecord | None:
        for repo in self.list_repos():
            if repo.slug == slug:
                return repo
        return None

    def snapshot(self, host: str) -> dict[str, Any]:
        repos = self.list_repos()
        with self._lock:
            instance_map = dict(self._instances)
        repo_items = []
        running_count = 0
        for repo in repos:
            instance = instance_map.get(repo.slug)
            if instance and not instance.is_running():
                self._finalize_dead_instance(repo.slug, instance)
                instance = None
            if instance:
                self._refresh_instance_status(instance)
                running_count += 1
            repo_items.append(self._repo_payload(repo, instance, host))
        return {
            "generatedAt": isoformat(utc_now()),
            "reposRoot": str(REPOS_ROOT),
            "runningInstances": running_count,
            "totalRepos": len(repos),
            "idleTimeoutSeconds": IDLE_TIMEOUT_SECONDS,
            "instancePortRange": [INSTANCE_PORT_START, INSTANCE_PORT_END],
            "repos": repo_items,
        }

    def ensure_instance(self, slug: str) -> InstanceRecord:
        repo = self.repo_by_slug(slug)
        if repo is None:
            raise KeyError(f"Unknown repo: {slug}")
        with self._lock:
            existing = self._instances.get(slug)
            if existing and existing.is_running():
                existing.last_access_at = utc_now()
                self._refresh_instance_status(existing)
                return existing
            if existing and not existing.is_running():
                self._finalize_dead_instance(slug, existing)
            port = self._allocate_port(repo.slug)
            instance = self._start_instance(repo, port)
            self._instances[slug] = instance
        self._wait_until_ready(instance)
        return instance

    def attach_command(self, slug: str, host: str) -> str:
        instance = self.ensure_instance(slug)
        return " ".join(
            [
                "opencode",
                "attach",
                "--username",
                shell_quote(USERNAME),
                "--password",
                shell_quote(PASSWORD),
                shell_quote(instance.url(host)),
            ]
        )

    def stop_instance(self, slug: str, reason: str = "manual") -> bool:
        with self._lock:
            instance = self._instances.get(slug)
            if instance is None:
                return False
            self._terminate_instance(instance, reason)
            self._instances.pop(slug, None)
        return True

    def clone_repo(self, url: str, directory_name: str | None = None) -> RepoRecord:
        url = url.strip()
        if not url:
            raise ValueError("Repository URL is required")
        target_name = directory_name.strip() if directory_name else self._repo_name_from_url(url)
        repo = self._create_repo_directory(target_name)
        env = self._git_clone_env()
        try:
            subprocess.run(
                ["git", "clone", url, str(repo.path)],
                check=True,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            shutil.rmtree(repo.path, ignore_errors=True)
            message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            raise RuntimeError(f"git clone failed: {message}") from exc
        return self.repo_by_slug(repo.slug) or repo

    def create_repo(self, name: str, initialize_git: bool = True) -> RepoRecord:
        repo = self._create_repo_directory(name)
        readme = repo.path / "README.md"
        readme.write_text(f"# {repo.name}\n", encoding="utf-8")
        if initialize_git:
            try:
                subprocess.run(
                    ["git", "init"],
                    cwd=repo.path,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except subprocess.CalledProcessError as exc:
                message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
                raise RuntimeError(f"git init failed: {message}") from exc
        return self.repo_by_slug(repo.slug) or repo

    def _repo_payload(self, repo: RepoRecord, instance: InstanceRecord | None, host: str) -> dict[str, Any]:
        payload = {
            "slug": repo.slug,
            "name": repo.name,
            "path": str(repo.path),
            "git": repo.git,
            "running": False,
        }
        if instance is None:
            return payload
        payload.update(
            {
                "running": instance.is_running(),
                "port": instance.port,
                "url": instance.url(host),
                "startedAt": isoformat(instance.started_at),
                "lastAccessAt": isoformat(instance.last_access_at),
                "lastHealthAt": isoformat(instance.last_health_at),
                "stateDir": str(instance.state_dir) if instance.state_dir else None,
                "logPath": str(instance.log_path) if instance.log_path else None,
                "stopReason": instance.stop_reason,
                "lastError": instance.last_error,
                "sessionCount": instance.last_session_count,
                "sessionTitles": instance.last_session_titles,
            }
        )
        return payload

    def _allocate_port(self, slug: str) -> int:
        used = {instance.port for instance in self._instances.values() if instance.is_running()}
        span = INSTANCE_PORT_END - INSTANCE_PORT_START + 1
        preferred_offset = int(hashlib.sha256(slug.encode("utf-8")).hexdigest(), 16) % span
        ordered_offsets = list(range(preferred_offset, span)) + list(range(0, preferred_offset))
        for offset in ordered_offsets:
            port = INSTANCE_PORT_START + offset
            if port in used:
                continue
            if self._port_available(port):
                return port
        raise RuntimeError("No free instance ports available")

    def _create_repo_directory(self, requested_name: str) -> RepoRecord:
        clean_name = requested_name.strip()
        if not clean_name:
            raise ValueError("Repository name is required")
        if "/" in clean_name or clean_name in {".", ".."}:
            raise ValueError("Repository name must be a single directory name")
        target = (REPOS_ROOT / clean_name).resolve()
        if target.parent != REPOS_ROOT:
            raise ValueError("Repository path must stay inside the repos root")
        if target.exists():
            raise ValueError(f"Repository already exists: {clean_name}")
        target.mkdir(parents=False, exist_ok=False)
        return RepoRecord(
            slug=slugify(clean_name),
            name=clean_name,
            path=target,
            git=False,
        )

    def _repo_name_from_url(self, url: str) -> str:
        candidate = url.rstrip("/").rsplit("/", 1)[-1]
        if candidate.endswith(".git"):
            candidate = candidate[:-4]
        if not candidate:
            raise ValueError("Could not derive a repository name from the URL")
        return candidate

    def _git_clone_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"

        username = env.get("GIT_AUTH_USERNAME", "")
        password = env.get("GIT_AUTH_PASSWORD", "")
        github_token = env.get("GITHUB_TOKEN", "")

        if github_token and not password:
            username = username or "x-access-token"
            password = github_token

        if not password:
            return env

        askpass_script = self._write_git_askpass()
        env["GIT_ASKPASS"] = askpass_script
        env["SSH_ASKPASS"] = askpass_script
        env["GIT_CLONE_ASKPASS"] = askpass_script
        env["GIT_AUTH_USERNAME_RUNTIME"] = username
        env["GIT_AUTH_PASSWORD_RUNTIME"] = password
        return env

    def _write_git_askpass(self) -> str:
        askpass_dir = DATA_ROOT / "git"
        askpass_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=askpass_dir,
            prefix="askpass-",
            suffix=".sh",
            delete=False,
        ) as handle:
            handle.write("#!/bin/sh\n")
            handle.write("case \"$1\" in\n")
            handle.write("  *Username*) printf '%s' \"$GIT_AUTH_USERNAME_RUNTIME\" ;;\n")
            handle.write("  *) printf '%s' \"$GIT_AUTH_PASSWORD_RUNTIME\" ;;\n")
            handle.write("esac\n")
        os.chmod(handle.name, 0o700)
        return handle.name

    def _port_available(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((INSTANCE_HOST, port))
            except OSError:
                return False
        return True

    def _start_instance(self, repo: RepoRecord, port: int) -> InstanceRecord:
        slug = repo.slug
        state_dir = DATA_ROOT / "instances" / slug
        home_dir = state_dir / "home"
        log_path = DATA_ROOT / "logs" / f"{slug}.log"
        home_dir.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["HOME"] = str(home_dir)
        env["OPENCODE_PORT"] = str(port)
        env["OPENCODE_HOSTNAME"] = INSTANCE_HOST
        env["BROWSER"] = "/bin/true"
        env["GIT_CONFIG_GLOBAL"] = str(SHARED_GITCONFIG_PATH)
        env.update(SETTINGS.runtime_env())
        for key in TOOL_ENV_KEYS:
            if key in os.environ:
                env[key] = os.environ[key]

        command = [
            "opencode",
            "web",
            "--port",
            str(port),
            "--hostname",
            INSTANCE_HOST,
        ]
        if truthy(os.environ.get("OPENCODE_MDNS", "")):
            command.append("--mdns")
        if os.environ.get("OPENCODE_MDNS_DOMAIN"):
            command.extend(["--mdns-domain", os.environ["OPENCODE_MDNS_DOMAIN"]])
        cors_value = os.environ.get("OPENCODE_CORS", "")
        if cors_value:
            for origin in cors_value.split(","):
                origin = origin.strip()
                if origin:
                    command.extend(["--cors", origin])

        log_file = log_path.open("a", encoding="utf-8")
        process = subprocess.Popen(
            command,
            cwd=repo.path,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        now = utc_now()
        return InstanceRecord(
            repo=repo,
            port=port,
            process=process,
            started_at=now,
            last_access_at=now,
            state_dir=state_dir,
            log_path=log_path,
        )

    def _wait_until_ready(self, instance: InstanceRecord) -> None:
        deadline = time.time() + 20
        last_error = ""
        while time.time() < deadline:
            if not instance.is_running():
                raise RuntimeError(f"OpenCode instance for {instance.repo.name} exited early")
            try:
                data = self._request_json(instance.port, "/global/health")
                if data.get("healthy") is True:
                    instance.last_health_at = utc_now()
                    self._refresh_instance_status(instance)
                    return
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
            time.sleep(0.5)
        raise RuntimeError(f"Timed out waiting for OpenCode instance for {instance.repo.name}: {last_error}")

    def _request_json(self, port: int, path: str) -> Any:
        request = Request(f"http://127.0.0.1:{port}{path}")
        request.add_header("Authorization", basic_auth_header())
        with urlopen(request, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))

    def _refresh_instance_status(self, instance: InstanceRecord) -> None:
        if not instance.is_running():
            return
        try:
            health = self._request_json(instance.port, "/global/health")
            if health.get("healthy") is True:
                instance.last_health_at = utc_now()
            sessions = self._request_json(instance.port, "/session")
            titles: list[str] = []
            if isinstance(sessions, list):
                fingerprint = json.dumps(sessions, sort_keys=True, default=str)
                if fingerprint != instance.session_fingerprint:
                    instance.last_access_at = utc_now()
                    instance.session_fingerprint = fingerprint
                for session in sessions[:5]:
                    if isinstance(session, dict):
                        title = session.get("title") or session.get("id")
                        if title:
                            titles.append(str(title))
                instance.last_session_count = len(sessions)
                instance.last_session_titles = titles
        except Exception as exc:  # noqa: BLE001
            instance.last_error = str(exc)

    def _terminate_instance(self, instance: InstanceRecord, reason: str) -> None:
        instance.stop_reason = reason
        if instance.is_running():
            instance.process.terminate()
            try:
                instance.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                instance.process.kill()
                instance.process.wait(timeout=5)

    def _finalize_dead_instance(self, slug: str, instance: InstanceRecord) -> None:
        self._instances.pop(slug, None)

    def _cleanup_loop(self) -> None:
        while not self._stop_event.wait(15):
            now = utc_now()
            to_stop: list[tuple[str, InstanceRecord]] = []
            with self._lock:
                for slug, instance in list(self._instances.items()):
                    if not instance.is_running():
                        to_stop.append((slug, instance))
                        continue
                    self._refresh_instance_status(instance)
                    if (now - instance.last_access_at).total_seconds() > IDLE_TIMEOUT_SECONDS:
                        to_stop.append((slug, instance))
                for slug, instance in to_stop:
                    if instance.is_running():
                        self._terminate_instance(instance, "idle-timeout")
                    self._instances.pop(slug, None)


def truthy(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


INSTANCE_MANAGER = InstanceManager()


def dashboard_html(snapshot: dict[str, Any], request_host: str) -> str:
    data = json.dumps(snapshot)
    open_target = "_blank" if OPEN_IN_BROWSER != "0" else "_self"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OpenFrame</title>
  <style>
    :root {{
      --bg: #f3efe5;
      --panel: #fffdf8;
      --ink: #1f1a16;
      --muted: #6f655d;
      --line: #d8cfc4;
      --accent: #0f766e;
      --accent-2: #164e63;
      --danger: #b42318;
      --shadow: 0 18px 45px rgba(35, 25, 17, 0.10);
      --radius: 18px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(15,118,110,0.18), transparent 28%),
        radial-gradient(circle at top right, rgba(22,78,99,0.12), transparent 22%),
        linear-gradient(180deg, #efe8db 0%, var(--bg) 45%, #ece6dc 100%);
      min-height: 100vh;
    }}
    .shell {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 32px 20px 56px;
    }}
    .hero {{
      display: grid;
      gap: 18px;
      margin-bottom: 24px;
    }}
    .headline {{
      display: flex;
      flex-wrap: wrap;
      align-items: end;
      justify-content: space-between;
      gap: 16px;
      padding: 26px;
      border: 1px solid rgba(31,26,22,0.08);
      border-radius: calc(var(--radius) + 6px);
      background: rgba(255,253,248,0.82);
      box-shadow: var(--shadow);
      backdrop-filter: blur(8px);
    }}
    h1 {{
      margin: 0;
      font-size: clamp(2rem, 4vw, 3.7rem);
      line-height: 0.95;
      letter-spacing: -0.05em;
    }}
    .sub {{
      margin-top: 8px;
      max-width: 720px;
      color: var(--muted);
      font-size: 1rem;
      line-height: 1.5;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 14px;
    }}
    .stat {{
      padding: 18px;
      border-radius: var(--radius);
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: var(--shadow);
    }}
    .stat strong {{
      display: block;
      font-size: 1.8rem;
      letter-spacing: -0.04em;
    }}
    .stat span {{
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 16px;
    }}
    .repo {{
      display: grid;
      gap: 14px;
      padding: 18px;
      border-radius: var(--radius);
      border: 1px solid var(--line);
      background: rgba(255,253,248,0.94);
      box-shadow: var(--shadow);
    }}
    .repo-head {{
      display: flex;
      justify-content: space-between;
      align-items: start;
      gap: 14px;
    }}
    .repo-name {{
      margin: 0;
      font-size: 1.2rem;
      letter-spacing: -0.03em;
    }}
    .repo-path {{
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      color: var(--muted);
      font-size: 0.83rem;
      word-break: break-all;
      margin-top: 6px;
    }}
    .badge {{
      border-radius: 999px;
      padding: 8px 11px;
      font-size: 0.76rem;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      white-space: nowrap;
    }}
    .running {{ background: rgba(15,118,110,0.12); color: var(--accent); }}
    .stopped {{ background: rgba(111,101,93,0.12); color: var(--muted); }}
    .meta {{
      display: grid;
      gap: 8px;
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .meta code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      color: var(--ink);
      background: rgba(31,26,22,0.05);
      padding: 2px 5px;
      border-radius: 6px;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    button, a.action {{
      appearance: none;
      border: 0;
      border-radius: 12px;
      padding: 11px 14px;
      text-decoration: none;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      transition: transform 120ms ease, opacity 120ms ease;
    }}
    button:hover, a.action:hover {{
      transform: translateY(-1px);
    }}
    .primary {{
      background: var(--accent);
      color: white;
    }}
    .secondary {{
      background: rgba(22,78,99,0.10);
      color: var(--accent-2);
    }}
    .danger {{
      background: rgba(180,35,24,0.11);
      color: var(--danger);
    }}
    .sessions {{
      display: grid;
      gap: 6px;
      margin-top: 4px;
    }}
    .session {{
      padding: 9px 10px;
      border-radius: 12px;
      background: rgba(31,26,22,0.04);
      font-size: 0.88rem;
    }}
    .empty {{
      color: var(--muted);
      font-style: italic;
      font-size: 0.88rem;
    }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 18px;
    }}
    .toolbar small {{
      color: var(--muted);
    }}
    .statusbar {{
      min-height: 24px;
      margin-bottom: 18px;
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .statusbar.error {{
      color: var(--danger);
    }}
    .statusbar.success {{
      color: var(--accent);
    }}
    dialog {{
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 0;
      width: min(640px, calc(100vw - 24px));
      background: var(--panel);
      box-shadow: var(--shadow);
    }}
    dialog::backdrop {{
      background: rgba(31,26,22,0.36);
      backdrop-filter: blur(4px);
    }}
    .modal {{
      display: grid;
      gap: 16px;
      padding: 22px;
    }}
    .modal h3 {{
      margin: 0;
      font-size: 1.2rem;
      letter-spacing: -0.03em;
    }}
    .modal p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.45;
    }}
    .field {{
      display: grid;
      gap: 6px;
    }}
    .field label {{
      color: var(--muted);
      font-size: 0.88rem;
      font-weight: 600;
    }}
    .field input, .field textarea {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 11px 12px;
      font: inherit;
      color: var(--ink);
      background: white;
    }}
    .field textarea {{
      min-height: 150px;
      resize: vertical;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.88rem;
    }}
    .checkbox {{
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 0.95rem;
    }}
    .modal-actions {{
      display: flex;
      justify-content: flex-end;
      gap: 10px;
    }}
    @media (max-width: 700px) {{
      .headline {{
        padding: 20px;
      }}
      .shell {{
        padding: 20px 14px 40px;
      }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="headline">
        <div>
          <h1>OpenFrame</h1>
          <div class="sub">One dashboard, many repos. Launch repo-scoped OpenCode web runtimes on demand, keep an overview of active work, and let idle instances shut themselves down.</div>
        </div>
        <div>
          <small>Repos root: <code>{escape_html(snapshot["reposRoot"])}</code></small>
        </div>
      </div>
      <div class="stats">
        <div class="stat"><strong id="total-repos">{snapshot["totalRepos"]}</strong><span>Visible repos</span></div>
        <div class="stat"><strong id="running-instances">{snapshot["runningInstances"]}</strong><span>Running instances</span></div>
        <div class="stat"><strong id="idle-timeout">{snapshot["idleTimeoutSeconds"] // 60}</strong><span>Idle timeout (minutes)</span></div>
      </div>
    </section>
    <section class="toolbar">
      <small>Manager: http://{escape_html(request_host)} | Instance ports: {snapshot["instancePortRange"][0]}-{snapshot["instancePortRange"][1]}</small>
      <div class="actions">
        <button class="secondary" id="git-settings">Git Settings</button>
        <button class="secondary" id="runtime-settings">API Keys + Config</button>
        <button class="secondary" id="clone-repo">Clone Repo</button>
        <button class="secondary" id="create-repo">Create Repo</button>
        <button class="secondary" id="refresh">Refresh</button>
      </div>
    </section>
    <div class="statusbar" id="statusbar"></div>
    <section class="grid" id="repo-grid"></section>
  </main>
  <dialog id="modal">
    <form method="dialog" class="modal" id="modal-form">
      <h3 id="modal-title"></h3>
      <p id="modal-copy"></p>
      <div id="modal-fields"></div>
      <div class="modal-actions">
        <button type="button" class="secondary" id="modal-cancel">Cancel</button>
        <button type="submit" class="primary" id="modal-submit">Save</button>
      </div>
    </form>
  </dialog>
  <script>
    const snapshot = {data};
    const grid = document.getElementById("repo-grid");
    const targetMode = {json.dumps(open_target)};
    const statusbar = document.getElementById("statusbar");
    const totalReposStat = document.getElementById("total-repos");
    const runningInstancesStat = document.getElementById("running-instances");
    const idleTimeoutStat = document.getElementById("idle-timeout");
    const modal = document.getElementById("modal");
    const modalForm = document.getElementById("modal-form");
    const modalTitle = document.getElementById("modal-title");
    const modalCopy = document.getElementById("modal-copy");
    const modalFields = document.getElementById("modal-fields");
    const modalCancel = document.getElementById("modal-cancel");
    const modalSubmit = document.getElementById("modal-submit");
    let modalHandler = null;

    function escapeHtml(value) {{
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }}

    function formatDate(value) {{
      if (!value) return "never";
      try {{
        return new Date(value).toLocaleString();
      }} catch (_err) {{
        return value;
      }}
    }}

    function setStatus(message = "", kind = "") {{
      statusbar.textContent = message;
      statusbar.className = `statusbar${{kind ? ` ${{kind}}` : ""}}`;
    }}

    function fieldHtml(field) {{
      if (field.type === "textarea") {{
        return `
          <div class="field">
            <label for="${{field.name}}">${{escapeHtml(field.label)}}</label>
            <textarea id="${{field.name}}" name="${{field.name}}" placeholder="${{escapeHtml(field.placeholder || "")}}">${{escapeHtml(field.value || "")}}</textarea>
          </div>
        `;
      }}
      if (field.type === "checkbox") {{
        return `
          <label class="checkbox">
            <input type="checkbox" name="${{field.name}}" ${{field.checked ? "checked" : ""}}>
            <span>${{escapeHtml(field.label)}}</span>
          </label>
        `;
      }}
      return `
        <div class="field">
          <label for="${{field.name}}">${{escapeHtml(field.label)}}</label>
          <input id="${{field.name}}" name="${{field.name}}" type="${{field.type || "text"}}" value="${{escapeHtml(field.value || "")}}" placeholder="${{escapeHtml(field.placeholder || "")}}">
        </div>
      `;
    }}

    function openModal(config) {{
      modalTitle.textContent = config.title;
      modalCopy.textContent = config.copy || "";
      modalSubmit.textContent = config.submitLabel || "Save";
      modalFields.innerHTML = config.fields.map(fieldHtml).join("");
      modalHandler = config.onSubmit;
      modal.showModal();
    }}

    function closeModal() {{
      modal.close();
      modalFields.innerHTML = "";
      modalHandler = null;
    }}

    modalCancel.addEventListener("click", closeModal);
    modal.addEventListener("close", () => {{
      modalFields.innerHTML = "";
      modalHandler = null;
    }});

    modalForm.addEventListener("submit", async (event) => {{
      event.preventDefault();
      if (!modalHandler) return;
      const formData = new FormData(modalForm);
      const payload = Object.fromEntries(formData.entries());
      for (const input of modalForm.querySelectorAll('input[type="checkbox"]')) {{
        payload[input.name] = input.checked;
      }}
      modalSubmit.setAttribute("disabled", "disabled");
      try {{
        await modalHandler(payload);
        closeModal();
      }} catch (error) {{
        setStatus(error.message, "error");
      }} finally {{
        modalSubmit.removeAttribute("disabled");
      }}
    }});

    function repoCard(repo) {{
      const badge = repo.running
        ? '<span class="badge running">running</span>'
        : '<span class="badge stopped">stopped</span>';

      const sessions = repo.sessionTitles && repo.sessionTitles.length
        ? repo.sessionTitles.map((title) => `<div class="session">${{escapeHtml(title)}}</div>`).join("")
        : '<div class="empty">No session summary available yet.</div>';

      const openAction = repo.running
        ? `<a class="action primary" target="${{targetMode}}" rel="noreferrer" href="${{repo.url}}">Open Repo</a>`
        : `<button class="primary" data-action="start" data-slug="${{repo.slug}}">Start Repo</button>`;

      const stopAction = repo.running
        ? `<button class="danger" data-action="stop" data-slug="${{repo.slug}}">Stop Instance</button>`
        : "";

      const attachAction = repo.running
        ? `<button class="secondary" data-action="attach" data-slug="${{repo.slug}}">Show Attach Command</button>`
        : "";

      return `
        <article class="repo">
          <div class="repo-head">
            <div>
              <h2 class="repo-name">${{escapeHtml(repo.name)}}</h2>
              <div class="repo-path">${{escapeHtml(repo.path)}}</div>
            </div>
            ${{badge}}
          </div>
          <div class="meta">
            <div>Git repo: <code>${{repo.git ? "yes" : "no"}}</code></div>
            <div>Last access: <code>${{formatDate(repo.lastAccessAt)}}</code></div>
            <div>Sessions seen: <code>${{repo.sessionCount ?? 0}}</code></div>
            ${{repo.port ? `<div>Port: <code>${{repo.port}}</code></div>` : ""}}
            ${{repo.lastError ? `<div>Last error: <code>${{escapeHtml(repo.lastError)}}</code></div>` : ""}}
          </div>
          <div class="actions">
            ${{openAction}}
            ${{stopAction}}
            ${{attachAction}}
          </div>
          <div class="sessions">${{sessions}}</div>
        </article>
      `;
    }}

    function renderStats(data) {{
      totalReposStat.textContent = String(data.totalRepos ?? 0);
      runningInstancesStat.textContent = String(data.runningInstances ?? 0);
      idleTimeoutStat.textContent = String(Math.round((data.idleTimeoutSeconds ?? 0) / 60));
    }}

    function render(data) {{
      renderStats(data);
      grid.innerHTML = data.repos.map(repoCard).join("");
    }}

    function openStartedInstance(url, pendingWindow) {{
      if (targetMode === "_self") {{
        window.location.assign(url);
        return;
      }}
      if (pendingWindow && !pendingWindow.closed) {{
        pendingWindow.location = url;
        pendingWindow.focus?.();
        return;
      }}
      const opened = window.open(url, targetMode);
      if (!opened) {{
        window.location.assign(url);
      }}
    }}

    async function api(path, method = "GET") {{
      let body;
      if (method !== "GET" && arguments.length > 2 && arguments[2] !== undefined) {{
        body = JSON.stringify(arguments[2]);
      }}
      const response = await fetch(path, {{
        method,
        body,
        headers: {{ "Content-Type": "application/json" }},
      }});
      if (!response.ok) {{
        const text = await response.text();
        throw new Error(text || `${{response.status}} ${{response.statusText}}`);
      }}
      return response.json();
    }}

    async function refresh() {{
      const latest = await api("/api/status");
      render(latest);
      setStatus(`Loaded ${{latest.totalRepos}} repos, ${{latest.runningInstances}} running instances.`, "success");
    }}

    grid.addEventListener("click", async (event) => {{
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      const action = target.dataset.action;
      if (!action) return;

      if (action === "start") {{
        const slug = target.dataset.slug;
        const pendingWindow = targetMode === "_blank" ? window.open("", targetMode) : null;
        target.setAttribute("disabled", "disabled");
        try {{
          const result = await api(`/api/repos/${{slug}}/start`, "POST");
          await refresh();
          openStartedInstance(result.url, pendingWindow);
        }} catch (error) {{
          pendingWindow?.close?.();
          setStatus(error.message, "error");
        }} finally {{
          target.removeAttribute("disabled");
        }}
      }}

      if (action === "stop") {{
        const slug = target.dataset.slug;
        target.setAttribute("disabled", "disabled");
        try {{
          await api(`/api/repos/${{slug}}/stop`, "POST");
          await refresh();
        }} catch (error) {{
          setStatus(error.message, "error");
        }} finally {{
          target.removeAttribute("disabled");
        }}
      }}

      if (action === "attach") {{
        const slug = target.dataset.slug;
        target.setAttribute("disabled", "disabled");
        try {{
          const result = await api(`/api/repos/${{slug}}/attach`, "POST");
          navigator.clipboard?.writeText(result.command).catch(() => undefined);
          setStatus(`Attach locally with: ${{result.command}}`, "success");
        }} catch (error) {{
          setStatus(error.message, "error");
        }} finally {{
          target.removeAttribute("disabled");
        }}
      }}
    }});

    document.getElementById("refresh").addEventListener("click", refresh);
    document.getElementById("git-settings").addEventListener("click", async () => {{
      try {{
        const current = await api("/api/settings/git");
        openModal({{
          title: "Git Settings",
          copy: "These values are stored locally and applied to new repo instances.",
          submitLabel: "Save Git Settings",
          fields: [
            {{ name: "userName", label: "Git user.name", value: current.userName ?? "" }},
            {{ name: "userEmail", label: "Git user.email", value: current.userEmail ?? "" }},
            {{ name: "defaultBranch", label: "Git init.defaultBranch", value: current.defaultBranch ?? "main" }},
            {{ name: "coreEditor", label: "Git core.editor", value: current.coreEditor ?? "" }},
          ],
          onSubmit: async (payload) => {{
            await api("/api/settings/git", "POST", payload);
            setStatus("Git settings saved. New repo instances will inherit them.", "success");
          }},
        }});
      }} catch (error) {{
        setStatus(error.message, "error");
      }}
    }});
    document.getElementById("runtime-settings").addEventListener("click", async () => {{
      try {{
        const current = await api("/api/settings/runtime");
        openModal({{
          title: "API Keys + Config",
          copy: "These settings are stored locally and applied to new repo instances.",
          submitLabel: "Save Runtime Settings",
          fields: [
            {{ name: "opencodeApiKey", label: "OPENCODE_API_KEY", value: current.opencodeApiKey ?? "", type: "password" }},
            {{ name: "openaiApiKey", label: "OPENAI_API_KEY", value: current.openaiApiKey ?? "", type: "password" }},
            {{ name: "anthropicApiKey", label: "ANTHROPIC_API_KEY", value: current.anthropicApiKey ?? "", type: "password" }},
            {{ name: "googleGenerativeAiApiKey", label: "GOOGLE_GENERATIVE_AI_API_KEY", value: current.googleGenerativeAiApiKey ?? "", type: "password" }},
            {{ name: "opencodeModel", label: "OPENCODE_MODEL", value: current.opencodeModel ?? "" }},
            {{ name: "opencodeSmallModel", label: "OPENCODE_SMALL_MODEL", value: current.opencodeSmallModel ?? "" }},
            {{ name: "extraConfigJson", label: "Extra OpenCode config JSON object", value: current.extraConfigJson ?? "", type: "textarea", placeholder: "{{\\n  \\"providers\\": {{}}\\n}}" }},
          ],
          onSubmit: async (payload) => {{
            await api("/api/settings/runtime", "POST", payload);
            setStatus("Runtime settings saved. New repo instances will inherit them.", "success");
          }},
        }});
      }} catch (error) {{
        setStatus(error.message, "error");
      }}
    }});
    document.getElementById("clone-repo").addEventListener("click", async () => {{
      openModal({{
        title: "Clone Repo",
        copy: "Clone a remote repository into /repos.",
        submitLabel: "Clone",
        fields: [
          {{ name: "url", label: "Git clone URL", value: "", placeholder: "https://github.com/org/repo.git" }},
          {{ name: "directoryName", label: "Directory name under /repos", value: "", placeholder: "Optional override" }},
        ],
        onSubmit: async (payload) => {{
          await api("/api/repos/clone", "POST", {{
            url: payload.url,
            directoryName: payload.directoryName || undefined,
          }});
          await refresh();
          setStatus("Repository cloned successfully.", "success");
        }},
      }});
    }});
    document.getElementById("create-repo").addEventListener("click", async () => {{
      openModal({{
        title: "Create Repo",
        copy: "Create a new repository directory under /repos.",
        submitLabel: "Create",
        fields: [
          {{ name: "name", label: "Repository directory name", value: "", placeholder: "my-new-repo" }},
          {{ name: "initializeGit", label: "Initialize this repo with git", type: "checkbox", checked: true }},
        ],
        onSubmit: async (payload) => {{
          await api("/api/repos/create", "POST", {{
            name: payload.name,
            initializeGit: payload.initializeGit,
          }});
          await refresh();
          setStatus("Repository created successfully.", "success");
        }},
      }});
    }});
    render(snapshot);
  </script>
</body>
</html>
"""


def escape_html(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


class ManagerHandler(BaseHTTPRequestHandler):
    server_version = "OpenCodeRemoteManager/0.1"

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/":
            snapshot = INSTANCE_MANAGER.snapshot(self._browser_host())
            text_response(self, HTTPStatus.OK, dashboard_html(snapshot, self.headers.get("Host", f"localhost:{MANAGER_PORT}")), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/status":
            json_response(self, HTTPStatus.OK, INSTANCE_MANAGER.snapshot(self._browser_host()))
            return
        if parsed.path == "/api/settings/git":
            json_response(self, HTTPStatus.OK, SETTINGS.git_settings())
            return
        if parsed.path == "/api/settings/runtime":
            json_response(self, HTTPStatus.OK, SETTINGS.runtime_settings())
            return
        if parsed.path == "/health":
            json_response(self, HTTPStatus.OK, {"healthy": True, "time": isoformat(utc_now())})
            return
        text_response(self, HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/settings/git":
            payload = self._read_json_body()
            if payload is None:
                return
            json_response(self, HTTPStatus.OK, SETTINGS.update_git_settings(payload))
            return
        if parsed.path == "/api/settings/runtime":
            payload = self._read_json_body()
            if payload is None:
                return
            try:
                updated = SETTINGS.update_runtime_settings(payload)
            except ValueError as exc:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            json_response(self, HTTPStatus.OK, updated)
            return
        if parsed.path == "/api/repos/clone":
            payload = self._read_json_body()
            if payload is None:
                return
            try:
                repo = INSTANCE_MANAGER.clone_repo(
                    str(payload.get("url", "")),
                    str(payload["directoryName"]) if payload.get("directoryName") else None,
                )
            except (ValueError, RuntimeError) as exc:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            json_response(self, HTTPStatus.CREATED, {"repo": repo.slug, "name": repo.name, "path": str(repo.path)})
            return
        if parsed.path == "/api/repos/create":
            payload = self._read_json_body()
            if payload is None:
                return
            try:
                repo = INSTANCE_MANAGER.create_repo(
                    str(payload.get("name", "")),
                    bool(payload.get("initializeGit", True)),
                )
            except (ValueError, RuntimeError) as exc:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            json_response(self, HTTPStatus.CREATED, {"repo": repo.slug, "name": repo.name, "path": str(repo.path)})
            return
        match = re.fullmatch(r"/api/repos/([a-z0-9._-]+)/start", parsed.path)
        if match:
            slug = match.group(1)
            try:
                instance = INSTANCE_MANAGER.ensure_instance(slug)
            except KeyError:
                json_response(self, HTTPStatus.NOT_FOUND, {"error": f"Unknown repo: {slug}"})
                return
            except Exception as exc:  # noqa: BLE001
                json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return
            host = self._browser_host()
            json_response(
                self,
                HTTPStatus.OK,
                {
                    "repo": slug,
                    "port": instance.port,
                    "url": instance.url(host),
                    "startedAt": isoformat(instance.started_at),
                },
            )
            return
        match = re.fullmatch(r"/api/repos/([a-z0-9._-]+)/attach", parsed.path)
        if match:
            slug = match.group(1)
            try:
                command = INSTANCE_MANAGER.attach_command(slug, self._browser_host())
            except KeyError:
                json_response(self, HTTPStatus.NOT_FOUND, {"error": f"Unknown repo: {slug}"})
                return
            except Exception as exc:  # noqa: BLE001
                json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return
            json_response(self, HTTPStatus.OK, {"repo": slug, "command": command})
            return
        match = re.fullmatch(r"/api/repos/([a-z0-9._-]+)/stop", parsed.path)
        if match:
            slug = match.group(1)
            stopped = INSTANCE_MANAGER.stop_instance(slug)
            if not stopped:
                json_response(self, HTTPStatus.NOT_FOUND, {"error": f"No running instance for {slug}"})
                return
            json_response(self, HTTPStatus.OK, {"repo": slug, "stopped": True})
            return
        text_response(self, HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        expected = basic_auth_header()
        if header == expected:
            return True
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("WWW-Authenticate", 'Basic realm="OpenFrame"')
        self.end_headers()
        return False

    def _read_json_body(self) -> dict[str, Any] | None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Invalid Content-Length"})
            return None
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Request body must be valid JSON"})
            return None
        if not isinstance(payload, dict):
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "Request body must be a JSON object"})
            return None
        return payload

    def _browser_host(self) -> str:
        host = self.headers.get("Host", f"localhost:{MANAGER_PORT}")
        return host_without_port(host)


def main() -> None:
    server = ThreadingHTTPServer((MANAGER_HOST, MANAGER_PORT), ManagerHandler)
    print(
        json.dumps(
            {
                "event": "manager.start",
                "reposRoot": str(REPOS_ROOT),
                "host": MANAGER_HOST,
                "port": MANAGER_PORT,
                "instancePortStart": INSTANCE_PORT_START,
                "instancePortEnd": INSTANCE_PORT_END,
                "idleTimeoutSeconds": IDLE_TIMEOUT_SECONDS,
            }
        ),
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
