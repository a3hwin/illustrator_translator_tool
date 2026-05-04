"""Bridge Adobe Illustrator assets through native ExtendScript (JSX) execution."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

LOGGER = logging.getLogger(__name__)

# --- THE JSX TEMPLATE (As specified in requirements) ---
JSX_CONVERT_TO_SVG = """
#target illustrator
app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;
function convertToSVG() {
    var sourcePath = "PYTHON_INJECT_SOURCE";
    var destPath = "PYTHON_INJECT_DEST";
    var sourceFile = new File(sourcePath);
    if (!sourceFile.exists) return;
    var doc = app.open(sourceFile);
    var destFile = new File(destPath);
    var options = new ExportOptionsSVG();
    options.fontType = SVGFontType.SVGFONT; 
    options.embedRasterImages = true; 
    options.cssProperties = SVGCSSPropertyLocation.STYLEATTRIBUTES;
    options.documentEncoding = SVGDocumentEncoding.UTF8;
    doc.exportFile(destFile, ExportType.SVG, options);
    doc.close(SaveOptions.DONOTSAVECHANGES);
}
convertToSVG();
"""

# Similar template for the return trip (SVG -> PDF/AI) to maintain pipeline parity
JSX_SAVE_AS_PDF = """
#target illustrator
app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;
function saveAsPDF() {
    var sourcePath = "PYTHON_INJECT_SOURCE";
    var destPath = "PYTHON_INJECT_DEST";
    var sourceFile = new File(sourcePath);
    if (!sourceFile.exists) return;
    var doc = app.open(sourceFile);
    var destFile = new File(destPath);
    var options = new PDFSaveOptions();
    options.preserveEditability = true;
    doc.saveAs(destFile, options);
    doc.close(SaveOptions.DONOTSAVECHANGES);
}
saveAsPDF();
"""

class VectorBridge:
    """Bridge Illustrator assets using native Adobe ExtendScript execution.
    
    This replaces the Inkscape-based 'SVG Bridge' with a native Adobe bridge
    to ensure that live text elements are preserved as <text> tags rather than
    being converted to vector paths.
    """

    DEFAULT_ILLUSTRATOR_PATH = r"C:\Program Files\Adobe\Adobe Illustrator 2024\Support Files\Contents\Windows\Illustrator.exe"

    def __init__(self, illustrator_path: str | None = None) -> None:
        """Initialize the bridge with the path to the Illustrator executable.

        Args:
            illustrator_path: Absolute path to Illustrator.exe. If omitted, 
                it checks the ILLUSTRATOR_PATH env var or uses the default.
        """
        self.illustrator_path = os.path.normpath(
            illustrator_path or 
            os.getenv("ILLUSTRATOR_PATH") or 
            self.DEFAULT_ILLUSTRATOR_PATH
        )

    def convert_ai_to_svg(self, input_path: str, output_path: str) -> bool:
        """Convert an Illustrator (.ai) or .eps file to SVG using native JSX.

        Args:
            input_path: Path to the source vector file.
            output_path: Destination path for the exported SVG.

        Returns:
            True if the SVG exists and is non-empty, False otherwise.
        """
        return self._run_jsx_bridge(input_path, output_path, JSX_CONVERT_TO_SVG)

    def convert_svg_to_pdf(self, input_path: str, output_path: str) -> bool:
        """Convert a localized SVG back to a PDF/AI file using native JSX.

        Args:
            input_path: Path to the translated SVG file.
            output_path: Destination path for the final PDF/AI file.

        Returns:
            True if the output file exists and is non-empty, False otherwise.
        """
        return self._run_jsx_bridge(input_path, output_path, JSX_SAVE_AS_PDF)

    def _run_jsx_bridge(self, input_path: str, output_path: str, template: str) -> bool:
        """Execute a dynamic JSX script within Adobe Illustrator.

        Args:
            input_path: Source file path.
            output_path: Destination file path.
            template: The JSX code block containing PYTHON_INJECT placeholders.

        Returns:
            True if the operation succeeded and the output file exists.
        """
        input_file = Path(input_path).expanduser().resolve()
        output_file = Path(output_path).expanduser().resolve()

        if not input_file.exists():
            LOGGER.error("Input file not found: %s", input_file)
            return False

        # --- PATH SANITIZATION (CRITICAL) ---
        # ExtendScript/Illustrator requires forward slashes for paths.
        safe_input = str(input_file).replace("\\", "/")
        safe_output = str(output_file).replace("\\", "/")

        # Inject paths into the JSX template
        jsx_content = template.replace("PYTHON_INJECT_SOURCE", safe_input)
        jsx_content = jsx_content.replace("PYTHON_INJECT_DEST", safe_output)

        # Create temporary JSX script in the output directory
        output_file.parent.mkdir(parents=True, exist_ok=True)
        jsx_script_path = output_file.parent / "temp_bridge.jsx"

        try:
            with open(jsx_script_path, "w", encoding="utf-8") as f:
                f.write(jsx_content)

            LOGGER.info("DEBUG: Using Illustrator Path -> %s", self.illustrator_path)
            LOGGER.info("DEBUG: Sanitized Source Path (JSX) -> %s", safe_input)
            
            # Subprocess execution: [path, "-run", jsx_file]
            command = [self.illustrator_path, "-run", str(jsx_script_path)]
            subprocess.run(command, check=True, capture_output=True, text=True)

        except (OSError, subprocess.CalledProcessError) as exc:
            LOGGER.error("Illustrator JSX execution failed: %s", exc)
            return False
        finally:
            # Cleanup temporary JSX script
            if jsx_script_path.exists():
                try:
                    os.remove(jsx_script_path)
                except OSError:
                    LOGGER.warning("Failed to delete temporary JSX script: %s", jsx_script_path)

        # Final Validation
        if output_file.exists() and output_file.stat().st_size > 0:
            LOGGER.info("Bridge successful. Output generated: %s", output_file)
            return True
        
        LOGGER.error("Illustrator finished but output file is missing or empty: %s", output_file)
        return False
