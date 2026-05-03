import asyncio
import json
from pathlib import Path

from .config import EXEC_TIMEOUT, MAX_FILE_BYTES, PROJECTS_DIR


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and directories at the given relative path inside the current project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path inside the project. Use '.' for the project root.",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a text file from the current project. Returns up to ~200KB of content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the file."}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or overwrite a text file inside the current project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the file."},
                    "content": {"type": "string", "description": "Full new content of the file."},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "exec_bash",
            "description": (
                "Run a shell command in the current project directory. "
                f"Timeout {EXEC_TIMEOUT}s. Returns stdout+stderr+exit code."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run."}
                },
                "required": ["command"],
            },
        },
    },
]


class ToolError(Exception):
    pass


def _resolve(cwd: Path, rel: str) -> Path:
    if not cwd:
        raise ToolError("No project selected. Use /clone or /project first.")
    target = (cwd / rel).resolve()
    cwd_resolved = cwd.resolve()
    if cwd_resolved not in target.parents and target != cwd_resolved:
        raise ToolError(f"Path '{rel}' escapes project root")
    return target


async def _run(cmd: list[str], cwd: Path | None = None, timeout: int = EXEC_TIMEOUT) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, "", f"timeout after {timeout}s"
    return proc.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def _run_shell(command: str, cwd: Path | None, timeout: int = EXEC_TIMEOUT) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, "", f"timeout after {timeout}s"
    return proc.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def list_dir(cwd: Path, path: str) -> str:
    target = _resolve(cwd, path or ".")
    if not target.exists():
        raise ToolError(f"path '{path}' does not exist")
    if target.is_file():
        return f"{path} is a file ({target.stat().st_size} bytes)"
    items = []
    for child in sorted(target.iterdir()):
        kind = "d" if child.is_dir() else "f"
        size = child.stat().st_size if child.is_file() else 0
        items.append(f"{kind} {child.name}{' (' + str(size) + ')' if kind == 'f' else '/'}")
    return "\n".join(items) if items else "(empty)"


async def read_file(cwd: Path, path: str) -> str:
    target = _resolve(cwd, path)
    if not target.exists() or not target.is_file():
        raise ToolError(f"file '{path}' not found")
    data = target.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        return data[:MAX_FILE_BYTES].decode(errors="replace") + f"\n\n[...truncated, total {len(data)} bytes]"
    return data.decode(errors="replace")


async def write_file(cwd: Path, path: str, content: str) -> str:
    target = _resolve(cwd, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return f"wrote {len(content)} chars to {path}"


async def exec_bash(cwd: Path, command: str) -> str:
    if not cwd:
        raise ToolError("No project selected. Use /clone or /project first.")
    code, out, err = await _run_shell(command, cwd=cwd)
    parts = []
    if out:
        parts.append(f"--- stdout ---\n{out}")
    if err:
        parts.append(f"--- stderr ---\n{err}")
    parts.append(f"exit code: {code}")
    return "\n".join(parts)


async def clone_repo(url: str, dest_name: str | None = None) -> Path:
    if not dest_name:
        dest_name = url.rstrip("/").split("/")[-1].removesuffix(".git")
    if not dest_name or dest_name in ("..", "."):
        raise ToolError(f"invalid project name '{dest_name}'")
    dest = PROJECTS_DIR / dest_name
    if dest.exists():
        raise ToolError(f"project '{dest_name}' already exists. /project {dest_name} to switch to it.")
    code, out, err = await _run(["git", "clone", "--depth", "20", url, str(dest)], timeout=120)
    if code != 0:
        raise ToolError(f"git clone failed: {err.strip() or out.strip()}")
    return dest


async def dispatch_tool(name: str, args_json: str, cwd: Path | None) -> str:
    try:
        args = json.loads(args_json or "{}")
    except json.JSONDecodeError as exc:
        raise ToolError(f"bad arguments json: {exc}")

    if cwd is None:
        raise ToolError("No project selected. Use /clone or /project first.")

    if name == "list_dir":
        return await list_dir(cwd, args.get("path", "."))
    if name == "read_file":
        return await read_file(cwd, args["path"])
    if name == "write_file":
        return await write_file(cwd, args["path"], args.get("content", ""))
    if name == "exec_bash":
        return await exec_bash(cwd, args["command"])
    raise ToolError(f"unknown tool: {name}")
