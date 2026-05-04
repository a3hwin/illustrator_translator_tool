# 🎨 AI Vector Localizer (Interview Submission)

This repository contains an automated pipeline to localize Adobe Illustrator (`.ai`) and SVG files using the Gemini 2.5 Flash API. It features a custom native JSX bridge to ensure non-destructive text extraction and injection.

## 🛠️ Prerequisites
* **Python 3.10+**
* **Adobe Illustrator** (Installed locally on Windows or macOS)
* **Google Gemini API Key**

## ⚙️ Quick Start

**1. Clone & Environment Setup**
```bash
git clone https://github.com/a3hwin/illustrator_translator_tool.git
cd ai-illustrator-translator
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
```

**2. Install Dependencies**
```bash
pip install -r requirements.txt
```

**3. Configure Environment (.env)**
Create a `.env` file in the root directory:
```env
GEMINI_API_KEY=your_gemini_api_key
# Example Windows Path:
ILLUSTRATOR_PATH=C:\Program Files\Adobe\Adobe Illustrator 2026\Support Files\Contents\Windows\Illustrator.exe
# Example macOS Path:
# ILLUSTRATOR_PATH=/Applications/Adobe Illustrator 2026/Adobe Illustrator.app/Contents/MacOS/Adobe Illustrator
```
> [!IMPORTANT]
> Ensure `ILLUSTRATOR_PATH` points to the actual Illustrator executable on your machine. For macOS, this is the binary **inside** the `.app` bundle.

**4. Run the Application**
```bash
streamlit run app.py
```

## 🚀 Key Features
* **Native Bridge:** Uses ExtendScript (JSX) to interact with Illustrator, preserving live text tags and vector coordinates.
* **Arabic RTL Support:** Implements automatic pre-shaping and `text-anchor` swapping for visually correct RTL alignment.
* **Resilience:** Includes exponential backoff for API rate limits and robust file-lock handling for Windows environments.

## ⏳ Usage & Performance Warning
Adobe Illustrator files contain complex nested coordinate systems. Depending on the size of the file and the target language, processing can take **3 to 5 minutes**.

1. **Upload** your `.ai` or `.svg` file.
2. **Select** your target language.
3. **Click** "Process Vector File".
4. **WAIT.** The progress bar will update as the system bridges with Illustrator, batches the API calls, and redraws the vectors. **Do not refresh the page while the system is processing.**
