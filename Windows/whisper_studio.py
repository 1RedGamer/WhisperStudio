#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
========================================================================
                          WHISPER STUDIO
                Studio Edition (v2.7.5) — Windows Edition
    Offline Audio & Video Transcription with NVIDIA CUDA & Intel/AMD CPU
========================================================================
"""

import os
import sys
sys.dont_write_bytecode = True
import re
import io
import time
import shutil
import subprocess
import multiprocessing
import threading
import ctypes
import json
import logging
from pathlib import Path

# Set resilient timeouts for Hugging Face Hub downloads and network requests
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "60")

# Multiprocessing freeze support for PyInstaller on Windows
multiprocessing.freeze_support()

# Explicit Windows AppUserModelID for taskbar branding and icon association
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("WhisperStudio.WindowsEdition.2.7.5")
except Exception:
    pass

# Safe stdout/stderr protection for PyInstaller windowed GUI apps (--windowed)
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()

# ==============================================================================
# PYAV COMPATIBILITY PATCH (METADATA_ERRORS HANDLING)
# ==============================================================================
def apply_pyav_patch():
    """
    Patches av.open to gracefully handle versions of PyAV that do not accept
    metadata_errors parameter, preventing unexpected TypeErrors.
    """
    try:
        import av
        orig_av_open = av.open
        def safe_av_open(*args, **kwargs):
            try:
                return orig_av_open(*args, **kwargs)
            except TypeError:
                kwargs.pop("metadata_errors", None)
                return orig_av_open(*args, **kwargs)
        av.open = safe_av_open
    except Exception:
        pass

apply_pyav_patch()

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QCheckBox, QProgressBar, QButtonGroup,
    QListWidget, QListWidgetItem, QFrame, QFileDialog, QMessageBox,
    QAbstractItemView, QDialog, QSizePolicy, QTextBrowser, QMenu
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QPoint, QPointF, QRectF, QMimeData, QSize, QSettings, QLocale
from PyQt6.QtGui import (
    QIcon, QPixmap, QDragEnterEvent, QDropEvent, QDrag, QPainter,
    QColor, QPen, QPainterPath, QAction, QActionGroup, QLinearGradient, QFont
)

# Resolve base directory for assets and portable environment
if getattr(sys, 'frozen', False):
    DIR_CORRENTE = Path(sys._MEIPASS)
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    DIR_CORRENTE = Path(__file__).resolve().parent
    BASE_DIR = DIR_CORRENTE

# Configure Logging in %LOCALAPPDATA%\WhisperStudio\logs to keep the project directory clean
LOG_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "WhisperStudio" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "whisper_studio.log"

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)

VALID_EXTENSIONS = {
    ".mp3", ".m4a", ".wav", ".mp4", ".mov", ".mkv",
    ".aac", ".ogg", ".webm", ".flac", ".alac", ".opus", ".wma", ".aiff"
}

# ==============================================================================
# WINDOWS CUDA & CUBLAS DLL PRELOADING
# ==============================================================================
def _preload_cuda_libraries():
    """
    Preloads dynamic NVIDIA CUDA / cuBLAS libraries (cublasLt64_12.dll and cublas64_12.dll)
    to guarantee full GPU acceleration out of the box without requiring CUDA Toolkit.
    """
    search_dirs = [
        BASE_DIR,
        BASE_DIR / "_internal",
        BASE_DIR / "dlls",
        DIR_CORRENTE,
        DIR_CORRENTE / "_internal",
    ]
    try:
        import site
        for sp in site.getsitepackages():
            search_dirs.append(Path(sp) / "nvidia" / "cublas" / "bin")
            search_dirs.append(Path(sp) / "ctranslate2")
    except Exception:
        pass

    added_paths = []
    for d in search_dirs:
        p = d.resolve() if hasattr(d, 'resolve') else Path(d)
        if p.exists():
            p_str = str(p)
            if hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(p_str)
                except Exception:
                    pass
            added_paths.append(p_str)

    if added_paths:
        cur_path = os.environ.get("PATH", "")
        os.environ["PATH"] = os.pathsep.join(added_paths) + os.pathsep + cur_path

    for dll_name in ("cublasLt64_12.dll", "cublas64_12.dll"):
        loaded = False
        for d in search_dirs:
            cand = Path(d) / dll_name
            if cand.is_file():
                try:
                    ctypes.CDLL(str(cand))
                    loaded = True
                    logging.info(f"Precaricata libreria CUDA: {cand}")
                    break
                except Exception as e:
                    logging.warning(f"Impossibile caricare {cand}: {e}")
        if not loaded:
            try:
                ctypes.CDLL(dll_name)
                logging.info(f"Precaricata libreria CUDA via sistema: {dll_name}")
            except Exception:
                pass

# Run CUDA preload immediately upon startup
_preload_cuda_libraries()

# ==============================================================================
# HARDWARE & MEMORY DETECTION FOR WINDOWS
# ==============================================================================
def detect_hardware():
    """
    Detects hardware capabilities using ctranslate2.
    Returns: (device, compute_type, hw_title, badge_color, badge_text)
    """
    try:
        import ctranslate2
        cuda_count = ctranslate2.get_cuda_device_count()
        if cuda_count > 0:
            return ("cuda", "float16", "NVIDIA CUDA ATTIVO", "#10b981", "⚡ NVIDIA CUDA • GPU Accelerata")
    except Exception as e:
        logging.info(f"Rilevamento CUDA non disponibile: {e}")

    return ("cpu", "int8", "CPU MULTITHREAD", "#f59e0b", "💻 Intel / AMD • CPU Multithread")

def get_vram_info():
    """Retrieves real VRAM usage on NVIDIA GPU via nvml.dll."""
    try:
        try:
            nvml = ctypes.CDLL("nvml.dll")
        except Exception:
            nvml = ctypes.CDLL(r"C:\Program Files\NVIDIA Corporation\NVSMI\nvml.dll")
        if nvml.nvmlInit_v2() != 0:
            return None
        try:
            class NVMemory(ctypes.Structure):
                _fields_ = [
                    ("total", ctypes.c_ulonglong),
                    ("free", ctypes.c_ulonglong),
                    ("used", ctypes.c_ulonglong)
                ]

            count = ctypes.c_uint(0)
            try:
                if nvml.nvmlDeviceGetCount_v2(ctypes.byref(count)) != 0 or count.value < 1:
                    count.value = 1
            except Exception:
                count.value = 1

            best_used = None
            best_total = -1
            for idx in range(count.value):
                handle = ctypes.c_void_p()
                if nvml.nvmlDeviceGetHandleByIndex_v2(idx, ctypes.byref(handle)) == 0:
                    mem = NVMemory()
                    if nvml.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(mem)) == 0 and mem.total > best_total:
                        best_total = mem.total
                        best_used = mem.used

            if best_total <= 0 or best_used is None:
                return None
            total_gb = best_total / (1024 ** 3)
            used_gb = best_used / (1024 ** 3)
            return round(used_gb, 1), round(total_gb, 1)
        finally:
            try:
                nvml.nvmlShutdown()
            except Exception:
                pass
    except Exception:
        return None

def get_system_ram_info():
    """Retrieves physical RAM status using psutil with fallback to Windows API."""
    try:
        import psutil
        vm = psutil.virtual_memory()
        return round((vm.total - vm.available) / (1024**3), 1), round(vm.total / (1024**3), 1)
    except Exception:
        pass
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ('dwLength', ctypes.c_ulong),
                ('dwMemoryLoad', ctypes.c_ulong),
                ('ullTotalPhys', ctypes.c_ulonglong),
                ('ullAvailPhys', ctypes.c_ulonglong),
                ('ullTotalPageFile', ctypes.c_ulonglong),
                ('ullAvailPageFile', ctypes.c_ulonglong),
                ('ullTotalVirtual', ctypes.c_ulonglong),
                ('ullAvailVirtual', ctypes.c_ulonglong),
                ('sullAvailExtendedVirtual', ctypes.c_ulonglong),
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        tot = stat.ullTotalPhys / (1024 ** 3)
        used = (stat.ullTotalPhys - stat.ullAvailPhys) / (1024 ** 3)
        return round(used, 1), round(tot, 1)
    except Exception:
        return 0.0, 16.0

def get_total_ram_gb():
    """Returns total installed system RAM in GB."""
    _, tot = get_system_ram_info()
    return tot

# ==============================================================================
# AUDIO / MEDIA HELPER FUNCTIONS
# ==============================================================================
def find_ffmpeg() -> str:
    """Locate bundled ffmpeg or system PATH ffmpeg if available."""
    candidates = [
        BASE_DIR / "ffmpeg.exe",
        DIR_CORRENTE / "ffmpeg.exe",
        BASE_DIR / "bin" / "ffmpeg.exe",
    ]
    for c in candidates:
        if c.is_file():
            return str(c.resolve())
    which_ff = shutil.which("ffmpeg")
    return which_ff or ""

def get_file_duration(file_path) -> float:
    """
    Retrieve audio/video duration in seconds using PyAV (standalone C bindings)
    or fallback to ffmpeg probe if available.
    """
    try:
        import av
        with av.open(str(file_path)) as container:
            if container.duration:
                return max(1.0, float(container.duration) / av.time_base)
            for stream in container.streams.audio:
                if stream.duration and stream.time_base:
                    return max(1.0, float(stream.duration * stream.time_base))
    except Exception:
        pass

    ff = find_ffmpeg()
    if ff:
        cmd = [ff, "-i", str(file_path)]
        try:
            res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, errors="replace")
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", res.stderr)
            if m:
                h, minuti, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
                return max(1.0, h * 3600 + minuti * 60 + s)
        except Exception:
            pass

    return 60.0

def format_time(seconds: float) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    s = int(round(seconds))
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def format_size(bytes_size: int) -> str:
    """Format bytes into readable units."""
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.1f} KB"
    else:
        return f"{bytes_size / (1024 * 1024):.1f} MB"

def generate_output_path(p_in: Path, fmt: str, lang: str = "it") -> Path:
    """
    Generate clean transcription output path in the source folder formatted as:
    'Trascrizione [data del file in gg-mm-aa - oo.mm].[fmt]' or 'Trascrizione [nome-pulito].[fmt]'
    """
    stem = p_in.stem
    prefix = "Trascrizione" if lang == "it" else "Transcription"

    # 1. Match YYYYMMDD_HHMM or YYYY-MM-DD HH-MM
    m1 = re.search(r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})[-_ ]+(\d{2})[-_.]?(\d{2})", stem)
    # 2. Match DD-MM-YYYY HH:MM or DD-MM-YY HH:MM (Italian/European format)
    m2 = re.search(r"(\d{2})[-_.](\d{2})[-_.](20\d{2}|\d{2})[-_ ]+(\d{2})[-_.](\d{2})", stem)

    if m1:
        anno_full, mese, giorno, ora, minuti = m1.groups()
        anno_breve = anno_full[-2:]
        nuovo_nome = f"{prefix} {giorno}-{mese}-{anno_breve} - {ora}.{minuti}.{fmt}"
    elif m2:
        giorno, mese, anno_raw, ora, minuti = m2.groups()
        anno_breve = anno_raw[-2:]
        nuovo_nome = f"{prefix} {giorno}-{mese}-{anno_breve} - {ora}.{minuti}.{fmt}"
    else:
        # Match standard recording names (e.g. 'Registratore vocale 01')
        pulito = re.sub(r"(?i)^(?:registratore|registrazione|recording)\s*[-_]?\s*", "", stem).strip(" -_")
        if not pulito:
            try:
                import datetime
                dt = datetime.datetime.fromtimestamp(p_in.stat().st_mtime)
                date_str = dt.strftime("%d-%m-%y - %H.%M")
                nuovo_nome = f"{prefix} {date_str}.{fmt}"
            except Exception:
                nuovo_nome = f"{prefix} {stem}.{fmt}"
        else:
            nuovo_nome = f"{prefix} {pulito}.{fmt}"

    candidate = p_in.with_name(nuovo_nome)
    base_out_stem = candidate.stem
    counter = 1
    while candidate.exists():
        candidate = p_in.with_name(f"{base_out_stem} ({counter}).{fmt}")
        counter += 1
    return candidate

def safe_save_transcription(p_target: Path, fmt: str, paragrafi: list, testo_completo: str) -> Path:
    """
    Safely writes transcription output to disk, protecting against Windows file locking
    (such as when the document is currently opened in Microsoft Word) by auto-incrementing.
    """
    counter = 1
    p_cur = p_target
    while True:
        try:
            if fmt == "docx":
                from docx import Document
                doc = Document()
                doc.add_heading(p_cur.stem, level=1)
                for par in paragrafi:
                    doc.add_paragraph(par)
                doc.save(str(p_cur))
            else:
                p_cur.write_text(testo_completo, encoding="utf-8")
            return p_cur
        except (PermissionError, OSError) as e:
            logging.warning(f"File {p_cur} bloccato o inaccessibile ({e}), incremento contatore...")
            p_cur = p_target.with_name(f"{p_target.stem} ({counter}).{fmt}")
            counter += 1
            if counter > 50:
                p_cur = p_target.with_name(f"{p_target.stem}_{int(time.time())}.{fmt}")
                if fmt == "docx":
                    from docx import Document
                    doc = Document()
                    doc.add_heading(p_cur.stem, level=1)
                    for par in paragrafi:
                        doc.add_paragraph(par)
                    doc.save(str(p_cur))
                else:
                    p_cur.write_text(testo_completo, encoding="utf-8")
                return p_cur

def play_completion_alert():
    """Play a pleasant notification chime on Windows."""
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_OK)
    except Exception:
        pass

def open_directory_in_explorer(path_str: str):
    """Open folder in Windows Explorer."""
    try:
        p = Path(path_str)
        if p.is_file():
            p = p.parent
        if p.exists():
            os.startfile(str(p))
    except Exception:
        try:
            subprocess.run(["explorer", str(path_str)], check=False)
        except Exception:
            pass

def prune_log_file(path: Path, max_entries: int = 500):
    """Keep log file lightweight and bounded."""
    try:
        if not path.is_file():
            return
        righe = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(righe) > max_entries:
            path.write_text("\n".join(righe[-max_entries:]), encoding="utf-8")
    except Exception:
        pass

def detect_system_language() -> str:
    """Detect Windows system language; returns 'it' or 'en'."""
    try:
        ui_langs = QLocale.system().uiLanguages()
        if ui_langs:
            first = ui_langs[0].lower()
            if first.startswith("it"):
                return "it"
            elif first.startswith("en"):
                return "en"
    except Exception:
        pass

    try:
        loc = QLocale.system().name().lower()
        if loc.startswith("it"):
            return "it"
    except Exception:
        pass

    return "en"

# ==============================================================================
# BILINGUAL LOCALIZATION DICTIONARY (IT & EN)
# ==============================================================================
STRINGS = {
    "it": {
        "win_title": "Whisper Studio v2.7.5",
        "sub_edition": "Versione 2.7.5",
        "hw_label_cuda": "⚡ NVIDIA CUDA • GPU Accelerata",
        "hw_label_cpu": "💻 Intel / AMD • CPU Multithread",
        "mem_vram_label": "🧠 VRAM GPU: {used:.1f} GB / {total:.0f} GB in uso",
        "mem_ram_label": "🧠 Memoria RAM: {used:.1f} GB / {total:.0f} GB in uso",
        "section_model": "MODELLO DI TRASCRIZIONE",
        "auto_tag": "🤖 Modalità Automatica Attiva",
        "model_large_title": "💎 Alta Fedeltà (Large-v3 Standard)",
        "model_turbo_title": "⚡ Alta Velocità (Turbo)",
        "auto_desc_large_gpu": "Rilevata GPU NVIDIA • Massima accuratezza GPU",
        "auto_desc_turbo_gpu": "Rilevata GPU NVIDIA • Velocità e VRAM ottimizzate",
        "auto_desc_large_cpu": "GPU NVIDIA non rilevata • Massima accuratezza CPU",
        "auto_desc_turbo_cpu": "GPU NVIDIA non rilevata • Velocità e memoria ottimizzate",
        "btn_switch_manual": "⚙️ Passa a Selezione Manuale",
        "manual_tag": "⚙️ Selezione Manuale",
        "btn_large": "💎 Alta Fedeltà\nLarge-v3 Standard (Accuratezza)",
        "btn_small": "⚡ Alta Velocità\nTurbo (Super Rapido)",
        "btn_return_auto": "🔄 Ripristina Modalità Automatica",
        "warn_large_low_spec": "⚠️ Attenzione: GPU NVIDIA non rilevata. Large-v3 Standard potrebbe rallentare l'elaborazione sulla CPU.",
        "warn_turbo_low_spec": "⚡ Consigliato per il tuo PC (GPU NVIDIA non rilevata): il modello Turbo è fluido e velocissimo.",
        "warn_large_high_spec": "💎 Consigliato per il tuo PC (GPU NVIDIA): massima precisione e fedeltà.",
        "warn_turbo_high_spec": "⚠️ Attenzione: la modalità Turbo è velocissima ma leggermente meno accurata rispetto a Large-v3.",
        "section_lang": "LINGUA AUDIO",
        "btn_lang_primary": "🇮🇹 Italiano",
        "btn_lang_auto": "🌐 Rileva Auto",
        "lang_subtitle": "Riconoscimento accenti e punteggiatura naturale",
        "section_formats": "FORMATI DI ESPORTAZIONE",
        "chk_txt": "File di Testo (.txt)",
        "chk_docx": "Documento Word (.docx)",
        "formats_subtitle": "Salvataggio automatico con data nella stessa cartella.",
        "footer": "🔒 100% Offline • Nessun dato inviato online",
        "queue_title": "<b>Coda Trascrizioni</b> <span style='color:#818cf8;'>({count})</span>",
        "btn_add": "➕ Aggiungi File",
        "btn_clear": "🗑 Svuota Coda",
        "empty_title": "<b>Trascina qui i tuoi file audio o video</b>",
        "empty_subtitle": "oppure clicca su '➕ Aggiungi File' in alto\nSupporta MP3, M4A, WAV, MP4, MOV, MKV, FLAC, OPUS...",
        "status_ready": "Pronto. Trascina i file nella coda o clicca su '➕ Aggiungi File'.",
        "status_loading_model": "⏳ Caricamento modello in corso: attendere...",
        "status_downloading": "⏳ Download del modello AI in corso da Hugging Face...",
        "status_paused": "⏸ Trascrizione in pausa.",
        "status_resumed": "▶ Trascrizione ripresa.",
        "status_cancelling": "Arresto in corso • Liberazione memoria...",
        "btn_cancel": "■ ANNULLA",
        "btn_pause": "⏸ PAUSA",
        "btn_resume": "▶ RIPRENDI",
        "btn_start": "🚀 AVVIA TRASCRIZIONE",
        "card_waiting": "⏸ In attesa",
        "card_completed": "✅ Completato",
        "card_error": "❌ Errore",
        "card_done": "Pronto",
        "card_failed": "Fallito",
        "card_elapsed": "⏱️ {elapsed} trascorsi • ~{rem}",
        "dlg_empty_title": "Coda vuota",
        "dlg_empty_msg": "Aggiungi almeno un file audio o video da trascrivere.",
        "dlg_formats_title": "Formati",
        "dlg_formats_msg": "Seleziona almeno un formato di output (.txt o .docx).",
        "dlg_clear_title": "Attenzione",
        "dlg_clear_msg": "Impossibile svuotare la coda durante l'elaborazione.",
        "dlg_manual_title": "Passaggio a Selezione Manuale",
        "dlg_manual_header": "⚠️ Passaggio alla Modalità Manuale",
        "dlg_manual_msg": "La modalità automatica è configurata per sfruttare al massimo l'hardware del tuo PC.<br><br>In modalità manuale, la selezione di un modello non adatto potrebbe <b>ridurre l'accuratezza della trascrizione</b> o <b>rallentare notevolmente l'elaborazione</b>.<br><br>Vuoi procedere comunque con la selezione manuale?",
        "dlg_manual_cancel": "Annulla",
        "dlg_manual_confirm": "Passa a Manuale",
        "file_dialog_title": "Seleziona file audio o video da trascrivere",
        "file_dialog_filter": "File Multimediali (*.mp3 *.m4a *.wav *.mp4 *.mov *.mkv *.aac *.ogg *.webm *.flac *.opus *.alac *.wma);;Tutti i file (*.*)",
        "menu_language": "Lingua",
        "menu_help": "Aiuto",
        "menu_guide": "Guida di Whisper Studio",
        "menu_open_logs": "Apri Cartella Log",
        "menu_about": "Informazioni su Whisper Studio",
        "help_title": "Guida & Istruzioni — Whisper Studio v2.7.5 (Windows)",
        "help_close": "Chiudi",
        "notif_completed": "Trascrizione completata ({count} file)!",
        "progress_total": "Avanzamento Totale: {perc}% (File {curr} di {total}) | ⏱️ {elapsed} trascorsi • rimasti ~{rem}",
        "finished_msg": "✨ Trascrizione completata: {count} file elaborati con successo • Memoria liberata.",
        "cancelled_msg": "Operazione interrotta • Memoria RAM e VRAM liberate.",
        "about_title": "Informazioni — Whisper Studio",
        "about_text": "<b>Whisper Studio — Edizione Windows v2.7.5</b><br><br>"
                      "Sviluppato con interfaccia grafica moderna PyQt6 e motore Faster-Whisper.<br>"
                      "Ottimizzato per GPU NVIDIA (CUDA) e CPU Intel/AMD.<br><br>"
                      "<i>100% Offline • Riservatezza Totale • Nessun dato inviato online.</i>"
    },
    "en": {
        "win_title": "Whisper Studio v2.7.5",
        "sub_edition": "Version 2.7.5",
        "hw_label_cuda": "⚡ NVIDIA CUDA • GPU Accelerated",
        "hw_label_cpu": "💻 Intel / AMD • CPU Multithread",
        "mem_vram_label": "🧠 GPU VRAM: {used:.1f} GB / {total:.0f} GB in use",
        "mem_ram_label": "🧠 System RAM: {used:.1f} GB / {total:.0f} GB in use",
        "section_model": "TRANSCRIPTION MODEL",
        "auto_tag": "🤖 Automatic Mode Active",
        "model_large_title": "💎 High Fidelity (Large-v3 Standard)",
        "model_turbo_title": "⚡ High Speed (Turbo)",
        "auto_desc_large_gpu": "NVIDIA GPU detected • Maximum GPU accuracy",
        "auto_desc_turbo_gpu": "NVIDIA GPU detected • Optimized speed and VRAM",
        "auto_desc_large_cpu": "No NVIDIA GPU detected • Maximum CPU accuracy",
        "auto_desc_turbo_cpu": "No NVIDIA GPU detected • Optimized speed and memory",
        "btn_switch_manual": "⚙️ Switch to Manual Selection",
        "manual_tag": "⚙️ Manual Selection",
        "btn_large": "💎 High Fidelity\nLarge-v3 Standard (Accuracy)",
        "btn_small": "⚡ High Speed\nTurbo (Super Fast)",
        "btn_return_auto": "🔄 Restore Automatic Mode",
        "warn_large_low_spec": "⚠️ Warning: No NVIDIA GPU detected. Large-v3 Standard may slow down processing on CPU.",
        "warn_turbo_low_spec": "⚡ Recommended for your PC (no NVIDIA GPU): Turbo model is fluid and lightning-fast.",
        "warn_large_high_spec": "💎 Recommended for your PC (NVIDIA GPU): maximum precision and fidelity.",
        "warn_turbo_high_spec": "⚠️ Note: Turbo mode is very fast but slightly less accurate than Large-v3.",
        "section_lang": "AUDIO LANGUAGE",
        "btn_lang_primary": "🇬🇧 English",
        "btn_lang_auto": "🌐 Auto Detect",
        "lang_subtitle": "Natural accents and punctuation recognition",
        "section_formats": "EXPORT FORMATS",
        "chk_txt": "Text File (.txt)",
        "chk_docx": "Word Document (.docx)",
        "formats_subtitle": "Automatically saved next to source audio files.",
        "footer": "🔒 100% Offline • No data sent online",
        "queue_title": "<b>Transcription Queue</b> <span style='color:#818cf8;'>({count})</span>",
        "btn_add": "➕ Add Files",
        "btn_clear": "🗑 Clear Queue",
        "empty_title": "<b>Drag and drop your audio or video files here</b>",
        "empty_subtitle": "or click '➕ Add Files' above\nSupports MP3, M4A, WAV, MP4, MOV, MKV, FLAC, OPUS...",
        "status_ready": "Ready. Drag files into queue or click '➕ Add Files'.",
        "status_loading_model": "⏳ Loading model: please wait...",
        "status_downloading": "⏳ Downloading AI model from Hugging Face...",
        "status_paused": "⏸ Transcription paused.",
        "status_resumed": "▶ Transcription resumed.",
        "status_cancelling": "Stopping transcription • Releasing memory...",
        "btn_cancel": "■ CANCEL",
        "btn_pause": "⏸ PAUSE",
        "btn_resume": "▶ RESUME",
        "btn_start": "🚀 START TRANSCRIPTION",
        "card_waiting": "⏸ Waiting",
        "card_completed": "✅ Completed",
        "card_error": "❌ Error",
        "card_done": "Done",
        "card_failed": "Failed",
        "card_elapsed": "⏱️ {elapsed} elapsed • ~{rem}",
        "dlg_empty_title": "Empty Queue",
        "dlg_empty_msg": "Please add at least one audio or video file to transcribe.",
        "dlg_formats_title": "Formats",
        "dlg_formats_msg": "Please select at least one output format (.txt or .docx).",
        "dlg_clear_title": "Warning",
        "dlg_clear_msg": "Cannot clear queue during active transcription.",
        "dlg_manual_title": "Switch to Manual Selection",
        "dlg_manual_header": "⚠️ Switch to Manual Selection",
        "dlg_manual_msg": "Automatic mode is configured to take full advantage of your PC's hardware.<br><br>In manual mode, selecting an unsuitable model could <b>reduce transcription accuracy</b> or <b>significantly slow down processing</b>.<br><br>Do you want to proceed with manual selection?",
        "dlg_manual_cancel": "Cancel",
        "dlg_manual_confirm": "Switch to Manual",
        "file_dialog_title": "Select audio or video files to transcribe",
        "file_dialog_filter": "Media Files (*.mp3 *.m4a *.wav *.mp4 *.mov *.mkv *.aac *.ogg *.webm *.flac *.opus *.alac *.wma);;All Files (*.*)",
        "menu_language": "Language",
        "menu_help": "Help",
        "menu_guide": "Whisper Studio Guide",
        "menu_open_logs": "Open Log Folder",
        "menu_about": "About Whisper Studio",
        "help_title": "User Guide — Whisper Studio v2.7.5 (Windows)",
        "help_close": "Close",
        "notif_completed": "Transcription completed ({count} files)!",
        "progress_total": "Total Progress: {perc}% (File {curr} of {total}) | ⏱️ {elapsed} elapsed • ~{rem} remaining",
        "finished_msg": "✨ Transcription completed: {count} files processed successfully • Memory reclaimed.",
        "cancelled_msg": "Operation cancelled • RAM and VRAM reclaimed.",
        "about_title": "About — Whisper Studio",
        "about_text": "<b>Whisper Studio — Windows Edition v2.7.5</b><br><br>"
                      "Built with a sleek PyQt6 modern dark interface and the Faster-Whisper neural engine.<br>"
                      "Optimized for NVIDIA GPUs (CUDA) and Intel/AMD CPUs.<br><br>"
                      "<i>100% Offline • Zero Telemetry • Completely Private.</i>"
    }
}

# ==============================================================================
# WINDOWS EMOJI FLAG RENDERING (ITALIAN 🇮🇹 & ENGLISH 🇬🇧)
# ==============================================================================
def create_flag_icon(lang: str) -> QIcon:
    """
    Generates a multi-resolution, high-DPI rounded emoji-style flag QIcon for Italian ('it')
    and English ('en'). Windows Segoe UI Emoji does not include country flag glyphs for
    regional indicator pairs, so we provide crisp antialiased vector-painted flag icons
    across all standard 1x-3x DPI sizes alongside the emoji text.
    """
    icon = QIcon()
    for w, h in ((16, 12), (20, 14), (24, 17), (32, 24), (40, 28), (48, 34), (64, 45)):
        pix = QPixmap(w, h)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        pad = 0.5
        rw = float(w) - 2.0 * pad
        rh = float(h) - 2.0 * pad
        radius = max(2.2, min(rw, rh) * 0.20)

        path = QPainterPath()
        path.addRoundedRect(QRectF(pad, pad, rw, rh), radius, radius)
        p.setClipPath(path)

        if lang == "it":
            sw = rw / 3.0
            p.fillRect(QRectF(pad, pad, sw + 0.3, rh), QColor("#009246"))
            p.fillRect(QRectF(pad + sw, pad, sw + 0.3, rh), QColor("#ffffff"))
            p.fillRect(QRectF(pad + 2.0 * sw, pad, rw - 2.0 * sw, rh), QColor("#ce2b37"))
        else:
            p.fillRect(QRectF(pad, pad, rw, rh), QColor("#012169"))
            diag_w = max(2.2, rh * 0.20)
            diag_r = max(1.1, rh * 0.10)
            p.setPen(QPen(QColor("#ffffff"), diag_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            p.drawLine(QRectF(pad, pad, rw, rh).topLeft(), QRectF(pad, pad, rw, rh).bottomRight())
            p.drawLine(QRectF(pad, pad, rw, rh).bottomLeft(), QRectF(pad, pad, rw, rh).topRight())
            p.setPen(QPen(QColor("#C8102E"), diag_r, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            p.drawLine(QRectF(pad, pad, rw, rh).topLeft(), QRectF(pad, pad, rw, rh).bottomRight())
            p.drawLine(QRectF(pad, pad, rw, rh).bottomLeft(), QRectF(pad, pad, rw, rh).topRight())

            cw_w = max(3.4, rh * 0.32)
            cw_r = max(2.0, rh * 0.19)
            cx = pad + rw / 2.0
            cy = pad + rh / 2.0
            p.fillRect(QRectF(pad, cy - cw_w / 2.0, rw, cw_w), QColor("#ffffff"))
            p.fillRect(QRectF(cx - cw_w / 2.0, pad, cw_w, rh), QColor("#ffffff"))
            p.fillRect(QRectF(pad, cy - cw_r / 2.0, rw, cw_r), QColor("#C8102E"))
            p.fillRect(QRectF(cx - cw_r / 2.0, pad, cw_r, rh), QColor("#C8102E"))

        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 70), max(0.75, rh * 0.04)))
        p.drawPath(path)
        p.end()

        for mode in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Selected):
            icon.addPixmap(pix, mode, QIcon.State.Off)
            icon.addPixmap(pix, mode, QIcon.State.On)
    return icon


class FlagButton(QPushButton):
    """
    QPushButton that preserves the Unicode flag emoji in .text() while painting
    the crisp emoji flag QIcon without Windows' fallback 'IT'/'GB'/'US' two-letter text.
    """
    def initStyleOption(self, option):
        super().initStyleOption(option)
        if not option.icon.isNull():
            option.text = re.sub(r"[\U0001F1E6-\U0001F1FF]+\s*", "", option.text)


class FlagMenu(QMenu):
    """
    QMenu that preserves Unicode flag emojis in QAction.text() while painting
    the crisp emoji flag QIcon and active checkmark without Windows' fallback 'IT'/'GB'/'US' letters.
    """
    def initStyleOption(self, option, action):
        super().initStyleOption(option, action)
        if not option.icon.isNull():
            clean_txt = re.sub(r"[\U0001F1E6-\U0001F1FF]+\s*", "", option.text)
            if action.isChecked():
                clean_txt = f"{clean_txt}   ✓"
            option.text = clean_txt


# ==============================================================================
# HUGGING FACE / LOCAL MODEL CACHE MANAGER & SAFE DIRECT STREAMING DOWNLOADER
# ==============================================================================
def is_model_dir_complete(p: Path) -> bool:
    """
    Verifica se la cartella contiene un modello faster-whisper/CTranslate2
    effettivamente presente, completo e integro su disco locale.
    Controlla config.json, tokenizer.json (indispensabile per esecuzione 100% offline),
    vocabolario (vocabulary.json o vocabulary.txt) e file dei pesi (> 10 MB per escludere
    file parziali, stub o download incompleti, analogamente alla versione macOS).
    """
    try:
        if not p.is_dir():
            return False

        cfg = p / "config.json"
        if not cfg.is_file() or cfg.stat().st_size == 0:
            return False

        # faster-whisper richiede tokenizer.json per non effettuare fallback online su openai/whisper-tiny
        tok = p / "tokenizer.json"
        if not tok.is_file() or tok.stat().st_size == 0:
            return False

        # ctranslate2 richiede vocabulary.json o vocabulary.txt
        has_vocab = any(
            (p / v).is_file() and (p / v).stat().st_size > 0
            for v in ("vocabulary.json", "vocabulary.txt")
        )
        if not has_vocab:
            return False

        # Verifica file dei pesi: model.bin o safetensors/npz (> 10 MB come su macOS)
        for w in ("model.bin", "model.safetensors", "weights.safetensors", "weights.npz"):
            wf = p / w
            if wf.is_file() and wf.stat().st_size > 10_000_000:
                return True
    except Exception:
        pass
    return False


def find_local_model_path(model_id: str) -> str:
    """Check if complete and valid model exists in local models/ or HF cache."""
    # Check if model_id is already a valid local directory
    try:
        p_direct = Path(model_id)
        if p_direct.is_dir() and is_model_dir_complete(p_direct):
            return str(p_direct.resolve())
    except Exception:
        pass

    candidates = []

    if model_id in ("turbo", "large-v3-turbo"):
        folder_names = [
            "faster-whisper-large-v3-turbo",
            "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo",
            "models--deepdml--faster-whisper-large-v3-turbo",
            "models--Systran--faster-whisper-large-v3-turbo",
            "turbo"
        ]
    else:
        folder_names = [
            f"faster-whisper-{model_id}",
            f"models--Systran--faster-whisper-{model_id}",
            f"models--{model_id}",
            model_id
        ]

    for base in [BASE_DIR / "models", DIR_CORRENTE / "models"]:
        for fn in folder_names:
            candidates.append(base / fn)

    try:
        hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
        if hf_cache.is_dir():
            for fn in folder_names:
                candidates.append(hf_cache / fn)
    except Exception:
        pass

    for c in candidates:
        if is_model_dir_complete(c):
            return str(c.resolve())

        # Check refs/main to resolve the active commit snapshot directly
        ref_main = c / "refs" / "main"
        if ref_main.is_file():
            try:
                commit_hash = ref_main.read_text(encoding="utf-8").strip()
                snap = c / "snapshots" / commit_hash
                if is_model_dir_complete(snap):
                    return str(snap.resolve())
            except Exception:
                pass

        # Check all snapshots subdirectories
        snap_dir = c / "snapshots"
        if snap_dir.is_dir():
            try:
                for snap in snap_dir.iterdir():
                    if is_model_dir_complete(snap):
                        return str(snap.resolve())
            except Exception:
                pass

    # Direct check via huggingface_hub snapshot_download (local_files_only=True)
    try:
        from huggingface_hub import snapshot_download
        hf_repos = []
        if model_id in ("turbo", "large-v3-turbo"):
            hf_repos = [
                "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
                "deepdml/faster-whisper-large-v3-turbo",
                "Systran/faster-whisper-large-v3-turbo"
            ]
        elif "/" in model_id:
            hf_repos = [model_id]
        elif model_id.startswith("faster-whisper-"):
            hf_repos = [f"Systran/{model_id}"]
        else:
            hf_repos = [f"Systran/faster-whisper-{model_id}", f"Systran/{model_id}"]

        for repo in hf_repos:
            try:
                local_dir = snapshot_download(repo_id=repo, local_files_only=True)
                if local_dir and is_model_dir_complete(Path(local_dir)):
                    return str(Path(local_dir).resolve())
            except Exception:
                pass
    except Exception:
        pass

    return ""


def download_model_safely(model_name: str, callback_progresso=None, is_aborted=None, lang: str = "it") -> str:
    """
    Downloads model directly from HuggingFace using standard urllib with Range resume support,
    without symlinks, hardlinks, file locks, or ctypes Win32 calls.
    Writes files directly into BASE_DIR / 'models' / folder_slug.
    """
    import urllib.request
    import json
    import time
    import socket

    socket.setdefaulttimeout(300)
    os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "300"
    os.environ["HF_HUB_ETAG_TIMEOUT"] = "60"

    WEIGHT_FILE_NAMES = ("model.bin", "model.safetensors", "weights.safetensors", "weights.npz")

    if model_name in ("turbo", "large-v3-turbo"):
        repo_id = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
        folder_slug = "faster-whisper-large-v3-turbo"
    elif "/" in model_name:
        repo_id = model_name
        folder_slug = model_name.split("/")[-1]
    elif model_name.startswith("faster-whisper-"):
        repo_id = f"Systran/{model_name}"
        folder_slug = model_name
    else:
        repo_id = f"Systran/faster-whisper-{model_name}"
        folder_slug = f"faster-whisper-{model_name}"

    dest_dir = BASE_DIR / "models" / folder_slug
    dest_dir.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": "WhisperStudio/2.7.5 (Windows NT 10.0; Win64; x64)"
    }

    # Phase 1: Notify initialization
    msg_init = "Inizializzazione download modello..." if lang == "it" else "Initializing model download..."
    if callback_progresso:
        callback_progresso(0.0, msg_init)

    if is_aborted and is_aborted():
        return ""

    # Fetch file list and sizes from HF tree API
    files_to_download = []
    tree_url = f"https://huggingface.co/api/models/{repo_id}/tree/main"
    try:
        req = urllib.request.Request(tree_url, headers=headers)
        with urllib.request.urlopen(req, timeout=300) as resp:
            items = json.loads(resp.read().decode("utf-8"))
            for it in items:
                fname = it.get("path", "")
                raw_size = it.get("size")
                if not raw_size and isinstance(it.get("lfs"), dict):
                    raw_size = it["lfs"].get("size", 0)
                size = int(raw_size) if raw_size else 0
                if fname in ("config.json", "tokenizer.json", "vocabulary.json", "vocabulary.txt", "preprocessor_config.json") or fname in WEIGHT_FILE_NAMES:
                    files_to_download.append((fname, size))
    except Exception as e:
        logging.warning(f"Impossibile ottenere tree metadata da HF ({e}), utilizzo fallback lista file...")

    if not files_to_download:
        default_files = ["config.json", "preprocessor_config.json", "tokenizer.json", "vocabulary.json", "model.bin"]
        for df in default_files:
            files_to_download.append((df, 0))

    # Small metadata files first, weight files last
    files_to_download.sort(key=lambda x: 1 if x[0] in WEIGHT_FILE_NAMES else 0)

    total_bytes_expected = sum(size for _, size in files_to_download if size > 0)
    total_downloaded_bytes = 0
    network_bytes_session = 0
    t_start = time.time()
    last_ui_update = 0.0
    last_speed_calc_time = t_start
    last_speed_calc_bytes = 0
    smoothed_speed_bps = 0.0

    for fname, expected_size in files_to_download:
        if is_aborted and is_aborted():
            return ""

        file_dest = dest_dir / fname
        part_dest = dest_dir / f"{fname}.part"

        # Check if already completely downloaded
        if file_dest.is_file() and file_dest.stat().st_size > 0:
            actual_file_size = file_dest.stat().st_size
            is_valid_existing = False
            if expected_size > 0 and actual_file_size == expected_size:
                is_valid_existing = True
            elif expected_size == 0:
                if fname in WEIGHT_FILE_NAMES and actual_file_size > 10_000_000:
                    is_valid_existing = True
                elif fname not in WEIGHT_FILE_NAMES:
                    is_valid_existing = True

            if is_valid_existing:
                total_downloaded_bytes += actual_file_size
                if expected_size == 0:
                    total_bytes_expected += actual_file_size
                continue

        # Prepare HTTP request with Range header if resuming .part file
        file_url = f"https://huggingface.co/{repo_id}/resolve/main/{fname}"
        part_offset = 0
        if part_dest.is_file():
            current_part_size = part_dest.stat().st_size
            if expected_size > 0 and 0 < current_part_size < expected_size:
                part_offset = current_part_size
            elif expected_size == 0 and current_part_size > 0:
                part_offset = current_part_size

        req_headers = dict(headers)
        if part_offset > 0:
            req_headers["Range"] = f"bytes={part_offset}-"
            total_downloaded_bytes += part_offset

        try:
            req = urllib.request.Request(file_url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=300) as resp:
                is_resumed = (resp.status == 206)
                if part_offset > 0 and not is_resumed:
                    # Server did not honor Range, rollback downloaded bytes counter
                    total_downloaded_bytes -= part_offset
                    part_offset = 0

                remote_len_hdr = resp.headers.get("Content-Length")
                if remote_len_hdr:
                    segment_len = int(remote_len_hdr)
                    real_file_size = (part_offset + segment_len) if is_resumed else segment_len
                else:
                    real_file_size = expected_size

                if expected_size == 0 and real_file_size > 0:
                    total_bytes_expected += real_file_size

                chunk_size = 128 * 1024  # 128 KB chunks
                file_mode = "ab" if (part_offset > 0 and is_resumed) else "wb"

                with open(part_dest, file_mode) as out_f:
                    while True:
                        if is_aborted and is_aborted():
                            out_f.close()
                            # Do NOT delete part_dest on user abort so it can resume cleanly
                            return ""

                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        out_f.write(chunk)
                        chunk_len = len(chunk)
                        total_downloaded_bytes += chunk_len
                        network_bytes_session += chunk_len

                        now = time.time()
                        if now - last_ui_update >= 0.2:  # Update UI every 200ms
                            last_ui_update = now
                            dt = now - last_speed_calc_time
                            if dt >= 0.4:
                                bytes_diff = network_bytes_session - last_speed_calc_bytes
                                inst_speed = bytes_diff / dt
                                if smoothed_speed_bps <= 0.0:
                                    smoothed_speed_bps = inst_speed
                                else:
                                    smoothed_speed_bps = 0.4 * inst_speed + 0.6 * smoothed_speed_bps
                                last_speed_calc_time = now
                                last_speed_calc_bytes = network_bytes_session
                            elif smoothed_speed_bps <= 0.0:
                                elapsed_tot = max(0.001, now - t_start)
                                smoothed_speed_bps = network_bytes_session / elapsed_tot

                            speed_mb_s = smoothed_speed_bps / (1024 * 1024)
                            speed_mbps = speed_mb_s * 8.0

                            if total_bytes_expected > 0:
                                perc = min(99.0, (total_downloaded_bytes / total_bytes_expected) * 100.0)
                                cur_mb = total_downloaded_bytes / (1024 * 1024)
                                tot_mb = total_bytes_expected / (1024 * 1024)
                                if lang == "it":
                                    msg = f"Download modello: {int(perc)}% • {speed_mbps:.1f} Mbps ({speed_mb_s:.1f} MB/s) • {cur_mb:.0f}/{tot_mb:.0f} MB"
                                else:
                                    msg = f"Downloading model: {int(perc)}% • {speed_mbps:.1f} Mbps ({speed_mb_s:.1f} MB/s) • {cur_mb:.0f}/{tot_mb:.0f} MB"
                            else:
                                cur_mb = total_downloaded_bytes / (1024 * 1024)
                                perc = 50.0
                                if lang == "it":
                                    msg = f"Download modello in corso • {speed_mbps:.1f} Mbps ({speed_mb_s:.1f} MB/s) • {cur_mb:.0f} MB"
                                else:
                                    msg = f"Downloading model • {speed_mbps:.1f} Mbps ({speed_mb_s:.1f} MB/s) • {cur_mb:.0f} MB"

                            if callback_progresso:
                                callback_progresso(perc / 100.0, msg)

                if part_dest.is_file():
                    part_dest.replace(file_dest)

        except urllib.error.HTTPError as he:
            if he.code == 404 and fname in ("preprocessor_config.json", "vocabulary.txt", "vocabulary.json"):
                try:
                    if part_dest.is_file():
                        part_dest.unlink(missing_ok=True)
                except Exception:
                    pass
                continue
            elif he.code == 416 and part_dest.is_file():
                # Range not satisfiable (e.g. part_dest is already complete)
                try:
                    part_dest.replace(file_dest)
                except Exception:
                    pass
                continue
            else:
                raise he
        except Exception as e:
            try:
                if part_dest.is_file() and part_dest.stat().st_size == 0:
                    part_dest.unlink(missing_ok=True)
            except Exception:
                pass
            raise e

    if not is_model_dir_complete(dest_dir):
        raise RuntimeError(f"Download incompleto o file dei pesi non validi in {dest_dir}")

    msg_done = "Caricamento modello in memoria..." if lang == "it" else "Loading model into memory..."
    if callback_progresso:
        callback_progresso(1.0, msg_done)

    return str(dest_dir.resolve())


def check_or_download_model(model_name: str, callback_progresso=None, is_aborted=None, lang: str = "it") -> str:
    """
    Validates model availability. If absent or incomplete, downloads model files directly and safely
    via standard HTTPS streaming with Range resume into models/ without symlinks, locks, or exploit-like calls.
    Returns the absolute path to the local model directory, or empty string on abort.
    """
    local = find_local_model_path(model_name)
    if local and is_model_dir_complete(Path(local)):
        return local

    downloaded = download_model_safely(model_name, callback_progresso=callback_progresso, is_aborted=is_aborted, lang=lang)
    if downloaded and is_model_dir_complete(Path(downloaded)):
        return downloaded

    local_check = find_local_model_path(model_name)
    if local_check and is_model_dir_complete(Path(local_check)):
        return local_check

    return downloaded

# ==============================================================================
# QSS STYLESHEET (EXACT PIXEL-PERFECT DARK THEME MATCHING MACOS)
# ==============================================================================
QSS_STILE = """
QMainWindow {
    background-color: #121214;
}
QWidget {
    color: #e4e4e7;
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "SF Pro Display", Roboto, Helvetica, Arial, sans-serif;
    font-size: 13px;
}
QMenuBar {
    background-color: #18181b;
    color: #e4e4e7;
    border-bottom: 1px solid #27272a;
    padding: 2px 6px;
}
QMenuBar::item {
    background: transparent;
    padding: 4px 10px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background-color: #27272a;
    color: #ffffff;
}
QMenu {
    background-color: #1c1c1f;
    color: #e4e4e7;
    border: 1px solid #27272a;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 20px 6px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #2e2a52;
    color: #ffffff;
}
QFrame#sidebarFrame {
    background-color: #18181b;
    border-radius: 14px;
    border: 1px solid #27272a;
}
QFrame#rightPanel {
    background-color: #161618;
    border-radius: 14px;
    border: 1px solid #27272a;
}

/* Schede della coda per stato */
QFrame#cardInAttesa {
    background-color: #1f1f23;
    border-radius: 11px;
    border: 1px solid #323238;
}
QFrame#cardInCorso {
    background-color: #27233d;
    border-radius: 11px;
    border: 2px solid #818cf8;
}
QFrame#cardCompletato {
    background-color: #17241d;
    border-radius: 11px;
    border: 1.5px solid #10b981;
}
QFrame#cardErrore {
    background-color: #271a1a;
    border-radius: 11px;
    border: 1.5px solid #ef4444;
}
QFrame#emptyCard {
    background-color: #18181c;
    border-radius: 12px;
    border: 2px dashed #3f3f46;
}

QLabel#titleLabel {
    font-size: 18px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: 0.5px;
}
QLabel#subLabel {
    font-size: 11px;
    color: #a1a1aa;
}
QLabel#sectionTitle {
    font-size: 11px;
    font-weight: 700;
    color: #a1a1aa;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* Pulsanti Toggle Modello e Lingua */
QPushButton.toggleBtn, QPushButton[class="toggleBtn"] {
    background-color: #222226;
    border: 1.5px solid #383840;
    border-radius: 9px;
    color: #ffffff;
    font-size: 12px;
    font-weight: 600;
    padding: 6px 12px;
    text-align: left;
}
QPushButton.toggleBtn:hover, QPushButton[class="toggleBtn"]:hover {
    background-color: #2a2a30;
    border-color: #52525b;
}
QPushButton.toggleBtn:checked, QPushButton[class="toggleBtn"]:checked {
    background-color: #2e2a52;
    border: 1.5px solid #818cf8;
    color: #ffffff;
}
QPushButton.toggleBtn:disabled, QPushButton[class="toggleBtn"]:disabled {
    background-color: #1a1a1d;
    border: 1.5px solid #27272a;
    color: #52525b;
}

QPushButton#btnLargeModello, QPushButton#btnSmallModello {
    background-color: #222226;
    border: 1.5px solid #383840;
    border-radius: 9px;
    color: #ffffff;
    font-size: 12px;
    font-weight: 600;
    padding: 6px 12px;
    text-align: left;
    min-height: 44px;
}
QPushButton#btnLargeModello:hover, QPushButton#btnSmallModello:hover {
    background-color: #2a2a30;
    border-color: #52525b;
}
QPushButton#btnLargeModello:checked, QPushButton#btnSmallModello:checked {
    background-color: #2e2a52;
    border: 1.5px solid #818cf8;
    color: #ffffff;
}

/* Checkbox */
QCheckBox {
    font-size: 13px;
    spacing: 8px;
    color: #e4e4e7;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1.5px solid #52525b;
    background-color: #222226;
}
QCheckBox::indicator:checked {
    background-color: #818cf8;
    border: 1.5px solid #818cf8;
}

/* Barra di Avanzamento Totale */
QProgressBar {
    background-color: #242428;
    border-radius: 6px;
    text-align: center;
    color: transparent;
    height: 12px;
    border: none;
}
QProgressBar::chunk {
    background-color: #818cf8;
    border-radius: 6px;
}

/* Pulsanti Coda e Azione */
QPushButton#btnAdd {
    background-color: #818cf8;
    color: #ffffff;
    border-radius: 8px;
    font-weight: bold;
    font-size: 13px;
    padding: 7px 14px;
    border: none;
}
QPushButton#btnAdd:hover {
    background-color: #6d78f5;
}

QPushButton#btnClear {
    background-color: #27272a;
    color: #e4e4e7;
    border-radius: 8px;
    font-weight: 600;
    font-size: 13px;
    padding: 7px 14px;
    border: 1px solid #3f3f46;
}
QPushButton#btnClear:hover {
    background-color: #ef4444;
    border: 1px solid #dc2626;
    color: #ffffff;
}

QPushButton#btnAvvia {
    background-color: #10b981;
    color: #ffffff;
    border-radius: 9px;
    font-size: 14px;
    font-weight: bold;
    border: none;
    min-height: 44px;
}
QPushButton#btnAvvia:hover {
    background-color: #059669;
}
QPushButton#btnAvvia:disabled {
    background-color: #27272a;
    color: #71717a;
}
QPushButton#btnPausa {
    background-color: #d97706;
    color: #ffffff;
    border-radius: 9px;
    font-size: 14px;
    font-weight: bold;
    border: none;
    min-height: 44px;
}
QPushButton#btnPausa:hover {
    background-color: #b45309;
}
QPushButton#btnPausa:disabled {
    background-color: #27272a;
    color: #71717a;
}
QPushButton#btnFerma {
    background-color: #ef4444;
    color: #ffffff;
    border-radius: 9px;
    font-size: 14px;
    font-weight: bold;
    border: none;
    min-height: 44px;
}
QPushButton#btnFerma:hover {
    background-color: #dc2626;
}
QPushButton#btnFerma:disabled {
    background-color: #27272a;
    color: #71717a;
}
QPushButton#cardDelBtn {
    background-color: #27272a;
    color: #a1a1aa;
    border: 1px solid #3f3f46;
    border-radius: 6px;
    font-size: 13px;
    font-weight: bold;
    padding: 0px;
}
QPushButton#cardDelBtn:hover {
    background-color: #ef4444;
    color: #ffffff;
    border-color: #dc2626;
}

QListWidget {
    background-color: transparent;
    border: none;
    outline: none;
}
QListWidget::item {
    background: transparent;
    border: none;
    padding: 0px;
}
QListWidget::item:selected {
    background: transparent;
}
"""

# ==============================================================================
# IN-PROCESS FASTER-WHISPER WORKER THREAD
# ==============================================================================
class TrascrizioneWorkerThread(QThread):
    file_avviato = pyqtSignal(int, str)
    progresso_file = pyqtSignal(int, int, float, float)  # idx, perc, trascorso, rimasto
    progresso_totale = pyqtSignal(int, str)              # perc_tot, text_tot
    file_completato = pyqtSignal(int, str)
    file_errore = pyqtSignal(int, str)
    coda_terminata = pyqtSignal(int, str)

    def __init__(self, coda_files, model_id, lingua_mode, formati, active_device, active_compute, lang="it", queue_lock=None):
        super().__init__()
        self.coda_files = coda_files
        self.model_id = model_id
        self.lingua_mode = lingua_mode
        self.formati = formati
        self.active_device = active_device
        self.active_compute = active_compute
        self.lang = lang
        self.queue_lock = queue_lock or threading.Lock()
        self.abort_requested = False
        self.is_paused = False
        self.loaded_model = None
        self.secondi_fatti_fino_a_qui = 0.0
        self.start_time_globale = 0.0
        self.paused_duration_globale = 0.0
        self.item_corrente = None
        self.ultimo_sec_att = 0.0

    def emetti_progresso_totale(self, sec_att: float = None):
        if self.start_time_globale <= 0:
            return
        with self.queue_lock:
            if sec_att is None:
                sec_att = self.ultimo_sec_att
            else:
                self.ultimo_sec_att = sec_att

            item_curr = self.item_corrente
            dur_curr = max(1.0, item_curr["durata"]) if item_curr else 0.0
            dur_attesa = sum(f["durata"] for f in self.coda_files if f.get("stato") == "in_attesa")
            durata_totale_audio = max(1.0, self.secondi_fatti_fino_a_qui + dur_curr + dur_attesa)
            sec_totali = self.secondi_fatti_fino_a_qui + min(sec_att, dur_curr)
            perc_globale = min(100, int((sec_totali / durata_totale_audio) * 100))

            tot_queue_count = max(1, len(self.coda_files))
            if item_curr in self.coda_files:
                curr_pos = self.coda_files.index(item_curr) + 1
            else:
                fatti_in_coda = sum(1 for f in self.coda_files if f.get("stato") in ("completato", "errore"))
                curr_pos = min(tot_queue_count, fatti_in_coda + 1)

        tempo_reale_globale = max(0.1, (time.time() - self.start_time_globale) - self.paused_duration_globale)
        velocita_globale = sec_totali / tempo_reale_globale
        rimasto_globale = max(0.0, (durata_totale_audio - sec_totali) / velocita_globale) if velocita_globale > 0 else 0.0

        tmpl = STRINGS[self.lang]["progress_total"]
        txt_globale = tmpl.format(
            perc=perc_globale,
            curr=curr_pos,
            total=tot_queue_count,
            elapsed=format_time(tempo_reale_globale),
            rem=format_time(rimasto_globale)
        )
        self.progresso_totale.emit(perc_globale, txt_globale)

    def run(self):
        from faster_whisper import WhisperModel
        from docx import Document
        import gc

        def cb_dl(p, txt):
            perc = int(p * 100) if isinstance(p, float) and p <= 1.0 else int(p)
            self.progresso_totale.emit(perc, txt)

        # 1. Download or verify model
        try:
            model_path_or_id = check_or_download_model(
                self.model_id,
                callback_progresso=cb_dl,
                is_aborted=lambda: self.abort_requested,
                lang=self.lang
            )
        except Exception as e_dl:
            logging.error(f"Errore download modello: {e_dl}")
            self.coda_terminata.emit(0, f"Errore download modello: {e_dl}")
            return

        if self.abort_requested or not model_path_or_id or not is_model_dir_complete(Path(model_path_or_id)):
            self.coda_terminata.emit(0, "Download annullato o modello incompleto")
            return

        # 2. Instantiate Faster-Whisper Model with GPU -> CPU Fallback
        def load_engine(dev, comp):
            return WhisperModel(
                model_path_or_id,
                device=dev,
                compute_type=comp,
                download_root=str(BASE_DIR / "models"),
                local_files_only=True
            )

        self.progresso_totale.emit(100, STRINGS[self.lang]["status_loading_model"])

        try:
            self.loaded_model = load_engine(self.active_device, self.active_compute)
        except Exception as e:
            logging.warning(f"Errore caricamento modello su {self.active_device}: {e}. Fallback su CPU int8...")
            try:
                self.loaded_model = load_engine("cpu", "int8")
                self.active_device = "cpu"
                self.active_compute = "int8"
            except Exception as e_cpu:
                logging.error(f"Errore critico caricamento modello su CPU: {e_cpu}")
                self.coda_terminata.emit(0, f"Errore caricamento modello: {e_cpu}")
                return

        start_time_globale = time.time()
        self.start_time_globale = start_time_globale
        self.paused_duration_globale = 0.0
        completati = 0
        cartella_out = ""

        try:
            while not self.abort_requested:
                with self.queue_lock:
                    target_idx = None
                    target_item = None
                    for i, it in enumerate(self.coda_files):
                        if it.get("stato") in ("in_corso", "in_attesa"):
                            target_idx = i
                            target_item = it
                            break

                    if target_item is None:
                        self.item_corrente = None
                        self.ultimo_sec_att = 0.0
                        break

                    for it in self.coda_files:
                        if it is not target_item and it.get("stato") == "in_corso":
                            it["stato"] = "in_attesa"

                    target_item["stato"] = "in_corso"
                    target_item["perc"] = 0
                    target_item["t_trasc"] = 0.0
                    target_item["t_rim"] = 0.0
                    self.item_corrente = target_item
                    self.ultimo_sec_att = 0.0
                    p_in = target_item["path"]
                    durata_file = max(1.0, target_item["durata"])
                    cartella_out = str(p_in.parent)

                self.file_avviato.emit(target_idx, str(p_in))

                lingua = None if self.lingua_mode == "auto" else self.lingua_mode
                transcribe_kwargs = {
                    "beam_size": 5,
                    "condition_on_previous_text": False,
                    "vad_filter": True,
                    "vad_parameters": dict(min_silence_duration_ms=500),
                }
                if lingua:
                    transcribe_kwargs["language"] = lingua

                file_start_time = time.time()
                file_paused_duration = 0.0

                try:
                    def execute_transcription():
                        nonlocal file_paused_duration
                        paragrafi_inner = []
                        buffer_inner = []
                        ultimo_end_inner = 0.0

                        segments, info = self.loaded_model.transcribe(str(p_in), **transcribe_kwargs)

                        for segment in segments:
                            if self.abort_requested:
                                raise InterruptedError("Trascrizione interrotta")
                            while self.is_paused:
                                t_p_start = time.time()
                                time.sleep(0.1)
                                dt_pause = time.time() - t_p_start
                                file_paused_duration += dt_pause
                                self.paused_duration_globale += dt_pause
                                if self.abort_requested:
                                    raise InterruptedError("Trascrizione interrotta")

                            t = segment.text.strip()
                            if t:
                                buffer_inner.append(t)
                                if len(buffer_inner) >= 4:
                                    paragrafi_inner.append(" ".join(buffer_inner))
                                    buffer_inner = []

                            # Timestamp Progress calculation
                            ultimo_end_inner = min(durata_file, max(ultimo_end_inner, segment.end))
                            perc_file = min(100, int((ultimo_end_inner / durata_file) * 100))
                            t_trascorso_file = max(0.1, (time.time() - file_start_time) - file_paused_duration)
                            velocita = ultimo_end_inner / t_trascorso_file
                            t_rimasto_file = max(0.0, (durata_file - ultimo_end_inner) / velocita) if velocita > 0 else 0.0

                            with self.queue_lock:
                                if target_item in self.coda_files:
                                    target_idx = self.coda_files.index(target_item)
                                target_item["perc"] = perc_file
                                target_item["t_trasc"] = t_trascorso_file
                                target_item["t_rim"] = t_rimasto_file
                                self.ultimo_sec_att = ultimo_end_inner

                            self.progresso_file.emit(target_idx, perc_file, t_trascorso_file, t_rimasto_file)
                            self.emetti_progresso_totale(ultimo_end_inner)

                        if buffer_inner:
                            paragrafi_inner.append(" ".join(buffer_inner))
                        testo_inner = "\n\n".join(paragrafi_inner)
                        return paragrafi_inner, testo_inner

                    try:
                        paragrafi, testo_completo = execute_transcription()
                    except (InterruptedError, SystemExit):
                        raise
                    except Exception as e_runtime:
                        if self.active_device == "cuda":
                            logging.warning(f"Errore runtime GPU ({e_runtime}). Fallback automatico a CPU int8...")
                            if self.loaded_model is not None:
                                try:
                                    del self.loaded_model
                                except Exception:
                                    pass
                            self.loaded_model = None
                            gc.collect()
                            self.loaded_model = load_engine("cpu", "int8")
                            self.active_device = "cpu"
                            self.active_compute = "int8"
                            file_start_time = time.time()
                            file_paused_duration = 0.0
                            paragrafi, testo_completo = execute_transcription()
                        else:
                            raise

                    # Export results with Windows lock protection
                    for fmt in self.formati:
                        p_out = generate_output_path(p_in, fmt, lang=self.lang)
                        safe_save_transcription(p_out, fmt, paragrafi, testo_completo)

                    with self.queue_lock:
                        if target_item in self.coda_files:
                            target_idx = self.coda_files.index(target_item)
                        target_item["stato"] = "completato"
                        target_item["perc"] = 100
                        self.secondi_fatti_fino_a_qui += durata_file
                        self.item_corrente = None
                        self.ultimo_sec_att = 0.0
                    completati += 1
                    self.file_completato.emit(target_idx, str(p_in))

                except InterruptedError:
                    with self.queue_lock:
                        target_item["stato"] = "in_attesa"
                        target_item["perc"] = 0
                        target_item["t_trasc"] = 0.0
                        target_item["t_rim"] = 0.0
                        self.item_corrente = None
                        self.ultimo_sec_att = 0.0
                    break
                except Exception as e:
                    import traceback
                    tb = traceback.format_exc()
                    logging.error(f"Errore elaborazione file {p_in}: {tb}")
                    prune_log_file(LOG_FILE)
                    with self.queue_lock:
                        if target_item in self.coda_files:
                            target_idx = self.coda_files.index(target_item)
                        target_item["stato"] = "errore"
                        target_item["err_dettaglio"] = str(e)
                        self.secondi_fatti_fino_a_qui += durata_file
                        self.item_corrente = None
                        self.ultimo_sec_att = 0.0
                    self.file_errore.emit(target_idx, str(e))

        finally:
            # MEMORY RECLAIM (ZERO LEAKAGE)
            logging.info("Espulsione modello AI da RAM/VRAM in corso...")
            if self.loaded_model is not None:
                try:
                    del self.loaded_model
                except Exception:
                    pass
            self.loaded_model = None
            gc.collect()
            logging.info("Modello espulso con successo. RAM e VRAM liberate.")

        if self.abort_requested:
            self.coda_terminata.emit(0, "")
        else:
            self.coda_terminata.emit(completati, cartella_out)

    def pausa(self):
        self.is_paused = True

    def riprendi(self):
        self.is_paused = False

    def ferma(self):
        self.abort_requested = True
        self.is_paused = False

# ==============================================================================
# LIVE LINEAR MEMORY GAUGE BAR (VRAM / SYSTEM RAM)
# ==============================================================================
class RAMGaugeBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(5)
        self._ratio = 0.25

    def set_ratio(self, ratio: float):
        self._ratio = max(0.05, min(1.0, float(ratio)))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = float(self.width())
        h = float(self.height())
        r = h / 2.0

        bg = QPainterPath()
        bg.addRoundedRect(0.0, 0.0, w, h, r, r)
        painter.fillPath(bg, QColor("#242428"))

        fill_w = w * self._ratio
        if fill_w > 0:
            painter.setClipPath(bg)
            fg = QPainterPath()
            fg.addRoundedRect(0.0, 0.0, fill_w, h, r, r)
            grad = QLinearGradient(0.0, 0.0, w, 0.0)
            grad.setColorAt(0.0, QColor("#10b981"))
            grad.setColorAt(1.0, QColor("#818cf8"))
            painter.fillPath(fg, grad)
        painter.end()

# ==============================================================================
# WINDOWS 11 VECTOR CHECKBOX (CRISP ANTIALIASED CHECKMARK)
# ==============================================================================
class WindowsCheckBox(QCheckBox):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hovered = False

    def hitButton(self, pos: QPoint) -> bool:
        return self.rect().contains(pos)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = float(self.width())
        h = float(self.height())
        enabled = self.isEnabled()
        checked = self.isChecked()

        box_size = 18.0
        bx = 1.0
        by = max(1.0, (h - box_size) / 2.0)
        box_rect = QRectF(bx, by, box_size, box_size)
        box_r = 5.0
        box_path = QPainterPath()
        box_path.addRoundedRect(box_rect, box_r, box_r)

        if checked:
            fill_col = QColor("#818cf8") if enabled else QColor("#3f3f5a")
            rim_col = QColor("#a5b4fc") if (enabled and self._hovered) else fill_col
            painter.fillPath(box_path, fill_col)
            painter.setPen(QPen(rim_col, 1.5))
            painter.drawPath(box_path)

            chk = QPainterPath()
            chk.moveTo(bx + 4.5, by + 9.2)
            chk.lineTo(bx + 7.6, by + 12.4)
            chk.lineTo(bx + 13.5, by + 5.8)
            chk_col = QColor("#ffffff") if enabled else QColor("#a1a1aa")
            painter.setPen(QPen(chk_col, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(chk)
        else:
            bg_col = QColor("#2a2a30") if (enabled and self._hovered) else QColor("#222226")
            rim_col = QColor("#818cf8") if (enabled and self._hovered) else (QColor("#52525b") if enabled else QColor("#323238"))
            painter.fillPath(box_path, bg_col)
            painter.setPen(QPen(rim_col, 1.5))
            painter.drawPath(box_path)

        f = QFont(self.font())
        f.setPixelSize(13)
        painter.setFont(f)
        txt_col = QColor("#ffffff") if (enabled and (checked or self._hovered)) else (QColor("#e4e4e7") if enabled else QColor("#71717a"))
        painter.setPen(txt_col)
        text_rect = QRectF(bx + box_size + 8.0, 0.0, max(10.0, w - (bx + box_size + 10.0)), h)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())
        painter.end()

# ==============================================================================
# ANIMATED ROTATING LOADING SPINNER
# ==============================================================================
class LoadingSpinner(QWidget):
    """
    A sleek rotating loading spinner widget.
    Paints smooth rotating rays using QPainter and QTimer.
    """
    def __init__(self, parent=None, size: int = 14, color: str = "#818cf8"):
        super().__init__(parent)
        self._size = size
        self._color = QColor(color)
        self._angle = 0
        self.setFixedSize(size, size)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._rotate)
        self.hide()

    def _rotate(self):
        self._angle = (self._angle + 30) % 360
        self.update()

    def start(self):
        self.show()
        if not self.timer.isActive():
            self._angle = 0
            self.timer.start(50)
        self.update()

    def stop(self):
        if self.timer.isActive():
            self.timer.stop()
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        r = (min(self.width(), self.height()) / 2.0) - 1.5

        painter.translate(cx, cy)
        painter.rotate(self._angle)

        pen = QPen()
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setWidthF(1.8)

        for i in range(8):
            alpha = int(255 * ((i + 1) / 8.0))
            col = QColor(self._color)
            col.setAlpha(alpha)
            pen.setColor(col)
            painter.setPen(pen)
            painter.drawLine(QPointF(r * 0.42, 0.0), QPointF(r, 0.0))
            painter.rotate(45.0)

        painter.end()


# ==============================================================================
# CUSTOM SMOOTH CURVED PROGRESS BAR (ANTI-GLITCH CLIPPED PILL)
# ==============================================================================
class WhisperProgressBar(QProgressBar):
    """Progress bar with continuous antialiased pill curvature."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(12)
        self.setTextVisible(False)
        self.setRange(0, 100)
        self.setValue(0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        radius = h / 2.0

        bg_path = QPainterPath()
        bg_path.addRoundedRect(0.0, 0.0, w, h, radius, radius)
        painter.fillPath(bg_path, QColor("#242428"))

        val = self.value()
        maximum = max(1, self.maximum())
        minimum = self.minimum()
        if val > minimum:
            perc = min(1.0, max(0.0, (val - minimum) / float(maximum - minimum)))
            fill_w = w * perc
            if fill_w > 0:
                painter.save()
                painter.setClipPath(bg_path)
                fill_path = QPainterPath()
                fill_path.addRoundedRect(0.0, 0.0, fill_w, h, radius, radius)
                grad = QLinearGradient(0.0, 0.0, w, 0.0)
                grad.setColorAt(0.0, QColor("#6366f1"))
                grad.setColorAt(0.6, QColor("#818cf8"))
                grad.setColorAt(1.0, QColor("#a5b4fc"))
                painter.fillPath(fill_path, grad)
                painter.restore()

        painter.setPen(QPen(QColor(255, 255, 255, 20), 1.0))
        painter.drawPath(bg_path)
        painter.end()

# ==============================================================================
# QUEUE ITEM CARD (HIGHLIGHTS, DRAG GHOST, BLUE INSERTION TARGET)
# ==============================================================================
class QueueItemCard(QFrame):
    def __init__(self, idx, file_info, on_remove_callback, lang="it"):
        super().__init__()
        self.file_info = file_info
        self.on_remove_callback = on_remove_callback
        self.idx = idx
        self.lang = lang
        self._drag_start_pos = None
        self.is_selezionato = False
        self.is_drop_target = False

        self.setFixedHeight(86)
        self._setup_ui()
        self.aggiorna_stato(file_info["stato"])

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        self.lbl_idx = QLabel(f"#{self.idx + 1}")
        self.lbl_idx.setStyleSheet("font-weight: 800; font-size: 14px; color: #818cf8; background: transparent; border: none;")
        self.lbl_idx.setFixedWidth(28)
        self.lbl_idx.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.lbl_idx, 0, Qt.AlignmentFlag.AlignVCenter)

        v_info = QVBoxLayout()
        v_info.setSpacing(4)

        self.lbl_nome = QLabel(f"<b>{self.file_info['path'].name}</b>")
        self.lbl_nome.setStyleSheet("font-size: 13px; color: #ffffff; background: transparent; border: none;")
        self.lbl_nome.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.lbl_nome.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        v_info.addWidget(self.lbl_nome)

        dur_str = format_time(self.file_info['durata'])
        peso_str = format_size(self.file_info['peso'])
        cartella_str = self.file_info['path'].parent.name
        self.lbl_dettagli = QLabel(f"⏱️ {dur_str}  •  💾 {peso_str}  •  📂 {cartella_str}/")
        self.lbl_dettagli.setStyleSheet("font-size: 11px; color: #a1a1aa; background: transparent; border: none;")
        self.lbl_dettagli.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.lbl_dettagli.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        v_info.addWidget(self.lbl_dettagli)
        layout.addLayout(v_info, 1)

        self.box_stato = QWidget()
        self.box_stato.setFixedWidth(155)
        self.box_stato.setStyleSheet("background: transparent; border: none;")
        self.box_stato.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        box_lay = QVBoxLayout(self.box_stato)
        box_lay.setContentsMargins(0, 0, 0, 0)
        box_lay.setSpacing(2)
        box_lay.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.lbl_stato_txt = QLabel(STRINGS[self.lang]["card_waiting"])
        self.lbl_stato_txt.setStyleSheet("font-size: 12px; font-weight: bold; color: #71717a; background: transparent; border: none;")
        self.lbl_stato_txt.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbl_stato_txt.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        box_lay.addWidget(self.lbl_stato_txt)

        self.lbl_stima_file = QLabel("")
        self.lbl_stima_file.setStyleSheet("font-size: 11px; color: #a1a1aa; background: transparent; border: none;")
        self.lbl_stima_file.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbl_stima_file.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        box_lay.addWidget(self.lbl_stima_file)

        layout.addWidget(self.box_stato, 0, Qt.AlignmentFlag.AlignVCenter)

        self.btn_del = QPushButton("✕")
        self.btn_del.setObjectName("cardDelBtn")
        self.btn_del.setFixedSize(28, 28)
        self.btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_del.clicked.connect(lambda: self.on_remove_callback(self.idx))
        layout.addWidget(self.btn_del, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_language(self, lang: str):
        self.lang = lang
        self.aggiorna_stato(self.file_info["stato"])

    def set_drop_target(self, attivo: bool):
        self.is_drop_target = attivo
        self._applica_stile_corrente()

    def set_selezionato(self, attivo: bool):
        self.is_selezionato = attivo
        self._applica_stile_corrente()

    def _applica_stile_corrente(self):
        if self.is_drop_target:
            self.setStyleSheet("""
                QFrame {
                    background-color: #172554;
                    border-radius: 11px;
                    border: 2px solid #3b82f6;
                }
            """)
            return

        if self.is_selezionato and self.file_info["stato"] != "in_corso":
            self.setStyleSheet("""
                QFrame {
                    background-color: #2e2a52;
                    border-radius: 11px;
                    border: 2px solid #818cf8;
                }
            """)
            return

        self.setStyleSheet("")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
            self.set_selezionato(False)
            parent_list = self.parentWidget()
            while parent_list and not isinstance(parent_list, QListWidget):
                parent_list = parent_list.parentWidget()
            if parent_list:
                parent_list.clearSelection()
                parent_list.setCurrentRow(-1)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        self.set_selezionato(False)
        parent_list = self.parentWidget()
        while parent_list and not isinstance(parent_list, QListWidget):
            parent_list = parent_list.parentWidget()
        if parent_list:
            parent_list.clearSelection()
            parent_list.setCurrentRow(-1)
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            main_win = self.window()
            is_transcribing = bool(
                hasattr(main_win, 'thread_lavoro')
                and main_win.thread_lavoro
                and main_win.thread_lavoro.isRunning()
            )
            if is_transcribing and self.file_info.get("stato") != "in_attesa":
                self._drag_start_pos = None
                self.set_selezionato(False)
                parent_list = self.parentWidget()
                while parent_list and not isinstance(parent_list, QListWidget):
                    parent_list = parent_list.parentWidget()
                if parent_list:
                    parent_list.clearSelection()
                    parent_list.setCurrentRow(-1)
                return

            if (event.pos() - self._drag_start_pos).manhattanLength() >= 8:
                self._avvia_drag(event.pos())
                self._drag_start_pos = None
                return
        super().mouseMoveEvent(event)

    def _avvia_drag(self, hotspot):
        pixmap = self.grab()
        sc_w = max(140, int(pixmap.width() * 0.45))
        sc_h = max(34, int(pixmap.height() * 0.45))
        scaled = pixmap.scaled(sc_w, sc_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

        ghost = QPixmap(scaled.size())
        ghost.fill(Qt.GlobalColor.transparent)
        painter = QPainter(ghost)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(0.85)
        painter.drawPixmap(0, 0, scaled)
        pen = QPen(QColor("#818cf8"), 2)
        painter.setPen(pen)
        painter.drawRoundedRect(1, 1, ghost.width() - 2, ghost.height() - 2, 7, 7)
        painter.end()

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setData("application/x-whisper-queue-item", str(self.idx).encode("utf-8"))
        drag.setMimeData(mime_data)
        drag.setPixmap(ghost)

        hs_x = int(hotspot.x() * (ghost.width() / max(1, pixmap.width())))
        hs_y = int(hotspot.y() * (ghost.height() / max(1, pixmap.height())))
        drag.setHotSpot(QPoint(hs_x, hs_y))

        main_win = self.window()
        drag.exec(Qt.DropAction.MoveAction)
        try:
            if hasattr(main_win, 'queue_list') and main_win.queue_list is not None:
                main_win.queue_list._rimuovi_hover_target()
                main_win.queue_list.clearSelection()
                main_win.queue_list.setCurrentRow(-1)
            if hasattr(main_win, 'card_widgets'):
                for c in main_win.card_widgets:
                    c.set_selezionato(False)
            self.set_selezionato(False)
        except RuntimeError:
            pass

    def aggiorna_stato(self, stato, perc=None, t_trasc=None, t_rim=None, err_dettaglio=None):
        self.file_info["stato"] = stato
        if perc is not None:
            self.file_info["perc"] = perc
        if t_trasc is not None:
            self.file_info["t_trasc"] = t_trasc
        if t_rim is not None:
            self.file_info["t_rim"] = t_rim
        if err_dettaglio is not None:
            self.file_info["err_dettaglio"] = err_dettaglio

        curr_perc = self.file_info.get("perc", 0)
        curr_t_trasc = self.file_info.get("t_trasc", 0.0)
        curr_t_rim = self.file_info.get("t_rim", 0.0)
        curr_err = self.file_info.get("err_dettaglio", "")

        s = STRINGS[self.lang]
        if stato == "in_corso":
            self.is_selezionato = False
            self.setObjectName("cardInCorso")
            self.lbl_stato_txt.setText(f"{curr_perc}%")
            self.lbl_stato_txt.setStyleSheet("font-size: 19px; font-weight: 800; color: #818cf8; background: transparent; border: none;")
            self.lbl_stima_file.setText(s["card_elapsed"].format(elapsed=format_time(curr_t_trasc), rem=format_time(curr_t_rim)))
            self.btn_del.setEnabled(False)
        elif stato == "completato":
            self.setObjectName("cardCompletato")
            self.lbl_stato_txt.setText(s["card_completed"])
            self.lbl_stato_txt.setStyleSheet("font-size: 12px; font-weight: bold; color: #10b981; background: transparent; border: none;")
            self.lbl_stima_file.setText(s["card_done"])
            self.btn_del.setEnabled(True)
        elif stato == "errore":
            self.setObjectName("cardErrore")
            self.lbl_stato_txt.setText(s["card_error"])
            self.lbl_stato_txt.setStyleSheet("font-size: 12px; font-weight: bold; color: #ef4444; background: transparent; border: none;")
            self.lbl_stima_file.setText(curr_err[:30] if curr_err else s["card_failed"])
            if curr_err:
                self.setToolTip(f"Errore: {curr_err}")
            self.btn_del.setEnabled(True)
        else:
            self.setObjectName("cardInAttesa")
            self.lbl_stato_txt.setText(s["card_waiting"])
            self.lbl_stato_txt.setStyleSheet("font-size: 12px; font-weight: 600; color: #71717a; background: transparent; border: none;")
            self.lbl_stima_file.setText("")
            self.btn_del.setEnabled(True)
        self._applica_stile_corrente()

# ==============================================================================
# NATIVE DRAG & DROP QUEUE LIST
# ==============================================================================
class QueueListWidget(QListWidget):
    fileDropped = pyqtSignal(list)
    orderChanged = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setSpacing(8)
        self._current_hover_target = None

    def _row_at_pos(self, pos: QPoint) -> int:
        cnt = self.count()
        if cnt == 0:
            return -1

        drop_item = self.itemAt(pos)
        if drop_item:
            r = self.row(drop_item)
            if r >= 0:
                return r

        y = pos.y()
        first_item = self.item(0)
        first_rect = self.visualItemRect(first_item)
        if y <= first_rect.bottom():
            return 0

        last_item = self.item(cnt - 1)
        last_rect = self.visualItemRect(last_item)
        if y >= last_rect.top():
            return cnt - 1

        for i in range(cnt - 1):
            r1 = self.visualItemRect(self.item(i))
            r2 = self.visualItemRect(self.item(i + 1))
            if r1.top() <= y <= r2.bottom():
                mid = (r1.bottom() + r2.top()) // 2
                return i if y <= mid else (i + 1)

        if self._current_hover_target is not None and 0 <= self._current_hover_target < cnt:
            return self._current_hover_target
        return 0 if y < first_rect.top() else (cnt - 1)

    def _first_waiting_index(self, main_win) -> int:
        if hasattr(main_win, 'coda_files'):
            for i, it in enumerate(main_win.coda_files):
                if it.get("stato") == "in_attesa":
                    return i
        return -1

    def _aggiorna_target_hover(self, target_row):
        if target_row == self._current_hover_target:
            return
        if self._current_hover_target is not None:
            old_item = self.item(self._current_hover_target)
            if old_item:
                old_card = self.itemWidget(old_item)
                if old_card and hasattr(old_card, 'set_drop_target'):
                    old_card.set_drop_target(False)

        self._current_hover_target = target_row

        if target_row is not None and 0 <= target_row < self.count():
            new_item = self.item(target_row)
            if new_item:
                new_card = self.itemWidget(new_item)
                if new_card and hasattr(new_card, 'set_drop_target'):
                    new_card.set_drop_target(True)

    def _rimuovi_hover_target(self):
        if self._current_hover_target is not None:
            old_item = self.item(self._current_hover_target)
            if old_item:
                old_card = self.itemWidget(old_item)
                if old_card and hasattr(old_card, 'set_drop_target'):
                    old_card.set_drop_target(False)
            self._current_hover_target = None

    def dragEnterEvent(self, event: QDragEnterEvent):
        main_win = self.window()
        is_transcribing = bool(
            hasattr(main_win, 'thread_lavoro')
            and main_win.thread_lavoro
            and main_win.thread_lavoro.isRunning()
        )

        if event.mimeData().hasFormat("application/x-whisper-queue-item"):
            try:
                src_row = int(event.mimeData().data("application/x-whisper-queue-item").data().decode("utf-8"))
            except Exception:
                src_row = -1

            if is_transcribing:
                first_wait = self._first_waiting_index(main_win)
                if first_wait < 0 or src_row < first_wait:
                    event.ignore()
                    return

            pos = event.position().toPoint()
            target_row = self._row_at_pos(pos)
            if is_transcribing:
                first_wait = self._first_waiting_index(main_win)
                if first_wait >= 0 and target_row < first_wait:
                    target_row = first_wait

            self._aggiorna_target_hover(target_row)
            event.acceptProposedAction()
        elif event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        main_win = self.window()
        is_transcribing = bool(
            hasattr(main_win, 'thread_lavoro')
            and main_win.thread_lavoro
            and main_win.thread_lavoro.isRunning()
        )

        if event.mimeData().hasFormat("application/x-whisper-queue-item"):
            try:
                src_row = int(event.mimeData().data("application/x-whisper-queue-item").data().decode("utf-8"))
            except Exception:
                src_row = -1

            if is_transcribing:
                first_wait = self._first_waiting_index(main_win)
                if first_wait < 0 or src_row < first_wait:
                    event.ignore()
                    return

            pos = event.position().toPoint()
            target_row = self._row_at_pos(pos)
            if is_transcribing:
                first_wait = self._first_waiting_index(main_win)
                if first_wait >= 0 and target_row < first_wait:
                    target_row = first_wait

            self._aggiorna_target_hover(target_row)
            event.acceptProposedAction()
        elif event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._rimuovi_hover_target()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        self._rimuovi_hover_target()
        main_win = self.window()
        is_transcribing = bool(
            hasattr(main_win, 'thread_lavoro')
            and main_win.thread_lavoro
            and main_win.thread_lavoro.isRunning()
        )

        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            percorsi = [u.toLocalFile() for u in urls if u.isLocalFile()]
            if percorsi:
                self.fileDropped.emit(percorsi)
            event.acceptProposedAction()
            return

        if event.mimeData().hasFormat("application/x-whisper-queue-item"):
            try:
                src_row = int(event.mimeData().data("application/x-whisper-queue-item").data().decode("utf-8"))
            except Exception:
                src_row = -1

            pos = event.position().toPoint()
            dst_row = self._row_at_pos(pos)

            if is_transcribing:
                first_wait = self._first_waiting_index(main_win)
                if first_wait < 0 or src_row < first_wait:
                    self.clearSelection()
                    self.setCurrentRow(-1)
                    event.ignore()
                    return
                if dst_row < first_wait:
                    dst_row = first_wait

            if 0 <= src_row < self.count() and 0 <= dst_row < self.count() and src_row != dst_row:
                self.orderChanged.emit(src_row, dst_row)
            self.clearSelection()
            self.setCurrentRow(-1)
            event.acceptProposedAction()

# ==============================================================================
# INTERACTIVE EMPTY QUEUE DROP ZONE
# ==============================================================================
class EmptyDropZone(QFrame):
    fileDropped = pyqtSignal(list)
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("emptyCard")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("""
                QFrame#emptyCard {
                    background-color: #1e1e24;
                    border-radius: 12px;
                    border: 2px dashed #818cf8;
                }
            """)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet("")
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet("")
        self.style().unpolish(self)
        self.style().polish(self)
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            percorsi = [u.toLocalFile() for u in urls if u.isLocalFile()]
            if percorsi:
                self.fileDropped.emit(percorsi)
            event.acceptProposedAction()
        else:
            event.ignore()

# ==============================================================================
# CONFIRMATION MODAL FOR MANUAL MODE SWITCH
# ==============================================================================
class DialogoConfermaPassaggioManuale(QDialog):
    def __init__(self, lang="it", parent=None):
        super().__init__(parent)
        self.lang = lang
        s = STRINGS[lang]
        self.setWindowTitle(s["dlg_manual_title"])
        self.setFixedSize(500, 240)
        self.setModal(True)

        self.setStyleSheet("""
            QDialog {
                background-color: #18181b;
                border: 1px solid #3f3f46;
                border-radius: 12px;
            }
            QLabel#dlgTitle {
                font-size: 15px;
                font-weight: bold;
                color: #ffffff;
            }
            QLabel#dlgMsg {
                font-size: 13px;
                color: #d4d4d8;
                line-height: 1.4;
            }
            QPushButton#btnDlgConferma {
                background-color: #818cf8;
                color: #ffffff;
                font-weight: bold;
                border-radius: 8px;
                padding: 9px 18px;
                font-size: 13px;
                border: none;
            }
            QPushButton#btnDlgConferma:hover {
                background-color: #6d78f5;
            }
            QPushButton#btnDlgAnnulla {
                background-color: #ef4444;
                color: #ffffff;
                font-weight: bold;
                border-radius: 8px;
                padding: 9px 18px;
                font-size: 13px;
                border: none;
            }
            QPushButton#btnDlgAnnulla:hover {
                background-color: #dc2626;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        lbl_titolo = QLabel(s["dlg_manual_header"])
        lbl_titolo.setObjectName("dlgTitle")
        layout.addWidget(lbl_titolo)

        lbl_messaggio = QLabel(s["dlg_manual_msg"])
        lbl_messaggio.setObjectName("dlgMsg")
        lbl_messaggio.setWordWrap(True)
        layout.addWidget(lbl_messaggio)

        layout.addStretch()

        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)

        btn_annulla = QPushButton(s["dlg_manual_cancel"])
        btn_annulla.setObjectName("btnDlgAnnulla")
        btn_annulla.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_annulla.clicked.connect(self.reject)
        btn_box.addWidget(btn_annulla)

        btn_box.addStretch()

        btn_conferma = QPushButton(s["dlg_manual_confirm"])
        btn_conferma.setObjectName("btnDlgConferma")
        btn_conferma.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_conferma.clicked.connect(self.accept)
        btn_box.addWidget(btn_conferma)

        layout.addLayout(btn_box)

# ==============================================================================
# INTEGRATED HELP GUIDE DIALOG
# ==============================================================================
class HelpGuideDialog(QDialog):
    def __init__(self, lang="it", parent=None):
        super().__init__(parent)
        self.lang = lang
        s = STRINGS[lang]
        self.setWindowTitle(s["help_title"])
        self.setFixedSize(680, 520)
        self.setModal(True)

        self.setStyleSheet("""
            QDialog {
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 12px;
            }
            QTextBrowser {
                background-color: #121214;
                color: #e4e4e7;
                border: 1px solid #27272a;
                border-radius: 10px;
                padding: 14px;
                font-family: "Segoe UI", sans-serif;
                font-size: 13px;
                line-height: 1.5;
            }
            QPushButton#btnCloseHelp {
                background-color: #27272a;
                color: #ffffff;
                border: 1px solid #3f3f46;
                border-radius: 8px;
                font-weight: bold;
                padding: 7px 18px;
                font-size: 13px;
            }
            QPushButton#btnCloseHelp:hover {
                background-color: #3f3f46;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(12)

        self.browser = QTextBrowser()
        self.browser.setHtml(self._get_html_content())
        layout.addWidget(self.browser)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_close = QPushButton(s["help_close"])
        btn_close.setObjectName("btnCloseHelp")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)

    def _get_html_content(self) -> str:
        if self.lang == "it":
            return """
            <h2 style='color: #ffffff; margin-bottom: 4px;'>Whisper Studio v2.7.5 — Guida & Istruzioni</h2>
            <p style='color: #818cf8; font-weight: bold; margin-top: 0;'>Trascrizione Audio & Video Offline con NVIDIA CUDA & Intel/AMD CPU</p>
            <hr style='border: 0; border-top: 1px solid #27272a;'>
            
            <h3 style='color: #10b981;'>Cos'è Whisper Studio:</h3>
            <p>Un'applicazione professionale, autonoma, portatile e completamente privata per Windows. Trascrive qualsiasi file audio e video in <b>Testo (.txt)</b> o <b>Documento Word (.docx)</b> sfruttando l'accelerazione NVIDIA CUDA (RTX/GTX) e CPU multithread senza mai inviare dati all'esterno.</p>
            
            <h3 style='color: #818cf8;'>Gestione Intelligente dei Modelli:</h3>
            <ul>
                <li><b>Modalità Automatica:</b> Rileva la presenza di una scheda video dedicata NVIDIA (con almeno 6 GB di VRAM) e seleziona automaticamente <i>Large-v3 Standard</i> per la massima accuratezza. Se rileva una GPU AMD o Intel (usando quindi il processore per trascrivere), passa automaticamente a <i>Large-v3 Turbo</i> per garantire fluidità e velocità.</li>
                <li><b>Modalità Manuale & Memoria Impostazioni:</b> Clicca su <i>Passa a Selezione Manuale</i> per scegliere liberamente il modello desiderato. La selezione della modalità e del modello rimane salvata in memoria al riavvio dell'app; se cambi modello viene ricordato, e tornando in automatico viene ripristinato.</li>
            </ul>

            <h3 style='color: #fbbf24;'>Come si usa:</h3>
            <ol>
                <li><b>Aggiungi File:</b> Trascina qualsiasi file audio/video nella finestra oppure clicca <i>➕ Aggiungi File</i>.</li>
                <li><b>Riordina Coda:</b> Trascina le schede con il mouse verso l'alto o il basso per cambiare l'ordine di elaborazione (indicatore blu di destinazione).</li>
                <li><b>Controlli:</b> Clicca <i>🚀 Avvia Trascrizione</i> per avviare il batch. Puoi mettere in pausa con <i>⏸ Pausa</i> o interrompere con <i>■ Annulla</i>.</li>
            </ol>

            <h3 style='color: #38bdf8;'>Gestione Risorse & Memory Reclaim:</h3>
            <p>Al termine della coda o in caso di stop, l'applicazione espelle il modello dalla memoria liberando istantaneamente il 100% della RAM e della VRAM GPU.</p>

            <h3 style='color: #e4e4e7;'>Dove vengono salvati i file:</h3>
            <p>I file trascritti vengono salvati automaticamente nella stessa cartella dei file multimediali d'origine con la data e l'ora formattate.</p>
            
            <h3 style='color: #e4e4e7;'>Formati Supportati:</h3>
            <p>MP3, WAV, M4A, AAC, MP4, MKV, FLAC, OGG, WEBM, MOV, WMA, ALAC, OPUS.</p>
            """
        else:
            return """
            <h2 style='color: #ffffff; margin-bottom: 4px;'>Whisper Studio v2.7.5 — User Guide & Instructions</h2>
            <p style='color: #818cf8; font-weight: bold; margin-top: 0;'>Offline Audio & Video Transcription powered by NVIDIA CUDA & Intel/AMD CPU</p>
            <hr style='border: 0; border-top: 1px solid #27272a;'>
            
            <h3 style='color: #10b981;'>About Whisper Studio:</h3>
            <p>A native, portable, and completely private Windows application. Transcribes audio and video files into <b>Plain Text (.txt)</b> or <b>Word (.docx)</b> documents leveraging NVIDIA CUDA GPU acceleration and CPU multithreading completely offline.</p>
            
            <h3 style='color: #818cf8;'>Smart Model Management:</h3>
            <ul>
                <li><b>Automatic Mode:</b> Detects whether a dedicated NVIDIA GPU (with 6 GB+ VRAM) is present and automatically selects <i>Large-v3 Standard</i> for highest fidelity. If an AMD or Intel GPU is detected (running transcription on the CPU), it automatically switches to <i>Large-v3 Turbo</i> for high speed.</li>
                <li><b>Manual Mode & Persistent Memory:</b> Click <i>Switch to Manual Selection</i> to freely choose models. Your selected mode and model are remembered across app restarts, updated whenever you change models, and reset when you restore Automatic Mode.</li>
            </ul>

            <h3 style='color: #fbbf24;'>How to Use:</h3>
            <ol>
                <li><b>Add Files:</b> Drag and drop audio or video files into the window, or click <i>➕ Add Files</i>.</li>
                <li><b>Reorder Queue:</b> Drag cards up or down to adjust processing priority (blue drop marker).</li>
                <li><b>Controls:</b> Click <i>🚀 Start Transcription</i> to begin. Pause anytime with <i>⏸ Pause</i> or cancel with <i>■ Cancel</i>.</li>
            </ol>

            <h3 style='color: #38bdf8;'>Memory Reclaim & Zero Leakage:</h3>
            <p>Upon queue completion or cancellation, the AI model is completely unloaded, freeing 100% of GPU VRAM and System RAM.</p>

            <h3 style='color: #e4e4e7;'>Output Location:</h3>
            <p>Transcribed files are automatically saved next to original media files and revealed upon completion.</p>
            
            <h3 style='color: #e4e4e7;'>Supported Formats:</h3>
            <p>MP3, WAV, M4A, AAC, MP4, MKV, FLAC, OGG, WEBM, MOV, WMA, ALAC, OPUS.</p>
            """

# ==============================================================================
# MAIN APPLICATION WINDOW
# ==============================================================================
class WhisperStudioWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._initializing = True
        self._is_high_spec_override = None
        self.settings = QSettings("WhisperStudio", "WhisperStudioWindows")
        saved_lang = self.settings.value("language", None)
        if saved_lang in ("it", "en"):
            self.current_lang = saved_lang
        else:
            self.current_lang = detect_system_language()

        self.setWindowTitle(self.t("win_title"))
        self.resize(960, 740)
        self.setMinimumSize(940, 720)
        self.setStyleSheet(QSS_STILE)
        self.setAcceptDrops(True)

        # Set App Icon
        icon_ico = DIR_CORRENTE / "wispr.ico"
        icon_black = DIR_CORRENTE / "app_icon_black.png"
        icon_png = DIR_CORRENTE / "wispr.png"
        if icon_ico.exists():
            self.setWindowIcon(QIcon(str(icon_ico)))
        elif icon_black.exists():
            self.setWindowIcon(QIcon(str(icon_black)))
        elif icon_png.exists():
            self.setWindowIcon(QIcon(str(icon_png)))

        self._flag_icon_it = create_flag_icon("it")
        self._flag_icon_en = create_flag_icon("en")

        self.coda_files = []
        self.queue_lock = threading.Lock()
        self.card_widgets = []
        self.thread_lavoro = None
        self.modalita_manuale = False
        self._active_file_path = None

        # Hardware setup
        self.dev_type, self.compute_type, self.hw_name, self.hw_color, self.hw_badge = detect_hardware()
        vram_info = get_vram_info()
        self.vram_gb = vram_info[1] if vram_info else 0.0
        self.ram_totale_gb = get_total_ram_gb()

        self._setup_menubar()
        self._costruisci_interfaccia()
        self._carica_impostazioni_modello()
        self._initializing = False
        self._avvia_timer_memoria()

    def __setattr__(self, name, value):
        if name in ("dev_type", "vram_gb") and "_is_high_spec_override" in self.__dict__:
            self.__dict__["_is_high_spec_override"] = None
        super().__setattr__(name, value)

    @property
    def is_high_spec(self) -> bool:
        if getattr(self, "_is_high_spec_override", None) is not None:
            return self._is_high_spec_override
        return self.dev_type == "cuda" and self.vram_gb >= 5.5

    @is_high_spec.setter
    def is_high_spec(self, value):
        self._is_high_spec_override = None if value is None else bool(value)

    def _aggiorna_info_modello_auto(self):
        if not hasattr(self, "lbl_auto_modello") or not hasattr(self, "lbl_auto_desc"):
            return
        if self.is_high_spec:
            self.lbl_auto_modello.setText(f"<b>{self.t('model_large_title')}</b>")
            if self.dev_type == "cuda":
                self.lbl_auto_desc.setText(self.t("auto_desc_large_gpu"))
            else:
                self.lbl_auto_desc.setText(self.t("auto_desc_large_cpu"))
        else:
            self.lbl_auto_modello.setText(f"<b>{self.t('model_turbo_title')}</b>")
            if self.dev_type == "cuda" and getattr(self, "_is_high_spec_override", None) is None:
                self.lbl_auto_desc.setText(self.t("auto_desc_turbo_gpu"))
            else:
                self.lbl_auto_desc.setText(self.t("auto_desc_turbo_cpu"))

    def t(self, key: str, **kwargs) -> str:
        s = STRINGS.get(self.current_lang, STRINGS["en"])
        val = s.get(key, key)
        if kwargs:
            val = val.format(**kwargs)
        return val

    def _setup_menubar(self):
        mb = self.menuBar()

        # 1. Menu Lingua / Language
        self.menu_lang = FlagMenu(self.t("menu_language"), self)
        mb.addMenu(self.menu_lang)
        self.grp_lang = QActionGroup(self)
        self.grp_lang.setExclusive(True)

        self.act_it = QAction("🇮🇹 Italiano", self)
        self.act_it.setIcon(self._flag_icon_it)
        self.act_it.setCheckable(True)
        self.act_it.setChecked(self.current_lang == "it")
        self.act_it.triggered.connect(lambda: self.set_language("it"))
        self.grp_lang.addAction(self.act_it)
        self.menu_lang.addAction(self.act_it)

        self.act_en = QAction("🇬🇧 English", self)
        self.act_en.setIcon(self._flag_icon_en)
        self.act_en.setCheckable(True)
        self.act_en.setChecked(self.current_lang == "en")
        self.act_en.triggered.connect(lambda: self.set_language("en"))
        self.grp_lang.addAction(self.act_en)
        self.menu_lang.addAction(self.act_en)

        # 2. Menu Aiuto / Help
        self.menu_help = mb.addMenu(self.t("menu_help"))
        self.act_help = QAction(self.t("menu_guide"), self)
        self.act_help.triggered.connect(self.mostra_guida)
        self.menu_help.addAction(self.act_help)

        self.act_logs = QAction(self.t("menu_open_logs"), self)
        self.act_logs.triggered.connect(self._apri_cartella_logs)
        self.menu_help.addAction(self.act_logs)

        self.act_about = QAction(self.t("menu_about"), self)
        self.act_about.triggered.connect(self._mostra_about)
        self.menu_help.addAction(self.act_about)

    def mostra_guida(self):
        dlg = HelpGuideDialog(lang=self.current_lang, parent=self)
        dlg.exec()

    def _apri_cartella_logs(self):
        open_directory_in_explorer(str(LOG_DIR))

    def _mostra_about(self):
        QMessageBox.about(self, self.t("about_title"), self.t("about_text"))

    def set_language(self, lang: str):
        if lang not in ("it", "en"):
            return
        self.current_lang = lang
        self.settings.setValue("language", self.current_lang)

        self.act_it.setChecked(self.current_lang == "it")
        self.act_en.setChecked(self.current_lang == "en")

        self.menu_lang.setTitle(self.t("menu_language"))
        if self.menu_lang.menuAction():
            self.menu_lang.menuAction().setText(self.t("menu_language"))
        self.menu_help.setTitle(self.t("menu_help"))
        if self.menu_help.menuAction():
            self.menu_help.menuAction().setText(self.t("menu_help"))
        self.act_help.setText(self.t("menu_guide"))
        self.act_logs.setText(self.t("menu_open_logs"))
        self.act_about.setText(self.t("menu_about"))

        self.retranslate_ui()

    def retranslate_ui(self):
        self.setWindowTitle(self.t("win_title"))
        if hasattr(self, "lbl_sub"):
            self.lbl_sub.setText(self.t("sub_edition"))

        # Hardware and Memory
        if self.dev_type == "cuda":
            self.lbl_hw.setText(self.t("hw_label_cuda"))
        else:
            self.lbl_hw.setText(self.t("hw_label_cpu"))
        self._aggiorna_memoria_display()

        self.lbl_m_title.setText(self.t("section_model"))
        self.lbl_auto_tag.setText(self.t("auto_tag"))
        self._aggiorna_info_modello_auto()

        self.btn_passa_manuale.setText(self.t("btn_switch_manual"))
        self.lbl_man_tag.setText(self.t("manual_tag"))
        self.btn_large.setText(self.t("btn_large"))
        self.btn_small.setText(self.t("btn_small"))
        self.btn_torna_auto.setText(self.t("btn_return_auto"))
        self._aggiorna_avviso_manuale()

        self.lbl_l_title.setText(self.t("section_lang"))
        self.btn_it.setText(self.t("btn_lang_primary"))
        self.btn_it.setIcon(self._flag_icon_it if self.current_lang == "it" else self._flag_icon_en)
        self.btn_auto.setText(self.t("btn_lang_auto"))
        self.lbl_sub_l.setText(self.t("lang_subtitle"))

        self.lbl_f_title.setText(self.t("section_formats"))
        self.chk_txt.setText(self.t("chk_txt"))
        self.chk_docx.setText(self.t("chk_docx"))
        self.lbl_salva.setText(self.t("formats_subtitle"))
        self.lbl_footer.setText(self.t("footer"))

        conteggio = len(self.coda_files)
        self.lbl_coda_count.setText(self.t("queue_title", count=conteggio))
        self.btn_add.setText(self.t("btn_add"))
        self.btn_clear.setText(self.t("btn_clear"))

        self.lbl_empty_t.setText(self.t("empty_title"))
        self.lbl_empty_sub.setText(self.t("empty_subtitle"))

        self.btn_ferma.setText(self.t("btn_cancel"))
        if self.thread_lavoro and self.thread_lavoro.isRunning() and self.thread_lavoro.is_paused:
            self.btn_pausa.setText(self.t("btn_resume"))
        else:
            self.btn_pausa.setText(self.t("btn_pause"))
        self.btn_avvia.setText(self.t("btn_start"))

        if not (self.thread_lavoro and self.thread_lavoro.isRunning()):
            self.lbl_stato.setText(self.t("status_ready"))
            if hasattr(self, 'spinner_loading'):
                self.spinner_loading.stop()

        for card in self.card_widgets:
            if hasattr(card, 'set_language'):
                card.set_language(self.current_lang)

        self._aggiorna_vincoli_dimensione_finestra()

    def _aggiorna_vincoli_dimensione_finestra(self):
        min_h = 720
        if hasattr(self, 'sidebar') and self.sidebar is not None:
            s_lay = self.sidebar.layout()
            if s_lay is not None:
                s_lay.activate()
            sidebar_min_h = self.sidebar.minimumSizeHint().height()
            if hasattr(self, 'card_manuale') and hasattr(self, 'card_auto') and self.card_manuale.isHidden():
                man_h = max(self.card_manuale.minimumHeight(), self.card_manuale.minimumSizeHint().height())
                extra_man = max(0, man_h - self.card_auto.minimumSizeHint().height())
                sidebar_min_h += extra_man
            self.sidebar.setMinimumHeight(sidebar_min_h)
            menubar_h = self.menuBar().sizeHint().height() if self.menuBar() else 28
            min_h = max(min_h, sidebar_min_h + menubar_h + 32)
        self.setMinimumSize(940, min_h)
        if self.height() < min_h:
            self.resize(max(self.width(), 940), min_h)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            percorsi = [u.toLocalFile() for u in urls if u.isLocalFile()]
            if percorsi:
                self._aggiungi_percorsi(percorsi)
            event.acceptProposedAction()

    def _costruisci_interfaccia(self):
        centrale = QWidget()
        centrale.setAcceptDrops(True)
        self.setCentralWidget(centrale)
        layout_orizzontale = QHBoxLayout(centrale)
        layout_orizzontale.setContentsMargins(14, 12, 14, 12)
        layout_orizzontale.setSpacing(14)

        # 1. SIDEBAR VERTICALE SINISTRA
        sidebar = QFrame()
        sidebar.setObjectName("sidebarFrame")
        sidebar.setFixedWidth(310)
        self.sidebar = sidebar
        s_layout = QVBoxLayout(sidebar)
        s_layout.setContentsMargins(14, 7, 14, 7)
        s_layout.setSpacing(4)

        # Header / Logo (New icon on black background with Windows 8px rounded corners)
        header_box = QHBoxLayout()
        header_box.setSpacing(10)
        icon_black = DIR_CORRENTE / "app_icon_black.png"
        icon_png = DIR_CORRENTE / "wispr.png"
        logo_src = icon_black if icon_black.exists() else icon_png
        if logo_src.exists():
            logo_lbl = QLabel()
            dpr = 2.0
            dim_logica = 36
            phys_sz = int(dim_logica * dpr)
            raw_pix = QPixmap(str(logo_src)).scaled(
                phys_sz, phys_sz,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            rounded_pix = QPixmap(phys_sz, phys_sz)
            rounded_pix.fill(Qt.GlobalColor.transparent)
            lp = QPainter(rounded_pix)
            lp.setRenderHint(QPainter.RenderHint.Antialiasing)
            lp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            clip_path = QPainterPath()
            clip_path.addRoundedRect(QRectF(0.5, 0.5, phys_sz - 1.0, phys_sz - 1.0), 16.0, 16.0)
            lp.setClipPath(clip_path)
            lp.fillRect(0, 0, phys_sz, phys_sz, QColor("#08080c"))
            lp.drawPixmap(0, 0, raw_pix)
            lp.setClipping(False)
            lp.setPen(QPen(QColor(255, 255, 255, 34), 1.5))
            lp.drawPath(clip_path)
            lp.end()
            rounded_pix.setDevicePixelRatio(dpr)
            logo_lbl.setPixmap(rounded_pix)
            logo_lbl.setFixedSize(dim_logica, dim_logica)
            logo_lbl.setStyleSheet("background: transparent; border: none;")
            self.logo_lbl = logo_lbl
            header_box.addWidget(logo_lbl)

        v_title = QVBoxLayout()
        v_title.setSpacing(2)
        lbl_title = QLabel("WHISPER STUDIO")
        lbl_title.setObjectName("titleLabel")
        lbl_title.setStyleSheet("background: transparent; border: none;")
        self.lbl_sub = QLabel(self.t("sub_edition"))
        self.lbl_sub.setObjectName("subLabel")
        self.lbl_sub.setStyleSheet("background: transparent; border: none;")
        v_title.addWidget(lbl_title)
        v_title.addWidget(self.lbl_sub)
        header_box.addLayout(v_title)
        header_box.addStretch()
        s_layout.addLayout(header_box)

        # Indicatori Hardware
        stats_box = QVBoxLayout()
        stats_box.setSpacing(2)

        self.lbl_hw = QLabel(self.t("hw_label_cuda") if self.dev_type == "cuda" else self.t("hw_label_cpu"))
        self.lbl_hw.setStyleSheet(f"color: {self.hw_color}; font-size: 12px; font-weight: 600; background: transparent; border: none; padding: 0;")
        stats_box.addWidget(self.lbl_hw)

        self.lbl_ram = QLabel("")
        self.lbl_ram.setStyleSheet("color: #a1a1aa; font-size: 11px; font-weight: 500; background: transparent; border: none; padding: 0;")
        stats_box.addWidget(self.lbl_ram)

        self.ram_gauge = RAMGaugeBar()
        stats_box.addWidget(self.ram_gauge)

        s_layout.addLayout(stats_box)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet("background-color: #27272a; max-height: 1px; border: none;")
        self.sep1 = sep1
        s_layout.addWidget(sep1)

        # Modello di Trascrizione
        self.lbl_m_title = QLabel(self.t("section_model"))
        self.lbl_m_title.setObjectName("sectionTitle")
        self.lbl_m_title.setStyleSheet("background: transparent; border: none;")
        s_layout.addWidget(self.lbl_m_title)

        # Scheda Modalità Automatica
        self.card_auto = QFrame()
        self.card_auto.setObjectName("cardAutoModello")
        self.card_auto.setStyleSheet("""
            QFrame#cardAutoModello {
                background-color: #1c1c1f;
                border: 1px solid #2e2e34;
                border-radius: 10px;
            }
        """)
        lay_auto = QVBoxLayout(self.card_auto)
        lay_auto.setContentsMargins(12, 10, 12, 10)
        lay_auto.setSpacing(6)

        self.lbl_auto_tag = QLabel(self.t("auto_tag"))
        self.lbl_auto_tag.setStyleSheet("font-size: 13px; font-weight: bold; color: #818cf8; background: transparent; border: none;")
        lay_auto.addWidget(self.lbl_auto_tag)

        self.lbl_auto_modello = QLabel("")
        self.lbl_auto_modello.setStyleSheet("font-size: 12px; color: #ffffff; background: transparent; border: none;")
        lay_auto.addWidget(self.lbl_auto_modello)

        self.lbl_auto_desc = QLabel("")
        self.lbl_auto_desc.setStyleSheet("font-size: 11px; color: #a1a1aa; background: transparent; border: none;")
        self.lbl_auto_desc.setWordWrap(True)
        lay_auto.addWidget(self.lbl_auto_desc)

        self.btn_passa_manuale = QPushButton(self.t("btn_switch_manual"))
        self.btn_passa_manuale.setObjectName("btnPassaManuale")
        self.btn_passa_manuale.setFixedHeight(34)
        self.btn_passa_manuale.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_passa_manuale.setStyleSheet("""
            QPushButton#btnPassaManuale {
                background-color: #27272a;
                color: #d4d4d8;
                border: 1px solid #3f3f46;
                border-radius: 7px;
                padding: 6px 10px;
                font-size: 12px;
                font-weight: 600;
                margin-top: 3px;
            }
            QPushButton#btnPassaManuale:hover {
                background-color: #3f3f46;
                color: #ffffff;
                border-color: #818cf8;
            }
        """)
        self.btn_passa_manuale.clicked.connect(self._richiedi_passaggio_manuale)
        lay_auto.addWidget(self.btn_passa_manuale)

        s_layout.addWidget(self.card_auto)

        # Scheda Modalità Manuale
        self.card_manuale = QFrame()
        self.card_manuale.setObjectName("cardManualeModello")
        self.card_manuale.setStyleSheet("""
            QFrame#cardManualeModello {
                background-color: #18181b;
                border: 1px solid #3f3f46;
                border-radius: 10px;
            }
        """)
        self.card_manuale.setMinimumHeight(300)
        lay_man = QVBoxLayout(self.card_manuale)
        lay_man.setContentsMargins(12, 10, 12, 10)
        lay_man.setSpacing(6)

        self.lbl_man_tag = QLabel(self.t("manual_tag"))
        self.lbl_man_tag.setFixedHeight(20)
        self.lbl_man_tag.setStyleSheet("font-size: 12px; font-weight: bold; color: #fbbf24; background: transparent; border: none;")
        lay_man.addWidget(self.lbl_man_tag)

        self.grp_modelli = QButtonGroup(self)
        self.grp_modelli.setExclusive(True)

        self.btn_large = QPushButton(self.t("btn_large"))
        self.btn_large.setObjectName("btnLargeModello")
        self.btn_large.setProperty("class", "toggleBtn")
        self.btn_large.setCheckable(True)
        self.btn_large.setFixedHeight(60)
        self.btn_large.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_large.clicked.connect(self._on_cambio_modello_manuale)

        self.btn_small = QPushButton(self.t("btn_small"))
        self.btn_small.setObjectName("btnSmallModello")
        self.btn_small.setProperty("class", "toggleBtn")
        self.btn_small.setCheckable(True)
        self.btn_small.setFixedHeight(60)
        self.btn_small.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_small.clicked.connect(self._on_cambio_modello_manuale)

        self.grp_modelli.addButton(self.btn_large)
        self.grp_modelli.addButton(self.btn_small)

        if self.is_high_spec:
            self.btn_large.setChecked(True)
        else:
            self.btn_small.setChecked(True)

        lay_man.addWidget(self.btn_large)
        lay_man.addWidget(self.btn_small)

        self.lbl_warn_manuale = QLabel("")
        self.lbl_warn_manuale.setWordWrap(True)
        self.lbl_warn_manuale.setMinimumHeight(52)
        self.lbl_warn_manuale.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.lbl_warn_manuale.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        lay_man.addWidget(self.lbl_warn_manuale)

        self.btn_torna_auto = QPushButton(self.t("btn_return_auto"))
        self.btn_torna_auto.setObjectName("btnTornaAuto")
        self.btn_torna_auto.setFixedHeight(36)
        self.btn_torna_auto.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_torna_auto.setStyleSheet("""
            QPushButton#btnTornaAuto {
                background-color: #27272a;
                color: #818cf8;
                border: 1px solid #818cf8;
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton#btnTornaAuto:hover {
                background-color: #2e2a52;
                color: #ffffff;
            }
        """)
        self.btn_torna_auto.clicked.connect(self._ripristina_modalita_automatica)
        lay_man.addWidget(self.btn_torna_auto)

        self._aggiorna_avviso_manuale()
        self.card_manuale.setVisible(False)
        s_layout.addWidget(self.card_manuale)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("background-color: #27272a; max-height: 1px; border: none;")
        self.sep2 = sep2
        s_layout.addWidget(sep2)

        # Selezione Lingua Audio
        self.lbl_l_title = QLabel(self.t("section_lang"))
        self.lbl_l_title.setObjectName("sectionTitle")
        self.lbl_l_title.setStyleSheet("background: transparent; border: none;")
        s_layout.addWidget(self.lbl_l_title)

        self.grp_lingue = QButtonGroup(self)
        self.grp_lingue.setExclusive(True)

        h_lang = QHBoxLayout()
        h_lang.setSpacing(8)

        self.btn_it = FlagButton(self.t("btn_lang_primary"))
        self.btn_it.setIcon(self._flag_icon_it if self.current_lang == "it" else self._flag_icon_en)
        self.btn_it.setIconSize(QSize(20, 14))
        self.btn_it.setProperty("class", "toggleBtn")
        self.btn_it.setStyleSheet("text-align: center;")
        self.btn_it.setCheckable(True)
        self.btn_it.setChecked(True)
        self.btn_it.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_auto = QPushButton(self.t("btn_lang_auto"))
        self.btn_auto.setProperty("class", "toggleBtn")
        self.btn_auto.setStyleSheet("text-align: center;")
        self.btn_auto.setCheckable(True)
        self.btn_auto.setCursor(Qt.CursorShape.PointingHandCursor)

        self.grp_lingue.addButton(self.btn_it)
        self.grp_lingue.addButton(self.btn_auto)

        h_lang.addWidget(self.btn_it)
        h_lang.addWidget(self.btn_auto)
        s_layout.addLayout(h_lang)

        self.lbl_sub_l = QLabel(self.t("lang_subtitle"))
        self.lbl_sub_l.setWordWrap(True)
        self.lbl_sub_l.setStyleSheet("font-size: 11px; color: #71717a; background: transparent; border: none;")
        s_layout.addWidget(self.lbl_sub_l)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        sep3.setStyleSheet("background-color: #27272a; max-height: 1px; border: none;")
        self.sep3 = sep3
        s_layout.addWidget(sep3)

        # Formati di Esportazione
        self.lbl_f_title = QLabel(self.t("section_formats"))
        self.lbl_f_title.setObjectName("sectionTitle")
        self.lbl_f_title.setStyleSheet("background: transparent; border: none;")
        s_layout.addWidget(self.lbl_f_title)

        self.chk_txt = WindowsCheckBox(self.t("chk_txt"))
        self.chk_txt.setChecked(True)

        self.chk_docx = WindowsCheckBox(self.t("chk_docx"))
        self.chk_docx.setChecked(False)

        s_layout.addWidget(self.chk_txt)
        s_layout.addWidget(self.chk_docx)

        self.lbl_salva = QLabel(self.t("formats_subtitle"))
        self.lbl_salva.setWordWrap(True)
        self.lbl_salva.setStyleSheet("font-size: 11px; color: #71717a; background: transparent; border: none;")
        s_layout.addWidget(self.lbl_salva)

        s_layout.addStretch()

        self.lbl_footer = QLabel(self.t("footer"))
        self.lbl_footer.setStyleSheet("font-size: 11px; color: #52525b; background: transparent; border: none;")
        s_layout.addWidget(self.lbl_footer)

        layout_orizzontale.addWidget(sidebar)

        # 2. AREA DESTRA (CODA, STATO E CONTROLLI)
        right_panel = QFrame()
        right_panel.setObjectName("rightPanel")
        right_panel.setAcceptDrops(True)
        r_layout = QVBoxLayout(right_panel)
        r_layout.setContentsMargins(18, 16, 18, 16)
        r_layout.setSpacing(12)

        # Header Coda File
        q_header = QHBoxLayout()
        self.lbl_coda_count = QLabel(self.t("queue_title", count=0))
        self.lbl_coda_count.setStyleSheet("font-size: 15px; color: #ffffff;")
        q_header.addWidget(self.lbl_coda_count)

        q_header.addStretch()

        self.btn_add = QPushButton(self.t("btn_add"))
        self.btn_add.setObjectName("btnAdd")
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.clicked.connect(self._apri_dialogo_file)
        q_header.addWidget(self.btn_add)

        self.btn_clear = QPushButton(self.t("btn_clear"))
        self.btn_clear.setObjectName("btnClear")
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.clicked.connect(self._svuota_coda)
        q_header.addWidget(self.btn_clear)

        r_layout.addLayout(q_header)

        # Lista Drag & Drop nativa
        self.queue_list = QueueListWidget()
        self.queue_list.fileDropped.connect(self._aggiungi_percorsi)
        self.queue_list.orderChanged.connect(self._on_item_reordered)
        self.queue_list.currentRowChanged.connect(self._on_riga_selezionata)
        r_layout.addWidget(self.queue_list, 1)

        # Drop-zone vuota interattiva con supporto Drag & Drop e Click nativo
        self.empty_card = EmptyDropZone()
        self.empty_card.fileDropped.connect(self._aggiungi_percorsi)
        self.empty_card.clicked.connect(self._apri_dialogo_file)
        empty_layout = QVBoxLayout(self.empty_card)
        empty_layout.setContentsMargins(20, 45, 20, 45)
        empty_layout.setSpacing(8)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_icon = QLabel("📥")
        lbl_icon.setStyleSheet("font-size: 42px; background: transparent; border: none;")
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        empty_layout.addWidget(lbl_icon)

        self.lbl_empty_t = QLabel(self.t("empty_title"))
        self.lbl_empty_t.setStyleSheet("font-size: 16px; color: #ffffff; background: transparent; border: none;")
        self.lbl_empty_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty_t.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        empty_layout.addWidget(self.lbl_empty_t)

        self.lbl_empty_sub = QLabel(self.t("empty_subtitle"))
        self.lbl_empty_sub.setStyleSheet("font-size: 12px; color: #a1a1aa; background: transparent; border: none;")
        self.lbl_empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty_sub.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        empty_layout.addWidget(self.lbl_empty_sub)
        r_layout.addWidget(self.empty_card, 1)

        self._aggiorna_vista_coda()

        # Area Stato & Progresso
        prog_box = QVBoxLayout()
        prog_box.setSpacing(6)

        self.prog_bar = WhisperProgressBar()
        prog_box.addWidget(self.prog_bar)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        status_row.setContentsMargins(0, 0, 0, 0)

        self.spinner_loading = LoadingSpinner(size=14, color="#818cf8")
        status_row.addWidget(self.spinner_loading, 0, Qt.AlignmentFlag.AlignVCenter)

        self.lbl_stato = QLabel(self.t("status_ready"))
        self.lbl_stato.setStyleSheet("color: #d4d4d8; font-size: 12px; background: transparent;")
        status_row.addWidget(self.lbl_stato, 0, Qt.AlignmentFlag.AlignVCenter)
        status_row.addStretch()

        prog_box.addLayout(status_row)

        r_layout.addLayout(prog_box)

        # Riga Pulsanti Azione (ANNULLA, PAUSA, AVVIA)
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)

        self.btn_ferma = QPushButton(self.t("btn_cancel"))
        self.btn_ferma.setObjectName("btnFerma")
        self.btn_ferma.setEnabled(False)
        self.btn_ferma.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ferma.clicked.connect(self.ferma_trascrizione)
        action_layout.addWidget(self.btn_ferma, 1)

        self.btn_pausa = QPushButton(self.t("btn_pause"))
        self.btn_pausa.setObjectName("btnPausa")
        self.btn_pausa.setEnabled(False)
        self.btn_pausa.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pausa.clicked.connect(self.toggle_pausa)
        action_layout.addWidget(self.btn_pausa, 1)

        self.btn_avvia = QPushButton(self.t("btn_start"))
        self.btn_avvia.setObjectName("btnAvvia")
        self.btn_avvia.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_avvia.clicked.connect(self.avvia_trascrizione)
        action_layout.addWidget(self.btn_avvia, 2)

        r_layout.addLayout(action_layout)
        layout_orizzontale.addWidget(right_panel, 1)

        self.retranslate_ui()

    def _on_riga_selezionata(self, row: int):
        if row != -1:
            self.queue_list.blockSignals(True)
            self.queue_list.clearSelection()
            self.queue_list.setCurrentRow(-1)
            self.queue_list.blockSignals(False)
        for card in self.card_widgets:
            if hasattr(card, 'set_selezionato'):
                card.set_selezionato(False)

    def _apri_dialogo_file(self):
        filtro = self.t("file_dialog_filter")
        titolo = self.t("file_dialog_title")
        scelti, _ = QFileDialog.getOpenFileNames(self, titolo, "", filtro)
        if scelti:
            self._aggiungi_percorsi(scelti)

    def _aggiungi_percorsi(self, lista_percorsi):
        aggiunti = 0
        def elabora_file(p: Path):
            nonlocal aggiunti
            if p.is_file() and p.suffix.lower() in VALID_EXTENSIONS:
                with self.queue_lock:
                    already = any(f["path"] == p for f in self.coda_files)
                if not already:
                    durata = get_file_duration(p)
                    peso = p.stat().st_size
                    with self.queue_lock:
                        self.coda_files.append({
                            "path": p,
                            "durata": durata,
                            "peso": peso,
                            "stato": "in_attesa"
                        })
                    aggiunti += 1

        for item in lista_percorsi:
            p = Path(item).resolve()
            if p.is_dir():
                for sub in sorted(p.rglob("*")):
                    elabora_file(sub)
            else:
                elabora_file(p)

        if aggiunti > 0:
            self._aggiorna_vista_coda()
            if self.thread_lavoro and self.thread_lavoro.isRunning() and hasattr(self.thread_lavoro, "emetti_progresso_totale"):
                self.thread_lavoro.emetti_progresso_totale()

    def _svuota_coda(self):
        if self.thread_lavoro and self.thread_lavoro.isRunning():
            with self.queue_lock:
                self.coda_files[:] = [f for f in self.coda_files if f.get("stato") == "in_corso"]
            self._aggiorna_vista_coda()
            if hasattr(self.thread_lavoro, "emetti_progresso_totale"):
                self.thread_lavoro.emetti_progresso_totale()
            return
        with self.queue_lock:
            self.coda_files.clear()
        self._aggiorna_vista_coda()

    def _rimuovi_file(self, index):
        if self.thread_lavoro and self.thread_lavoro.isRunning():
            with self.queue_lock:
                if not (0 <= index < len(self.coda_files)):
                    return
                if self.coda_files[index].get("stato") == "in_corso":
                    return
                self.coda_files.pop(index)
            self._aggiorna_vista_coda()
            if hasattr(self.thread_lavoro, "emetti_progresso_totale"):
                self.thread_lavoro.emetti_progresso_totale()
            return

        with self.queue_lock:
            if 0 <= index < len(self.coda_files):
                self.coda_files.pop(index)
        self._aggiorna_vista_coda()

    def _on_item_reordered(self, src_idx, dst_idx):
        if self.thread_lavoro and self.thread_lavoro.isRunning():
            with self.queue_lock:
                if not (0 <= src_idx < len(self.coda_files) and 0 <= dst_idx < len(self.coda_files)):
                    self.queue_list.clearSelection()
                    self.queue_list.setCurrentRow(-1)
                    return
                first_wait = -1
                for i, it in enumerate(self.coda_files):
                    if it.get("stato") == "in_attesa":
                        first_wait = i
                        break
                if (
                    first_wait < 0
                    or src_idx < first_wait
                    or dst_idx < first_wait
                    or self.coda_files[src_idx].get("stato") != "in_attesa"
                    or self.coda_files[dst_idx].get("stato") != "in_attesa"
                ):
                    self.queue_list.clearSelection()
                    self.queue_list.setCurrentRow(-1)
                    return
                item = self.coda_files.pop(src_idx)
                self.coda_files.insert(dst_idx, item)
            self._aggiorna_vista_coda()
            self.queue_list.clearSelection()
            self.queue_list.setCurrentRow(-1)
            return

        with self.queue_lock:
            if 0 <= src_idx < len(self.coda_files) and 0 <= dst_idx < len(self.coda_files):
                item = self.coda_files.pop(src_idx)
                self.coda_files.insert(dst_idx, item)
        self._aggiorna_vista_coda()
        self.queue_list.clearSelection()
        self.queue_list.setCurrentRow(-1)

    def _aggiorna_vista_coda(self):
        self.queue_list.blockSignals(True)
        self.queue_list.clear()
        self.card_widgets.clear()
        with self.queue_lock:
            conteggio = len(self.coda_files)
            items_snapshot = list(self.coda_files)
        self.lbl_coda_count.setText(self.t("queue_title", count=conteggio))

        if conteggio == 0:
            self.queue_list.blockSignals(False)
            self.queue_list.setVisible(False)
            self.empty_card.setVisible(True)
            return

        self.queue_list.setVisible(True)
        self.empty_card.setVisible(False)

        for idx, item in enumerate(items_snapshot):
            card = QueueItemCard(idx, item, self._rimuovi_file, lang=self.current_lang)
            card.set_selezionato(False)
            self.card_widgets.append(card)

            list_item = QListWidgetItem(self.queue_list)
            list_item.setSizeHint(QSize(200, 86))
            self.queue_list.addItem(list_item)
            self.queue_list.setItemWidget(list_item, card)

        self.queue_list.clearSelection()
        self.queue_list.setCurrentRow(-1)
        self.queue_list.blockSignals(False)

    def _aggiorna_memoria_display(self):
        if self.dev_type == "cuda":
            vinfo = get_vram_info()
            if vinfo:
                used, tot = vinfo
                self.lbl_ram.setText(self.t("mem_vram_label", used=used, total=tot))
                if hasattr(self, "ram_gauge") and tot > 0:
                    self.ram_gauge.set_ratio(used / tot)
                return
        used_ram, tot_ram = get_system_ram_info()
        self.lbl_ram.setText(self.t("mem_ram_label", used=used_ram, total=tot_ram))
        if hasattr(self, "ram_gauge") and tot_ram > 0:
            self.ram_gauge.set_ratio(used_ram / tot_ram)

    def _avvia_timer_memoria(self):
        self._aggiorna_memoria_display()
        self.timer_mem = QTimer(self)
        self.timer_mem.timeout.connect(self._aggiorna_memoria_display)
        self.timer_mem.start(2500)

    def _salva_impostazioni_modello(self):
        if getattr(self, "_initializing", False):
            return
        modello = "large-v3" if self.btn_large.isChecked() else "turbo"
        self.settings.setValue("manual_mode", bool(self.modalita_manuale))
        self.settings.setValue("manual_model", modello)
        self.settings.sync()

    def _carica_impostazioni_modello(self):
        manual_raw = self.settings.value("manual_mode", None)
        needs_sanitize = False
        if isinstance(manual_raw, bool):
            is_manual = manual_raw
        elif manual_raw is None:
            is_manual = False
        else:
            raw_str = str(manual_raw).strip().lower()
            if raw_str in ("true", "1", "yes"):
                is_manual = True
            elif raw_str in ("false", "0", "no", ""):
                is_manual = False
            else:
                is_manual = False
                needs_sanitize = True

        saved_model_raw = self.settings.value("manual_model", None)
        saved_model = str(saved_model_raw).strip().lower() if saved_model_raw is not None else ""

        self.btn_large.blockSignals(True)
        self.btn_small.blockSignals(True)
        if is_manual:
            self.modalita_manuale = True
            if saved_model in ("large-v3", "large"):
                self.btn_large.setChecked(True)
                if saved_model_raw != "large-v3":
                    needs_sanitize = True
            elif saved_model in ("turbo", "large-v3-turbo", "small"):
                self.btn_small.setChecked(True)
                if saved_model_raw != "turbo":
                    needs_sanitize = True
            else:
                if saved_model_raw is not None:
                    needs_sanitize = True
                if self.is_high_spec:
                    self.btn_large.setChecked(True)
                else:
                    self.btn_small.setChecked(True)
            self.card_auto.setVisible(False)
            self.card_manuale.setVisible(True)
        else:
            self.modalita_manuale = False
            if saved_model_raw is not None and saved_model not in ("large-v3", "turbo"):
                needs_sanitize = True
            if self.is_high_spec:
                self.btn_large.setChecked(True)
            else:
                self.btn_small.setChecked(True)
            self.card_auto.setVisible(True)
            self.card_manuale.setVisible(False)
        self.btn_large.blockSignals(False)
        self.btn_small.blockSignals(False)

        if needs_sanitize:
            modello_corrente = "large-v3" if self.btn_large.isChecked() else "turbo"
            self.settings.setValue("manual_mode", bool(self.modalita_manuale))
            self.settings.setValue("manual_model", modello_corrente)
            self.settings.sync()

        self._aggiorna_info_modello_auto()
        self._aggiorna_avviso_manuale()
        self._aggiorna_vincoli_dimensione_finestra()

    def _on_cambio_modello_manuale(self):
        self._aggiorna_avviso_manuale()
        self._salva_impostazioni_modello()

    def _aggiorna_avviso_manuale(self):
        if not self.is_high_spec:
            if self.btn_large.isChecked():
                testo = self.t("warn_large_low_spec")
                stile = "background: transparent; border: none; color: #fbbf24; padding: 2px 2px; font-size: 11px; font-weight: 500;"
            else:
                testo = self.t("warn_turbo_low_spec")
                stile = "background: transparent; border: none; color: #10b981; padding: 2px 2px; font-size: 11px; font-weight: 500;"
        else:
            if self.btn_large.isChecked():
                testo = self.t("warn_large_high_spec")
                stile = "background: transparent; border: none; color: #10b981; padding: 2px 2px; font-size: 11px; font-weight: 500;"
            else:
                testo = self.t("warn_turbo_high_spec")
                stile = "background: transparent; border: none; color: #fbbf24; padding: 2px 2px; font-size: 11px; font-weight: 500;"
        self.lbl_warn_manuale.setText(testo)
        self.lbl_warn_manuale.setStyleSheet(stile)
        if not getattr(self, "_initializing", False):
            self._salva_impostazioni_modello()

    def _imposta_abilitazione_modello(self, abilitato: bool):
        self.btn_passa_manuale.setEnabled(abilitato)
        self.btn_large.setEnabled(abilitato)
        self.btn_small.setEnabled(abilitato)
        self.btn_torna_auto.setEnabled(abilitato)
        self.btn_it.setEnabled(abilitato)
        self.btn_auto.setEnabled(abilitato)
        self.chk_txt.setEnabled(abilitato)
        self.chk_docx.setEnabled(abilitato)
        self.btn_add.setEnabled(True)
        self.btn_clear.setEnabled(True)

    def _richiedi_passaggio_manuale(self):
        if self.thread_lavoro and self.thread_lavoro.isRunning():
            return
        dlg = DialogoConfermaPassaggioManuale(lang=self.current_lang, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.modalita_manuale = True
            self.card_auto.setVisible(False)
            self.card_manuale.setVisible(True)
            self._aggiorna_avviso_manuale()
            self._salva_impostazioni_modello()
            self._aggiorna_vincoli_dimensione_finestra()

    def _ripristina_modalita_automatica(self):
        if self.thread_lavoro and self.thread_lavoro.isRunning():
            return
        self.modalita_manuale = False
        self.card_manuale.setVisible(False)
        self.card_auto.setVisible(True)
        if self.is_high_spec:
            self.btn_large.setChecked(True)
        else:
            self.btn_small.setChecked(True)
        self._aggiorna_info_modello_auto()
        self._aggiorna_avviso_manuale()
        self._salva_impostazioni_modello()
        self._aggiorna_vincoli_dimensione_finestra()

    # ----------------------------------------------------
    # GESTIONE TRASCRIZIONE
    # ----------------------------------------------------
    def avvia_trascrizione(self):
        if not self.coda_files:
            QMessageBox.information(self, self.t("dlg_empty_title"), self.t("dlg_empty_msg"))
            return

        formati = []
        if self.chk_txt.isChecked():
            formati.append("txt")
        if self.chk_docx.isChecked():
            formati.append("docx")
        if not formati:
            QMessageBox.warning(self, self.t("dlg_formats_title"), self.t("dlg_formats_msg"))
            return

        if not self.modalita_manuale:
            modello_scelto = "large-v3" if self.is_high_spec else "turbo"
        else:
            modello_scelto = "large-v3" if self.btn_large.isChecked() else "turbo"

        lingua_primaria = "it" if self.current_lang == "it" else "en"
        lingua_mode = lingua_primaria if self.btn_it.isChecked() else "auto"

        with self.queue_lock:
            if all(f.get("stato") == "completato" for f in self.coda_files):
                for f in self.coda_files:
                    f["stato"] = "in_attesa"
            self._active_file_path = None
            first_active_set = False
            for f in self.coda_files:
                if f["stato"] != "completato":
                    f["perc"] = 0
                    f["t_trasc"] = 0.0
                    f["t_rim"] = 0.0
                    f["err_dettaglio"] = ""
                    if not first_active_set:
                        f["stato"] = "in_corso"
                        self._active_file_path = f["path"]
                        first_active_set = True
                    else:
                        f["stato"] = "in_attesa"

        self.btn_avvia.setEnabled(False)
        self.btn_pausa.setEnabled(True)
        self.btn_pausa.setText(self.t("btn_pause"))
        self.btn_pausa.setStyleSheet("")
        self.btn_ferma.setEnabled(True)
        self.prog_bar.setValue(0)
        self._imposta_abilitazione_modello(False)

        # Avviso arancione caldo caricamento modello (#fbbf24)
        if hasattr(self, 'spinner_loading'):
            self.spinner_loading.start()
        self.lbl_stato.setStyleSheet("color: #fbbf24; font-size: 13px; font-weight: 600; background: transparent;")
        self.lbl_stato.setText(self.t("status_loading_model"))

        self._aggiorna_vista_coda()

        self.thread_lavoro = TrascrizioneWorkerThread(
            self.coda_files, modello_scelto, lingua_mode, formati,
            active_device=self.dev_type, active_compute=self.compute_type,
            lang=self.current_lang, queue_lock=self.queue_lock
        )
        self.thread_lavoro.file_avviato.connect(self._on_file_avviato)
        self.thread_lavoro.progresso_file.connect(self._on_progresso_file)
        self.thread_lavoro.progresso_totale.connect(self._on_progresso_totale)
        self.thread_lavoro.file_completato.connect(self._on_file_completato)
        self.thread_lavoro.file_errore.connect(self._on_file_errore)
        self.thread_lavoro.coda_terminata.connect(self._on_coda_terminata)
        self.thread_lavoro.start()

    def _on_file_avviato(self, idx: int, percorso: str):
        target_path = Path(percorso)
        self._active_file_path = target_path
        matched_idx = None
        for i, card in enumerate(self.card_widgets):
            if card.file_info.get("path") == target_path:
                matched_idx = i
                break
        if matched_idx is None and 0 <= idx < len(self.card_widgets):
            matched_idx = idx

        for i, card in enumerate(self.card_widgets):
            if i == matched_idx:
                if card.file_info.get("stato") not in ("completato", "errore"):
                    card.aggiorna_stato("in_corso", 0, 0, 0)
            elif card.objectName() == "cardInCorso" or card.file_info.get("stato") == "in_corso":
                vero_stato = card.file_info.get("stato", "in_attesa")
                if vero_stato not in ("completato", "errore"):
                    vero_stato = "in_attesa"
                card.aggiorna_stato(vero_stato)

    def _on_progresso_file(self, idx: int, perc: int, t_trasc: float, t_rim: float):
        target_card = None
        if getattr(self, "_active_file_path", None) is not None:
            for card in self.card_widgets:
                if card.file_info.get("path") == self._active_file_path:
                    target_card = card
                    break
        if target_card is None and 0 <= idx < len(self.card_widgets):
            if self.card_widgets[idx].objectName() == "cardInCorso":
                target_card = self.card_widgets[idx]
        if target_card is None:
            for card in self.card_widgets:
                if card.objectName() == "cardInCorso":
                    target_card = card
                    break
        if target_card is not None:
            if target_card.file_info.get("stato") in ("completato", "errore"):
                return
            target_card.aggiorna_stato("in_corso", perc, t_trasc, t_rim)

    def _on_progresso_totale(self, perc_tot: int, txt_tot: str):
        self.lbl_stato.setStyleSheet("color: #d4d4d8; font-size: 12px; background: transparent;")
        self.prog_bar.setValue(perc_tot)
        self.lbl_stato.setText(txt_tot)
        is_loading = any(k in txt_tot.lower() for k in ["inizializzaz", "initializ", "caricamento", "loading", "attendere", "wait"]) and not ("download modello:" in txt_tot.lower() or "downloading model:" in txt_tot.lower())
        if is_loading:
            if hasattr(self, 'spinner_loading'):
                self.spinner_loading.start()
        else:
            if hasattr(self, 'spinner_loading'):
                self.spinner_loading.stop()

    def _on_file_completato(self, idx: int, percorso: str):
        target_path = Path(percorso)
        for card in self.card_widgets:
            if card.file_info.get("path") == target_path:
                card.aggiorna_stato("completato")
                return
        if 0 <= idx < len(self.card_widgets) and self.card_widgets[idx].file_info.get("stato") == "completato":
            self.card_widgets[idx].aggiorna_stato("completato")

    def _on_file_errore(self, idx: int, err: str):
        if 0 <= idx < len(self.card_widgets) and self.card_widgets[idx].file_info.get("stato") == "errore":
            self.card_widgets[idx].aggiorna_stato("errore", err_dettaglio=err)
            return
        found_err = False
        for card in self.card_widgets:
            if card.file_info.get("stato") == "errore":
                if not card.file_info.get("err_dettaglio") or card.objectName() != "cardErrore":
                    card.aggiorna_stato("errore", err_dettaglio=err)
                found_err = True
        if found_err:
            return
        if 0 <= idx < len(self.card_widgets) and self.card_widgets[idx].objectName() == "cardInCorso":
            self.card_widgets[idx].aggiorna_stato("errore", err_dettaglio=err)
            return
        for card in self.card_widgets:
            if card.objectName() == "cardInCorso":
                card.aggiorna_stato("errore", err_dettaglio=err)
                break

    def _on_coda_terminata(self, completati: int, cartella_out: str):
        if hasattr(self, 'spinner_loading'):
            self.spinner_loading.stop()
        self._active_file_path = None
        with self.queue_lock:
            for f in self.coda_files:
                if f.get("stato") == "in_corso":
                    f["stato"] = "in_attesa"
                    f["perc"] = 0
                    f["t_trasc"] = 0.0
                    f["t_rim"] = 0.0
        self.btn_avvia.setEnabled(True)
        self.btn_pausa.setEnabled(False)
        self.btn_pausa.setText(self.t("btn_pause"))
        self.btn_pausa.setStyleSheet("")
        self.btn_ferma.setEnabled(False)
        self.prog_bar.setValue(100 if completati > 0 else 0)
        self._imposta_abilitazione_modello(True)

        if cartella_out and cartella_out.startswith("Errore"):
            self.lbl_stato.setStyleSheet("color: #ef4444; font-size: 12px; font-weight: 600; background: transparent;")
            self.lbl_stato.setText(cartella_out)
        else:
            self.lbl_stato.setStyleSheet("color: #d4d4d8; font-size: 12px; background: transparent;")
            msg = self.t("finished_msg", count=completati) if completati > 0 else self.t("cancelled_msg")
            self.lbl_stato.setText(msg)

        self._aggiorna_vista_coda()

        if completati > 0:
            play_completion_alert()
            if cartella_out and os.path.exists(cartella_out):
                open_directory_in_explorer(cartella_out)

    def toggle_pausa(self):
        if not self.thread_lavoro:
            return
        if not self.thread_lavoro.is_paused:
            self.thread_lavoro.pausa()
            if hasattr(self, 'spinner_loading'):
                self.spinner_loading.stop()
            self.btn_pausa.setText(self.t("btn_resume"))
            self.btn_pausa.setStyleSheet("QPushButton#btnPausa { background-color: #10b981; } QPushButton#btnPausa:hover { background-color: #059669; }")
            self.lbl_stato.setStyleSheet("color: #d4d4d8; font-size: 12px; background: transparent;")
            self.lbl_stato.setText(self.t("status_paused"))
        else:
            self.thread_lavoro.riprendi()
            self.btn_pausa.setText(self.t("btn_pause"))
            self.btn_pausa.setStyleSheet("")
            self.lbl_stato.setStyleSheet("color: #d4d4d8; font-size: 12px; background: transparent;")
            self.lbl_stato.setText(self.t("status_resumed"))

    def ferma_trascrizione(self):
        if hasattr(self, 'spinner_loading'):
            self.spinner_loading.stop()
        if not self.thread_lavoro:
            return
        self.lbl_stato.setStyleSheet("color: #d4d4d8; font-size: 12px; background: transparent;")
        self.lbl_stato.setText(self.t("status_cancelling"))
        self.thread_lavoro.ferma()
        self.thread_lavoro.wait()
        self._on_coda_terminata(0, "")

    def closeEvent(self, event):
        if self.thread_lavoro and self.thread_lavoro.isRunning():
            self.thread_lavoro.ferma()
            self.thread_lavoro.wait(3000)
        event.accept()

def avvia_gui():
    app = QApplication(sys.argv)
    icon_ico = DIR_CORRENTE / "wispr.ico"
    icon_black = DIR_CORRENTE / "app_icon_black.png"
    icon_png = DIR_CORRENTE / "wispr.png"
    if icon_ico.exists():
        app.setWindowIcon(QIcon(str(icon_ico)))
    elif icon_black.exists():
        app.setWindowIcon(QIcon(str(icon_black)))
    elif icon_png.exists():
        app.setWindowIcon(QIcon(str(icon_png)))
    finestra = WhisperStudioWindow()
    finestra.show()
    finestra.raise_()
    finestra.activateWindow()
    sys.exit(app.exec())

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and (sys.argv[1].startswith("--multiprocessing") or sys.argv[1] == "-c"):
        sys.exit(0)
    avvia_gui()
