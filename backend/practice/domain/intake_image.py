"""Image bytes for one intake page. The standard library only. No photo library."""

from __future__ import annotations

_JPEG = b"\xff\xd8"
_PNG = b"\x89PNG\r\n\x1a\n"
_DROP = {0xE1, 0xED}


def image_kind(data: bytes) -> str | None:
    """Return jpeg or png when the magic matches. Anything else is refused."""
    if data.startswith(_JPEG):
        return "jpeg"
    if data.startswith(_PNG):
        return "png"
    return None


def content_type_of(kind: str) -> str:
    if kind == "jpeg":
        return "image/jpeg"
    if kind == "png":
        return "image/png"
    return ""


def strip_jpeg_capture(data: bytes) -> bytes:
    """Drop APP1 (EXIF / XMP) and APP13. The rest of the JPEG stays.

    A non-JPEG is returned unchanged. The caller checks the magic first.
    """
    if not data.startswith(_JPEG):
        return data
    out = bytearray(_JPEG)
    index = 2
    size = len(data)
    while index < size:
        if data[index] != 0xFF:
            out.extend(data[index:])
            break
        start = index
        while index < size and data[index] == 0xFF:
            index += 1
        if index >= size:
            out.extend(data[start:])
            break
        marker = data[index]
        index += 1
        if marker == 0x01 or 0xD0 <= marker <= 0xD9:
            out.append(0xFF)
            out.append(marker)
            if marker == 0xD9:
                break
            continue
        if index + 1 >= size:
            out.extend(data[start:])
            break
        length = (data[index] << 8) | data[index + 1]
        if length < 2 or index + length > size:
            out.extend(data[start:])
            break
        end = index + length
        if marker in _DROP:
            index = end
            continue
        out.append(0xFF)
        out.append(marker)
        out.extend(data[index:end])
        index = end
        if marker == 0xDA:
            out.extend(data[index:])
            break
    return bytes(out)
