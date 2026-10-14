# Whisper Studio

[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Windows-blue?logo=apple&logoColor=white)](https://github.com/Ritolino/WhisperStudio)
[![macOS Engine](https://img.shields.io/badge/macOS-Apple%20Silicon%20(MLX)-purple?logo=apple)](https://github.com/ml-explore/mlx-examples/tree/main/whisper)
[![Windows Engine](https://img.shields.io/badge/Windows-NVIDIA%20CUDA%20%2F%20CPU-green?logo=nvidia)](https://developer.nvidia.com/cuda-toolkit)
[![UI](https://img.shields.io/badge/UI-PyQt6%20Modern%20Dark-purple)](https://riverbankcomputing.com/software/pyqt/)
[![Release](https://img.shields.io/badge/Release-v2.7.5-orange)](https://github.com/Ritolino/WhisperStudio/releases/tag/v2.7.5)
[![License](https://img.shields.io/badge/License-MIT-brightgreen.svg)](LICENSE)

A native, standalone, privacy-first audio and video transcription studio tailored for **macOS** (Apple Silicon Metal) and **Windows** (NVIDIA CUDA & Intel/AMD CPU).

Transcribes local media files into **Plain Text (.txt)** and **Word (.docx)** documents with complete offline execution, zero telemetry, and maximum hardware performance.

---

### ⬇️ Download Pre-built App (No Python Required)

| Platform | Recommended Hardware | Download Link |
| :--- | :--- | :--- |
| **🍏 macOS** | Apple Silicon (M1 / M2 / M3 / M4 / M5) | [**Download for macOS (.zip)**](https://github.com/Ritolino/WhisperStudio/releases/download/v2.7.5/Whisper-Studio-v2.7.5-macOS.zip) |
| **🪟 Windows** | NVIDIA GeForce RTX / GTX or Intel/AMD CPU | [**Download for Windows (.zip)**](https://github.com/Ritolino/WhisperStudio/releases/download/v2.7.5/Whisper-Studio-v2.7.5-Windows.zip) |

*Simply download the `.zip` for your platform, extract it to any folder on your computer, and run the app immediately.*

---

## ✨ Features

- **🔒 Privacy First & 100% Offline**: All processing occurs strictly on your machine. Your audio files and transcripts never touch the cloud or external servers.
- **⚡ Zero Hallucinations & Turbocharged Speed**:
  - Configured with `condition_on_previous_text=False` and Silero Voice Activity Detection (VAD) to eradicate silence loops, repetitive hallucinations (e.g. repeated words on silent pauses), and fallback slowdowns.
  - Doubled transcription throughput across both Apple Silicon and NVIDIA/CPU architectures.
- **🚀 Hardware-Accelerated Neural Engines**:
  - **macOS**: Powered by Apple MLX (`mlx-whisper`), leveraging unified memory and Metal GPU cores across M1, M2, M3, M4, and M5 chips.
  - **Windows**: Powered by Faster-Whisper (`CTranslate2`), automatically preloading cuBLAS 12 libraries for `float16` GPU inference on NVIDIA cards, with an automatic runtime fallback to multithreaded `INT8` on Intel and AMD CPUs.
- **🧠 Smart Hardware & Memory Management**:
  - **Automatic Mode**: Automatically selects **Large-v3 Standard** on high-spec hardware (>8 GB RAM on Mac; NVIDIA GPU with ≥6 GB VRAM on Windows) for maximum fidelity, and switches to **Large-v3 Turbo** on lighter machines.
  - **Manual Mode & Persistent Memory**: Freely pick between Large-v3 Standard and Turbo. Preferences are remembered in `QSettings` across app restarts.
  - **Full Memory Reclaim**: Unloads neural weights completely from VRAM/RAM as soon as a batch finishes or is cancelled.
- **🌐 Dual-Language UI with Country Flags (Italian & English)**:
  - Automatically detects system locale on launch.
  - Live runtime language switching from the top Menu Bar (**🇮🇹 Italiano** / **🇬🇧 English**) with crisp native flag icons, instant UI refresh, and persistent preference saving.
- **📄 Dual Export Formats**: Simultaneous plain text (`.txt`) and Microsoft Word (`.docx`) file generation directly beside original media files, with protection against Windows file locks.
- **📂 Smooth Drag & Drop Queue**: Drag files or folders directly into the queue, reorder waiting items with visual feedback, and inspect live progress cards with duration and ETA.
- **💻 Platform-Tailored Polish**:
  - **macOS**: Native MacBook Pro Touch Bar controls and real-time status display, macOS Notification Center alerts with automatic Finder reveal.
  - **Windows**: Antialiased custom curved progress bar, taskbar branding via `AppUserModelID`, and multi-resolution icons.

---

## 🎧 Supported Audio & Video Formats

Supported out of the box via PyAV and bundled FFmpeg:
- **Audio**: MP3, WAV, M4A, AAC, FLAC, OGG, OPUS, ALAC, AIFF, WMA
- **Video**: MP4, MOV, MKV, WEBM, AVI

---

## 🛠 System Requirements

| Specification | macOS Edition | Windows Edition |
| :--- | :--- | :--- |
| **Operating System** | macOS 13.0 (Ventura) or newer | Windows 10 (64-bit) or Windows 11 (64-bit) |
| **Processor / GPU** | Apple Silicon (M1 / M2 / M3 / M4 / M5) | NVIDIA GeForce RTX / GTX (CUDA 12) or 64-bit Intel/AMD CPU |
| **RAM** | Minimum 8 GB (16 GB+ recommended) | Minimum 8 GB (16 GB+ recommended) |
| **Disk Space** | ~4 GB for model weights cache | ~4 GB for model weights cache |

---

## 🚀 Running from Source

If you prefer to run Whisper Studio from source code using Python:

### For macOS
```bash
cd macOS
python3 -m pip install -r requirements.txt
python3 whisper_studio.py
```

### For Windows
```bash
cd Windows
python -m pip install -r requirements.txt
python whisper_studio.py
```

---

## 📦 Building Standalone Packages

To compile standalone standalone packages using PyInstaller:

### On macOS
```bash
cd macOS
python3 -m PyInstaller --clean -y "Whisper Studio.spec"
```
The compiled application bundle (`Whisper Studio.app`) will be located in `dist/`.

### On Windows
```bash
cd Windows
python -m PyInstaller --clean -y WhisperPortable.spec
```
The compiled standalone executable (`WhisperPortable.exe`) and `_internal` directory will be located in `dist/WhisperPortable/`.

---

## 📁 Repository Structure

```
WhisperStudio/
├── README.md               # Master documentation and cross-platform download portal
├── LICENSE                 # MIT License
├── .gitignore              # Unified Git ignore rules
│
├── assets/                 # Shared brand icons and graphics
│   ├── wispr.png
│   ├── app_icon_black.png
│   ├── wispr.ico
│   └── AppIcon.icns
│
├── macOS/                  # macOS Edition (Apple Silicon MLX)
│   ├── whisper_studio.py
│   ├── requirements.txt
│   ├── Whisper Studio.spec
│   ├── touchbar.m
│   ├── libtouchbar.dylib
│   ├── Unlock_Whisper.command
│   └── AppIcon.icns
│
└── Windows/                # Windows Edition (NVIDIA CUDA & Intel/AMD CPU)
    ├── whisper_studio.py
    ├── requirements.txt
    ├── WhisperPortable.spec
    ├── ISTRUZIONI.txt
    ├── wispr.ico
    └── app_icon_black.png
```

---

## 💡 About this Project & Disclaimer

This project was conceived, designed, and tested by **Gabriele Clemente ([@Ritolino](https://github.com/Ritolino))**.

> **Full Disclosure:**  
> I am not a professional software engineer or UI/UX designer — I'm a passionate tech enthusiast! This application was architected, written, and refined through human-AI pair programming using **Google Antigravity** powered by **Gemini 3.8**.
> 
> My primary contribution has been the initial concept, iterative testing, UI/UX design, feature scoping, and real-world verification across both Apple Silicon and Windows hardware (including Metal acceleration, Touch Bar controls, NVIDIA CUDA acceleration, CPU fallback, and bilingual localization).
> 
> Because of this, suggestions, code reviews, and Pull Requests to improve the codebase, optimize dependencies, or enhance software architecture are warmly welcomed and appreciated!

---

### ⚖️ Legal & Acknowledgements

- **OpenAI Whisper**: Speech recognition models created by OpenAI, licensed under the MIT License.
- **Apple MLX**: High-performance machine learning framework developed by Apple Silicon research teams.
- **Faster-Whisper & CTranslate2**: Fast inference engine developed by SYSTRAN, licensed under the MIT License.
- **PyAV & FFmpeg**: Multimedia processing handled by PyAV and FFmpeg libraries.
- All product names, logos, and brands are property of their respective owners.

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
