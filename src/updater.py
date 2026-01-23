import asyncio
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from src import __version__

GITHUB_REPO = "spfcraze/Ultra-Claude"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}"
GITHUB_RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}"


@dataclass
class UpdateInfo:
    current_version: str
    latest_version: Optional[str]
    update_available: bool
    release_url: Optional[str] = None
    release_notes: Optional[str] = None
    published_at: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "update_available": self.update_available,
            "release_url": self.release_url,
            "release_notes": self.release_notes,
            "published_at": self.published_at,
            "error": self.error,
        }


class Updater:
    def __init__(self):
        self.current_version = __version__
        self._project_root = self._find_project_root()

    def _find_project_root(self) -> Path:
        current = Path(__file__).parent.parent
        if (current / ".git").exists():
            return current
        if (current / "pyproject.toml").exists():
            return current
        return current

    def _parse_version(self, version: str) -> tuple:
        version = version.lstrip("v")
        parts = version.split(".")
        result = []
        for part in parts:
            try:
                result.append(int(part.split("-")[0].split("+")[0]))
            except ValueError:
                result.append(0)
        while len(result) < 3:
            result.append(0)
        return tuple(result[:3])

    def _is_newer_version(self, latest: str, current: str) -> bool:
        latest_tuple = self._parse_version(latest)
        current_tuple = self._parse_version(current)
        return latest_tuple > current_tuple

    async def check_for_updates(self) -> UpdateInfo:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{GITHUB_API_URL}/releases/latest",
                    headers={"Accept": "application/vnd.github.v3+json"},
                )

                if response.status_code == 404:
                    return await self._check_commits_for_updates(client)

                if response.status_code != 200:
                    return UpdateInfo(
                        current_version=self.current_version,
                        latest_version=None,
                        update_available=False,
                        error=f"GitHub API error: {response.status_code}",
                    )

                data = response.json()
                latest_version = data.get("tag_name", "").lstrip("v")

                if not latest_version:
                    return await self._check_commits_for_updates(client)

                update_available = self._is_newer_version(latest_version, self.current_version)

                return UpdateInfo(
                    current_version=self.current_version,
                    latest_version=latest_version,
                    update_available=update_available,
                    release_url=data.get("html_url"),
                    release_notes=data.get("body", "")[:500] if data.get("body") else None,
                    published_at=data.get("published_at"),
                )

        except httpx.TimeoutException:
            return UpdateInfo(
                current_version=self.current_version,
                latest_version=None,
                update_available=False,
                error="Connection timeout",
            )
        except Exception as e:
            return UpdateInfo(
                current_version=self.current_version,
                latest_version=None,
                update_available=False,
                error=str(e),
            )

    async def _check_commits_for_updates(self, client: httpx.AsyncClient) -> UpdateInfo:
        try:
            response = await client.get(
                f"{GITHUB_RAW_URL}/main/src/__init__.py",
                follow_redirects=True,
            )

            if response.status_code != 200:
                response = await client.get(
                    f"{GITHUB_RAW_URL}/master/src/__init__.py",
                    follow_redirects=True,
                )

            if response.status_code == 200:
                content = response.text
                for line in content.split("\n"):
                    if "__version__" in line and "=" in line:
                        version = line.split("=")[1].strip().strip("\"'")
                        update_available = self._is_newer_version(version, self.current_version)
                        return UpdateInfo(
                            current_version=self.current_version,
                            latest_version=version,
                            update_available=update_available,
                            release_url=f"https://github.com/{GITHUB_REPO}",
                        )

            return UpdateInfo(
                current_version=self.current_version,
                latest_version=None,
                update_available=False,
                error="Could not determine latest version",
            )

        except Exception as e:
            return UpdateInfo(
                current_version=self.current_version,
                latest_version=None,
                update_available=False,
                error=str(e),
            )

    def is_git_repo(self) -> bool:
        return (self._project_root / ".git").exists()

    async def get_local_git_status(self) -> dict:
        if not self.is_git_repo():
            return {"is_git": False, "error": "Not a git repository"}

        try:
            result = await asyncio.create_subprocess_exec(
                "git", "rev-parse", "--short", "HEAD",
                cwd=str(self._project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await result.communicate()
            local_commit = stdout.decode().strip() if result.returncode == 0 else None

            result = await asyncio.create_subprocess_exec(
                "git", "status", "--porcelain",
                cwd=str(self._project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await result.communicate()
            has_changes = bool(stdout.decode().strip()) if result.returncode == 0 else False

            result = await asyncio.create_subprocess_exec(
                "git", "rev-parse", "--abbrev-ref", "HEAD",
                cwd=str(self._project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await result.communicate()
            branch = stdout.decode().strip() if result.returncode == 0 else "unknown"

            return {
                "is_git": True,
                "local_commit": local_commit,
                "branch": branch,
                "has_uncommitted_changes": has_changes,
            }

        except Exception as e:
            return {"is_git": True, "error": str(e)}

    async def update(self, force: bool = False) -> dict:
        if not self.is_git_repo():
            return {
                "success": False,
                "error": "Not a git repository. Please update manually by downloading from GitHub.",
                "manual_url": f"https://github.com/{GITHUB_REPO}",
            }

        git_status = await self.get_local_git_status()
        if git_status.get("has_uncommitted_changes") and not force:
            return {
                "success": False,
                "error": "You have uncommitted changes. Commit or stash them first, or use force=true.",
            }

        try:
            result = await asyncio.create_subprocess_exec(
                "git", "fetch", "origin",
                cwd=str(self._project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await result.communicate()
            if result.returncode != 0:
                return {"success": False, "error": f"git fetch failed: {stderr.decode()}"}

            branch = git_status.get("branch", "main")
            
            if force:
                result = await asyncio.create_subprocess_exec(
                    "git", "reset", "--hard", f"origin/{branch}",
                    cwd=str(self._project_root),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                result = await asyncio.create_subprocess_exec(
                    "git", "pull", "origin", branch,
                    cwd=str(self._project_root),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                return {"success": False, "error": f"git pull failed: {stderr.decode()}"}

            output = stdout.decode()
            already_up_to_date = "Already up to date" in output or "Already up-to-date" in output

            result = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "-e", ".",
                cwd=str(self._project_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            pip_stdout, pip_stderr = await result.communicate()

            return {
                "success": True,
                "already_up_to_date": already_up_to_date,
                "git_output": output,
                "pip_output": pip_stdout.decode()[:500],
                "restart_required": not already_up_to_date,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


updater = Updater()
