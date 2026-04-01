"""File storage for room assets (images, music).

Security: validates room_id as UUID before path construction to prevent
path traversal. Sanitizes filenames to alphanumeric + dots/hyphens only.
"""

import re
from pathlib import Path
from uuid import UUID


_SAFE_FILENAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
_MAX_FILENAME_LEN = 255


def _validate_uuid(value: str) -> str:
    """Validate and return the canonical UUID string. Raises ValueError if invalid."""
    try:
        return str(UUID(value, version=4))
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid UUID: {value!r}") from exc


def _sanitize_filename(name: str) -> str:
    """Sanitize a filename to prevent path traversal and unsafe characters.

    Raises ValueError if the filename is empty, too long, or contains
    path separators after sanitization.
    """
    if not name:
        raise ValueError("Filename cannot be empty")
    if len(name) > _MAX_FILENAME_LEN:
        raise ValueError(f"Filename too long (max {_MAX_FILENAME_LEN} chars)")

    # Reject any path separators
    if "/" in name or "\\" in name:
        raise ValueError("Filename must not contain path separators")

    # Reject relative path components
    if name in (".", "..") or name.startswith(".."):
        raise ValueError("Filename must not be a relative path component")

    # Only allow safe characters
    if not _SAFE_FILENAME_RE.match(name):
        raise ValueError(
            f"Unsafe filename: {name!r}. "
            "Only alphanumeric, dots, hyphens, and underscores allowed."
        )

    return name


class FileStore:
    """Manages room asset files on disk."""

    def __init__(self, data_dir: str) -> None:
        self._base = Path(data_dir)

    def _room_dir(self, room_id: str) -> Path:
        """Get the directory for a room's assets, creating it if needed."""
        validated_id = _validate_uuid(room_id)
        room_path = self._base / "rooms" / validated_id
        # Verify the resolved path is under base (defense in depth)
        resolved = room_path.resolve()
        base_resolved = self._base.resolve()
        if not str(resolved).startswith(str(base_resolved)):
            raise ValueError("Path traversal detected")
        return room_path

    async def save_asset(self, room_id: str, filename: str, data: bytes) -> Path:
        """Save asset bytes to data/rooms/{room_id}/{filename}.

        Returns the path to the saved file.
        """
        safe_name = _sanitize_filename(filename)
        room_dir = self._room_dir(room_id)
        room_dir.mkdir(parents=True, exist_ok=True)

        file_path = room_dir / safe_name
        # Final traversal check on resolved path
        if not str(file_path.resolve()).startswith(str(self._base.resolve())):
            raise ValueError("Path traversal detected")

        file_path.write_bytes(data)
        return file_path

    async def load_asset(self, room_id: str, filename: str) -> bytes:
        """Load asset bytes from data/rooms/{room_id}/{filename}.

        Raises FileNotFoundError if the file doesn't exist.
        """
        safe_name = _sanitize_filename(filename)
        room_dir = self._room_dir(room_id)
        file_path = room_dir / safe_name

        if not str(file_path.resolve()).startswith(str(self._base.resolve())):
            raise ValueError("Path traversal detected")

        if not file_path.exists():
            raise FileNotFoundError(f"Asset not found: {room_id}/{safe_name}")

        return file_path.read_bytes()

    async def list_assets(self, room_id: str) -> list[str]:
        """List all asset filenames for a room."""
        room_dir = self._room_dir(room_id)
        if not room_dir.exists():
            return []
        return [f.name for f in room_dir.iterdir() if f.is_file()]

    async def get_asset_path(self, room_id: str, filename: str) -> Path:
        """Get the full path to an asset file. Raises FileNotFoundError if missing."""
        safe_name = _sanitize_filename(filename)
        room_dir = self._room_dir(room_id)
        file_path = room_dir / safe_name

        if not str(file_path.resolve()).startswith(str(self._base.resolve())):
            raise ValueError("Path traversal detected")

        if not file_path.exists():
            raise FileNotFoundError(f"Asset not found: {room_id}/{safe_name}")

        return file_path
