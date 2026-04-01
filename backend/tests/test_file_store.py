"""Tests for app.storage.file_store — save/load assets, path traversal prevention, invalid UUID rejection."""

import uuid

import pytest

from app.storage.file_store import FileStore, _sanitize_filename, _validate_uuid


@pytest.fixture
def file_store(tmp_path) -> FileStore:
    """Create a FileStore with a temp data directory."""
    return FileStore(data_dir=str(tmp_path / "data"))


def _room_id() -> str:
    return str(uuid.uuid4())


class TestValidateUUID:
    """Test UUID validation."""

    def test_valid_uuid(self) -> None:
        uid = str(uuid.uuid4())
        assert _validate_uuid(uid) == uid

    def test_valid_uuid_uppercase(self) -> None:
        uid = str(uuid.uuid4()).upper()
        result = _validate_uuid(uid)
        # Should return canonical lowercase
        assert result == uid.lower()

    def test_invalid_uuid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid UUID"):
            _validate_uuid("not-a-uuid")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid UUID"):
            _validate_uuid("")

    def test_path_traversal_in_uuid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid UUID"):
            _validate_uuid("../../etc/passwd")

    def test_partial_uuid_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid UUID"):
            _validate_uuid("12345678-1234-1234")


class TestSanitizeFilename:
    """Test filename sanitization."""

    def test_valid_filename(self) -> None:
        assert _sanitize_filename("image.png") == "image.png"

    def test_valid_filename_with_hyphens(self) -> None:
        assert _sanitize_filename("my-image-01.jpg") == "my-image-01.jpg"

    def test_valid_filename_with_underscores(self) -> None:
        assert _sanitize_filename("music_track.mp3") == "music_track.mp3"

    def test_empty_filename_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            _sanitize_filename("")

    def test_too_long_filename_raises(self) -> None:
        with pytest.raises(ValueError, match="too long"):
            _sanitize_filename("a" * 256)

    def test_path_separator_slash_raises(self) -> None:
        with pytest.raises(ValueError, match="path separators"):
            _sanitize_filename("../etc/passwd")

    def test_path_separator_backslash_raises(self) -> None:
        with pytest.raises(ValueError, match="path separators"):
            _sanitize_filename("..\\windows\\system32")

    def test_dot_dot_raises(self) -> None:
        with pytest.raises(ValueError, match="relative path"):
            _sanitize_filename("..")

    def test_single_dot_raises(self) -> None:
        with pytest.raises(ValueError, match="relative path"):
            _sanitize_filename(".")

    def test_unsafe_characters_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsafe filename"):
            _sanitize_filename("file name.txt")  # space

    def test_leading_dot_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsafe filename"):
            _sanitize_filename(".hidden")


class TestFileStoreSaveAsset:
    """Test saving assets."""

    @pytest.mark.asyncio
    async def test_save_and_load(self, file_store: FileStore) -> None:
        rid = _room_id()
        data = b"fake image data"
        path = await file_store.save_asset(rid, "image.png", data)
        assert path.exists()
        loaded = await file_store.load_asset(rid, "image.png")
        assert loaded == data

    @pytest.mark.asyncio
    async def test_save_creates_directory(self, file_store: FileStore) -> None:
        rid = _room_id()
        path = await file_store.save_asset(rid, "test.txt", b"content")
        assert path.parent.exists()
        assert path.parent.name == rid

    @pytest.mark.asyncio
    async def test_save_invalid_uuid_raises(self, file_store: FileStore) -> None:
        with pytest.raises(ValueError, match="Invalid UUID"):
            await file_store.save_asset("not-a-uuid", "image.png", b"data")

    @pytest.mark.asyncio
    async def test_save_unsafe_filename_raises(self, file_store: FileStore) -> None:
        rid = _room_id()
        with pytest.raises(ValueError, match="path separators"):
            await file_store.save_asset(rid, "../escape.txt", b"data")

    @pytest.mark.asyncio
    async def test_save_overwrite(self, file_store: FileStore) -> None:
        rid = _room_id()
        await file_store.save_asset(rid, "file.txt", b"original")
        await file_store.save_asset(rid, "file.txt", b"updated")
        loaded = await file_store.load_asset(rid, "file.txt")
        assert loaded == b"updated"


class TestFileStoreLoadAsset:
    """Test loading assets."""

    @pytest.mark.asyncio
    async def test_load_nonexistent_raises(self, file_store: FileStore) -> None:
        rid = _room_id()
        with pytest.raises(FileNotFoundError, match="Asset not found"):
            await file_store.load_asset(rid, "nope.png")

    @pytest.mark.asyncio
    async def test_load_invalid_uuid_raises(self, file_store: FileStore) -> None:
        with pytest.raises(ValueError, match="Invalid UUID"):
            await file_store.load_asset("bad-uuid", "image.png")


class TestFileStoreListAssets:
    """Test listing assets."""

    @pytest.mark.asyncio
    async def test_list_empty(self, file_store: FileStore) -> None:
        rid = _room_id()
        assets = await file_store.list_assets(rid)
        assert assets == []

    @pytest.mark.asyncio
    async def test_list_multiple(self, file_store: FileStore) -> None:
        rid = _room_id()
        await file_store.save_asset(rid, "image.png", b"img")
        await file_store.save_asset(rid, "music.mp3", b"audio")
        assets = await file_store.list_assets(rid)
        assert sorted(assets) == ["image.png", "music.mp3"]

    @pytest.mark.asyncio
    async def test_list_invalid_uuid_raises(self, file_store: FileStore) -> None:
        with pytest.raises(ValueError, match="Invalid UUID"):
            await file_store.list_assets("not-valid")


class TestFileStoreGetAssetPath:
    """Test getting asset paths."""

    @pytest.mark.asyncio
    async def test_get_existing_path(self, file_store: FileStore) -> None:
        rid = _room_id()
        await file_store.save_asset(rid, "image.png", b"data")
        path = await file_store.get_asset_path(rid, "image.png")
        assert path.exists()
        assert path.name == "image.png"

    @pytest.mark.asyncio
    async def test_get_nonexistent_raises(self, file_store: FileStore) -> None:
        rid = _room_id()
        with pytest.raises(FileNotFoundError, match="Asset not found"):
            await file_store.get_asset_path(rid, "missing.png")


class TestPathTraversal:
    """Security tests for path traversal prevention."""

    @pytest.mark.asyncio
    async def test_uuid_with_slashes_rejected(self, file_store: FileStore) -> None:
        with pytest.raises(ValueError):
            await file_store.save_asset("../../etc", "passwd", b"data")

    @pytest.mark.asyncio
    async def test_filename_with_dotdot_rejected(self, file_store: FileStore) -> None:
        rid = _room_id()
        with pytest.raises(ValueError):
            await file_store.save_asset(rid, "..secret", b"data")

    @pytest.mark.asyncio
    async def test_filename_with_slash_rejected(self, file_store: FileStore) -> None:
        rid = _room_id()
        with pytest.raises(ValueError):
            await file_store.save_asset(rid, "sub/file.txt", b"data")
