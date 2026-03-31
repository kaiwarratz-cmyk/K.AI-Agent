from __future__ import annotations

import json
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

# ── Registry cache ────────────────────────────────────────────────────────────
_CACHE_TTL_SEC = 6 * 3600          # 6 Stunden
_CACHE_MAX_PAGES = 40              # max. 4 000 Server laden
_CACHE_PAGE_SIZE = 100

def _cache_path() -> Path:
    from app.config import ROOT_DIR
    p = ROOT_DIR / "data" / "mcp_registry_cache.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_cache() -> Optional[List[Dict[str, Any]]]:
    """Lädt den Cache wenn er noch frisch ist."""
    p = _cache_path()
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        ts = raw.get("timestamp", 0)
        if time.time() - ts > _CACHE_TTL_SEC:
            return None
        return raw.get("servers", [])
    except Exception:
        return None


def _save_cache(servers: List[Dict[str, Any]]) -> None:
    p = _cache_path()
    try:
        p.write_text(
            json.dumps({"timestamp": time.time(), "servers": servers}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def _install_type_from_server(s: dict) -> str:
    """Bestimmt den Install-Typ aus Server-Daten der List-API.
    - 'npm_stdio' → hat npm-Package mit stdio-Transport → direkt installierbar via npx
    - 'local'     → hat packages aber kein npm+stdio (z.B. pypi, docker) → evtl. installierbar
    - 'remote'    → hat remotes (HTTP/SSE) aber keine packages → KEIN lokaler Install möglich
    - 'unknown'   → weder remotes noch packages bekannt
    """
    remotes = s.get("remotes") or []
    packages = s.get("packages") or []
    has_npm_stdio = False
    has_any_pkg = bool(packages)
    for p in packages:
        if not isinstance(p, dict):
            continue
        reg = str(p.get("registryType") or p.get("registry_type") or "").lower()
        tp = p.get("transport") or p.get("transports") or {}
        if isinstance(tp, list):
            tp_str = ",".join(str(x.get("type", "") if isinstance(x, dict) else x) for x in tp).lower()
        elif isinstance(tp, dict):
            tp_str = str(tp.get("type") or "").lower()
        else:
            tp_str = str(tp).lower()
        if reg == "npm" and "stdio" in tp_str:
            has_npm_stdio = True
            break
    if has_npm_stdio:
        return "npm_stdio"
    if remotes and not has_any_pkg:
        return "remote"
    if has_any_pkg:
        return "local"
    return "unknown"


def _fetch_all_official_servers(base_url: str) -> List[Dict[str, Any]]:
    """Lädt alle Server aus der offiziellen MCP-Registry (paginiert)."""
    results: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    try:
        with httpx.Client(timeout=15.0) as client:
            for _ in range(_CACHE_MAX_PAGES):
                params: Dict[str, Any] = {"limit": _CACHE_PAGE_SIZE}
                if cursor:
                    params["cursor"] = cursor
                r = client.get(f"{base_url}/v0.1/servers", params=params)
                r.raise_for_status()
                data = r.json()
                page_servers = data.get("servers", [])
                for item in page_servers:
                    if not isinstance(item, dict):
                        continue
                    s = item.get("server", item)
                    if not isinstance(s, dict):
                        continue
                    results.append({
                        "name": str(s.get("name") or s.get("id") or "").strip(),
                        "title": str(s.get("title") or "").strip(),
                        "description": str(s.get("description") or s.get("summary") or "").strip(),
                        "version": str(s.get("version") or "").strip(),
                        "install_type": _install_type_from_server(s),
                        "data": s,
                    })
                cursor = data.get("metadata", {}).get("nextCursor")
                if not cursor or not page_servers:
                    break
    except Exception:
        pass
    return results


def _get_official_servers(base_url: str) -> List[Dict[str, Any]]:
    """Gibt gecachte oder frisch geladene Server zurück (dedupliziert nach Name)."""
    cached = _load_cache()
    if cached is not None:
        return cached
    servers = _fetch_all_official_servers(base_url)
    if servers:
        # Deduplizieren: pro Name nur den ersten Eintrag behalten (API gibt manchmal mehrere Versionen zurück)
        seen: set = set()
        unique = []
        for s in servers:
            n = s.get("name", "")
            if n and n not in seen:
                seen.add(n)
                unique.append(s)
        servers = unique
        _save_cache(servers)
    return servers


def _score_server(server: Dict[str, Any], terms: List[str]) -> int:
    """Berechnet einen Relevanz-Score für ein Server-Objekt."""
    name = server.get("name", "").lower()
    title = server.get("title", "").lower()
    desc = server.get("description", "").lower()
    score = 0
    for term in terms:
        t = term.lower()
        if t in name:
            score += 10
        if t in title:
            score += 8
        if t in desc:
            score += 4
    return score


DEFAULT_REGISTRY_SOURCES = [
    {
        "id": "mcp_registry_official",
        "type": "mcp_registry",
        "name": "Official MCP Registry",
        "base_url": "https://registry.modelcontextprotocol.io",
        "enabled": True,
    },
    {
        "id": "github",
        "type": "github",
        "name": "GitHub (topic:mcp-server)",
        "base_url": "https://api.github.com",
        "enabled": True,
    },
]


def _ensure_sources(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    mcp = cfg.setdefault("mcp", {})
    sources = mcp.get("registry_sources")
    if not isinstance(sources, list) or not sources:
        mcp["registry_sources"] = list(DEFAULT_REGISTRY_SOURCES)
        return mcp["registry_sources"]
    # normalize entries
    out = []
    for src in sources:
        if not isinstance(src, dict):
            continue
        src_id = str(src.get("id", "")).strip()
        src_type = str(src.get("type", "")).strip().lower()
        base = str(src.get("base_url", "")).strip()
        if not src_id or not src_type or not base:
            continue
        out.append(
            {
                "id": src_id,
                "type": src_type,
                "name": str(src.get("name", "")).strip() or src_id,
                "base_url": base.rstrip("/"),
                "enabled": bool(src.get("enabled", True)),
            }
        )
    if not out:
        out = list(DEFAULT_REGISTRY_SOURCES)
        mcp["registry_sources"] = out
    else:
        mcp["registry_sources"] = out
    return out


def list_registry_sources(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(_ensure_sources(cfg))


def upsert_registry_source(cfg: Dict[str, Any], entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    sources = _ensure_sources(cfg)
    src_id = str(entry.get("id", "")).strip()
    src_type = str(entry.get("type", "")).strip().lower()
    base = str(entry.get("base_url", "")).strip().rstrip("/")
    name = str(entry.get("name", "")).strip() or src_id
    enabled = bool(entry.get("enabled", True))
    if not src_id or not src_type or not base:
        return sources
    updated = False
    for src in sources:
        if str(src.get("id")) == src_id:
            src.update({"type": src_type, "base_url": base, "name": name, "enabled": enabled})
            updated = True
            break
    if not updated:
        sources.append(
            {
                "id": src_id,
                "type": src_type,
                "name": name,
                "base_url": base,
                "enabled": enabled,
            }
        )
    cfg.setdefault("mcp", {})["registry_sources"] = sources
    return sources


def delete_registry_source(cfg: Dict[str, Any], source_id: str) -> List[Dict[str, Any]]:
    sources = _ensure_sources(cfg)
    kept = [s for s in sources if str(s.get("id")) != str(source_id)]
    cfg.setdefault("mcp", {})["registry_sources"] = kept
    return kept


def _request_json(url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Tuple[bool, Any, str]:
    try:
        with httpx.Client(timeout=12.0, headers=headers) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            return True, r.json(), ""
    except Exception as exc:
        return False, None, str(exc)


def search_registry_sources(cfg: Dict[str, Any], query: str, limit: int = 20) -> List[Dict[str, Any]]:
    q = str(query or "").strip()
    if not q:
        return []
    limit = max(1, min(50, int(limit)))
    terms = [t for t in q.split() if t]
    results: List[Dict[str, Any]] = []
    for src in _ensure_sources(cfg):
        if not bool(src.get("enabled", True)):
            continue
        src_type = str(src.get("type", "")).lower()
        base = str(src.get("base_url", "")).rstrip("/")
        if not base:
            continue
        if src_type == "mcp_registry":
            # Die offizielle Registry unterstützt keine serverseitige Suche.
            # Wir laden alle Server einmalig (gecacht) und filtern client-seitig.
            all_servers = _get_official_servers(base)
            if not all_servers:
                results.append({
                    "source_id": src.get("id"),
                    "source_type": src_type,
                    "error": "registry_error: Keine Server aus Registry geladen (Netzwerkfehler?)",
                })
                continue
            # Scoring + Filtern; npm+stdio Server zuerst, remote ignorieren
            scored = []
            for srv in all_servers:
                score = _score_server(srv, terms)
                if score > 0:
                    install_type = srv.get("install_type", "unknown")
                    if install_type == "npm_stdio":
                        score += 15   # Bestätigt npm+stdio → ganz oben
                    elif install_type == "local":
                        score += 5    # Hat Packages (nicht npm+stdio) → mittig
                    elif install_type == "unknown":
                        score += 2    # möglicherweise installierbar
                    # remote → kein Bonus, erscheint unten
                    scored.append((score, srv))
            scored.sort(key=lambda x: -x[0])
            for score, srv in scored[:limit]:
                name = srv.get("name", "")
                if not name:
                    continue
                install_type = srv.get("install_type", "local")
                encoded_name = urllib.parse.quote(name, safe='')
                results.append({
                    "name": name,
                    "title": srv.get("title", ""),
                    "description": srv.get("description", ""),
                    "install_type": install_type,
                    "source_id": src.get("id"),
                    "source_type": src_type,
                    "source_name": src.get("name") or src.get("id"),
                    "detail": f"{base}/v0.1/servers/{encoded_name}/versions/latest",
                    "data": srv.get("data", {}),
                })
        elif src_type == "github":
            params = {"q": f"{q} topic:mcp-server", "per_page": limit}
            headers = {"Accept": "application/vnd.github+json"}
            ok, payload, err = _request_json(f"{base}/search/repositories", params=params, headers=headers)
            if not ok:
                results.append(
                    {
                        "source_id": src.get("id"),
                        "source_type": src_type,
                        "error": f"github_error: {err}",
                    }
                )
                continue
            items = payload.get("items", []) if isinstance(payload, dict) else []
            for repo in items[:limit]:
                if not isinstance(repo, dict):
                    continue
                results.append(
                    {
                        "name": repo.get("full_name") or repo.get("name"),
                        "description": repo.get("description") or "",
                        "source_id": src.get("id"),
                        "source_type": src_type,
                        "source_name": src.get("name") or src.get("id"),
                        "detail": repo.get("html_url") or "",
                    }
                )
    return results


def get_registry_details(cfg: Dict[str, Any], source_id: str, name: str) -> Dict[str, Any]:
    src = None
    for s in _ensure_sources(cfg):
        if str(s.get("id")) == str(source_id):
            src = s
            break
    if not src:
        return {"ok": False, "message": f"Quelle nicht gefunden: {source_id}"}
    src_type = str(src.get("type", "")).lower()
    base = str(src.get("base_url", "")).rstrip("/")
    if src_type != "mcp_registry":
        return {"ok": False, "message": "Details nur fuer MCP-Registry verfuegbar."}
    
    encoded_name = urllib.parse.quote(name, safe='')
    ok, payload, err = _request_json(f"{base}/v0.1/servers/{encoded_name}/versions/latest")
    if not ok:
        return {"ok": False, "message": f"Registry-Fehler: {err}"}
    return {"ok": True, "data": payload}


def suggest_server_from_details(details: Dict[str, Any]) -> Dict[str, Any]:
    # 0. Remote-only Server (streamable-http / sse) — kein lokaler Install möglich
    data = details.get("data") if isinstance(details, dict) else None
    if isinstance(data, dict):
        s = data.get("server", data)
        remotes = s.get("remotes") or [] if isinstance(s, dict) else []
        packages = s.get("packages") or [] if isinstance(s, dict) else []
        if remotes and not packages:
            remote_url = remotes[0].get("url", "") if isinstance(remotes[0], dict) else ""
            remote_type = remotes[0].get("type", "streamable-http") if isinstance(remotes[0], dict) else "streamable-http"
            return {
                "ok": False,
                "remote": True,
                "remote_url": remote_url,
                "remote_type": remote_type,
                "message": (
                    f"Dies ist ein gehosteter Remote-Service ({remote_type}), kein lokal installierbares npm-Package. "
                    f"URL: {remote_url}. "
                    "K.AI unterstuetzt derzeit nur stdio (npm) MCP-Server. "
                    "Bitte waehle ein anderes Tool mit lokalem npm-Package."
                ),
            }

    # 1. Standard MCP Registry (NPM)
    data = details.get("data") if isinstance(details, dict) else None
    if isinstance(data, dict):
        # API gibt {"server": {"packages": [...]}} zurück → in server-Node schauen
        _srv_node = data.get("server", data) if isinstance(data, dict) else data
        packages = _srv_node.get("packages") or _srv_node.get("package") or \
                   data.get("packages") or data.get("package") or []
        if isinstance(packages, dict):
            packages = [packages]
        npm_pkg = None
        for p in packages:
            if not isinstance(p, dict):
                continue
            reg_type = str(p.get("registry_type") or p.get("registryType") or p.get("registry") or "").lower()
            transports = p.get("transport") or p.get("transports") or ""
            if isinstance(transports, list):
                transports = ",".join(str(x) for x in transports)
            if reg_type == "npm" and "stdio" in str(transports).lower():
                npm_pkg = p
                break
        if npm_pkg:
            name = str(npm_pkg.get("package_name") or npm_pkg.get("name") or npm_pkg.get("identifier") or "").strip()
            version = str(npm_pkg.get("version") or "").strip()
            if name:
                pkg = f"{name}@{version}" if version else name
                # Warnung bei bekannt problematischen Paketen (Browser-Downloads auf Windows)
                _browser_keywords = ("playwright", "puppeteer", "chromium", "selenium", "browser", "headless")
                _server_desc = str(details.get("data", {}).get("description") or "").lower()
                _browser_warn = any(k in _server_desc or k in name.lower() for k in _browser_keywords)
                return {
                    "ok": True,
                    "server": {
                        "type": "stdio",
                        "command": "npx",
                        "args": ["-y", pkg],
                        "env": {},
                    },
                    "note": "Vorschlag basiert auf npm stdio Package aus Registry.",
                    "browser_warning": _browser_warn,
                }

    # 2. GitHub Fallback
    github_url = str(details.get("detail") or details.get("detail_url") or "")
    if "github.com" in github_url:
        return {
            "ok": True,
            "server": {
                "type": "github_auto",
                "url": github_url,
            },
            "note": "GitHub Repository erkannt. System wird versuchen, das Tool automatisch zu laden und zu konfigurieren.",
        }

    return {"ok": False, "message": "Kein npm-Package fuer diesen Server gefunden. Naechstes Suchergebnis waehlen — KEIN manueller git/npm-Install!"}


def install_from_registry(cfg: Dict[str, Any], source_id: str, name: str) -> Dict[str, Any]:
    # Robustheit: source_id kann auch der source_name sein (z.B. "Official MCP Registry" statt "mcp_registry_official")
    # → Wir suchen die echte source_id über _ensure_sources
    sources = _ensure_sources(cfg)
    resolved_source_id = source_id
    for src in sources:
        if str(src.get("id")) == source_id:
            resolved_source_id = source_id
            break
        if str(src.get("name", "")).lower() == source_id.lower():
            resolved_source_id = str(src.get("id"))
            break
    source_id = resolved_source_id

    # Wir brauchen die Suchergebnisse, um die Detail-URL zu finden, falls es GitHub ist
    from app.mcp_registry import search_registry_sources
    results = search_registry_sources(cfg, name, limit=10)
    
    match = None
    for r in results:
        if str(r.get("name")).strip() == name and str(r.get("source_id")).strip() == source_id:
            match = r
            break
            
    # Falls es eine MCP-Registry ist, brauchen wir IMMER die aktuellen Details für Version/Packages
    if match and str(match.get("source_type")).lower() == "mcp_registry":
        # Wir ueberschreiben match mit den echten Details
        details = get_registry_details(cfg, source_id, name)
        if details.get("ok"):
            match = details
            
    if not match:
        # Falls kein direkter Match, versuchen wir es über die Registry-Details (für offizielle Registry)
        details = get_registry_details(cfg, source_id, name)
        if details.get("ok"):
            proposal = suggest_server_from_details(details)
            return {"ok": True, "proposal": proposal.get("server", {}), "note": proposal.get("note", "")}
        return {"ok": False, "message": f"Quelle '{name}' konnte nicht identifiziert werden (ID: {source_id})."}
    
    proposal = suggest_server_from_details(match)
    if not proposal.get("ok", False):
        msg = proposal.get("message", "Kein npm-Package fuer diesen Server gefunden.")
        if not proposal.get("remote"):
            msg += " KEIN manueller git/npm-Install versuchen — naechstes Suchergebnis waehlen!"
        return {"ok": False, "message": msg}
    return {"ok": True, "proposal": proposal.get("server", {}), "note": proposal.get("note", "")}
