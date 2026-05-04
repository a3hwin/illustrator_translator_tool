import logging
import os
from src.cli_bridge import VectorBridge
from src.extractor import SVGSpatialExtractor
from src.translator import LLMTranslator  # Verify if your class is 'LLMTranslator' or 'translator'
from src.injector import SVGSpatialInjector

# Set up logging to see the bridge's internal movements
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s | %(name)s | %(message)s', force=True)

# Define paths
input_file = os.path.abspath("data/input/test_file.ai")
temp_svg = os.path.abspath("data/temp/temp_from_ai.svg")
translated_svg = os.path.abspath("data/temp/final_translated.svg")

print("\n=== STAGE 1: NATIVE BRIDGE (Illustrator JSX) ===")
bridge = VectorBridge()
if bridge.convert_ai_to_svg(input_file, temp_svg):
    print("SUCCESS: Adobe Illustrator generated the SVG.")
else:
    print("FAILED: Check if Illustrator is installed and the path is correct.")
    exit()

print("\n=== STAGE 2: EXTRACTION ===")
extractor = SVGSpatialExtractor()
nodes = extractor.extract_text_nodes(temp_svg)
print(f"Extracted {len(nodes)} text nodes.")

if len(nodes) > 0:
    print("\n=== STAGE 3: TRANSLATION (Gemini 2.5-Flash) ===")
    translator = LLMTranslator()
    translations = translator.translate_nodes(nodes, "Hindi")
    
    print("\n=== STAGE 4: INJECTION ===")
    injector = SVGSpatialInjector()
    injection_status = injector.inject_translations(temp_svg, translations, translated_svg, "hi")
    print(f"Injection Complete. Status: {injection_status}")
    print(f"\nDONE! Open this file to see results: {translated_svg}")
else:
    print("ERROR: No text nodes found. The SVG might still be outlined.")