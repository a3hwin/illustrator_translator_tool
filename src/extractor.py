"""SVG text extraction utilities for spatially-aware localization workflows."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from bs4 import BeautifulSoup, Tag


LOGGER = logging.getLogger(__name__)


class SVGSpatialExtractor:
    """Extract text-bearing SVG nodes and their spatial metadata."""

    # Both prefixed and unprefixed variants to survive the XML Namespace
    # Trap: Inkscape emits xmlns:svg="...", causing lxml-xml to prefix
    # elements as svg:text / svg:tspan.
    _TEXT_TAGS: list[str] = ["text", "tspan", "svg:text", "svg:tspan"]

    def extract_text_nodes(self, svg_filepath: str) -> list[dict[str, Any]]:
        """Extract text nodes and positioning metadata from an SVG file.

        The extractor walks all ``<text>`` and ``<tspan>`` elements and returns
        a normalized record for each node containing textual and spatial data.

        Args:
            svg_filepath: Absolute or relative path to the SVG document.

        Returns:
            A list of dictionaries containing ``node_id``, ``text``, ``x``,
            ``y``, ``font-size``, inherited ``transform``, and ``textLength``
            values for each discovered node.

        Raises:
            ValueError: If ``svg_filepath`` is empty.
            FileNotFoundError: If the provided SVG file does not exist.
            OSError: If the file cannot be opened for reading.
        """
        if not svg_filepath:
            raise ValueError("svg_filepath must be provided.")

        with open(svg_filepath, "r", encoding="utf-8") as svg_file:
            soup = BeautifulSoup(svg_file, "lxml-xml")

        extracted_nodes: list[dict[str, Any]] = []

        for tag in soup.find_all(self._TEXT_TAGS):
            if not isinstance(tag, Tag):
                continue

            # CRITICAL: Only extract nodes that contain direct text content.
            # We ignore container elements that only hold child <tspan> nodes.
            direct_text_chunks = tag.find_all(string=True, recursive=False)
            direct_text = "".join(direct_text_chunks).strip()

            if not direct_text:
                continue

            try:
                extracted_nodes.append(
                    {
                        "node_id": tag.get("id") or self._generate_node_id(tag),
                        "text": direct_text,
                        "x": self._get_inherited_attribute(tag, "x"),
                        "y": self._get_inherited_attribute(tag, "y"),
                        "font-size": self._get_inherited_attribute(tag, "font-size"),
                        "transform": self._get_inherited_attribute(tag, "transform"),
                        "textLength": self._get_inherited_attribute(tag, "textLength"),
                    }
                )
            except Exception:
                LOGGER.warning(
                    "Skipping malformed SVG node at line %s; "
                    "extraction could not complete for this element.",
                    getattr(tag, "sourceline", "unknown"),
                )
                continue

        LOGGER.info("Extracted %d text node(s).", len(extracted_nodes))
        for sample_node in extracted_nodes[:2]:
            LOGGER.debug(
                "  Sample node -> id=%s, text='%s'",
                sample_node.get("node_id", "?"),
                sample_node.get("text", "")[:80],
            )

        return extracted_nodes

    def _get_inherited_attribute(self, tag: Tag, attribute_name: str) -> str | None:
        """Resolve an attribute on a tag, falling back to ancestor nodes.

        Args:
            tag: SVG node being inspected.
            attribute_name: Attribute name to resolve.

        Returns:
            The resolved attribute value when present, otherwise `None`.
        """
        current: Tag | None = tag
        while current is not None:
            value = current.get(attribute_name)
            if value is not None:
                return value
            parent = current.parent
            current = parent if isinstance(parent, Tag) else None
        return None

    def _generate_node_id(self, tag: Tag) -> str:
        """Generate a deterministic SHA-1 identifier for a tag without an id.

        Args:
            tag: SVG node being inspected.

        Returns:
            A deterministic SHA-1 based identifier for the node.
        """
        fingerprint = "|".join(
            [
                self._build_dom_path(tag),
                tag.get("x", ""),
                tag.get("y", ""),
                tag.get("font-size", ""),
                self._get_inherited_attribute(tag, "transform") or "",
                str(tag.sourceline or ""),
                str(tag.sourcepos or ""),
            ]
        )
        digest = hashlib.sha1(fingerprint.encode("utf-8"), usedforsecurity=False)
        return f"generated-{digest.hexdigest()}"

    def _build_dom_path(self, tag: Tag) -> str:
        """Build a structural DOM path for a tag.

        Args:
            tag: SVG node being inspected.

        Returns:
            A deterministic DOM path string based on ancestor names and sibling
            positions among same-named elements.
        """
        path_segments: list[str] = []
        current: Tag | None = tag

        while current is not None:
            if current.name is None:
                break

            sibling_index = 1
            sibling = current.previous_sibling
            while sibling is not None:
                if isinstance(sibling, Tag) and sibling.name == current.name:
                    sibling_index += 1
                sibling = sibling.previous_sibling

            path_segments.append(f"{current.name}[{sibling_index}]")
            parent = current.parent
            current = parent if isinstance(parent, Tag) else None

        return "/".join(reversed(path_segments))
