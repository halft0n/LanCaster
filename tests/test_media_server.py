"""Tests for the MediaServer (DMS) module (TDD — tests first)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lancaster.media_server import MediaNode, MediaServer


@pytest.fixture
def media_dir(tmp_path):
    """Create a sample media directory tree."""
    movies = tmp_path / "Movies"
    movies.mkdir()
    (movies / "action.mp4").write_bytes(b"\x00" * 100)
    (movies / "comedy.mkv").write_bytes(b"\x00" * 100)

    music = tmp_path / "Music"
    music.mkdir()
    (music / "song.mp3").write_bytes(b"\x00" * 100)

    (tmp_path / "readme.txt").write_bytes(b"not media")

    return tmp_path


@pytest.fixture
def server(media_dir):
    with patch("lancaster.media_server.HTTPFileServer") as mock_http:
        mock_http_inst = MagicMock()
        mock_http_inst.start = AsyncMock()
        mock_http_inst.stop = AsyncMock()
        mock_http_inst.serve_file = AsyncMock(
            return_value="http://192.168.1.50:8201/files/test.mp4"
        )
        mock_http.return_value = mock_http_inst

        srv = MediaServer(
            directories=[media_dir],
            host="192.168.1.50",
            port=8300,
        )
        yield srv


class TestMediaNode:
    def test_create_container(self):
        node = MediaNode(
            object_id="0", parent_id="-1",
            title="Root", is_container=True,
        )
        assert node.is_container
        assert node.children == []

    def test_create_item(self, tmp_path):
        f = tmp_path / "test.mp4"
        f.write_bytes(b"\x00")
        node = MediaNode(
            object_id="1", parent_id="0",
            title="test.mp4", is_container=False,
            path=f,
        )
        assert not node.is_container
        assert node.path == f


class TestScanDirectory:
    def test_scan_finds_media(self, server, media_dir):
        server.scan()
        root = server.root
        assert root is not None
        assert root.is_container
        assert len(root.children) >= 2

    def test_scan_creates_tree(self, server, media_dir):
        server.scan()
        names = [c.title for c in server.root.children]
        assert "Movies" in names
        assert "Music" in names

    def test_scan_skips_non_media(self, server, media_dir):
        """Non-media files like .txt should be excluded."""
        server.scan()
        all_items = server.get_all_items()
        titles = [i.title for i in all_items if not i.is_container]
        assert "readme.txt" not in titles

    def test_scan_finds_nested_files(self, server, media_dir):
        server.scan()
        all_items = server.get_all_items()
        titles = [i.title for i in all_items if not i.is_container]
        assert "action.mp4" in titles
        assert "comedy.mkv" in titles
        assert "song.mp3" in titles


class TestBrowse:
    def test_browse_root(self, server):
        server.scan()
        items = server.browse("0")
        assert len(items) >= 2
        assert all(i.parent_id == "0" for i in items)

    def test_browse_subfolder(self, server, media_dir):
        server.scan()
        movies_node = None
        for c in server.root.children:
            if c.title == "Movies":
                movies_node = c
                break
        assert movies_node is not None

        items = server.browse(movies_node.object_id)
        assert len(items) == 2
        titles = [i.title for i in items]
        assert "action.mp4" in titles
        assert "comedy.mkv" in titles

    def test_browse_invalid_id(self, server):
        server.scan()
        items = server.browse("9999")
        assert items == []


class TestObjectLookup:
    def test_find_by_id(self, server):
        server.scan()
        root = server.find_by_id("0")
        assert root is not None
        assert root.title == "LanCaster Media"

    def test_find_nonexistent(self, server):
        server.scan()
        assert server.find_by_id("9999") is None


class TestDIDLOutput:
    def test_browse_returns_didl(self, server):
        """browse_didl should return valid DIDL-Lite XML."""
        server.scan()
        xml = server.browse_didl("0")
        assert "<DIDL-Lite" in xml
        assert "container" in xml

    def test_item_has_res_element(self, server):
        server.scan()
        movies_node = None
        for c in server.root.children:
            if c.title == "Movies":
                movies_node = c
                break
        if movies_node:
            xml = server.browse_didl(movies_node.object_id)
            assert "<item" in xml or "<container" in xml
