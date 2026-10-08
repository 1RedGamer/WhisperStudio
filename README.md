# Whisper Studio (macOS Edition)

[![Platform](https://img.shields.io/badge/Platform-macOS%2013.0%2B-black?logo=apple)](https://www.apple.com/macos/)
[![Apple Silicon](https://img.shields.io/badge/Apple%20Silicon-M1%20%2F%20M2%20%2F%20M3%20%2F%20M4%20%2F%20M5-blue?logo=apple)](https://developer.apple.com/metal/)
[![MLX Acceleration](https://img.shields.io/badge/Engine-MLX%20Whisper-purple)](https://github.com/ml-explore/mlx-examples/tree/main/whisper)
[![Download](https://img.shields.io/badge/Download-Latest%20Release-orange?logo=apple)](https://github.com/1RedGamer/WhisperStudio/releases)
[![License](https://img.shields.io/badge/License-MIT-brightgreen.svg)](LICENSE)

A native, standalone, privacy-first audio and video transcription studio tailored for macOS and heavily optimized for Apple Silicon (Metal GPU and Unified Memory).

**[⬇️ Download Ready-to-Run App (.zip)](https://github.com/1RedGamer/WhisperStudio/releases)**

Transcribes local media files into **Text (.txt)** and **Word (.docx)** documents with near-zero latency, complete offline execution, zero telemetry, and native MacBook Pro Touch Bar integration.

---

## ✨ Features

- **🚀 100% Apple Silicon Metal Acceleration**: Powered by `mlx-whisper` and Apple MLX framework, leveraging unified memory and high-bandwidth GPU cores on M1/M2/M3/M4/M5 chips.
- **🔒 Privacy First & 100% Offline**: All processing occurs locally on your machine. Audio files and transcriptions never leave your computer.
- **🌐 Dual-Language UI (Italian & English)**:
  - Automatically detects macOS system language on launch.
  - Live runtime language switching from the macOS Menu Bar (**🇮🇹 Italiano** / **🇺🇸 English**) with instant UI refresh and persistent preference saving in `QSettings`.
- **⏳ Model Loading Indicator**:
  - Displays a warm orange indicator (`#fbbf24`) under the progress bar while the model is loaded into Metal GPU memory.
  - Live status reflection on the MacBook Touch Bar (`Caricamento...` / `Loading...`).
  - Seamlessly transitions to active transcription percentage when audio chunk processing begins.
- **📖 Integrated Native macOS Help Guide**:
  - Native **Help / Aiuto** menu in the macOS menu bar.
  - Built-in rich dark-mode guide dialog with complete instructions, tips, and format specifications.
- **🧠 Intelligent Hardware Management**:
  - Automatically assesses available unified RAM.
  - Selects `Large-v3 Standard` for Macs with >8 GB RAM for maximum transcription accuracy.
  - Selects `Turbo` for 8 GB RAM machines to maximize speed without memory pressure.
  - Optional manual mode with real-time hardware recommendations.
- **💻 Native MacBook Pro Touch Bar Support**:
  - Dynamic localized action buttons (`■ Cancel`, `⏸️ Pause / ▶️ Resume`, `🚀 Start`).
  - Real-time purple progress bar and status display with sub-millisecond Cocoa response and <200 KB RAM footprint.
- **📊 Real-Time System Monitoring**: Live tracking of overall macOS system RAM utilization.
- **📂 Native Drag & Drop Queue**:
  - Drag files from Finder directly into the queue.
  - Visual blue drop marker for queue reordering.
  - Finder-style translucent drag preview.
  - File removal and queue clearing.
- **📄 Dual Export Formats**: Simultaneous plain text (`.txt`) and Microsoft Word (`.docx`) file generation.
- **🔔 macOS Notification Center**: Native audio-visual alerts upon batch completion, with automatic Finder reveal.

---

## 🎧 Supported Audio & Video Formats

Whisper Studio bundles a standalone static build of `ffmpeg`:
- **Audio**: MP3, WAV, M4A, AAC, FLAC, OGG, OPUS, ALAC, AIFF, WMA
- **Video**: MP4, MOV, MKV, WEBM

---

## 🛠 System Requirements

- **Operating System**: macOS 13.0 (Ventura), macOS 14.0 (Sonoma), or macOS 15.0 (Sequoia) / newer.
- **Architecture**: Apple Silicon (`arm64`) recommended (M1, M1 Pro/Max/Ultra, M2, M3, M4, M5).
- **RAM**: Minimum 8 GB Unified Memory (16 GB or higher recommended for Large-v3 models).
- **Python** (for running from source): Python 3.9 to 3.12.

---

## 🚀 Quick Start (Running from Source)

### 1. Set Up Environment & Install Dependencies
```bash
python3 -m pip install -r requirements.txt
```

### 2. Compile Touch Bar Native Library
```bash
clang -dynamiclib -framework Cocoa -O3 touchbar.m -o libtouchbar.dylib
```

### 3. Launch Whisper Studio
```bash
python3 whisper_studio.py
```

---

## 📦 Building Standalone macOS App Bundle (`.app`)

To produce an independent, standalone `Whisper Studio.app` using PyInstaller:

```bash
# 1. Compile native Touch Bar library
clang -dynamiclib -framework Cocoa -O3 touchbar.m -o libtouchbar.dylib

# 2. Run PyInstaller with the portable specification
python3 -m PyInstaller --clean "Whisper Studio.spec"
```

The compiled application bundle will be created at:
```
dist/Whisper Studio.app
```

### Deploying the Standalone App
```bash
# Clear macOS Gatekeeper quarantine attributes and ensure execute permissions
xattr -cr "dist/Whisper Studio.app"
chmod -R +x "dist/Whisper Studio.app"
```

You can also use the included `Unlock_Whisper.command` script to bypass Gatekeeper on fresh installs.

---

## 📁 Project Structure

```
Whisper Studio/
├── whisper_studio.py       # Core PyQt6 application, UI logic, and transcription worker
├── touchbar.m              # Objective-C Cocoa Touch Bar controller with bilingual support
├── libtouchbar.dylib       # Compiled native dylib bridge
├── ffmpeg                  # Bundled static ffmpeg binary
├── AppIcon.icns            # macOS native Dock & Application icon
├── app_icon_black.png      # Application icon asset
├── wispr.png               # High-DPI UI brand asset
├── Whisper Studio.spec     # PyInstaller macOS build configuration (SPECPATH-portable)
├── Unlock_Whisper.command  # Quick Gatekeeper bypass script
├── requirements.txt        # Python dependency manifest
├── .gitignore              # Git ignore rules
└── README.md               # Project documentation
```

---

## ⚙️ Architecture & Technical Details

1. **In-Process MLX Worker**: Transcription runs inside a dedicated `QThread` without spawned helper GUI processes, ensuring a single clean Dock tile and minimal memory overhead.
2. **Warm Orange Loading Feedback**: When the user starts transcription, a warm orange `#fbbf24` indicator informs the user that the model weights are loading into unified Metal GPU memory.
3. **Dynamic Audio Interception**: Subprocess and stdout streams are intercepted in real time to extract timestamp markers (`--> HH:MM:SS`), providing smooth progress percentage and time estimates.
4. **Smooth Curved Rendering**: The custom `WhisperProgressBar` employs an antialiased clip path conforming to the pill curvature, eliminating rectangular edge glitches at low percentages.
5. **Native macOS Menu Integration**: Connects to the macOS Application Menu and top menu bar with checkable language switching and the native Help guide dialog.

---

## 📥 Download Pre-built App (No Terminal Required)

If you don't want to build from source using Python, you can download the ready-to-run macOS application:

1. Go to the **[Releases](https://github.com/1RedGamer/WhisperStudio/releases)** tab on GitHub.
2. Download the latest `Whisper-Studio-v2.7.0-macOS.zip`.
3. Double-click to unzip it and move **`Whisper Studio.app`** to your **Applications** folder.
4. If macOS Gatekeeper shows an *"Unidentified Developer"* alert on the first launch:
   - Either double-click `Unlock_Whisper.command` included in the project, OR
   - Right-click (or Control-click) `Whisper Studio.app` in Finder and select **Open** $\rightarrow$ **Open**.

---

## 💡 About this Project & Disclaimer

This project was conceived, ideated, and tested by **Gabriele Clemente ([@1RedGamer](https://github.com/1RedGamer))**.

> **Full Disclosure:**  
> I am not a professional software engineer or UI/UX designer — I'm a passionate tech enthusiast! This application was architected, written, and built through human-AI pair programming using **Google Antigravity** powered by **Gemini 3.8**.
> 
> My primary contribution has been the initial concept, iterative testing, UI/UX conceptual design, feature scoping, and extensive real-world verification on Apple Silicon hardware (including the custom Touch Bar implementation, queue mechanics, bilingual localization, and Metal GPU acceleration).
> 
> Because of this, suggestions, code reviews, and Pull Requests to improve the codebase, optimize dependencies, or enhance software architecture are warmly welcomed and appreciated!

---

### ⚖️ Legal & Acknowledgements

- **OpenAI Whisper**: Speech recognition models created by OpenAI, licensed under the MIT License.
- **Apple MLX**: High-performance machine learning framework developed by Apple Silicon Research, licensed under the MIT License.
- **FFmpeg**: Multimedia processing handled by static FFmpeg builds.
- All product names, logos, and brands are property of their respective owners.

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
