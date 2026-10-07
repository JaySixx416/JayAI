"""Small UTF-8 files confined to a separate directory for each user."""

from pathlib import Path, PureWindowsPath
from uuid import UUID

from jayai.contracts import PermissionSpec, PolicyMode, Risk, ToolSpec
from jayai.registry import Registry

MAX_BYTES = 1_000_000


class UserWorkspace:
    def __init__(self, base: Path):
        self.base = base.expanduser().resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def _root(self, user_id: UUID) -> Path:
        root = self.base / str(user_id)
        root.mkdir(exist_ok=True)
        resolved = root.resolve()
        if not resolved.is_relative_to(self.base) or resolved == self.base:
            raise PermissionError("User workspace escapes configured root")
        return resolved

    def path(self, user_id: UUID, name: str) -> Path:
        parts = Path(name).parts
        windows_path = PureWindowsPath(name)
        if not name or Path(name).is_absolute() or windows_path.drive or windows_path.root or any(p in (".", "..") for p in parts):
            raise ValueError("Use a relative path without parent traversal")
        root = self._root(user_id)
        candidate = root.joinpath(*parts)
        if not candidate.resolve().is_relative_to(root):
            raise PermissionError("Path escapes user workspace")
        for component in (root, *[root.joinpath(*parts[:i]) for i in range(1, len(parts) + 1)]):
            if component.is_symlink() or component.is_junction():
                raise PermissionError("Linked paths are not allowed")
        return candidate

    def read(self, user_id: UUID, name: str) -> dict:
        target = self.path(user_id, name)
        if not target.is_file() or target.stat().st_size > MAX_BYTES:
            raise ValueError("File missing or exceeds size limit")
        return {"text": target.read_text(encoding="utf-8")}

    def write(self, user_id: UUID, name: str, content: str) -> dict:
        if len(content.encode("utf-8")) > MAX_BYTES:
            raise ValueError("File exceeds size limit")
        target = self.path(user_id, name)
        if not target.parent.is_dir():
            raise ValueError("Parent directory does not exist")
        target.write_text(content, encoding="utf-8")
        return {"path": name, "bytes": len(content.encode("utf-8"))}

    def list(self, user_id: UUID) -> dict:
        root = self._root(user_id)
        names = [p.name for p in root.iterdir() if p.is_file() and not p.is_symlink() and not p.is_junction()]
        return {"names": sorted(names)[:1000]}


def register_file_tools(registry: Registry, workspace: UserWorkspace) -> None:
    for tool_id, action, risk, input_schema, output_schema, operation in [
        ("files.read", "read", Risk.LOW,
         {"type": "object", "properties": {"path": {"type": "string", "maxLength": 255}}, "required": ["path"], "additionalProperties": False},
         {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False},
         lambda user, args: workspace.read(user, args["path"])),
        ("files.write", "write", Risk.MEDIUM,
         {"type": "object", "properties": {"path": {"type": "string", "maxLength": 255}, "text": {"type": "string", "maxLength": MAX_BYTES}}, "required": ["path", "text"], "additionalProperties": False},
         {"type": "object", "properties": {"path": {"type": "string"}, "bytes": {"type": "integer"}}, "required": ["path", "bytes"], "additionalProperties": False},
         lambda user, args: workspace.write(user, args["path"], args["text"])),
        ("files.list", "list", Risk.LOW,
         {"type": "object", "properties": {}, "additionalProperties": False},
         {"type": "object", "properties": {"names": {"type": "array", "items": {"type": "string"}}}, "required": ["names"], "additionalProperties": False},
         lambda user, _args: workspace.list(user)),
    ]:
        registry.register(ToolSpec(id=tool_id, description=tool_id, input_schema=input_schema, output_schema=output_schema,
                                   permission=PermissionSpec(resource="user.files", actions=[action], risk=risk,
                                                             mode=PolicyMode.APPROVE_SCOPE), timeout_seconds=10,
                                   max_retries=0), operation)
