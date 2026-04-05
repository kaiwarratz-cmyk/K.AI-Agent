"""
Einmalige Bereinigung der bestehenden Facts-Datenbank.
Entfernt: agent_state_*, triviale pkg_* Facts, _status Facts, kurze/nichtssagende Values.
AUSNAHME: svc_*, hue_bridge*, *_ip, *_username, *_token, *_path werden immer behalten.

Ausfuehren: python scripts/cleanup_facts.py
"""
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.context_manager import ContextManager

ctx = ContextManager()
facts = ctx.read_facts_with_meta()

DELETE_PATTERNS = [
    re.compile(r"^agent_state_"),
    re.compile(
        r"^pkg_(requests|json|os|sys|re|math|time|datetime|pathlib|subprocess|"
        r"threading|logging|uuid|enum|typing|io|copy|shutil|glob|hashlib|base64|"
        r"urllib|http|socket|ssl|queue|random|string|struct|array|collections|"
        r"itertools|functools|contextlib|warnings|traceback|inspect|operator|"
        r"heapq|bisect|weakref|gc|platform|signal|select|errno|ctypes|unittest|"
        r"dataclasses|abc|csv|sqlite3|xml|email|html|fnmatch)$"
    ),
    re.compile(r"_(setup_status|needs_setup|step_status|task_status|job_status)$"),
]

KEEP_ALWAYS = [
    re.compile(r"^svc_"),
    re.compile(r"^hue_bridge"),
    re.compile(r"_ip$"),
    re.compile(r"_username$"),
    re.compile(r"_token$"),
    re.compile(r"_path$"),
    re.compile(r"_port$"),
    re.compile(r"_key$"),
]

TRIVIAL_VALUES = re.compile(
    r"^(True|False|None|0|1|ok|done|fertig|verfuegbar|available|installed|"
    r"not installed|ja|nein|yes|no)$",
    re.IGNORECASE,
)

deleted = []
kept = []

for key, meta in facts.items():
    value = meta.get("value", "")
    k = key.lower()

    if any(p.search(k) for p in KEEP_ALWAYS):
        kept.append((key, value[:80]))
        continue

    if any(p.search(k) for p in DELETE_PATTERNS):
        deleted.append((key, value[:80]))
        continue

    if TRIVIAL_VALUES.search(value.strip()):
        deleted.append((key, value[:80]))
        continue

    if len(value.strip()) < 15:
        deleted.append((key, value[:80]))
        continue

    kept.append((key, value[:80]))

print(f"\n{'='*60}")
print(f"VORSCHAU: {len(deleted)} loeschen, {len(kept)} behalten")
print(f"{'='*60}")

if deleted:
    print(f"\n--- ZU LOESCHEN ({len(deleted)}) ---")
    for k, v in deleted:
        print(f"  DEL  {k!r:45s} = {v!r}")

print(f"\n--- ZU BEHALTEN ({len(kept)}) ---")
for k, v in kept:
    print(f"  KEEP {k!r:45s} = {v!r}")

if not deleted:
    print("\nNichts zu loeschen - Datenbank ist bereits sauber.")
    sys.exit(0)

print(f"\n{'='*60}")
confirm = input(f"Diese {len(deleted)} Facts loeschen? (ja/nein): ").strip().lower()

if confirm == "ja":
    with ctx._lock:
        conn = ctx._get_conn()
        for k, _ in deleted:
            conn.execute("DELETE FROM discovered_facts WHERE key = ?", (k,))
        conn.commit()
    print(f"\n{len(deleted)} Facts geloescht. {len(kept)} Facts behalten.")
else:
    print("\nAbgebrochen - keine Aenderungen.")
