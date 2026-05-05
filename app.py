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

class SimpleTracker:
    """A robust status tracker using native Streamlit containers."""
    def __init__(self, progress_bar, status_obj):
        self.pb = progress_bar
        self.status = status_obj
        self.step = 0
        self.total_steps = 5

    def write(self, text):
        """Log a step and update the progress bar."""
        self.step += 1
        progress = min(self.step / self.total_steps, 1.0)
        self.pb.progress(progress)
        self.status.write(f"✅ {text}")
        self.status.update(label=f"Current Task: {text}...")

def main():
    # Page setup
    st.set_page_config(page_title="AI Vector Localizer", page_icon="🎨", layout="centered")
    
    # Header
    st.title("🎨 AI Vector Localizer")
    st.markdown("Automatically extract, translate, and inject text inside Adobe Illustrator & SVG files.")

    # Usage Warning
    st.info(
        "⏳ **Usage & Performance Warning**\n\n"
        "Adobe Illustrator files contain complex nested coordinate systems. Depending on the size of the file and the target language, processing can take **3 to 5 minutes**.\n\n"
        "1. Upload your .ai or .svg file.\n"
        "2. Select your target language.\n"
        "3. Click 'Process Vector File'.\n\n"
        "**WAIT.** The progress bar will update as the system bridges with Illustrator, batches the API calls, and redraws the vectors. **Do not refresh the page while the system is processing.**"
    )

    # Environment Instructions
    with st.expander("⚙️ System Setup & Requirements", expanded=False):
        st.warning(
            "**Make sure your `.env` file contains the following:**\n\n"
            "1. `GEMINI_API_KEY`: Your active Google Gemini API key.\n"
            "2. `ILLUSTRATOR_PATH`: The absolute path to the Illustrator executable on this machine.\n"
            "   - **Windows:** `C:\\Program Files\\Adobe\\Adobe Illustrator 2026\\Support Files\\Contents\\Windows\\Illustrator.exe`\n"
            "   - **macOS:** `/Applications/Adobe Illustrator 2026/Adobe Illustrator.app/Contents/MacOS/Adobe Illustrator`"
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

    # --- Result Persistence ---
    if "result_svg" not in st.session_state:
        st.session_state.result_svg = None
    if "download_bytes" not in st.session_state:
        st.session_state.download_bytes = None
    if "download_ai_bytes" not in st.session_state:
        st.session_state.download_ai_bytes = None
    if "processing" not in st.session_state:
        st.session_state.processing = False

    def trigger_processing():
        st.session_state.processing = True
        st.session_state.result_svg = None # Reset previous results

    # Process Button
    if uploaded_file and st.button(
        "Process Vector File", 
        type="primary", 
        use_container_width=True, 
        disabled=st.session_state.processing,
        on_click=trigger_processing
    ):
        # Verify API Key is loaded before starting
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            st.error("🚨 Gemini API Key missing! Please add `GEMINI_API_KEY` to your `.env` file.")
            st.session_state.processing = False
            st.stop()

        # Save uploaded file
        input_path = INPUT_DIR / uploaded_file.name
        with open(input_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        service = TranslationService(api_key=api_key)

        with st.status("Initializing Localization Pipeline...", expanded=True) as status:
            progress_bar = st.progress(0)
            tracker = SimpleTracker(progress_bar, status)

            try:
                final_svg_path, final_ai_path = service.process_file(
                    input_path=input_path,
                    target_language=target_lang,
                    status_container=tracker
                )
                
                # Update status to success
                status.update(label="✨ Translation pipeline complete!", state="complete", expanded=False)

                # Store SVG results
                with open(final_svg_path, "rb") as f:
                    svg_content = f.read()
                    st.session_state.download_bytes = svg_content
                    st.session_state.result_svg = base64.b64encode(svg_content).decode('utf-8')
                
                # Store AI results
                with open(final_ai_path, "rb") as f:
                    st.session_state.download_ai_bytes = f.read()

            except Exception as e:
                status.update(label=f"❌ Pipeline Failure: {str(e)}", state="error", expanded=True)
                logging.exception("Pipeline failed")
            
            finally:
                st.session_state.processing = False
                # We don't call st.rerun here so the status container remains visible for a moment
                # Streamlit will naturally re-render once the interaction loop finishes.

    # --- Persistent Result Display ---
    if st.session_state.result_svg:
        st.divider()
        st.markdown("### Localized Preview")
        
        svg_html = f'''
            <div style="display: flex; justify-content: center; border: 1px solid #ddd; padding: 10px; border-radius: 8px; background-color: #f9f9f9; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                <img src="data:image/svg+xml;base64,{st.session_state.result_svg}" alt="Localized Vector" style="max-width: 100%;">
            </div>
            <br>
        '''
        st.markdown(svg_html, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        
        with col1:
            st.download_button(
                label="⬇️ Download .AI Asset",
                data=st.session_state.download_ai_bytes,
                file_name=f"localized_{target_lang}_{uploaded_file.name}.ai" if uploaded_file else "translated.ai",
                mime="application/postscript",
                type="primary",
                use_container_width=True
            )

        with col2:
            st.download_button(
                label="⬇️ Download .SVG Asset",
                data=st.session_state.download_bytes,
                file_name=f"localized_{target_lang}_{uploaded_file.name}.svg" if uploaded_file else "translated.svg",
                mime="image/svg+xml",
                type="secondary",
                use_container_width=True
            )

if __name__ == "__main__":
    main()