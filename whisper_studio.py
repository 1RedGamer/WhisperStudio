#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
========================================================================
                          WHISPER STUDIO
                 Studio Edition (v2.7) — macOS Native
       Offline Audio & Video Transcription with Apple Silicon Metal (MLX)
========================================================================
"""

import os
import sys
import re
import io
import time
import shutil
import subprocess
import multiprocessing
import ctypes
from pathlib import Path

# Multiprocessing freeze support for PyInstaller on macOS
multiprocessing.freeze_support()
try:
    multiprocessing.set_start_method("fork", force=True)
except Exception:
    pass

# Safe stdout/stderr protection for PyInstaller windowed GUI apps (--windowed)
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QCheckBox, QProgressBar, QButtonGroup,
    QListWidget, QListWidgetItem, QFrame, QFileDialog, QMessageBox,
    QAbstractItemView, QDialog, QSizePolicy, QTextBrowser, QMenu
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QPoint, QMimeData, QSize, QSettings, QLocale
from PyQt6.QtGui import QIcon, QPixmap, QDragEnterEvent, QDropEvent, QDrag, QPainter, QColor, QPen, QPainterPath, QAction, QActionGroup

# Resolve current directory for ffmpeg and bundled assets
if getattr(sys, 'frozen', False):
    DIR_CORRENTE = Path(sys._MEIPASS)
else:
    DIR_CORRENTE = Path(__file__).resolve().parent

VALID_EXTENSIONS = {
    ".mp3", ".m4a", ".wav", ".mp4", ".mov", ".mkv",
    ".aac", ".ogg", ".webm", ".flac", ".alac", ".opus", ".wma", ".aiff"
}

def find_ffmpeg() -> str:
    """Locate bundled ffmpeg binary, system installations, or standard PATH entries."""
    candidates = []
    if getattr(sys, 'frozen', False):
        meipass = Path(sys._MEIPASS)
        candidates.extend([
            meipass / "ffmpeg",
            meipass.parent / "Resources" / "ffmpeg",
            meipass.parent / "Frameworks" / "ffmpeg",
            meipass.parent / "MacOS" / "ffmpeg",
        ])
    exe_p = Path(sys.executable).resolve()
    candidates.extend([
        exe_p.parent / "ffmpeg",
        exe_p.parent.parent / "Frameworks" / "ffmpeg",
        exe_p.parent.parent / "Resources" / "ffmpeg",
        DIR_CORRENTE / "ffmpeg",
        Path("/opt/homebrew/bin/ffmpeg"),
        Path("/usr/local/bin/ffmpeg")
    ])

    for c in candidates:
        if c.is_file():
            try:
                os.chmod(c, 0o755)
            except Exception:
                pass
            if os.access(c, os.X_OK):
                return str(c.resolve())

    which_ff = shutil.which("ffmpeg")
    if which_ff:
        return which_ff
    return "ffmpeg"

# Prepend ffmpeg directory to PATH for helper libraries
FFMPEG_BIN = find_ffmpeg()
if FFMPEG_BIN and os.path.isabs(FFMPEG_BIN):
    ff_dir = str(Path(FFMPEG_BIN).parent)
    if ff_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{ff_dir}:{os.environ.get('PATH', '')}"

def apply_mlx_whisper_patch():
    """Ensure mlx_whisper.audio uses the exact localized ffmpeg binary found."""
    try:
        import mlx_whisper.audio
        import mlx.core as mx
        import numpy as np

        ff_bin = find_ffmpeg()
        if not ff_bin:
            return

        def patch_load_audio(file, sr=16000, from_stdin=False):
            if from_stdin:
                cmd = [ff_bin, "-i", "pipe:0"]
            else:
                cmd = [ff_bin, "-nostdin", "-i", str(file)]
            cmd.extend([
                "-threads", "0",
                "-f", "s16le",
                "-ac", "1",
                "-acodec", "pcm_s16le",
                "-ar", str(sr),
                "-"
            ])
            try:
                out = subprocess.run(cmd, capture_output=True, check=True).stdout
            except subprocess.CalledProcessError as err:
                err_msg = err.stderr.decode("utf-8", errors="replace") if err.stderr else str(err)
                raise RuntimeError(f"FFmpeg decoding error: {err_msg}") from err
            return mx.array(np.frombuffer(out, np.int16)).flatten().astype(mx.float32) / 32768.0

        mlx_whisper.audio.load_audio = patch_load_audio
    except Exception:
        pass

# Apply the patch immediately upon launch
apply_mlx_whisper_patch()

def get_file_duration(file_path):
    """Retrieve audio/video duration in seconds using ffmpeg probe."""
    ff = find_ffmpeg()
    cmd = [ff, "-i", str(file_path)]
    try:
        res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", res.stderr)
        if m:
            h, minuti, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
            return max(1.0, h * 3600 + minuti * 60 + s)
    except Exception:
        pass
    return 60.0

def format_time(seconds):
    """Format seconds into HH:MM:SS or MM:SS."""
    s = int(round(seconds))
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def format_size(bytes_size):
    """Format bytes into readable units."""
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.1f} KB"
    else:
        return f"{bytes_size / (1024 * 1024):.1f} MB"

def generate_output_path(p_in: Path, fmt: str, lang: str = "it") -> Path:
    """Generate clean transcription output path in the source folder."""
    stem = p_in.stem
    prefix = "Trascrizione" if lang == "it" else "Transcription"
    m = re.search(r"(\d{4})(\d{2})(\d{2})[-_ ]*(\d{2})(\d{2})", stem)
    if m:
        anno_full, mese, giorno, ora, minuti = m.groups()
        anno_breve = anno_full[-2:]
        nuovo_nome = f"{prefix} {giorno}-{mese}-{anno_breve} - {ora}.{minuti}.{fmt}"
    else:
        pulito = re.sub(r"(?i)^(registratore|recording)\s*[-_]?\s*", "", stem).strip()
        if not pulito:
            pulito = stem
        nuovo_nome = f"{prefix} {pulito}.{fmt}"
    return p_in.with_name(nuovo_nome)

def show_macos_notification(title: str, message: str):
    """Trigger native macOS Notification Center banner with sound."""
    try:
        t = title.replace('"', '\"')
        m = message.replace('"', '\"')
        script = f'display notification "{m}" with title "{t}" sound name "Glass"'
        subprocess.run(["osascript", "-e", script], check=False)
    except Exception:
        pass

def get_total_ram_gb():
    """Get total installed physical RAM in GB."""
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        try:
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"]).strip()
            return int(out) / (1024 ** 3)
        except Exception:
            return 16.0

def get_system_ram_gb():
    """Return overall macOS system RAM status: (used_ram_gb, total_ram_gb)."""
    try:
        import psutil
        vm = psutil.virtual_memory()
        tot = vm.total / (1024 ** 3)
        usata = (vm.total - vm.available) / (1024 ** 3)
        return round(usata, 1), round(tot, 1)
    except Exception:
        tot = get_total_ram_gb()
        return 0.0, round(tot, 1)

def detect_system_language() -> str:
    """Detect system language on macOS; returns 'it' or 'en'."""
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
        "win_title": "Whisper Studio v2.7",
        "hw_label": "🍏 Apple Silicon • GPU Metal Accelerata",
        "ram_label": "🧠 Memoria RAM: {used:.1f} GB / {total:.0f} GB in uso",
        "section_model": "MODELLO DI TRASCRIZIONE",
        "auto_tag": "🤖 Modalità Automatica Attiva",
        "model_large_title": "💎 Alta Fedeltà (Large-v3 Standard)",
        "model_turbo_title": "⚡ Alta Velocità (Turbo)",
        "auto_desc_large": "Rilevati {ram:.0f} GB RAM • Massima accuratezza",
        "auto_desc_turbo": "Rilevati {ram:.0f} GB RAM • Velocità e memoria ottimizzate",
        "btn_switch_manual": "⚙️ Passa a Selezione Manuale",
        "manual_tag": "⚙️ Selezione Manuale",
        "btn_large": "💎 Alta Fedeltà\nLarge-v3 Standard (Accuratezza)",
        "btn_small": "⚡ Alta Velocità\nTurbo (Super Rapido)",
        "btn_return_auto": "🔄 Ripristina Modalità Automatica",
        "warn_large_8gb": "⚠️ Attenzione: Large-v3 Standard richiede molta memoria e rallenterà sensibilmente un Mac da 8 GB.",
        "warn_turbo_8gb": "⚡ Consigliato per 8 GB RAM: il modello Turbo è ottimizzato, fluido e velocissimo per il tuo Mac.",
        "warn_large_gt8gb": "💎 Consigliato per il tuo Mac ({ram:.0f} GB RAM): massima precisione e fedeltà.",
        "warn_turbo_gt8gb": "⚠️ Attenzione: la modalità Turbo è velocissima ma meno accurata rispetto a Large-v3.",
        "section_lang": "LINGUA AUDIO",
        "btn_lang_primary": "🇮🇹 Italiano",
        "btn_lang_auto": "🌐 Rileva Auto",
        "lang_subtitle": "Riconoscimento accenti e punteggiatura naturale",
        "section_formats": "FORMATI DI ESPORTAZIONE",
        "chk_txt": "File di Testo (.txt)",
        "chk_docx": "Documento Word (.docx)",
        "formats_subtitle": "Salvataggio automatico con data nella stessa cartella.",
        "footer": "100% Offline • Nessun dato inviato online",
        "queue_title": "<b>Coda Trascrizioni</b> ({count} file)",
        "btn_add": "➕ Aggiungi File",
        "btn_clear": "🗑 Svuota Coda",
        "empty_title": "<b>Trascina qui i tuoi file audio o video</b>",
        "empty_subtitle": "oppure clicca su '➕ Aggiungi File' in alto\nSupporta MP3, M4A, WAV, MP4, MOV, MKV, FLAC, OPUS...",
        "status_ready": "Pronto. Trascina i file nella coda o clicca su '➕ Aggiungi File'.",
        "status_loading_model": "⏳ Caricamento modello in corso: attendere...",
        "status_paused": "⏸ Trascrizione in pausa.",
        "status_resumed": "▶ Trascrizione ripresa.",
        "status_cancelling": "Arresto in corso...",
        "btn_cancel": "■ ANNULLA",
        "btn_pause": "⏸ PAUSA",
        "btn_resume": "▶ RIPRENDI",
        "btn_start": "🚀 AVVIA TRASCRIZIONE",
        "card_waiting": "⏸ In attesa",
        "card_completed": "✅ Completato",
        "card_error": "❌ Errore",
        "card_done": "Pronto",
        "card_failed": "Fallito",
        "card_elapsed": "⏱️ {elapsed} trascorsi • rimasti ~{rem}",
        "tb_ready": "Pronto",
        "tb_loading": "Caricamento...",
        "tb_paused": "In pausa",
        "tb_completed": "Completato! ✨",
        "tb_cancelled": "Arrestato",
        "tb_queued": "{count} file in coda",
        "dlg_empty_title": "Coda vuota",
        "dlg_empty_msg": "Aggiungi almeno un file audio o video da trascrivere.",
        "dlg_formats_title": "Formati",
        "dlg_formats_msg": "Seleziona almeno un formato di output (.txt o .docx).",
        "dlg_clear_title": "Attenzione",
        "dlg_clear_msg": "Impossibile svuotare la coda durante l'elaborazione.",
        "dlg_manual_title": "Passaggio a Selezione Manuale",
        "dlg_manual_header": "⚠️ Passaggio alla Modalità Manuale",
        "dlg_manual_msg": "La modalità automatica è pensata per sfruttare tutta la potenza e la memoria del tuo Mac.<br><br>In modalità manuale potresti <b>ridurre la precisione</b> delle tue trascrizioni o <b>rallentarle drasticamente</b>.<br><br>Vuoi procedere comunque con la selezione manuale?",
        "dlg_manual_cancel": "Annulla",
        "dlg_manual_confirm": "Passa a Manuale",
        "file_dialog_title": "Seleziona file audio o video da trascrivere",
        "file_dialog_filter": "File Multimediali (*.mp3 *.m4a *.wav *.mp4 *.mov *.mkv *.aac *.ogg *.webm *.flac *.opus *.alac *.wma);;Tutti i file (*.*)",
        "menu_language": "Lingua",
        "menu_help": "Aiuto",
        "menu_guide": "Guida di Whisper Studio",
        "help_title": "Guida & Istruzioni — Whisper Studio v2.7",
        "help_close": "Chiudi",
        "notif_completed": "Trascrizione completata ({count} file)!",
        "progress_total": "Avanzamento Totale: {perc}% (File {curr} di {total}) | ⏱️ {elapsed} trascorsi • rimasti ~{rem} sul totale",
        "finished_msg": "Trascrizione completata: {count} file elaborati con successo.",
        "cancelled_msg": "Operazione interrotta."
    },
    "en": {
        "win_title": "Whisper Studio v2.7",
        "hw_label": "🍏 Apple Silicon • Metal GPU Accelerated",
        "ram_label": "🧠 System RAM: {used:.1f} GB / {total:.0f} GB in use",
        "section_model": "TRANSCRIPTION MODEL",
        "auto_tag": "🤖 Automatic Mode Active",
        "model_large_title": "💎 High Fidelity (Large-v3 Standard)",
        "model_turbo_title": "⚡ High Speed (Turbo)",
        "auto_desc_large": "Detected {ram:.0f} GB RAM • Maximum accuracy",
        "auto_desc_turbo": "Detected {ram:.0f} GB RAM • Speed and memory optimized",
        "btn_switch_manual": "⚙️ Switch to Manual Selection",
        "manual_tag": "⚙️ Manual Selection",
        "btn_large": "💎 High Fidelity\nLarge-v3 Standard (Accuracy)",
        "btn_small": "⚡ High Speed\nTurbo (Super Fast)",
        "btn_return_auto": "🔄 Restore Automatic Mode",
        "warn_large_8gb": "⚠️ Warning: Large-v3 Standard requires significant RAM and will noticeably slow down an 8 GB Mac.",
        "warn_turbo_8gb": "⚡ Recommended for 8 GB RAM: Turbo model is optimized, smooth and lightning-fast for your Mac.",
        "warn_large_gt8gb": "💎 Recommended for your Mac ({ram:.0f} GB RAM): maximum precision and fidelity.",
        "warn_turbo_gt8gb": "⚠️ Note: Turbo mode is very fast but slightly less accurate than Large-v3.",
        "section_lang": "AUDIO LANGUAGE",
        "btn_lang_primary": "🇺🇸 English",
        "btn_lang_auto": "🌐 Auto Detect",
        "lang_subtitle": "Natural accents and punctuation recognition",
        "section_formats": "EXPORT FORMATS",
        "chk_txt": "Text File (.txt)",
        "chk_docx": "Word Document (.docx)",
        "formats_subtitle": "Automatically saved next to source audio files.",
        "footer": "100% Offline • No data sent online",
        "queue_title": "<b>Transcription Queue</b> ({count} files)",
        "btn_add": "➕ Add Files",
        "btn_clear": "🗑 Clear Queue",
        "empty_title": "<b>Drag and drop your audio or video files here</b>",
        "empty_subtitle": "or click '➕ Add Files' above\nSupports MP3, M4A, WAV, MP4, MOV, MKV, FLAC, OPUS...",
        "status_ready": "Ready. Drag files into queue or click '➕ Add Files'.",
        "status_loading_model": "⏳ Loading model: please wait...",
        "status_paused": "⏸ Transcription paused.",
        "status_resumed": "▶ Transcription resumed.",
        "status_cancelling": "Stopping transcription...",
        "btn_cancel": "■ CANCEL",
        "btn_pause": "⏸ PAUSE",
        "btn_resume": "▶ RESUME",
        "btn_start": "🚀 START TRANSCRIPTION",
        "card_waiting": "⏸ Waiting",
        "card_completed": "✅ Completed",
        "card_error": "❌ Error",
        "card_done": "Done",
        "card_failed": "Failed",
        "card_elapsed": "⏱️ {elapsed} elapsed • ~{rem} left",
        "tb_ready": "Ready",
        "tb_loading": "Loading...",
        "tb_paused": "Paused",
        "tb_completed": "Completed! ✨",
        "tb_cancelled": "Stopped",
        "tb_queued": "{count} files in queue",
        "dlg_empty_title": "Empty Queue",
        "dlg_empty_msg": "Please add at least one audio or video file to transcribe.",
        "dlg_formats_title": "Formats",
        "dlg_formats_msg": "Please select at least one output format (.txt or .docx).",
        "dlg_clear_title": "Warning",
        "dlg_clear_msg": "Cannot clear queue during active transcription.",
        "dlg_manual_title": "Switch to Manual Selection",
        "dlg_manual_header": "⚠️ Switch to Manual Selection",
        "dlg_manual_msg": "Automatic mode is configured to take full advantage of your Mac's hardware and unified memory.<br><br>In manual mode, selecting an unsuitable model could <b>reduce transcription accuracy</b> or <b>significantly slow down processing</b>.<br><br>Do you want to proceed with manual selection?",
        "dlg_manual_cancel": "Cancel",
        "dlg_manual_confirm": "Switch to Manual",
        "file_dialog_title": "Select audio or video files to transcribe",
        "file_dialog_filter": "Media Files (*.mp3 *.m4a *.wav *.mp4 *.mov *.mkv *.aac *.ogg *.webm *.flac *.opus *.alac *.wma);;All Files (*.*)",
        "menu_language": "Language",
        "menu_help": "Help",
        "menu_guide": "Whisper Studio Guide",
        "help_title": "User Guide — Whisper Studio v2.7",
        "help_close": "Close",
        "notif_completed": "Transcription completed ({count} files)!",
        "progress_total": "Total Progress: {perc}% (File {curr} of {total}) | ⏱️ {elapsed} elapsed • ~{rem} remaining overall",
        "finished_msg": "Transcription completed: {count} files processed successfully.",
        "cancelled_msg": "Operation cancelled."
    }
}

# ==============================================================================
# DOWNLOAD PROGRESS MANAGER (Hugging Face)
# ==============================================================================
def check_or_download_model(repo_id: str, callback_progresso=None, lang: str = "it"):
    from huggingface_hub import snapshot_download
    try:
        snapshot_download(repo_id=repo_id, local_files_only=True)
        return True
    except Exception:
        pass

    if callback_progresso:
        msg = f"Avvio download {repo_id} da Hugging Face..." if lang == "it" else f"Downloading {repo_id} from Hugging Face..."
        callback_progresso(0.0, msg)

    try:
        snapshot_download(repo_id=repo_id, local_files_only=False)
        if callback_progresso:
            msg = "Download completato con successo!" if lang == "it" else "Download completed successfully!"
            callback_progresso(1.0, msg)
        return True
    except Exception as e:
        if callback_progresso:
            msg = f"Errore download: {e}" if lang == "it" else f"Download error: {e}"
            callback_progresso(0.0, msg)
        return False

# ==============================================================================
# PROCESS / STDOUT INTERCEPTOR FOR QTHREAD
# ==============================================================================
class ThreadStdoutInterceptor:
    def __init__(self, durata_file, callback_progresso, check_abort, check_pause, fallback_stream=None):
        self.durata_file = max(durata_file, 1.0)
        self.callback_progresso = callback_progresso
        self.check_abort = check_abort
        self.check_pause = check_pause
        self.fallback_stream = fallback_stream
        self.start_time = time.time()
        self.regex = re.compile(r"-->\s*([0-9:\.]+)")
        self.ultimo_invio = 0.0
        self.encoding = "utf-8"
        self.errors = "replace"

    def write(self, text):
        if not text:
            return 0
        if self.fallback_stream:
            try:
                self.fallback_stream.write(text)
            except Exception:
                pass

        if self.check_abort():
            raise InterruptedError("Trascrizione interrotta")
        while self.check_pause():
            time.sleep(0.1)
            if self.check_abort():
                raise InterruptedError("Trascrizione interrotta")

        m = self.regex.search(text)
        if m:
            ts_str = m.group(1).strip()
            try:
                parti = ts_str.split(":")
                if len(parti) == 3:
                    sec_att = float(parti[0]) * 3600 + float(parti[1]) * 60 + float(parti[2])
                elif len(parti) == 2:
                    sec_att = float(parti[0]) * 60 + float(parti[1])
                else:
                    sec_att = float(parti[0])

                sec_att = min(sec_att, self.durata_file)
                perc = int((sec_att / self.durata_file) * 100)
                trascorso = time.time() - self.start_time
                if sec_att > 0 and trascorso > 0:
                    velocita = sec_att / trascorso
                    rimasto = max(0.0, (self.durata_file - sec_att) / velocita)
                else:
                    rimasto = 0.0

                adesso = time.time()
                if adesso - self.ultimo_invio >= 0.25 or perc >= 100:
                    self.ultimo_invio = adesso
                    self.callback_progresso(sec_att, perc, trascorso, rimasto)
            except Exception:
                pass
        return len(text)

    def flush(self):
        if self.fallback_stream:
            try:
                self.fallback_stream.flush()
            except Exception:
                pass

    def isatty(self):
        return False

    def writable(self):
        return True

    def readable(self):
        return False

    def seekable(self):
        return False

# ==============================================================================
# ORIGINAL QSS STYLESHEET (100% UNTOUCHED, EXACT PIXEL-PERFECT ORIGINAL)
# ==============================================================================
QSS_STILE = """
QMainWindow {
    background-color: #121214;
}
QWidget {
    color: #e4e4e7;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 13px;
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

/* Schede della coda per stato (altezza fissa e zero sovrapposizioni) */
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
QPushButton.toggleBtn:checked:disabled, QPushButton[class="toggleBtn"]:checked:disabled {
    background-color: #24223d;
    border: 1.5px solid #4338ca;
    color: #94a3b8;
}

QPushButton#btnLargeModello, QPushButton#btnSmallModello {
    background-color: #222226;
    border: 1.5px solid #383840;
    border-radius: 9px;
    color: #ffffff;
    font-size: 12px;
    font-weight: 600;
    padding: 5px 12px;
    text-align: left;
    min-height: 46px;
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
QPushButton#btnLargeModello:disabled, QPushButton#btnSmallModello:disabled {
    background-color: #1a1a1d;
    border: 1.5px solid #27272a;
    color: #52525b;
}
QPushButton#btnLargeModello:checked:disabled, QPushButton#btnSmallModello:checked:disabled {
    background-color: #24223d;
    border: 1.5px solid #4338ca;
    color: #94a3b8;
}
QPushButton#btnPassaManuale:disabled, QPushButton#btnTornaAuto:disabled {
    background-color: #1a1a1d;
    border: 1px solid #27272a;
    color: #52525b;
}
QPushButton#btnAdd:disabled, QPushButton#btnClear:disabled {
    background-color: #1a1a1d;
    border: 1px solid #27272a;
    color: #52525b;
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

/* Pulsante Svuota Coda - Diventa Rosso al passaggio del mouse */
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

/* QListWidget con Drag & Drop fluido nativo */
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
# WORKER THREAD (100% IN-PROCESS, ZERO SUBPROCESS, ZERO DOPPIA APP NEL DOCK)
# ==============================================================================
class TrascrizioneWorkerThread(QThread):
    progresso_file = pyqtSignal(int, int, float, float) # idx, perc, trascorso, rimasto
    progresso_totale = pyqtSignal(int, str)             # perc_tot, text_tot
    file_completato = pyqtSignal(int, str)
    file_errore = pyqtSignal(int, str)
    coda_terminata = pyqtSignal(int, str)

    def __init__(self, coda_files, repo_modello, lingua_mode, formati, lang="it"):
        super().__init__()
        self.coda_files = coda_files
        self.repo_modello = repo_modello
        self.lingua_mode = lingua_mode
        self.formati = formati
        self.lang = lang
        self.abort_requested = False
        self.is_paused = False
        self.indice_corrente = 0
        self.start_time_globale = 0.0
        self.secondi_fatti_fino_a_qui = 0.0

    def run(self):
        apply_mlx_whisper_patch()
        import mlx_whisper
        import mlx.core as mx
        from docx import Document

        def cb_dl(p, txt):
            self.progresso_totale.emit(int(p * 100), txt)

        ok = check_or_download_model(self.repo_modello, callback_progresso=cb_dl, lang=self.lang)
        if not ok:
            err_msg = "Errore nel download del modello." if self.lang == "it" else "Error downloading model."
            self.coda_terminata.emit(0, err_msg)
            return

        self.start_time_globale = time.time()
        durata_totale_audio = max(1.0, sum(f["durata"] for f in self.coda_files))
        completati = 0
        cartella_out = ""
        orig_stdout = sys.stdout

        try:
            for idx, item in enumerate(self.coda_files):
                if self.abort_requested:
                    break
                if item["stato"] == "completato":
                    self.secondi_fatti_fino_a_qui += item["durata"]
                    continue

                self.indice_corrente = idx
                p_in = item["path"]
                durata_file = item["durata"]
                cartella_out = str(p_in.parent)

                def on_chunk(sec_att, perc_file, t_trasc, t_rim):
                    self.progresso_file.emit(idx, perc_file, t_trasc, t_rim)
                    sec_totali_fatti = self.secondi_fatti_fino_a_qui + sec_att
                    perc_globale = min(100, int((sec_totali_fatti / durata_totale_audio) * 100))
                    tempo_reale = max(0.1, time.time() - self.start_time_globale)
                    velocita = sec_totali_fatti / tempo_reale
                    rimasto_totale = max(0.0, (durata_totale_audio - sec_totali_fatti) / velocita) if velocita > 0 else 0.0

                    tmpl = STRINGS[self.lang]["progress_total"]
                    txt_globale = tmpl.format(
                        perc=perc_globale,
                        curr=idx + 1,
                        total=len(self.coda_files),
                        elapsed=format_time(tempo_reale),
                        rem=format_time(rimasto_totale)
                    )
                    self.progresso_totale.emit(perc_globale, txt_globale)

                interceptor = ThreadStdoutInterceptor(
                    durata_file=durata_file,
                    callback_progresso=on_chunk,
                    check_abort=lambda: self.abort_requested,
                    check_pause=lambda: self.is_paused,
                    fallback_stream=orig_stdout
                )
                sys.stdout = interceptor

                lingua = None if self.lingua_mode == "auto" else self.lingua_mode
                kwargs = {
                    "path_or_hf_repo": self.repo_modello,
                    "verbose": True
                }
                if lingua:
                    kwargs["language"] = lingua

                try:
                    try:
                        mx.clear_cache()
                    except Exception:
                        pass

                    risultato = mlx_whisper.transcribe(str(p_in), **kwargs)

                    segments = risultato.get("segments", [])
                    paragrafi = []
                    buffer = []
                    for s in segments:
                        t = s.get("text", "").strip()
                        if t:
                            buffer.append(t)
                            if len(buffer) >= 4:
                                paragrafi.append(" ".join(buffer))
                                buffer = []
                    if buffer:
                        paragrafi.append(" ".join(buffer))
                    testo_completo = "\n\n".join(paragrafi)

                    for fmt in self.formati:
                        p_out = generate_output_path(p_in, fmt, lang=self.lang)
                        if fmt == "docx":
                            doc = Document()
                            doc.add_heading(p_out.stem, level=1)
                            for par in paragrafi:
                                doc.add_paragraph(par)
                            doc.save(p_out)
                        else:
                            with open(p_out, "w", encoding="utf-8") as f:
                                f.write(testo_completo)

                    item["stato"] = "completato"
                    completati += 1
                    self.secondi_fatti_fino_a_qui += durata_file
                    self.file_completato.emit(idx, str(p_in))

                    try:
                        mx.clear_cache()
                    except Exception:
                        pass

                except InterruptedError:
                    item["stato"] = "in_attesa"
                    break
                except Exception as e:
                    import traceback
                    tb_str = traceback.format_exc()
                    try:
                        with open("/tmp/whisper_studio.log", "a", encoding="utf-8") as lf:
                            lf.write(f"\n--- ERRORE [{time.ctime()}] File {p_in} ---\n{tb_str}\n")
                    except Exception:
                        pass
                    item["stato"] = "errore"
                    self.file_errore.emit(idx, str(e))
                    self.secondi_fatti_fino_a_qui += durata_file

        finally:
            sys.stdout = orig_stdout
            try:
                mx.clear_cache()
            except Exception:
                pass

        self.coda_terminata.emit(completati, cartella_out)

    def pausa(self):
        self.is_paused = True

    def riprendi(self):
        self.is_paused = False

    def ferma(self):
        self.abort_requested = True
        self.is_paused = False

# ==============================================================================
# BARRA DI AVANZAMENTO PERSONALIZZATA (CLIPPING ANTI-GLITCH A QUALSIASI PERCENTUALE)
# ==============================================================================
class WhisperProgressBar(QProgressBar):
    """Progress bar with antialiased rendering and continuous curved clip path."""
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
                painter.setClipPath(bg_path)
                fill_path = QPainterPath()
                fill_path.addRoundedRect(0.0, 0.0, fill_w, h, radius, radius)
                painter.fillPath(fill_path, QColor("#818cf8"))

# ==============================================================================
# WIDGET SCHEDA CODA (EVIDENZIAZIONE VIOLA/BLU, FANTASMA COMPATTO STILE FINDER)
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
            parent_list = self.parentWidget()
            while parent_list and not isinstance(parent_list, QListWidget):
                parent_list = parent_list.parentWidget()
            if parent_list:
                parent_list.setCurrentRow(self.idx)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            if (event.pos() - self._drag_start_pos).manhattanLength() >= 8:
                self._avvia_drag(event.pos())
                self._drag_start_pos = None
                return
        super().mouseMoveEvent(event)

    def _avvia_drag(self, hotspot):
        pixmap = self.grab()

        sc_w = max(140, int(pixmap.width() * 0.40))
        sc_h = max(34, int(pixmap.height() * 0.40))
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

        self.set_selezionato(True)
        drag.exec(Qt.DropAction.MoveAction)

    def aggiorna_stato(self, stato, perc=0, t_trasc=0, t_rim=0, err_dettaglio=""):
        self.file_info["stato"] = stato
        s = STRINGS[self.lang]
        if stato == "in_corso":
            self.setObjectName("cardInCorso")
            self.lbl_stato_txt.setText(f"{perc}%")
            self.lbl_stato_txt.setStyleSheet("font-size: 19px; font-weight: 800; color: #818cf8; background: transparent; border: none;")
            self.lbl_stima_file.setText(s["card_elapsed"].format(elapsed=format_time(t_trasc), rem=format_time(t_rim)))
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
            self.lbl_stima_file.setText(err_dettaglio[:30] if err_dettaglio else s["card_failed"])
            if err_dettaglio:
                self.setToolTip(f"Errore: {err_dettaglio}")
            self.btn_del.setEnabled(True)
        else:
            self.setObjectName("cardInAttesa")
            self.lbl_stato_txt.setText(s["card_waiting"])
            self.lbl_stato_txt.setStyleSheet("font-size: 12px; font-weight: 600; color: #71717a; background: transparent; border: none;")
            self.lbl_stima_file.setText("")
            self.btn_del.setEnabled(True)
        self._applica_stile_corrente()

# ==============================================================================
# LISTA DRAG & DROP NATIVA MACOS CON TARGET BLU E FANTASMA COMPATTO
# ==============================================================================
class QueueListWidget(QListWidget):
    fileDropped = pyqtSignal(list)
    orderChanged = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setSpacing(8)
        self._current_hover_target = None

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
        if hasattr(main_win, 'thread_lavoro') and main_win.thread_lavoro and main_win.thread_lavoro.isRunning():
            event.ignore()
            return
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-whisper-queue-item"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        main_win = self.window()
        if hasattr(main_win, 'thread_lavoro') and main_win.thread_lavoro and main_win.thread_lavoro.isRunning():
            event.ignore()
            return
        if event.mimeData().hasFormat("application/x-whisper-queue-item"):
            pos = event.position().toPoint()
            drop_item = self.itemAt(pos)
            target_row = self.row(drop_item) if drop_item else (self.count() - 1)
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
        if hasattr(main_win, 'thread_lavoro') and main_win.thread_lavoro and main_win.thread_lavoro.isRunning():
            event.ignore()
            return

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
            drop_item = self.itemAt(pos)
            dst_row = self.row(drop_item) if drop_item else (self.count() - 1)

            if 0 <= src_row < self.count() and 0 <= dst_row < self.count() and src_row != dst_row:
                self.orderChanged.emit(src_row, dst_row)
            event.acceptProposedAction()

# ==============================================================================
# DIALOGO CONFERMA PASSAGGIO A MODALITÀ MANUALE (PULSANTE ANNULLA ROSSO)
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
# FINESTRA DI DIALOGO GUIDA & ISTRUZIONI (INTEGRATA NEL MENU HELP)
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
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif;
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
            <h2 style='color: #ffffff; margin-bottom: 4px;'>Whisper Studio v2.7 — Guida & Istruzioni</h2>
            <p style='color: #818cf8; font-weight: bold; margin-top: 0;'>Trascrizione Audio & Video Offline con Apple Silicon Metal (GPU MLX)</p>
            <hr style='border: 0; border-top: 1px solid #27272a;'>
            
            <h3 style='color: #10b981;'>Cos'è Whisper Studio:</h3>
            <p>Un'applicazione autonoma, portatile e completamente privata per macOS ottimizzata per chip Apple Silicon (M1, M2, M3, M4, M5). Trascrive file audio e video in <b>Testo (.txt)</b> o <b>Documento Word (.docx)</b> sfruttando al 100% la GPU Metal e la memoria unificata del tuo Mac, senza inviare dati all'esterno.</p>
            
            <h3 style='color: #818cf8;'>Gestione Modelli AI:</h3>
            <ul>
                <li><b>Modalità Automatica:</b> Rileva la RAM complessiva del Mac. Con più di 8 GB imposta <i>Large-v3 Standard</i> per la massima accuratezza; con 8 GB imposta <i>Turbo</i> per la massima fluidità e velocità.</li>
                <li><b>Modalità Manuale:</b> Clicca su <i>Passa a Selezione Manuale</i> per scegliere liberamente il modello desiderato. Durante la trascrizione (e in pausa) le impostazioni sono protette da modifiche accidentali.</li>
            </ul>

            <h3 style='color: #fbbf24;'>Come si usa:</h3>
            <ol>
                <li><b>Aggiungi File:</b> Trascina qualsiasi file audio/video nella finestra oppure clicca <i>➕ Aggiungi File</i>.</li>
                <li><b>Riordina Coda:</b> Trascina le schede verso l'alto o verso il basso per cambiare l'ordine di elaborazione (indicatore blu di destinazione).</li>
                <li><b>Controlli:</b> Clicca <i>🚀 Avvia Trascrizione</i> per avviare il batch. Puoi mettere in pausa con <i>⏸ Pausa</i> (diventa verde <i>▶ Riprendi</i>) o interrompere con <i>■ Annulla</i>.</li>
            </ol>

            <h3 style='color: #38bdf8;'>Touch Bar & Monitor Hardware:</h3>
            <p>Se utilizzi un MacBook Pro con Touch Bar troverai tutti i controlli (Annulla, Pausa/Riprendi, Avvia, barra viola e stato) direttamente sulla tastiera con consumi minimi (&lt; 200 KB RAM). In alto a sinistra è sempre visibile la memoria RAM in uso complessiva del tuo Mac.</p>

            <h3 style='color: #e4e4e7;'>Dove vengono salvati i file:</h3>
            <p>I file trascritti vengono salvati automaticamente nella stessa cartella dei file multimediali d'origine e aperti nel Finder al termine.</p>
            
            <h3 style='color: #e4e4e7;'>Formati Supportati:</h3>
            <p>MP3, WAV, M4A, AAC, MP4, MKV, FLAC, OGG, WEBM, MOV, WMA, ALAC, OPUS.</p>
            """
        else:
            return """
            <h2 style='color: #ffffff; margin-bottom: 4px;'>Whisper Studio v2.7 — User Guide & Instructions</h2>
            <p style='color: #818cf8; font-weight: bold; margin-top: 0;'>Offline Audio & Video Transcription powered by Apple Silicon Metal (MLX)</p>
            <hr style='border: 0; border-top: 1px solid #27272a;'>
            
            <h3 style='color: #10b981;'>About Whisper Studio:</h3>
            <p>A native, portable, and completely private macOS application optimized for Apple Silicon (M1, M2, M3, M4, M5). Transcribes audio and video files into <b>Plain Text (.txt)</b> or <b>Word (.docx)</b> documents leveraging 100% Metal GPU acceleration and Unified Memory, operating fully offline.</p>
            
            <h3 style='color: #818cf8;'>AI Model Management:</h3>
            <ul>
                <li><b>Automatic Mode:</b> Evaluates installed system RAM. Macs with >8 GB RAM use <i>Large-v3 Standard</i> for highest fidelity; Macs with 8 GB RAM use <i>Turbo</i> for speed and low memory pressure.</li>
                <li><b>Manual Mode:</b> Click <i>Switch to Manual Selection</i> to freely choose models. Settings are locked during active transcription and pause to guarantee session stability.</li>
            </ul>

            <h3 style='color: #fbbf24;'>How to Use:</h3>
            <ol>
                <li><b>Add Files:</b> Drag and drop audio or video files into the window, or click <i>➕ Add Files</i>.</li>
                <li><b>Reorder Queue:</b> Drag cards up or down to adjust processing priority (blue drop marker).</li>
                <li><b>Controls:</b> Click <i>🚀 Start Transcription</i> to begin. Pause anytime with <i>⏸ Pause</i> (turns green <i>▶ Resume</i>) or cancel with <i>■ Cancel</i>.</li>
            </ol>

            <h3 style='color: #38bdf8;'>Touch Bar & Hardware Monitor:</h3>
            <p>On MacBook Pro models equipped with a Touch Bar, control buttons (Cancel, Pause/Resume, Start, purple progress bar, and status) appear directly on your keyboard with ultra-low resource usage (&lt; 200 KB RAM). Real-time overall system RAM utilization is displayed at the top left.</p>

            <h3 style='color: #e4e4e7;'>Output Location:</h3>
            <p>Transcribed files are automatically saved next to the original media files and revealed in Finder upon completion.</p>
            
            <h3 style='color: #e4e4e7;'>Supported Formats:</h3>
            <p>MP3, WAV, M4A, AAC, MP4, MKV, FLAC, OGG, WEBM, MOV, WMA, ALAC, OPUS.</p>
            """

# ==============================================================================
# BRIDGE TOUCH BAR MACOS (MacBook Pro con Touch Bar)
# ==============================================================================
TOUCHBAR_CB_TYPE = ctypes.CFUNCTYPE(None, ctypes.c_int)

class TouchBarBridge:
    def __init__(self, main_window):
        self.main_window = main_window
        self.lib = None
        self._cb_ref = TOUCHBAR_CB_TYPE(self._on_action)
        self._init_lib()

    def _init_lib(self):
        candidati = [
            DIR_CORRENTE / "libtouchbar.dylib",
            Path(__file__).resolve().parent / "libtouchbar.dylib" if "__file__" in globals() else None,
            DIR_CORRENTE.parent / "Frameworks" / "libtouchbar.dylib",
            DIR_CORRENTE.parent / "Resources" / "libtouchbar.dylib",
            DIR_CORRENTE.parent / "MacOS" / "libtouchbar.dylib",
            Path(sys.executable).resolve().parent / "libtouchbar.dylib",
        ]
        for p in candidati:
            if p and p.is_file():
                try:
                    self.lib = ctypes.CDLL(str(p))
                    self.lib.attach_touchbar_to_window.argtypes = [ctypes.c_void_p, TOUCHBAR_CB_TYPE]
                    self.lib.attach_touchbar_to_window.restype = None
                    self.lib.update_touchbar_progress.argtypes = [ctypes.c_double, ctypes.c_char_p]
                    self.lib.update_touchbar_progress.restype = None
                    self.lib.update_touchbar_state.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
                    self.lib.update_touchbar_state.restype = None
                    if hasattr(self.lib, 'set_touchbar_language'):
                        self.lib.set_touchbar_language.argtypes = [ctypes.c_int]
                        self.lib.set_touchbar_language.restype = None
                    break
                except Exception:
                    pass

    def attach(self, win_id):
        if not self.lib:
            return
        try:
            self.lib.attach_touchbar_to_window(ctypes.c_void_p(int(win_id)), self._cb_ref)
        except Exception:
            pass

    def set_language(self, lang_code: int):
        if self.lib and hasattr(self.lib, 'set_touchbar_language'):
            try:
                self.lib.set_touchbar_language(ctypes.c_int(lang_code))
            except Exception:
                pass

    def update_progress(self, perc: float, status_text: str):
        if not self.lib:
            return
        try:
            self.lib.update_touchbar_progress(ctypes.c_double(perc), status_text.encode('utf-8'))
        except Exception:
            pass

    def update_state(self, is_running: bool, is_paused: bool, can_start: bool):
        if not self.lib:
            return
        try:
            self.lib.update_touchbar_state(
                ctypes.c_int(1 if is_running else 0),
                ctypes.c_int(1 if is_paused else 0),
                ctypes.c_int(1 if can_start else 0)
            )
        except Exception:
            pass

    def _on_action(self, action_id: int):
        QTimer.singleShot(0, lambda: self._dispatch_action(action_id))

    def _dispatch_action(self, action_id: int):
        if action_id == 1:
            if self.main_window.btn_avvia.isEnabled():
                self.main_window.avvia_trascrizione()
        elif action_id == 2:
            if self.main_window.btn_pausa.isEnabled():
                self.main_window.toggle_pausa()
        elif action_id == 3:
            if self.main_window.btn_ferma.isEnabled():
                self.main_window.ferma_trascrizione()

# ==============================================================================
# FINESTRA PRINCIPALE DELL'APPLICAZIONE
# ==============================================================================
class WhisperStudioWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("WhisperStudio", "WhisperStudio")
        saved_lang = self.settings.value("language", None)
        if saved_lang in ("it", "en"):
            self.current_lang = saved_lang
        else:
            self.current_lang = detect_system_language()

        self.setWindowTitle(self.t("win_title"))
        self.resize(960, 640)
        self.setMinimumSize(920, 580)
        self.setStyleSheet(QSS_STILE)
        self.setAcceptDrops(True)

        icon_png = DIR_CORRENTE / "app_icon_black.png"
        if not icon_png.exists():
            icon_png = DIR_CORRENTE / "wispr.png"
        if icon_png.exists():
            if sys.platform != "darwin" or not getattr(sys, "frozen", False):
                self.setWindowIcon(QIcon(str(icon_png)))

        self.coda_files = []
        self.card_widgets = []
        self.thread_lavoro = None
        self.modalita_manuale = False
        self.ram_totale_gb = get_total_ram_gb()

        self._setup_menubar()
        self._costruisci_interfaccia()
        self._avvia_timer_ram()

        self.touchbar = TouchBarBridge(self)
        QTimer.singleShot(250, lambda: self._init_touchbar())

    def t(self, key: str, **kwargs) -> str:
        s = STRINGS.get(self.current_lang, STRINGS["en"])
        val = s.get(key, key)
        if kwargs:
            val = val.format(**kwargs)
        return val

    def _init_touchbar(self):
        if hasattr(self, 'touchbar') and self.touchbar:
            self.touchbar.attach(self.winId())
            self.touchbar.set_language(0 if self.current_lang == "it" else 1)

    def _setup_menubar(self):
        mb = self.menuBar()

        # 1. Menu Lingua / Language direttamente nella barra superiore di macOS
        self.menu_lang = mb.addMenu(self.t("menu_language"))

        self.grp_lang = QActionGroup(self)
        self.grp_lang.setExclusive(True)

        self.act_it = QAction("🇮🇹 Italiano", self)
        self.act_it.setCheckable(True)
        self.act_it.setChecked(self.current_lang == "it")
        self.act_it.triggered.connect(lambda: self.set_language("it"))
        self.grp_lang.addAction(self.act_it)
        self.menu_lang.addAction(self.act_it)

        self.act_en = QAction("🇺🇸 English", self)
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

    def mostra_guida(self):
        dlg = HelpGuideDialog(lang=self.current_lang, parent=self)
        dlg.exec()

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

        if hasattr(self, 'touchbar') and self.touchbar:
            self.touchbar.set_language(0 if self.current_lang == "it" else 1)

        self.retranslate_ui()

    def retranslate_ui(self):
        self.setWindowTitle(self.t("win_title"))
        self.lbl_hw.setText(self.t("hw_label"))
        usata_ram, tot_ram = get_system_ram_gb()
        self.lbl_ram.setText(self.t("ram_label", used=usata_ram, total=tot_ram))

        self.lbl_m_title.setText(self.t("section_model"))
        self.lbl_auto_tag.setText(self.t("auto_tag"))

        if self.ram_totale_gb > 8.5:
            self.lbl_auto_modello.setText(f"<b>{self.t('model_large_title')}</b>")
            self.lbl_auto_desc.setText(self.t("auto_desc_large", ram=self.ram_totale_gb))
        else:
            self.lbl_auto_modello.setText(f"<b>{self.t('model_turbo_title')}</b>")
            self.lbl_auto_desc.setText(self.t("auto_desc_turbo", ram=self.ram_totale_gb))

        self.btn_passa_manuale.setText(self.t("btn_switch_manual"))
        self.lbl_man_tag.setText(self.t("manual_tag"))
        self.btn_large.setText(self.t("btn_large"))
        self.btn_small.setText(self.t("btn_small"))
        self.btn_torna_auto.setText(self.t("btn_return_auto"))
        self._aggiorna_avviso_manuale()

        self.lbl_l_title.setText(self.t("section_lang"))
        self.btn_it.setText(self.t("btn_lang_primary"))
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

        for card in self.card_widgets:
            if hasattr(card, 'set_language'):
                card.set_language(self.current_lang)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self.thread_lavoro and self.thread_lavoro.isRunning():
            event.ignore()
            return
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self.thread_lavoro and self.thread_lavoro.isRunning():
            event.ignore()
            return
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        if self.thread_lavoro and self.thread_lavoro.isRunning():
            event.ignore()
            return
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
        layout_orizzontale.setContentsMargins(14, 14, 14, 14)
        layout_orizzontale.setSpacing(14)

        # 1. SIDEBAR VERTICALE SINISTRA
        sidebar = QFrame()
        sidebar.setObjectName("sidebarFrame")
        sidebar.setFixedWidth(310)
        s_layout = QVBoxLayout(sidebar)
        s_layout.setContentsMargins(14, 14, 14, 14)
        s_layout.setSpacing(8)

        # Header / Logo
        header_box = QHBoxLayout()
        header_box.setSpacing(10)
        icon_png = DIR_CORRENTE / "wispr.png"
        if icon_png.exists():
            logo_lbl = QLabel()
            dpr = 2.0
            dim_logica = 36
            pix = QPixmap(str(icon_png)).scaled(
                int(dim_logica * dpr), int(dim_logica * dpr),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            pix.setDevicePixelRatio(dpr)
            logo_lbl.setPixmap(pix)
            logo_lbl.setFixedSize(dim_logica, dim_logica)
            logo_lbl.setStyleSheet("background: transparent; border: none;")
            header_box.addWidget(logo_lbl)

        v_title = QVBoxLayout()
        v_title.setSpacing(2)
        lbl_title = QLabel("WHISPER STUDIO")
        lbl_title.setObjectName("titleLabel")
        lbl_title.setStyleSheet("background: transparent; border: none;")
        lbl_sub = QLabel("v2.7")
        lbl_sub.setObjectName("subLabel")
        lbl_sub.setStyleSheet("background: transparent; border: none;")
        v_title.addWidget(lbl_title)
        v_title.addWidget(lbl_sub)
        header_box.addLayout(v_title)
        header_box.addStretch()
        s_layout.addLayout(header_box)

        # Indicatori Hardware
        stats_box = QVBoxLayout()
        stats_box.setSpacing(3)

        self.lbl_hw = QLabel(self.t("hw_label"))
        self.lbl_hw.setStyleSheet("color: #10b981; font-size: 12px; font-weight: 600; background: transparent; border: none; padding: 0;")
        stats_box.addWidget(self.lbl_hw)

        usata_ram, tot_ram = get_system_ram_gb()
        self.lbl_ram = QLabel(self.t("ram_label", used=usata_ram, total=tot_ram))
        self.lbl_ram.setStyleSheet("color: #a1a1aa; font-size: 11px; font-weight: 500; background: transparent; border: none; padding: 0;")
        stats_box.addWidget(self.lbl_ram)

        s_layout.addLayout(stats_box)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet("background-color: #27272a; max-height: 1px; border: none;")
        s_layout.addWidget(sep1)

        # Modello di Trascrizione
        self.lbl_m_title = QLabel(self.t("section_model"))
        self.lbl_m_title.setObjectName("sectionTitle")
        self.lbl_m_title.setStyleSheet("background: transparent; border: none;")
        s_layout.addWidget(self.lbl_m_title)

        # 1. Scheda Modalità Automatica
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

        if self.ram_totale_gb > 8.5:
            modello_auto_nome = self.t("model_large_title")
            desc_ram = self.t("auto_desc_large", ram=self.ram_totale_gb)
        else:
            modello_auto_nome = self.t("model_turbo_title")
            desc_ram = self.t("auto_desc_turbo", ram=self.ram_totale_gb)

        self.lbl_auto_modello = QLabel(f"<b>{modello_auto_nome}</b>")
        self.lbl_auto_modello.setStyleSheet("font-size: 12px; color: #ffffff; background: transparent; border: none;")
        lay_auto.addWidget(self.lbl_auto_modello)

        self.lbl_auto_desc = QLabel(desc_ram)
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

        # 2. Scheda Modalità Manuale
        self.card_manuale = QFrame()
        self.card_manuale.setObjectName("cardManualeModello")
        self.card_manuale.setStyleSheet("""
            QFrame#cardManualeModello {
                background-color: #18181b;
                border: 1px solid #3f3f46;
                border-radius: 10px;
            }
        """)
        lay_man = QVBoxLayout(self.card_manuale)
        lay_man.setContentsMargins(12, 12, 12, 12)
        lay_man.setSpacing(10)

        self.lbl_man_tag = QLabel(self.t("manual_tag"))
        self.lbl_man_tag.setStyleSheet("font-size: 12px; font-weight: bold; color: #fbbf24; background: transparent; border: none;")
        lay_man.addWidget(self.lbl_man_tag)

        self.grp_modelli = QButtonGroup(self)
        self.grp_modelli.setExclusive(True)

        self.btn_large = QPushButton(self.t("btn_large"))
        self.btn_large.setObjectName("btnLargeModello")
        self.btn_large.setProperty("class", "toggleBtn")
        self.btn_large.setCheckable(True)
        self.btn_large.setFixedHeight(52)
        self.btn_large.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_large.clicked.connect(self._aggiorna_avviso_manuale)

        self.btn_small = QPushButton(self.t("btn_small"))
        self.btn_small.setObjectName("btnSmallModello")
        self.btn_small.setProperty("class", "toggleBtn")
        self.btn_small.setCheckable(True)
        self.btn_small.setFixedHeight(52)
        self.btn_small.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_small.clicked.connect(self._aggiorna_avviso_manuale)

        self.grp_modelli.addButton(self.btn_large)
        self.grp_modelli.addButton(self.btn_small)

        if self.ram_totale_gb > 8.5:
            self.btn_large.setChecked(True)
        else:
            self.btn_small.setChecked(True)

        lay_man.addWidget(self.btn_large)
        lay_man.addWidget(self.btn_small)

        self.lbl_warn_manuale = QLabel("")
        self.lbl_warn_manuale.setWordWrap(True)
        self.lbl_warn_manuale.setMinimumHeight(44)
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

        self.btn_it = QPushButton(self.t("btn_lang_primary"))
        self.btn_it.setProperty("class", "toggleBtn")
        self.btn_it.setCheckable(True)
        self.btn_it.setChecked(True)
        self.btn_it.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_auto = QPushButton(self.t("btn_lang_auto"))
        self.btn_auto.setProperty("class", "toggleBtn")
        self.btn_auto.setCheckable(True)
        self.btn_auto.setCursor(Qt.CursorShape.PointingHandCursor)

        self.grp_lingue.addButton(self.btn_it)
        self.grp_lingue.addButton(self.btn_auto)

        h_lang.addWidget(self.btn_it)
        h_lang.addWidget(self.btn_auto)
        s_layout.addLayout(h_lang)

        self.lbl_sub_l = QLabel(self.t("lang_subtitle"))
        self.lbl_sub_l.setStyleSheet("font-size: 11px; color: #71717a; background: transparent; border: none;")
        s_layout.addWidget(self.lbl_sub_l)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        sep3.setStyleSheet("background-color: #27272a; max-height: 1px; border: none;")
        s_layout.addWidget(sep3)

        # Formati di Esportazione
        self.lbl_f_title = QLabel(self.t("section_formats"))
        self.lbl_f_title.setObjectName("sectionTitle")
        self.lbl_f_title.setStyleSheet("background: transparent; border: none;")
        s_layout.addWidget(self.lbl_f_title)

        self.chk_txt = QCheckBox(self.t("chk_txt"))
        self.chk_txt.setChecked(True)

        self.chk_docx = QCheckBox(self.t("chk_docx"))
        self.chk_docx.setChecked(False)

        s_layout.addWidget(self.chk_txt)
        s_layout.addWidget(self.chk_docx)

        self.lbl_salva = QLabel(self.t("formats_subtitle"))
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

        # Drop-zone vuota
        self.empty_card = QFrame()
        self.empty_card.setObjectName("emptyCard")
        self.empty_card.setAcceptDrops(True)
        empty_layout = QVBoxLayout(self.empty_card)
        empty_layout.setContentsMargins(20, 45, 20, 45)
        empty_layout.setSpacing(8)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_icon = QLabel("📥")
        lbl_icon.setStyleSheet("font-size: 42px; background: transparent; border: none;")
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(lbl_icon)

        self.lbl_empty_t = QLabel(self.t("empty_title"))
        self.lbl_empty_t.setStyleSheet("font-size: 16px; color: #ffffff; background: transparent; border: none;")
        self.lbl_empty_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.lbl_empty_t)

        self.lbl_empty_sub = QLabel(self.t("empty_subtitle"))
        self.lbl_empty_sub.setStyleSheet("font-size: 12px; color: #a1a1aa; background: transparent; border: none;")
        self.lbl_empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.lbl_empty_sub)
        r_layout.addWidget(self.empty_card)

        self._aggiorna_vista_coda()

        # Area Stato & Progresso
        prog_box = QVBoxLayout()
        prog_box.setSpacing(6)

        self.prog_bar = WhisperProgressBar()
        prog_box.addWidget(self.prog_bar)

        self.lbl_stato = QLabel(self.t("status_ready"))
        self.lbl_stato.setStyleSheet("color: #d4d4d8; font-size: 12px;")
        prog_box.addWidget(self.lbl_stato)

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

    def _on_riga_selezionata(self, row: int):
        for i, card in enumerate(self.card_widgets):
            if hasattr(card, 'set_selezionato'):
                card.set_selezionato(i == row)

    def _apri_dialogo_file(self):
        filtro = self.t("file_dialog_filter")
        titolo = self.t("file_dialog_title")
        scelti, _ = QFileDialog.getOpenFileNames(self, titolo, "", filtro)
        if scelti:
            self._aggiungi_percorsi(scelti)

    def _aggiungi_percorsi(self, lista_percorsi):
        if self.thread_lavoro and self.thread_lavoro.isRunning():
            return
        aggiunti = 0
        for item in lista_percorsi:
            p = Path(item).resolve()
            if p.is_file() and p.suffix.lower() in VALID_EXTENSIONS:
                if not any(f["path"] == p for f in self.coda_files):
                    durata = get_file_duration(p)
                    peso = p.stat().st_size
                    self.coda_files.append({
                        "path": p,
                        "durata": durata,
                        "peso": peso,
                        "stato": "in_attesa"
                    })
                    aggiunti += 1
        if aggiunti > 0:
            self._aggiorna_vista_coda()

    def _svuota_coda(self):
        if self.thread_lavoro and self.thread_lavoro.isRunning():
            QMessageBox.warning(self, self.t("dlg_clear_title"), self.t("dlg_clear_msg"))
            return
        self.coda_files.clear()
        self._aggiorna_vista_coda()

    def _rimuovi_file(self, index):
        if self.thread_lavoro and self.thread_lavoro.isRunning():
            return
        if 0 <= index < len(self.coda_files):
            self.coda_files.pop(index)
            self._aggiorna_vista_coda()

    def _on_item_reordered(self, src_idx, dst_idx):
        if self.thread_lavoro and self.thread_lavoro.isRunning():
            return
        if 0 <= src_idx < len(self.coda_files) and 0 <= dst_idx < len(self.coda_files):
            item = self.coda_files.pop(src_idx)
            self.coda_files.insert(dst_idx, item)
            self._aggiorna_vista_coda()
            self.queue_list.setCurrentRow(dst_idx)

    def _aggiorna_vista_coda(self):
        self.queue_list.clear()
        self.card_widgets.clear()
        conteggio = len(self.coda_files)
        self.lbl_coda_count.setText(self.t("queue_title", count=conteggio))

        if conteggio == 0:
            self.queue_list.setVisible(False)
            self.empty_card.setVisible(True)
            if hasattr(self, 'touchbar') and self.touchbar:
                self.touchbar.update_state(is_running=False, is_paused=False, can_start=False)
                self.touchbar.update_progress(0.0, self.t("tb_ready"))
            return

        self.queue_list.setVisible(True)
        self.empty_card.setVisible(False)

        cur_row = self.queue_list.currentRow()
        for idx, item in enumerate(self.coda_files):
            card = QueueItemCard(idx, item, self._rimuovi_file, lang=self.current_lang)
            self.card_widgets.append(card)

            list_item = QListWidgetItem(self.queue_list)
            list_item.setSizeHint(QSize(200, 86))
            self.queue_list.addItem(list_item)
            self.queue_list.setItemWidget(list_item, card)

            if idx == cur_row:
                card.set_selezionato(True)

        if hasattr(self, 'touchbar') and self.touchbar:
            is_running = bool(self.thread_lavoro and self.thread_lavoro.isRunning())
            is_paused = bool(self.thread_lavoro and self.thread_lavoro.is_paused)
            self.touchbar.update_state(is_running=is_running, is_paused=is_paused, can_start=(not is_running and conteggio > 0))
            if not is_running:
                self.touchbar.update_progress(0.0, self.t("tb_queued", count=conteggio))

    def _avvia_timer_ram(self):
        def agg_ram():
            usata_ram, tot_ram = get_system_ram_gb()
            if tot_ram > 0:
                self.lbl_ram.setText(self.t("ram_label", used=usata_ram, total=tot_ram))
        agg_ram()
        self.timer_ram = QTimer(self)
        self.timer_ram.timeout.connect(agg_ram)
        self.timer_ram.start(2500)

    def _aggiorna_avviso_manuale(self):
        if self.ram_totale_gb <= 8.5:
            if self.btn_large.isChecked():
                testo = self.t("warn_large_8gb")
                stile = "background: transparent; border: none; color: #fbbf24; padding: 2px 2px; font-size: 11px; font-weight: 500;"
            else:
                testo = self.t("warn_turbo_8gb")
                stile = "background: transparent; border: none; color: #10b981; padding: 2px 2px; font-size: 11px; font-weight: 500;"
        else:
            if self.btn_large.isChecked():
                testo = self.t("warn_large_gt8gb", ram=self.ram_totale_gb)
                stile = "background: transparent; border: none; color: #10b981; padding: 2px 2px; font-size: 11px; font-weight: 500;"
            else:
                testo = self.t("warn_turbo_gt8gb")
                stile = "background: transparent; border: none; color: #fbbf24; padding: 2px 2px; font-size: 11px; font-weight: 500;"
        self.lbl_warn_manuale.setText(testo)
        self.lbl_warn_manuale.setStyleSheet(stile)

    def _imposta_abilitazione_modello(self, abilitato: bool):
        self.btn_passa_manuale.setEnabled(abilitato)
        self.btn_large.setEnabled(abilitato)
        self.btn_small.setEnabled(abilitato)
        self.btn_torna_auto.setEnabled(abilitato)
        self.btn_it.setEnabled(abilitato)
        self.btn_auto.setEnabled(abilitato)
        self.chk_txt.setEnabled(abilitato)
        self.chk_docx.setEnabled(abilitato)
        if hasattr(self, 'btn_add'):
            self.btn_add.setEnabled(abilitato)
        if hasattr(self, 'btn_clear'):
            self.btn_clear.setEnabled(abilitato)

    def _richiedi_passaggio_manuale(self):
        if self.thread_lavoro and self.thread_lavoro.isRunning():
            return
        dlg = DialogoConfermaPassaggioManuale(lang=self.current_lang, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.modalita_manuale = True
            self.card_auto.setVisible(False)
            self.card_manuale.setVisible(True)
            self._aggiorna_avviso_manuale()

    def _ripristina_modalita_automatica(self):
        if self.thread_lavoro and self.thread_lavoro.isRunning():
            return
        self.modalita_manuale = False
        self.card_manuale.setVisible(False)
        self.card_auto.setVisible(True)
        if self.ram_totale_gb > 8.5:
            self.btn_large.setChecked(True)
        else:
            self.btn_small.setChecked(True)
        self._aggiorna_avviso_manuale()

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
            repo_modello = "mlx-community/whisper-large-v3-mlx" if self.ram_totale_gb > 8.5 else "mlx-community/whisper-large-v3-turbo"
        else:
            repo_modello = "mlx-community/whisper-large-v3-mlx" if self.btn_large.isChecked() else "mlx-community/whisper-large-v3-turbo"

        lingua_primaria = "it" if self.current_lang == "it" else "en"
        lingua_mode = lingua_primaria if self.btn_it.isChecked() else "auto"

        for f in self.coda_files:
            if f["stato"] != "completato":
                f["stato"] = "in_attesa"

        self.btn_avvia.setEnabled(False)
        self.btn_pausa.setEnabled(True)
        self.btn_pausa.setText(self.t("btn_pause"))
        self.btn_pausa.setStyleSheet("")
        self.btn_ferma.setEnabled(True)
        self.prog_bar.setValue(0)
        self._imposta_abilitazione_modello(False)

        # AVVISO ARANCIONE CALDO CARICAMENTO MODELLO (#fbbf24)
        self.lbl_stato.setStyleSheet("color: #fbbf24; font-size: 13px; font-weight: 600;")
        self.lbl_stato.setText(self.t("status_loading_model"))

        if hasattr(self, 'touchbar') and self.touchbar:
            self.touchbar.update_state(is_running=True, is_paused=False, can_start=False)
            self.touchbar.update_progress(0.0, self.t("tb_loading"))

        for i, f in enumerate(self.coda_files):
            if f["stato"] != "completato":
                if i < len(self.card_widgets):
                    self.card_widgets[i].aggiorna_stato("in_corso", 0, 0, 0)
                break

        self.thread_lavoro = TrascrizioneWorkerThread(
            self.coda_files, repo_modello, lingua_mode, formati, lang=self.current_lang
        )
        self.thread_lavoro.progresso_file.connect(self._on_progresso_file)
        self.thread_lavoro.progresso_totale.connect(self._on_progresso_totale)
        self.thread_lavoro.file_completato.connect(self._on_file_completato)
        self.thread_lavoro.file_errore.connect(self._on_file_errore)
        self.thread_lavoro.coda_terminata.connect(self._on_coda_terminata)
        self.thread_lavoro.start()

    def _on_progresso_file(self, idx: int, perc: int, t_trasc: float, t_rim: float):
        if idx < len(self.card_widgets):
            self.card_widgets[idx].aggiorna_stato("in_corso", perc, t_trasc, t_rim)

    def _on_progresso_totale(self, perc_tot: int, txt_tot: str):
        # Ripristina stile neutro (#d4d4d8) al primo chunk effettivo di avanzamento
        self.lbl_stato.setStyleSheet("color: #d4d4d8; font-size: 12px;")
        self.prog_bar.setValue(perc_tot)
        self.lbl_stato.setText(txt_tot)
        if hasattr(self, 'touchbar') and self.touchbar:
            self.touchbar.update_progress(float(perc_tot), f"{perc_tot}%")

    def _on_file_completato(self, idx: int, percorso: str):
        if idx < len(self.card_widgets):
            self.card_widgets[idx].aggiorna_stato("completato")
        next_idx = idx + 1
        if next_idx < len(self.card_widgets):
            self.card_widgets[next_idx].aggiorna_stato("in_corso", 0, 0, 0)

    def _on_file_errore(self, idx: int, err: str):
        if idx < len(self.card_widgets):
            self.card_widgets[idx].aggiorna_stato("errore", err_dettaglio=err)

    def _on_coda_terminata(self, completati: int, cartella_out: str):
        self.btn_avvia.setEnabled(True)
        self.btn_pausa.setEnabled(False)
        self.btn_pausa.setText(self.t("btn_pause"))
        self.btn_pausa.setStyleSheet("")
        self.btn_ferma.setEnabled(False)
        self.prog_bar.setValue(100 if completati > 0 else 0)
        self._imposta_abilitazione_modello(True)

        self.lbl_stato.setStyleSheet("color: #d4d4d8; font-size: 12px;")

        if hasattr(self, 'touchbar') and self.touchbar:
            self.touchbar.update_state(is_running=False, is_paused=False, can_start=(len(self.coda_files) > 0))
            if completati > 0:
                self.touchbar.update_progress(100.0, self.t("tb_completed"))
            else:
                self.touchbar.update_progress(0.0, self.t("tb_ready"))

        msg = self.t("finished_msg", count=completati) if completati > 0 else self.t("cancelled_msg")
        self.lbl_stato.setText(msg)

        if completati > 0:
            show_macos_notification("Whisper Studio", self.t("notif_completed", count=completati))
            if cartella_out and os.path.exists(cartella_out):
                try:
                    subprocess.run(["open", cartella_out], check=False)
                except Exception:
                    pass

    def toggle_pausa(self):
        if not self.thread_lavoro:
            return
        if not self.thread_lavoro.is_paused:
            self.thread_lavoro.pausa()
            self.btn_pausa.setText(self.t("btn_resume"))
            self.btn_pausa.setStyleSheet("QPushButton#btnPausa { background-color: #10b981; } QPushButton#btnPausa:hover { background-color: #059669; }")
            self.lbl_stato.setStyleSheet("color: #d4d4d8; font-size: 12px;")
            self.lbl_stato.setText(self.t("status_paused"))
            if hasattr(self, 'touchbar') and self.touchbar:
                self.touchbar.update_state(is_running=True, is_paused=True, can_start=False)
                self.touchbar.update_progress(self.prog_bar.value(), self.t("tb_paused"))
        else:
            self.thread_lavoro.riprendi()
            self.btn_pausa.setText(self.t("btn_pause"))
            self.btn_pausa.setStyleSheet("")
            self.lbl_stato.setStyleSheet("color: #d4d4d8; font-size: 12px;")
            self.lbl_stato.setText(self.t("status_resumed"))
            if hasattr(self, 'touchbar') and self.touchbar:
                self.touchbar.update_state(is_running=True, is_paused=False, can_start=False)
                self.touchbar.update_progress(self.prog_bar.value(), f"{self.prog_bar.value()}%")

    def ferma_trascrizione(self):
        if not self.thread_lavoro:
            return
        self.lbl_stato.setStyleSheet("color: #d4d4d8; font-size: 12px;")
        self.lbl_stato.setText(self.t("status_cancelling"))
        if hasattr(self, 'touchbar') and self.touchbar:
            self.touchbar.update_progress(0.0, self.t("tb_cancelled"))
        self.thread_lavoro.ferma()
        self.thread_lavoro.wait()
        self._on_coda_terminata(0, "")

def avvia_gui():
    app = QApplication(sys.argv)
    finestra = WhisperStudioWindow()
    finestra.show()
    finestra.raise_()
    finestra.activateWindow()
    sys.exit(app.exec())

# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================
if __name__ == "__main__":
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and (sys.argv[1].startswith("--multiprocessing") or sys.argv[1] == "-c"):
        sys.exit(0)
    avvia_gui()
