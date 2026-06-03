"""DIDL-Lite XML builder for UPnP media metadata."""

from __future__ import annotations

from datetime import timedelta
from xml.sax.saxutils import escape

from lancaster.utils import format_duration

_DIDL_TEMPLATE = (
    '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/"'
    ' xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"'
    ' xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"'
    ' xmlns:sec="http://www.sec.co.kr/"'
    ' xmlns:dlna="urn:schemas-dlna-org:metadata-1-0/">'
    "{items}"
    "</DIDL-Lite>"
)


class DIDLBuilder:
    """Build DIDL-Lite XML for DLNA media items."""

    @staticmethod
    def video_item(
        url: str,
        title: str,
        mime: str = "video/mp4",
        duration: timedelta | None = None,
        subtitle_url: str | None = None,
        item_id: str = "0",
        parent_id: str = "-1",
    ) -> str:
        """Build a DIDL-Lite XML string for a single video item."""
        dur_attr = ""
        if duration:
            dur_attr = f' duration="{format_duration(duration)}"'

        protocol_info = f"http-get:*:{escape(mime)}:*"
        res_element = (
            f'<res protocolInfo="{protocol_info}"{dur_attr}>'
            f"{escape(url)}</res>"
        )

        subtitle_element = ""
        if subtitle_url:
            subtitle_element = (
                f'<sec:CaptionInfoEx sec:type="srt">'
                f"{escape(subtitle_url)}</sec:CaptionInfoEx>"
            )

        item_xml = (
            f'<item id="{escape(item_id)}" parentID="{escape(parent_id)}" restricted="1">'
            f"<dc:title>{escape(title)}</dc:title>"
            f"<upnp:class>object.item.videoItem</upnp:class>"
            f"{res_element}"
            f"{subtitle_element}"
            f"</item>"
        )

        return _DIDL_TEMPLATE.format(items=item_xml)

    @staticmethod
    def audio_item(
        url: str,
        title: str,
        mime: str = "audio/mpeg",
        duration: timedelta | None = None,
        artist: str = "",
        album: str = "",
        item_id: str = "0",
        parent_id: str = "-1",
    ) -> str:
        """Build a DIDL-Lite XML string for a single audio item."""
        dur_attr = ""
        if duration:
            dur_attr = f' duration="{format_duration(duration)}"'

        protocol_info = f"http-get:*:{escape(mime)}:*"
        res_element = (
            f'<res protocolInfo="{protocol_info}"{dur_attr}>'
            f"{escape(url)}</res>"
        )

        extra = ""
        if artist:
            extra += f"<upnp:artist>{escape(artist)}</upnp:artist>"
        if album:
            extra += f"<upnp:album>{escape(album)}</upnp:album>"

        item_xml = (
            f'<item id="{escape(item_id)}" parentID="{escape(parent_id)}" restricted="1">'
            f"<dc:title>{escape(title)}</dc:title>"
            f"<upnp:class>object.item.audioItem.musicTrack</upnp:class>"
            f"{res_element}"
            f"{extra}"
            f"</item>"
        )

        return _DIDL_TEMPLATE.format(items=item_xml)

    @staticmethod
    def container(
        container_id: str,
        title: str,
        child_count: int = 0,
        parent_id: str = "-1",
    ) -> str:
        """Build a DIDL-Lite container element (for Browse responses)."""
        return (
            f'<container id="{escape(container_id)}" parentID="{escape(parent_id)}"'
            f' restricted="1" childCount="{child_count}">'
            f"<dc:title>{escape(title)}</dc:title>"
            f"<upnp:class>object.container.storageFolder</upnp:class>"
            f"</container>"
        )

    @staticmethod
    def wrap(items_xml: str) -> str:
        """Wrap raw item/container XML in a DIDL-Lite envelope."""
        return _DIDL_TEMPLATE.format(items=items_xml)
