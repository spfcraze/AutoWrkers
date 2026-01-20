"""
Agentic Tools for Local LLM Support

Provides file operations, shell execution, and search capabilities
that local LLMs can use to perform coding tasks.
"""
import os
import asyncio
import subprocess
import glob as glob_module
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from pathlib import Path


@dataclass
class ToolResult:
    """Result from executing a tool"""
    success: bool
    output: str
    error: Optional[str] = None


class Tool(ABC):
    """Base class for agentic tools"""
    name: str
    description: str
    parameters: Dict[str, Any]

    def __init__(self, working_dir: str):
        self.working_dir = working_dir

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters"""
        pass

    def to_openai_schema(self) -> Dict:
        """Convert to OpenAI function calling format"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }

    def _resolve_path(self, path: str) -> str:
        """Resolve path relative to working directory with security checks"""
        # Handle absolute paths
        if os.path.isabs(path):
            resolved = os.path.normpath(path)
        else:
            resolved = os.path.normpath(os.path.join(self.working_dir, path))

        # Security: ensure path is within working directory or /tmp
        working_real = os.path.realpath(self.working_dir)
        resolved_real = os.path.realpath(resolved)

        if not (resolved_real.startswith(working_real) or resolved_real.startswith('/tmp')):
            raise ValueError(f"Path {path} is outside allowed directories")

        return resolved


class FileReadTool(Tool):
    """Read the contents of a file"""
    name = "read_file"
    description = "Read the contents of a file. Can optionally read specific line ranges."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to read (relative to working directory or absolute)"
            },
            "start_line": {
                "type": "integer",
                "description": "Starting line number (1-indexed, optional)"
            },
            "end_line": {
                "type": "integer",
                "description": "Ending line number (1-indexed, inclusive, optional)"
            }
        },
        "required": ["path"]
    }

    async def execute(self, path: str, start_line: int = None, end_line: int = None) -> ToolResult:
        try:
            resolved = self._resolve_path(path)

            if not os.path.exists(resolved):
                return ToolResult(False, "", f"File not found: {path}")

            if not os.path.isfile(resolved):
                return ToolResult(False, "", f"Not a file: {path}")

            with open(resolved, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()

            # Apply line range if specified
            if start_line is not None or end_line is not None:
                start_idx = (start_line - 1) if start_line else 0
                end_idx = end_line if end_line else len(lines)
                lines = lines[start_idx:end_idx]

                # Add line numbers
                output_lines = []
                for i, line in enumerate(lines, start=start_idx + 1):
                    output_lines.append(f"{i:4d} | {line.rstrip()}")
                content = '\n'.join(output_lines)
            else:
                # Add line numbers for full file
                output_lines = []
                for i, line in enumerate(lines, start=1):
                    output_lines.append(f"{i:4d} | {line.rstrip()}")
                content = '\n'.join(output_lines)

            return ToolResult(True, content)

        except Exception as e:
            return ToolResult(False, "", str(e))


class FileWriteTool(Tool):
    """Write or create a file with content"""
    name = "write_file"
    description = "Write content to a file. Creates the file if it doesn't exist, or overwrites if it does."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to write (relative to working directory or absolute)"
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file"
            }
        },
        "required": ["path", "content"]
    }

    async def execute(self, path: str, content: str) -> ToolResult:
        try:
            resolved = self._resolve_path(path)

            # Create parent directories if needed
            os.makedirs(os.path.dirname(resolved), exist_ok=True)

            with open(resolved, 'w', encoding='utf-8') as f:
                f.write(content)

            return ToolResult(True, f"Successfully wrote {len(content)} characters to {path}")

        except Exception as e:
            return ToolResult(False, "", str(e))


class FileEditTool(Tool):
    """Edit a specific section of a file using search/replace"""
    name = "edit_file"
    description = "Edit a file by replacing a specific string with new content. Use for precise edits."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to edit"
            },
            "old_string": {
                "type": "string",
                "description": "The exact string to find and replace (must be unique in the file)"
            },
            "new_string": {
                "type": "string",
                "description": "The string to replace it with"
            },
            "replace_all": {
                "type": "boolean",
                "description": "Replace all occurrences (default: false, only replace first)"
            }
        },
        "required": ["path", "old_string", "new_string"]
    }

    async def execute(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> ToolResult:
        try:
            resolved = self._resolve_path(path)

            if not os.path.exists(resolved):
                return ToolResult(False, "", f"File not found: {path}")

            with open(resolved, 'r', encoding='utf-8') as f:
                content = f.read()

            # Check if old_string exists
            if old_string not in content:
                return ToolResult(False, "", f"String not found in file: {old_string[:50]}...")

            # Check uniqueness if not replacing all
            if not replace_all and content.count(old_string) > 1:
                count = content.count(old_string)
                return ToolResult(False, "", f"String appears {count} times. Use replace_all=true or provide more context.")

            # Perform replacement
            if replace_all:
                new_content = content.replace(old_string, new_string)
                count = content.count(old_string)
            else:
                new_content = content.replace(old_string, new_string, 1)
                count = 1

            with open(resolved, 'w', encoding='utf-8') as f:
                f.write(new_content)

            return ToolResult(True, f"Replaced {count} occurrence(s) in {path}")

        except Exception as e:
            return ToolResult(False, "", str(e))


class ShellExecuteTool(Tool):
    """Execute a shell command"""
    name = "run_command"
    description = "Execute a shell command in the working directory. Use for running tests, builds, git commands, etc."
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 60)"
            }
        },
        "required": ["command"]
    }

    async def execute(self, command: str, timeout: int = 60) -> ToolResult:
        try:
            # Security: block obviously dangerous commands
            dangerous_patterns = [
                r'\brm\s+-rf\s+/',  # rm -rf /
                r'\bmkfs\b',
                r'\bdd\s+if=',
                r'>\s*/dev/sd',
                r'\bshutdown\b',
                r'\breboot\b',
            ]
            for pattern in dangerous_patterns:
                if re.search(pattern, command, re.IGNORECASE):
                    return ToolResult(False, "", f"Command blocked for safety: {command}")

            # Run the command
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return ToolResult(False, "", f"Command timed out after {timeout} seconds")

            output = stdout.decode('utf-8', errors='replace')
            error_output = stderr.decode('utf-8', errors='replace')

            if process.returncode == 0:
                return ToolResult(True, output + (f"\nSTDERR: {error_output}" if error_output else ""))
            else:
                return ToolResult(
                    False,
                    output,
                    f"Command failed with exit code {process.returncode}: {error_output}"
                )

        except Exception as e:
            return ToolResult(False, "", str(e))


class GlobSearchTool(Tool):
    """Find files matching a glob pattern"""
    name = "glob_search"
    description = "Find files matching a glob pattern (e.g., '**/*.py', 'src/**/*.js')"
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern to match files"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 50)"
            }
        },
        "required": ["pattern"]
    }

    async def execute(self, pattern: str, max_results: int = 50) -> ToolResult:
        try:
            # Use glob with working directory
            search_pattern = os.path.join(self.working_dir, pattern)
            matches = glob_module.glob(search_pattern, recursive=True)

            # Filter to files only and limit results
            files = [f for f in matches if os.path.isfile(f)][:max_results]

            # Make paths relative to working directory
            relative_files = [os.path.relpath(f, self.working_dir) for f in files]

            if not relative_files:
                return ToolResult(True, f"No files found matching pattern: {pattern}")

            output = f"Found {len(relative_files)} file(s):\n" + '\n'.join(relative_files)
            if len(matches) > max_results:
                output += f"\n... (truncated, {len(matches)} total matches)"

            return ToolResult(True, output)

        except Exception as e:
            return ToolResult(False, "", str(e))


class GrepSearchTool(Tool):
    """Search file contents with regex"""
    name = "grep_search"
    description = "Search for a pattern in files. Returns matching lines with file paths and line numbers."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regex pattern to search for"
            },
            "file_pattern": {
                "type": "string",
                "description": "Glob pattern to filter files (e.g., '*.py', default: all files)"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of matches to return (default: 50)"
            },
            "case_insensitive": {
                "type": "boolean",
                "description": "Case-insensitive search (default: false)"
            }
        },
        "required": ["pattern"]
    }

    async def execute(
        self,
        pattern: str,
        file_pattern: str = "**/*",
        max_results: int = 50,
        case_insensitive: bool = False
    ) -> ToolResult:
        try:
            # Compile regex
            flags = re.IGNORECASE if case_insensitive else 0
            try:
                regex = re.compile(pattern, flags)
            except re.error as e:
                return ToolResult(False, "", f"Invalid regex pattern: {e}")

            # Find files to search
            search_pattern = os.path.join(self.working_dir, file_pattern)
            files = [f for f in glob_module.glob(search_pattern, recursive=True) if os.path.isfile(f)]

            matches = []
            for filepath in files:
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                rel_path = os.path.relpath(filepath, self.working_dir)
                                matches.append(f"{rel_path}:{line_num}: {line.rstrip()}")
                                if len(matches) >= max_results:
                                    break
                except (IOError, UnicodeDecodeError):
                    continue  # Skip unreadable files

                if len(matches) >= max_results:
                    break

            if not matches:
                return ToolResult(True, f"No matches found for pattern: {pattern}")

            output = f"Found {len(matches)} match(es):\n" + '\n'.join(matches)
            return ToolResult(True, output)

        except Exception as e:
            return ToolResult(False, "", str(e))


class ListDirectoryTool(Tool):
    """List files in a directory"""
    name = "list_directory"
    description = "List files and directories in a path. Shows file sizes and types."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to list (default: working directory)"
            },
            "show_hidden": {
                "type": "boolean",
                "description": "Show hidden files (default: false)"
            }
        },
        "required": []
    }

    async def execute(self, path: str = ".", show_hidden: bool = False) -> ToolResult:
        try:
            resolved = self._resolve_path(path)

            if not os.path.exists(resolved):
                return ToolResult(False, "", f"Directory not found: {path}")

            if not os.path.isdir(resolved):
                return ToolResult(False, "", f"Not a directory: {path}")

            entries = []
            for entry in sorted(os.listdir(resolved)):
                if not show_hidden and entry.startswith('.'):
                    continue

                full_path = os.path.join(resolved, entry)
                if os.path.isdir(full_path):
                    entries.append(f"[DIR]  {entry}/")
                else:
                    size = os.path.getsize(full_path)
                    size_str = self._format_size(size)
                    entries.append(f"[FILE] {entry} ({size_str})")

            if not entries:
                return ToolResult(True, f"Directory is empty: {path}")

            return ToolResult(True, '\n'.join(entries))

        except Exception as e:
            return ToolResult(False, "", str(e))

    def _format_size(self, size: int) -> str:
        """Format file size in human-readable form"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"


def get_all_tools(working_dir: str) -> List[Tool]:
    """Get all available tools for a working directory"""
    return [
        FileReadTool(working_dir),
        FileWriteTool(working_dir),
        FileEditTool(working_dir),
        ShellExecuteTool(working_dir),
        GlobSearchTool(working_dir),
        GrepSearchTool(working_dir),
        ListDirectoryTool(working_dir),
    ]
