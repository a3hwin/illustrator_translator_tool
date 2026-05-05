"""Core orchestration for the AI vector localization pipeline."""

from __future__ import annotations

import logging
from pathlib import Path

from src.cli_bridge import VectorBridge
from src.extractor import SVGSpatialExtractor
from src.translator import LLMTranslator
from src.injector import SVGSpatialInjector

LOGGER = logging.getLogger(__name__)


class TranslationService:
    """Unified service for vector asset localization.
    
    This class consolidates the JSX Bridge, Spatial Extractor, LLM Translator,
    and Spatial Injector into a single atomic workflow.
    """

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize the localization sub-components.
        
        Args:
            api_key: Gemini API key. Falls back to env var if omitted.
        """
        self.bridge = VectorBridge()
        self.extractor = SVGSpatialExtractor()
        self.translator = LLMTranslator(api_key=api_key)
        self.injector = SVGSpatialInjector()

    def process_file(
        self, 
        input_path: Path, 
        target_language: str,
        status_container: Any = None
    ) -> tuple[Path, Path]:
        """Execute the full 5-stage localization pipeline.
        
        Returns:
            A tuple of (translated_svg_path, translated_ai_path).
        """
        base_dir = Path(__file__).resolve().parent.parent
        temp_dir = base_dir / "data" / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        input_path = Path(input_path)
        temp_svg = temp_dir / "bridge_output.svg"
        translated_svg = temp_dir / "final_translated.svg"

        # Stage 1: Bridge
        if status_container:
            status_container.write("Step 1: Launching Adobe Illustrator Bridge...")
            
        if input_path.suffix.lower() == ".svg":
            import shutil
            shutil.copy(input_path, temp_svg)
        else:
            if not self.bridge.convert_ai_to_svg(str(input_path), str(temp_svg)):
                raise RuntimeError("Adobe Illustrator failed to export native SVG.")

        # Stage 2: Extraction
        if status_container:
            status_container.write("Step 2: Extracting Spatial Text Nodes...")
            
        nodes = self.extractor.extract_text_nodes(str(temp_svg))
        if not nodes:
            raise ValueError("No text elements found. The file may have outlined text.")

        # Stage 3: Translation
        if status_container:
            status_container.write(f"Step 3: Translating via Gemini 2.5-Flash ({target_language})...")
            
        translated_nodes = self.translator.translate_nodes(nodes, target_language)

        # Stage 4: Injection
        if status_container:
            status_container.write(f"Step 4: Injecting {target_language} Vectors...")
            
        success = self.injector.inject_translations(
            str(temp_svg),
            translated_nodes,
            str(translated_svg),
            target_language
        )
        
        if not success:
            raise RuntimeError("Failed to inject translated vectors into SVG DOM.")

        # Stage 5: Round-Trip (SVG -> AI)
        final_ai = translated_svg.with_suffix(".ai")
        if status_container:
            status_container.write("Step 5: Exporting Final Native .ai Asset...")
            
        self.bridge.convert_svg_to_ai(str(translated_svg), str(final_ai), target_language)

        return translated_svg, final_ai
