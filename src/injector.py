"""SVG injection utilities for translated and shaped text content."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import arabic_reshaper
from bidi.algorithm import get_display
from bs4 import BeautifulSoup, NavigableString, Tag


LOGGER = logging.getLogger(__name__)


class SVGSpatialInjector:
    """Inject translated text back into an SVG document."""

    # Must match SVGSpatialExtractor._TEXT_TAGS exactly so structural
    # fingerprints remain symmetrical across extraction and injection.
    _TEXT_TAGS: list[str] = ["text", "tspan", "svg:text", "svg:tspan"]

    def inject_translations(
        self,
        svg_filepath: str,
        translated_nodes: list[dict[str, Any]],
        output_filepath: str,
        target_language: str,
    ) -> bool:
        """Inject translated text into an SVG and write the modified file.

        Args:
            svg_filepath: Path to the original SVG input file.
            translated_nodes: Translated node dictionaries containing `node_id`
                and `translated_text`.
            output_filepath: Destination path for the modified SVG file.
            target_language: Human-readable target language name.

        Returns:
            `True` when the SVG is successfully written, otherwise `False`.

        Raises:
            ValueError: If any required file path or `target_language` is empty.
        """
        if not svg_filepath:
            raise ValueError("svg_filepath must be provided.")
        if not output_filepath:
            raise ValueError("output_filepath must be provided.")
        if not target_language:
            raise ValueError("target_language must be provided.")

        try:
            with open(svg_filepath, "r", encoding="utf-8") as svg_file:
                soup = BeautifulSoup(svg_file, "lxml-xml")
        except OSError:
            LOGGER.exception("Failed to open SVG file for injection: %s", svg_filepath)
            return False

        successful_injections = 0
        missed_nodes = 0

        for translated_node in translated_nodes:
            node_id = str(translated_node.get("node_id", "")).strip()
            translated_text = str(translated_node.get("translated_text", ""))

            if not node_id:
                LOGGER.warning("Skipping translated node without node_id: %s", translated_node)
                missed_nodes += 1
                continue

            LOGGER.debug("Evaluating Node ID: %s", node_id)
            target_tag = self._find_target_tag(soup, node_id)
            if target_tag is None:
                LOGGER.warning("Fingerprint mismatch or missing translation for ID: %s", node_id)
                missed_nodes += 1
                continue

            final_text = self._shape_text_if_needed(translated_text, target_language)
            self._replace_direct_text(target_tag, final_text)

            # --- RTL Attribute & Layout Injection ---
            is_rtl = target_language.lower().strip() in ['arabic', 'ar', 'hebrew', 'he', 'urdu', 'ur', 'farsi', 'fa']
            if is_rtl:
                target_tag["xml:lang"] = "ar" if target_language.lower().strip() in ['arabic', 'ar'] else ""
                target_tag["direction"] = "rtl"
                target_tag["unicode-bidi"] = "embed"

                # Anchor Swap to prevent visual drift
                current_anchor = target_tag.get("text-anchor", "start").lower()
                new_anchor = current_anchor
                if current_anchor == "start":
                    new_anchor = "end"
                elif current_anchor == "end":
                    new_anchor = "start"
                
                if new_anchor != current_anchor:
                    target_tag["text-anchor"] = new_anchor
                    # Also scrub from style attribute to avoid CSS overrides
                    if target_tag.has_attr("style"):
                        styles = target_tag["style"].split(";")
                        new_styles = [s for s in styles if "text-anchor" not in s.lower()]
                        target_tag["style"] = ";".join(new_styles)

            self._apply_textlength_clamping(target_tag)
            self._apply_font_fallback(target_tag, target_language)
            successful_injections += 1
            LOGGER.debug(
                "Injected node '%s' -> '%s'",
                node_id,
                final_text[:60],
            )

        LOGGER.info(
            "Injection complete. Success: %d, Missed: %d",
            successful_injections,
            missed_nodes,
        )

        try:
            with open(output_filepath, "w", encoding="utf-8") as output_file:
                output_file.write(str(soup))
        except OSError:
            LOGGER.exception("Failed to write translated SVG file: %s", output_filepath)
            return False

        LOGGER.info("Injected translations into SVG: %s", output_filepath)
        return True

    def _find_target_tag(self, soup: BeautifulSoup, node_id: str) -> Tag | None:
        """Locate a target SVG node by explicit id or generated structural hash.

        Args:
            soup: Parsed SVG document.
            node_id: Target node identifier from the translation payload.

        Returns:
            The matching SVG tag when found, otherwise `None`.
        """
        direct_match = soup.find(id=node_id)
        if isinstance(direct_match, Tag):
            return direct_match

        for tag in soup.find_all(self._TEXT_TAGS):
            if not isinstance(tag, Tag):
                continue
            generated_id = tag.get("id") or self._generate_node_id(tag)
            if generated_id == node_id:
                return tag

        return None

    def _shape_text_if_needed(self, text: str, target_language: str) -> str:
        """Apply Arabic reshaping and bidi ordering when required.

        Args:
            text: Translated text to inject.
            target_language: Requested target language.

        Returns:
            The original or script-shaped text, depending on the language.
        """
        normalized_language = target_language.strip().lower()
        if normalized_language in {"arabic", "ar"}:
            reshaped_text = arabic_reshaper.reshape(text)
            return get_display(reshaped_text)
        return text

    def _replace_direct_text(self, tag: Tag, new_text: str) -> None:
        """Replace only immediate NavigableString children of a tag.

        This ensures that translated text is injected exactly where it was
        extracted from, without bleeding into parent nodes or destroying
        the layout of sibling elements.

        Args:
            tag: SVG node whose direct text content should be replaced.
            new_text: The localized string to inject.
        """
        # 1. Clear all existing direct NavigableString children
        for child in list(tag.children):
            if isinstance(child, NavigableString):
                child.extract()

        # 2. Inject the new localized string
        tag.append(NavigableString(new_text))

    def _apply_textlength_clamping(self, tag: Tag) -> None:
        """Enforce spatial constraints via ``textLength`` and ``lengthAdjust``.

        If the original node defined a ``textLength`` attribute, the injected
        node retains it and receives ``lengthAdjust="spacingAndGlyphs"`` to
        compress the localized string into the original bounding box.

        Args:
            tag: SVG node to apply spatial clamping to.
        """
        text_length = tag.get("textLength")
        if text_length is not None:
            tag["lengthAdjust"] = "spacingAndGlyphs"
            LOGGER.info(
                "Applied textLength clamping (%s) with spacingAndGlyphs to node '%s'.",
                text_length,
                tag.get("id", "unknown"),
            )

    def _apply_font_fallback(self, tag: Tag, target_language: str) -> None:
        """Inject script-appropriate font fallbacks to prevent tofu glyphs.

        Appends locale-specific font families to the node's ``font-family``
        declaration.

        Args:
            tag: SVG node to apply font fallbacks to.
            target_language: Human-readable target language name.
        """
        normalized = target_language.strip().lower()
        fallback_map: dict[str, str] = {
            "hindi": ", 'Noto Sans Devanagari', sans-serif",
            "hi": ", 'Noto Sans Devanagari', sans-serif",
            "arabic": ", 'Noto Naskh Arabic', sans-serif",
            "ar": ", 'Noto Naskh Arabic', sans-serif",
        }

        fallback_suffix = fallback_map.get(normalized)
        if not fallback_suffix:
            return

        primary_fallback = fallback_suffix.split(",")[1].strip().strip("'")

        # Strategy 1: font-family inside a `style` attribute (Inkscape default).
        style = tag.get("style", "")
        if style and "font-family" in style:
            if primary_fallback not in style:
                segments = style.split(";")
                updated: list[str] = []
                for segment in segments:
                    if segment.strip().lower().startswith("font-family"):
                        segment = segment.rstrip() + fallback_suffix
                    updated.append(segment)
                tag["style"] = ";".join(updated)
            return

        # Strategy 2: font-family as a direct XML attribute.
        font_family = tag.get("font-family")
        if font_family is not None:
            if primary_fallback not in font_family:
                tag["font-family"] = font_family + fallback_suffix
            return

        # Strategy 3: Inherit from ancestors and set explicitly.
        inherited = self._get_inherited_attribute(tag, "font-family")
        if inherited:
            if primary_fallback not in inherited:
                tag["font-family"] = inherited + fallback_suffix
            else:
                tag["font-family"] = inherited

    def _generate_node_id(self, tag: Tag) -> str:
        """Generate the extractor-compatible SHA-1 identifier for a tag.

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
