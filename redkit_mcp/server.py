"""Local, bounded MCP access to the installed Witcher 3 REDkit depot."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path


REDKIT = Path(os.environ.get("REDKIT_ROOT", "/mnt/ssd/Games/The Witcher 3 REDkit")).resolve()
DEPOT = REDKIT / "r4data"
PROJECT = Path(__file__).resolve().parents[1]
CHECKOUT = PROJECT / "depot"
EDITOR = REDKIT / "bin/x64_RedKit/editor.exe"
MAX_ASSET_SIZE = 64 * 1024 * 1024
STRING_RE = re.compile(rb"[\x20-\x7e]{4,}")

def _relative_asset(asset_path: str) -> Path:
    path = Path(asset_path.replace("\\", "/"))
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("Use a relative depot path without '.' or '..'.")
    return path


def _inside_depot(asset_path: str) -> Path:
    path = (DEPOT / _relative_asset(asset_path)).resolve()
    if not path.is_relative_to(DEPOT.resolve()):
        raise ValueError("Path escapes the REDkit depot.")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_redkit_status() -> dict:
    """Check the local REDkit depot, editor executable, and workspace checkout location."""
    return {
        "redkit_root": str(REDKIT),
        "redkit_exists": REDKIT.is_dir(),
        "depot": str(DEPOT),
        "depot_exists": DEPOT.is_dir(),
        "editor": str(EDITOR),
        "editor_exists": EDITOR.is_file(),
        "workspace_checkout": str(CHECKOUT),
        "note": "The editor is a Windows GUI executable; this server does not control its UI.",
    }


def list_depot_assets(directory: str = "gameplay/community/dialogues/brothels", suffix: str = ".w2scene", limit: int = 100) -> dict:
    """List direct child assets in one REDkit depot directory, with optional filename suffix; does not scan the entire 74 GB depot."""
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    if suffix and ("/" in suffix or "\\" in suffix or len(suffix) > 64):
        raise ValueError("suffix must be a simple filename suffix")
    base = _inside_depot(directory)
    if not base.is_dir():
        raise FileNotFoundError(str(base))
    assets = []
    truncated = False
    for entry in sorted(base.iterdir(), key=lambda p: p.name):
        if entry.is_file() and entry.name.endswith(suffix):
            if len(assets) == limit:
                truncated = True
                break
            assets.append({"path": entry.relative_to(DEPOT).as_posix(), "size": entry.stat().st_size})
    return {"assets": assets, "truncated": truncated}


def inspect_depot_asset(asset_path: str, contains: str = "", limit: int = 100) -> dict:
    """Read one depot asset's metadata and printable embedded strings; strings are clues and do not decode CR2W structure."""
    if not 1 <= limit <= 300:
        raise ValueError("limit must be between 1 and 300")
    if len(contains) > 200:
        raise ValueError("contains is too long")
    path = _inside_depot(asset_path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    size = path.stat().st_size
    if size > MAX_ASSET_SIZE:
        raise ValueError("Asset exceeds the 64 MiB inspection limit")
    data = path.read_bytes()
    needle = contains.casefold()
    strings = []
    total = 0
    for match in STRING_RE.finditer(data):
        value = match.group().decode("ascii")
        if needle and needle not in value.casefold():
            continue
        total += 1
        if len(strings) < limit:
            strings.append({"offset": match.start(), "text": value[:500]})
    return {
        "path": path.relative_to(DEPOT).as_posix(),
        "size": size,
        "format_magic": data[:4].decode("ascii", errors="replace"),
        "sha256": hashlib.sha256(data).hexdigest(),
        "strings": strings,
        "matching_string_count": total,
        "truncated": total > limit,
    }


def checkout_depot_asset(asset_path: str) -> dict:
    """Copy one REDkit depot asset into this mod workspace at depot/<same path>; refuses to overwrite any existing checkout."""
    source = _inside_depot(asset_path)
    if not source.is_file():
        raise FileNotFoundError(str(source))
    if source.stat().st_size > MAX_ASSET_SIZE:
        raise ValueError("Asset exceeds the 64 MiB checkout limit")
    destination = CHECKOUT / source.relative_to(DEPOT)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation preserves any previous work even if another caller races us.
    with source.open("rb") as input_file, destination.open("xb") as output_file:
        shutil.copyfileobj(input_file, output_file)
    return {
        "source": str(source),
        "checkout": str(destination),
        "size": destination.stat().st_size,
        "sha256": _sha256(destination),
    }


def compare_checkout(asset_path: str) -> dict:
    """Compare the workspace checkout of one asset with the installed REDkit original using SHA-256."""
    source = _inside_depot(asset_path)
    checkout = (CHECKOUT / _relative_asset(asset_path)).resolve()
    if not checkout.is_relative_to(CHECKOUT.resolve()):
        raise ValueError("Checkout path escapes the workspace")
    if not source.is_file() or not checkout.is_file():
        raise FileNotFoundError("Both source and checkout must exist")
    original_hash = _sha256(source)
    checkout_hash = _sha256(checkout)
    return {
        "asset_path": asset_path,
        "source_sha256": original_hash,
        "checkout_sha256": checkout_hash,
        "changed": original_hash != checkout_hash,
    }


TOOLS = {
    "get_redkit_status": (get_redkit_status, {}, [], True),
    "list_depot_assets": (
        list_depot_assets,
        {"directory": {"type": "string"}, "suffix": {"type": "string"}, "limit": {"type": "integer"}},
        [], True,
    ),
    "inspect_depot_asset": (
        inspect_depot_asset,
        {"asset_path": {"type": "string"}, "contains": {"type": "string"}, "limit": {"type": "integer"}},
        ["asset_path"], True,
    ),
    "checkout_depot_asset": (
        checkout_depot_asset,
        {"asset_path": {"type": "string"}}, ["asset_path"], False,
    ),
    "compare_checkout": (
        compare_checkout,
        {"asset_path": {"type": "string"}}, ["asset_path"], True,
    ),
}


def _send(message: dict) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _handle(request: dict) -> dict | None:
    if "id" not in request:
        return None  # Notifications have no response.
    request_id = request["id"]
    method = request.get("method")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": request_id, "result": {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "witcher3-redkit-local", "version": "0.1.0"},
            "instructions": "Read the REDkit depot and make non-overwriting workspace copies. CR2W strings are clues; use REDkit for structured scene edits. Installed game and REDkit files are never changed.",
        }}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        tools = []
        for name, (function, properties, required, readonly) in TOOLS.items():
            tools.append({
                "name": name,
                "description": function.__doc__,
                "inputSchema": {"type": "object", "properties": properties, "required": required, "additionalProperties": False},
                "annotations": {"readOnlyHint": readonly, "destructiveHint": False, "openWorldHint": False},
            })
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools}}
    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        if name not in TOOLS:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Unknown tool"}}
        function, properties, required, _ = TOOLS[name]
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict) or any(k not in properties for k in arguments) or any(k not in arguments for k in required):
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Invalid tool arguments"}}
        try:
            output = function(**arguments)
            return {"jsonrpc": "2.0", "id": request_id, "result": {
                "content": [{"type": "text", "text": json.dumps(output, ensure_ascii=False)}],
                "structuredContent": output,
                "isError": False,
            }}
        except (OSError, ValueError, TypeError) as exc:
            return {"jsonrpc": "2.0", "id": request_id, "result": {
                "content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}],
                "isError": True,
            }}
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}


def main() -> None:
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                continue
            response = _handle(request)
            if response is not None:
                _send(response)
        except (json.JSONDecodeError, UnicodeError):
            continue


if __name__ == "__main__":
    main()
