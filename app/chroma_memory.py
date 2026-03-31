import warnings
import os
import logging
import json

# Vor allen Imports setzen – sonst zu spät
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

warnings.filterwarnings("ignore", message=".*unauthenticated.*", category=UserWarning)
warnings.filterwarnings("ignore", message=".*HF Hub.*", category=UserWarning)

# Unterdrückt BERT LOAD REPORT, "not sharded", tqdm-Fortschrittsbalken
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("transformers.utils.loading_report").setLevel(logging.ERROR)
logging.getLogger("transformers.modeling_utils").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

from sentence_transformers import SentenceTransformer
import chromadb
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import hashlib

# Progress-Balken und "not sharded"-Meldungen nach Import deaktivieren
try:
    from transformers import logging as _hf_logging
    _hf_logging.set_verbosity_error()
    _hf_logging.disable_progress_bar()
except Exception:
    pass

class ChromaMemoryStore:
    def __init__(self, db_path: Any, collection_name: str = "memories"):
        from pathlib import Path
        # Robuste Pfad-Extraktion falls cfg-Dict uebergeben wurde
        if isinstance(db_path, dict):
            # ROOT_DIR muss hier lokal ermittelt werden falls noetig
            root = Path(__file__).resolve().parent.parent
            raw_path = db_path.get("memory", {}).get("db_path", "data/chroma_memory")
            db_path = root / raw_path
            
        self.db_path = str(db_path)
        self.collection_name = collection_name
        _dir = Path(db_path)
        _dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(_dir))
        self.collection = self.client.get_or_create_collection(self.collection_name)
        self.model = None
        # Fix 6: Flag zeigt an, ob das echte Embedding-Modell nicht verfügbar ist.
        # Bei True werden search() und search_hybrid() frühzeitig mit [] abgebrochen,
        # weil SHA256-Fallback-Vektoren keine semantische Ähnlichkeit abbilden.
        self._fallback_active = False
        try:
            self.model = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception as exc:
            self._fallback_active = True
            logging.getLogger(__name__).warning(
                "SentenceTransformer nicht verfügbar – Similarity-Search deaktiviert! "
                "Speichern weiterhin möglich (Neuindizierung nach Modell-Install). Fehler: %s",
                exc,
            )

    def _fallback_embed(self, text: str, dims: int = 384) -> list[float]:
        raw = hashlib.sha256(text.encode("utf-8", errors="ignore")).digest()
        out: list[float] = []
        for i in range(dims):
            b = raw[i % len(raw)]
            out.append((b / 255.0) * 2.0 - 1.0)
        return out

    def _encode_texts(self, texts: List[str]) -> List[List[float]]:
        if self.model is None:
            return [self._fallback_embed(t) for t in texts]
        vectors = self.model.encode(texts)
        try:
            return vectors.tolist()
        except Exception:
            return [list(v) for v in vectors]

    def _compute_content_hash(self, text: str) -> str:
        """Berechnet Hash fuer Deduplizierung."""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]

    def upsert_memory(self, kind: str, key: str, content: Dict[str, Any], confidence: float = 0.7, collection_name: Optional[str] = None):
        """Speichert Fact mit Metadaten und Deduplizierungs-Check."""
        # Ziel-Collection bestimmen
        target_coll_name = collection_name or kind or self.collection_name
        try:
            target_coll = self.client.get_or_create_collection(name=target_coll_name)
        except Exception:
            target_coll = self.collection

        if isinstance(content, dict):
            if "info" in content and isinstance(content.get("info"), str):
                text = str(content.get("info", ""))
            else:
                text = json.dumps(content, ensure_ascii=False)
        elif isinstance(content, list):
            text = json.dumps(content, ensure_ascii=False)
        else:
            text = str(content)
        doc_id = f"{kind}:{key}"
        
        # Deduplizierungs-Check
        content_hash = self._compute_content_hash(text)
        try:
            existing = target_coll.get(ids=[doc_id])
            if existing and existing.get("metadatas"):
                old_hash = existing["metadatas"][0].get("content_hash", "")
                if old_hash == content_hash:
                    meta = existing["metadatas"][0]
                    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
                    target_coll.update(
                        ids=[doc_id],
                        metadatas=[meta]
                    )
                    return
        except Exception:
            pass
        
        embedding = self._encode_texts([text])[0]
        meta = {
            "kind": kind,
            "key": key,
            "confidence": confidence,
            "content_hash": content_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        target_coll.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[meta]
        )

    def search(
        self, 
        query: str, 
        limit: int = 10, 
        min_similarity: float = 0.0,
        kind: Optional[str] = None,
        collection_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Sucht relevante Facts mit Confidence-Filtering ueber alle Collections.
        """
        # Fix 6: Fallback-Embeddings haben keine semantische Bedeutung → kein Ergebnis.
        if self._fallback_active:
            return []
        embedding = self._encode_texts([query])[0]
        out = []
        
        try:
            # Bestimme welche Collections durchsucht werden sollen
            if collection_name:
                target_names = [collection_name]
            else:
                colls = self.client.list_collections()
                target_names = [c.name if hasattr(c, 'name') else str(c) for c in colls]
            
            for c_name in target_names:
                try:
                    coll = self.client.get_collection(name=c_name)
                    coll_count = coll.count()
                    if coll_count == 0: continue
                    
                    # Query mit optionalem Kind-Filter
                    where_filter = {"kind": kind} if kind else None
                    
                    results = coll.query(
                        query_embeddings=[embedding],
                        n_results=min(limit, coll_count),
                        where=where_filter
                    )
                    
                    if not results or not results.get("documents") or not results["documents"][0]:
                        continue
                        
                    for i, doc in enumerate(results["documents"][0]):
                        meta = results["metadatas"][0][i]
                        distance = results["distances"][0][i] if "distances" in results else 1.0
                        similarity = max(0.0, 1.0 - (distance / 2.0))
                        
                        if similarity < min_similarity:
                            continue
                        
                        out.append({
                            "kind": meta.get("kind", c_name),
                            "key": meta.get("key"),
                            "confidence": meta.get("confidence", 0.0),
                            "similarity": similarity,
                            "text": str(doc or ""),
                            "content": str(doc or ""),
                            "updated_at": meta.get("updated_at", "")
                        })
                except Exception:
                    continue
                    
            # Sortiere nach Similarity * Confidence
            out.sort(key=lambda x: x["similarity"] * x["confidence"], reverse=True)
            return out[:limit]
        except Exception as exc:
            logging.getLogger(__name__).error(f"Error in search: {exc}")
            return []

    def search_by_kind(self, kind: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Sucht Facts nach Typ (ohne Query)."""
        try:
            # Versuche die spezifische Collection fuer diesen Typ zu finden
            try:
                target_coll = self.client.get_collection(name=kind)
            except Exception:
                # Fallback auf Standard-Collection falls die kind-spezifische nicht existiert
                target_coll = self.collection

            results = target_coll.get(
                where={"kind": kind} if target_coll.name == self.collection_name else None,
                limit=limit
            )
            if not results or not results.get("documents"):
                # Wenn in der spezifischen nichts war, schau nochmal in der Haupt-Collection (Abwaertskompatibilitaet)
                if target_coll.name != self.collection_name:
                    results = self.collection.get(where={"kind": kind}, limit=limit)
                
                if not results or not results.get("documents"):
                    return []
            
            out = []
            for i, doc in enumerate(results["documents"]):
                meta = results["metadatas"][i]
                out.append({
                    "kind": meta.get("kind"),
                    "key": meta.get("key"),
                    "confidence": meta.get("confidence", 0.0),
                    "content": doc,
                    "updated_at": meta.get("updated_at", "")
                })
            return out
        except Exception:
            return []

    def delete_memory(self, kind: str, key: str):
        doc_id = f"{kind}:{key}"
        self.collection.delete(ids=[doc_id])

    # Backward-compatible helper used by existing main.py call-sites.
    def delete_key(self, kind: str, key: str) -> int:
        doc_id = f"{kind}:{key}"
        try:
            existing = self.collection.get(ids=[doc_id])
            ids = existing.get("ids", []) if isinstance(existing, dict) else []
            if ids:
                self.collection.delete(ids=[doc_id])
                return 1
            return 0
        except Exception:
            return 0

    def delete_all(self, kind: Optional[str] = None) -> int:
        """Loescht alle Eintraege in allen Collections, optional gefiltert nach kind. Gibt Anzahl zurueck."""
        total_deleted = 0
        try:
            colls = self.client.list_collections()
            for coll_obj in colls:
                # In modern chromadb, list_collections returns objects with a .name attribute
                c_name = coll_obj.name if hasattr(coll_obj, 'name') else str(coll_obj)
                coll = self.client.get_collection(name=c_name)
                where = {"kind": kind} if kind else None
                result = coll.get(where=where)
                ids = result.get("ids", []) if result else []
                if ids:
                    coll.delete(ids=ids)
                    total_deleted += len(ids)
            return total_deleted
        except Exception as exc:
            logging.getLogger(__name__).error(f"Error in delete_all: {exc}")
            return total_deleted

    # Backward-compatible helper used by existing main.py call-sites.
    def delete_kind(self, kind: str) -> int:
        return self.delete_all(kind=kind)

    def cleanup_old_facts(self, max_age_days: int = 30):
        """Loescht Facts aelter als max_age_days (optional, experimentell)."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        cutoff_iso = cutoff.isoformat()
        
        try:
            all_items = self.collection.get()
            if not all_items or not all_items.get("ids"):
                return
            
            to_delete = []
            for i, doc_id in enumerate(all_items["ids"]):
                meta = all_items["metadatas"][i]
                updated = meta.get("updated_at", "")
                if updated and updated < cutoff_iso:
                    to_delete.append(doc_id)
            
            if to_delete:
                self.collection.delete(ids=to_delete)
        except Exception:
            pass  # Silent fail bei Cleanup

    def search_hybrid(
        self, 
        query: str, 
        limit: int = 10, 
        min_similarity: float = 0.5,
        keywords: Optional[List[str]] = None,
        kind: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Kombinierte Suche: Vektor-Aehnlichkeit + Keyword-Matching.
        Besonders effektiv fuer technische IDs, Pfade und Namen.
        """
        # Fix 6: search() prüft _fallback_active bereits, hier zur Klarheit doppelt.
        if self._fallback_active:
            return []
        # 1. Semantische Suche
        results = self.search(query=query, limit=limit, min_similarity=min_similarity, kind=kind)
        
        # 2. Keyword-Suche (falls Keywords vorhanden oder aus Query extrahierbar)
        if not keywords and len(query.split()) < 4:
            keywords = [query.strip().lower()]
        
        if keywords:
            kw_results = []
            try:
                colls = self.client.list_collections()
                for coll_obj in colls:
                    c_name = coll_obj.name if hasattr(coll_obj, 'name') else str(coll_obj)
                    coll = self.client.get_collection(name=c_name)
                    
                    # Suche in Dokumenten nach Keywords
                    for kw in keywords:
                        if not kw or len(kw) < 3: continue
                        kw_matches = coll.get(
                            where_document={"$contains": kw},
                            where={"kind": kind} if kind else None,
                            limit=limit
                        )
                        
                        if kw_matches and kw_matches.get("documents"):
                            for i, doc in enumerate(kw_matches["documents"]):
                                meta = kw_matches["metadatas"][i]
                                # Keyword-Matches erhalten einen Bonus-Score (Similarity = 0.95)
                                kw_results.append({
                                    "kind": meta.get("kind", c_name),
                                    "key": meta.get("key"),
                                    "confidence": meta.get("confidence", 0.0),
                                    "similarity": 0.95, 
                                    "text": str(doc or ""),
                                    "content": str(doc or ""),
                                    "updated_at": meta.get("updated_at", ""),
                                    "source": "keyword"
                                })
                
                # Zusammenfuehren und Deduplizieren
                seen_keys = {f"{r['kind']}:{r['key']}" for r in results}
                for kr in kw_results:
                    rk = f"{kr['kind']}:{kr['key']}"
                    if rk not in seen_keys:
                        results.append(kr)
                        seen_keys.add(rk)
            except Exception as exc:
                logging.getLogger(__name__).error(f"Error in hybrid keyword search: {exc}")
        
        # 3. Reranking / Sortierung
        results.sort(key=lambda x: x["similarity"] * x["confidence"], reverse=True)
        return results[:limit]

    def count(self) -> int:
        return self.collection.count()

    def count_by_kind(self) -> List[Dict[str, Any]]:
        """Gibt Anzahl der Eintraege pro Kind zurueck."""
        try:
            counts: Dict[str, int] = {}
            colls = self.client.list_collections()
            for coll_obj in colls:
                c_name = coll_obj.name if hasattr(coll_obj, 'name') else str(coll_obj)
                coll = self.client.get_collection(name=c_name)
                # In den spezialisierten Collections ist der Name oft gleich der kind
                # Wir zaehlen aber trotzdem die Metadaten fuer Praezision
                all_items = coll.get()
                if all_items and all_items.get("metadatas"):
                    for meta in all_items["metadatas"]:
                        k = str(meta.get("kind", c_name))
                        counts[k] = counts.get(k, 0) + 1
            return [{"kind": k, "count": v} for k, v in sorted(counts.items())]
        except Exception:
            return []

    def list_all(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Gibt alle Eintraege ohne Semantic-Search zurueck, sortiert nach Datum."""
        try:
            out = []
            colls = self.client.list_collections()
            for coll_obj in colls:
                c_name = coll_obj.name if hasattr(coll_obj, 'name') else str(coll_obj)
                coll = self.client.get_collection(name=c_name)
                all_items = coll.get()
                if all_items and all_items.get("documents"):
                    for i, doc in enumerate(all_items["documents"]):
                        meta = all_items["metadatas"][i]
                        out.append({
                            "kind": meta.get("kind", c_name),
                            "key": meta.get("key"),
                            "confidence": meta.get("confidence", 0.0),
                            "content": doc,
                            "updated_at": meta.get("updated_at", ""),
                        })
            out.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            return out[:limit]
        except Exception:
            return []
