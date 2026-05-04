import streamlit as st
import os
import base64
import shutil
from pathlib import Path
from dotenv import load_dotenv
from src.core import TranslationService
import logging


# --- Restore Terminal Debug Logs ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)


# Load environment variables (API Key and Illustrator Path)
load_dotenv()

# Define core paths
BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "data" / "input"
TEMP_DIR = BASE_DIR / "data" / "temp"

def clear_temp():
    """Safely clear the temp directory in the background, ignoring Windows file locks."""
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    INPUT_DIR.mkdir(parents=True, exist_ok=True)

class ProgressTracker:
    """A clever wrapper to convert text updates from core.py into a filling progress bar."""
    def __init__(self, progress_bar, status_text):
        self.pb = progress_bar
        self.st_text = status_text
        self.step = 0
        self.total_steps = 4 # Total number of steps in TranslationService

    def write(self, text):
        # Display the text cleanly
        self.st_text.info(f"⏳ {text}")
        self.step += 1
        # Fill the bar proportionally, capped at 100%
        progress = min(self.step / self.total_steps, 1.0)
        self.pb.progress(progress)

def main():
    # Page setup
    st.set_page_config(page_title="AI Vector Localizer", page_icon="🎨", layout="centered")
    
    # Header
    st.title("🎨 AI Vector Localizer")
    st.markdown("Automatically extract, translate, and inject text inside Adobe Illustrator & SVG files.")

    # Environment Instructions
    with st.expander("⚙️ System Setup & Requirements", expanded=False):
        st.warning(
            "**Make sure your `.env` file contains the following:**\n\n"
            "1. `GEMINI_API_KEY`: Your active Google Gemini API key.\n"
            "2. `ILLUSTRATOR_PATH`: The absolute path to the Illustrator executable on this machine.\n"
            "   *(Example: `C:\\Program Files\\Adobe\\Adobe Illustrator 2026\\Support Files\\Contents\\Windows\\Illustrator.exe`)*"
        )

    # Silent background cleanup
    clear_temp()

    # --- UI Layout ---
    st.markdown("### 1. Upload File")
    uploaded_file = st.file_uploader("Drop your .ai or .svg file here", type=["ai", "svg"], label_visibility="collapsed")

    st.markdown("### 2. Target Language")
    target_lang = st.selectbox(
        "Select language",
        ["Arabic", "Hindi"],
        label_visibility="collapsed"
    )

    st.markdown("<br>", unsafe_allow_html=True) # Spacer

    # Process Button
    if uploaded_file and st.button("Process Vector File", type="primary", use_container_width=True):
        
        # Verify API Key is loaded before starting
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            st.error("🚨 Gemini API Key missing! Please add `GEMINI_API_KEY` to your `.env` file.")
            st.stop()

        # Save uploaded file
        input_path = INPUT_DIR / uploaded_file.name
        with open(input_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        service = TranslationService(api_key=api_key)

        st.markdown("### Processing...")
        
        # Initialize the progress bar UI
        progress_bar = st.progress(0)
        status_text = st.empty()
        tracker = ProgressTracker(progress_bar, status_text)

        try:
            # Run the pipeline
            final_svg_path = service.process_file(
                input_path=input_path,
                target_language=target_lang,
                status_container=tracker
            )
            
            # Force 100% and success state
            progress_bar.progress(1.0)
            status_text.success("✨ Translation pipeline complete!")

            # --- Base64 SVG Preview ---
            st.markdown("### Localized Preview")
            with open(final_svg_path, "rb") as f:
                base64_svg = base64.b64encode(f.read()).decode('utf-8')

            svg_html = f'''
                <div style="display: flex; justify-content: center; border: 1px solid #ddd; padding: 10px; border-radius: 8px; background-color: #f9f9f9; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                    <img src="data:image/svg+xml;base64,{base64_svg}" alt="Localized Vector" style="max-width: 100%;">
                </div>
                <br>
            '''
            st.markdown(svg_html, unsafe_allow_html=True)

            # Download Button
            with open(final_svg_path, "rb") as f:
                st.download_button(
                    label="⬇️ Download Translated SVG",
                    data=f,
                    file_name=f"localized_{target_lang}_{uploaded_file.name}.svg",
                    mime="image/svg+xml",
                    type="primary",
                    use_container_width=True
                )

        except Exception as e:
            status_text.error(f"Pipeline Failure: {str(e)}")
            progress_bar.empty() # Hide the broken progress bar

if __name__ == "__main__":
    main()