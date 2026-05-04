import streamlit as st
import os
import base64
import shutil
from pathlib import Path
from dotenv import load_dotenv
from src.core import TranslationService
import logging
import threading
import time


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
    """A background-threaded tracker that provides smooth, continuous progress bar updates."""
    def __init__(self, progress_bar, status_text):
        self.pb = progress_bar
        self.st_text = status_text
        self.current_value = 0.0
        self.target_value = 0.0
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        """Background loop to crawl the progress bar toward the target milestone."""
        while not self.stop_event.is_set():
            if self.current_value < self.target_value:
                # Deceleration logic: Slow down as we approach the target to avoid "jumping"
                remaining = self.target_value - self.current_value
                
                if remaining > 0.05:
                    increment = 0.008  # Normal crawl
                else:
                    increment = 0.001  # Fine-grained crawl near milestone
                
                self.current_value = min(self.current_value + increment, 0.99) # Cap at 99% until stopped
                self.pb.progress(self.current_value)
            
            time.sleep(0.2)

    def write(self, text):
        """Update the status text and move the target milestone forward."""
        self.st_text.info(f"⏳ {text}")
        # Each step adds 25% to the target milestone (assuming 4 core steps)
        self.target_value = min(self.target_value + 0.25, 1.0)

    def stop(self, success=True):
        """Stop the background thread and set the bar to 100% or clear it."""
        self.stop_event.set()
        if success:
            self.pb.progress(1.0)
        else:
            self.pb.empty()
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)

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

        st.markdown("### Processing...")
        progress_bar = st.progress(0)
        status_text = st.empty()
        tracker = ProgressTracker(progress_bar, status_text)

        try:
            final_svg_path = service.process_file(
                input_path=input_path,
                target_language=target_lang,
                status_container=tracker
            )
            
            tracker.stop(success=True)
            status_text.success("✨ Translation pipeline complete!")

            # Store results in session state for persistence
            with open(final_svg_path, "rb") as f:
                content = f.read()
                st.session_state.download_bytes = content
                st.session_state.result_svg = base64.b64encode(content).decode('utf-8')

        except Exception as e:
            if 'tracker' in locals():
                tracker.stop(success=False)
            status_text.error(f"Pipeline Failure: {str(e)}")
            progress_bar.empty()
        
        finally:
            st.session_state.processing = False
            st.rerun()

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

        st.download_button(
            label="⬇️ Download Translated SVG",
            data=st.session_state.download_bytes,
            file_name=f"localized_{target_lang}_{uploaded_file.name}.svg" if uploaded_file else "translated.svg",
            mime="image/svg+xml",
            type="primary",
            use_container_width=True
        )

if __name__ == "__main__":
    main()