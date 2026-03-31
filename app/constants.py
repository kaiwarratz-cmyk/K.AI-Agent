"""
K.AI – Zentrale Konstanten
==========================
Single source of truth für Werte, die in mehreren Modulen genutzt werden.
Kein Zirkulär-Import-Risiko, weil diese Datei nichts aus app.* importiert.
"""

# Arbeitsgedächtnis / Working Memory
MAX_WORKING_NOTES = 10     # Maximale Anzahl Working Notes pro Dialog-Key
KEEP_RAW_TURNS = 4         # Letzte N Turns bleiben unkomprimiert im History-Buffer
