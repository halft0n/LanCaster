"""DLNA Media Server (DMS) — expose local directories for TV browsing."""

from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

from lancaster.http_server import HTTPFileServer

_LOGGER = logging.getLogger(__name__)

_MEDIA_EXTENSIONS = {
    ".mp4", ".m4v", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".ts", ".m2ts",
    ".webm", ".3gp", ".ogv",
    ".mp3", ".m4a", ".flac", ".wav", ".ogg", ".wma", ".aac",
}

_VIDEO_EXTENSIONS = {
    ".mp4", ".m4v", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".ts", ".m2ts",
    ".webm", ".3gp", ".ogv",
}

_AUDIO_EXTENSIONS = {
    ".mp3", ".m4a", ".flac", ".wav", ".ogg", ".wma", ".aac",
}


@dataclass
class MediaNode:
    """A node in the virtual media directory tree."""

    object_id: str
    parent_id: str
    title: str
    is_container: bool
    path: Path | None = None
    children: list[MediaNode] = field(default_factory=list)
    mime_type: str = ""


class MediaServer:
    """Scans directories and exposes them as a browsable DLNA media library."""

    def __init__(
        self,
        directories: list[Path],
        host: str = "0.0.0.0",
        port: int = 8300,
    ) -> None:
        self._directories = [Path(d) for d in directories]
        self._host = host
        self._port = port
        self._http_server = HTTPFileServer(host=host, port=port)

        self._root: MediaNode | None = None
        self._node_map: dict[str, MediaNode] = {}
        self._next_id = 1

    @property
    def root(self) -> MediaNode | None:
        return self._root

    def _alloc_id(self) -> str:
        oid = str(self._next_id)
        self._next_id += 1
        return oid

    def scan(self) -> None:
        """Scan configured directories and build the media tree."""
        self._root = MediaNode(
            object_id="0", parent_id="-1",
            title="LanCaster Media", is_container=True,
        )
        self._node_map = {"0": self._root}
        self._next_id = 1

        for directory in self._directories:
            if directory.is_dir():
                self._scan_dir_contents(directory, self._root)

        _LOGGER.info(
            "Media scan complete: %d items in %d nodes",
            sum(1 for n in self._node_map.values() if not n.is_container),
            len(self._node_map),
        )

    def _scan_dir_contents(self, path: Path, parent: MediaNode) -> None:
        """Scan contents of a directory directly into the parent node."""
        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            _LOGGER.warning("Permission denied: %s", path)
            return

        for entry in entries:
            if entry.is_dir():
                self._scan_dir_recursive(entry, parent)
            elif entry.suffix.lower() in _MEDIA_EXTENSIONS:
                mime = mimetypes.guess_type(str(entry))[0] or "application/octet-stream"
                item = MediaNode(
                    object_id=self._alloc_id(),
                    parent_id=parent.object_id,
                    title=entry.name,
                    is_container=False,
                    path=entry,
                    mime_type=mime,
                )
                self._node_map[item.object_id] = item
                parent.children.append(item)

    def _scan_dir_recursive(self, path: Path, parent: MediaNode) -> None:
        """Create a container node for a subdirectory and scan its contents."""
        dir_node = MediaNode(
            object_id=self._alloc_id(),
            parent_id=parent.object_id,
            title=path.name,
            is_container=True,
            path=path,
        )
        self._node_map[dir_node.object_id] = dir_node
        parent.children.append(dir_node)
        self._scan_dir_contents(path, dir_node)

    def browse(self, object_id: str) -> list[MediaNode]:
        """Return children of the given container, or empty list."""
        node = self._node_map.get(object_id)
        if not node or not node.is_container:
            return []
        return node.children

    def find_by_id(self, object_id: str) -> MediaNode | None:
        return self._node_map.get(object_id)

    def get_all_items(self) -> list[MediaNode]:
        return list(self._node_map.values())

    def browse_didl(self, object_id: str) -> str:
        """Return DIDL-Lite XML for the children of a container."""
        items = self.browse(object_id)
        parts = [
            '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"'
            ' xmlns:dc="http://purl.org/dc/elements/1.1/"'
            ' xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">',
        ]

        for item in items:
            if item.is_container:
                parts.append(
                    f'<container id="{item.object_id}" parentID="{item.parent_id}"'
                    f' childCount="{len(item.children)}" restricted="true">'
                    f'<dc:title>{escape(item.title)}</dc:title>'
                    f'<upnp:class>object.container.storageFolder</upnp:class>'
                    f'</container>'
                )
            else:
                upnp_class = (
                    "object.item.videoItem"
                    if item.path and item.path.suffix.lower() in _VIDEO_EXTENSIONS
                    else "object.item.audioItem.musicTrack"
                )
                res_url = (
                    f"http://{self._host}:{self._port}"
                    f"/files/{item.object_id}"
                )
                parts.append(
                    f'<item id="{item.object_id}" parentID="{item.parent_id}"'
                    f' restricted="true">'
                    f'<dc:title>{escape(item.title)}</dc:title>'
                    f'<upnp:class>{upnp_class}</upnp:class>'
                    f'<res protocolInfo="http-get:*:{item.mime_type}:*">'
                    f'{escape(res_url)}</res>'
                    f'</item>'
                )

        parts.append('</DIDL-Lite>')
        return "\n".join(parts)
