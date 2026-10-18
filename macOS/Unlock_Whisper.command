#!/bin/bash
# ==============================================================================
# Automatic Security Unlock for Whisper Studio (macOS)
# Sblocco Automatico di Sicurezza per Whisper Studio (macOS)
# ==============================================================================
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "Rimozione blocchi di sicurezza di macOS (Gatekeeper)..."
echo "Removing macOS Gatekeeper security quarantine attributes..."
xattr -cr "$DIR/Whisper Studio.app" 2>/dev/null
chmod -R +x "$DIR/Whisper Studio.app" 2>/dev/null
echo ""
echo "✅ Whisper Studio sbloccato con successo! / Successfully unlocked!"
echo "Avvio dell'applicazione in corso / Launching Whisper Studio..."
open "$DIR/Whisper Studio.app"
exit 0
