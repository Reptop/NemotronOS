from __future__ import annotations

from pathlib import Path, PureWindowsPath


class SandboxPathError(ValueError):
    """Raised when a Windows path cannot be safely mapped into the sandbox."""


class FakeWindowsPathMapper:
    def __init__(self, fake_windows_root: Path) -> None:
        self.fake_windows_root = fake_windows_root.resolve()

    def to_local_path(self, windows_path: str) -> Path:
        if not windows_path:
            raise SandboxPathError("Path is required.")

        normalized = windows_path.replace("/", "\\")
        parsed = PureWindowsPath(normalized)

        if parsed.drive.upper() != "C:" or not parsed.root:
            raise SandboxPathError("Only absolute C: paths are supported.")

        relative_parts = list(parsed.parts[1:])
        if not relative_parts:
            raise SandboxPathError("Path must point to a location inside the fake Windows drive.")

        for part in relative_parts:
            if part in {"", ".", ".."}:
                raise SandboxPathError("Path traversal is not allowed.")

        local_path = (self.fake_windows_root / Path(*relative_parts)).resolve()
        self._assert_within_root(local_path)
        return local_path

    def to_windows_path(self, local_path: Path) -> str:
        resolved = local_path.resolve()
        self._assert_within_root(resolved)
        relative_path = resolved.relative_to(self.fake_windows_root)
        return str(PureWindowsPath("C:/", *relative_path.parts))

    def _assert_within_root(self, path: Path) -> None:
        try:
            path.relative_to(self.fake_windows_root)
        except ValueError as exc:
            raise SandboxPathError("Path escapes the fake Windows sandbox.") from exc
