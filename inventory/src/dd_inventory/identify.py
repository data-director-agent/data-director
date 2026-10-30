"""Identify a file's format against PRONOM with fido. The one module that knows fido.

fido reads the start and end of a file and matches them against PRONOM's byte signatures, then
its container signatures for ZIP and OLE2 files, and falls back to the file's extension. Each
step can match several formats, so every PRONOM identifier (PUID) it returns is kept, with the
step that found them.

Where fido cannot be loaded, `ExtensionIdentifier` guesses a media type from the extension and
gives no PUID (ADR-0034, dependencies).
"""

from __future__ import annotations

import contextlib
import io
import mimetypes
import warnings
from collections.abc import Iterator
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path
from typing import Any, Protocol
from xml.etree import ElementTree

# fido's step names are the core's `IdentificationMethod` values; an empty match is `none`.
SIGNATURE, CONTAINER, EXTENSION, NONE = "signature", "container", "extension", "none"


@dataclass(frozen=True)
class Identification:
    method: str
    pronom_ids: list[str] = field(default_factory=list)
    media_type: str | None = None


class Identifier(Protocol):
    # What identified the formats, recorded in the inventory.
    description: str

    def identify(self, path: Path) -> Identification: ...


class FidoUnavailableError(Exception):
    """fido could not be loaded; the reason is recorded in the inventory's limitations."""


@contextlib.contextmanager
def _quiet_fido() -> Iterator[None]:
    """fido tests an XML element's truth value, which Python 3.12 deprecates, and writes notices
    (an empty file, an unreadable one) to stderr itself. Neither is the caller's to see."""
    with warnings.catch_warnings(), contextlib.redirect_stderr(io.StringIO()):
        warnings.simplefilter("ignore", DeprecationWarning)
        yield


def guess_media_type(path: Path) -> str | None:
    return mimetypes.guess_type(path.name, strict=False)[0]


class ExtensionIdentifier:
    description = "file extensions only"

    def identify(self, path: Path) -> Identification:
        media_type = guess_media_type(path)
        return Identification(EXTENSION if media_type else NONE, [], media_type)


class FidoIdentifier:
    """fido's own steps, in the order its `identify_file` takes them, on a file this opens and
    closes: `identify_file` leaves every file it reads open."""

    def __init__(self) -> None:
        try:
            from fido import CONFIG_DIR
            from fido.fido import Fido
            from fido.package import OlePackage, ZipPackage
            from fido.versions import get_local_versions

            # The library's defaults name a signature file fido 1.6.1 does not ship; its CLI
            # reads the files from versions.xml, and so does this.
            versions = get_local_versions()
            with _quiet_fido():
                self._fido = Fido(
                    quiet=True,
                    format_files=[versions.pronom_signature, versions.fido_extension_signature],
                )
                self._containers = ElementTree.parse(
                    Path(CONFIG_DIR) / versions.pronom_container_signature
                )
            pronom = versions.pronom_version
        except Exception as exc:  # fido raises bare OSError, ParseError, ...
            raise FidoUnavailableError(f"fido could not be loaded: {exc}") from exc
        self._packages = {"zip": ("ZIP", ZipPackage), "ole": ("OLE2", OlePackage)}
        self.description = f"fido {version('opf-fido')} with PRONOM signatures v{pronom}"

    def identify(self, path: Path) -> Identification:
        fido = self._fido
        with _quiet_fido():
            size = path.stat().st_size
            with path.open("rb") as fh:
                bof, eof, _read = fido.get_buffers(fh, size, seekable=True)
            # An empty file matches RTF's signature, so fido goes by its extension instead.
            matches = fido.match_formats(bof, eof) if size else []
            package = self._packages.get(fido.container_type(matches))
            if package is not None:
                kind, cls = package
                inside = fido.match_container(kind, cls, str(path), self._containers)
                if inside:
                    return self._found(path, inside, CONTAINER)
            if matches:
                return self._found(path, matches, SIGNATURE)
            return self._found(path, fido.match_extensions(str(path)), EXTENSION)

    @staticmethod
    def _found(path: Path, matches: list[tuple[Any, Any]], method: str) -> Identification:
        puids = [p.text for f, _sig in matches if (p := f.find("puid")) is not None and p.text]
        mimes = [m.text for f, _sig in matches if (m := f.find("mime")) is not None and m.text]
        media_type = mimes[0] if mimes else guess_media_type(path)
        return Identification(method if puids else NONE, puids, media_type)


def default_identifier() -> tuple[Identifier, str | None]:
    """fido, or the extension fallback and why fido was not used."""
    try:
        return FidoIdentifier(), None
    except FidoUnavailableError as exc:
        return ExtensionIdentifier(), str(exc)
