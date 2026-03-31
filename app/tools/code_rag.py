import os
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
import datetime

# Chroma & NLP
import chromadb
from chromadb.utils import embedding_functions
from sentence_transformers import SentenceTransformer

from app.config import ROOT_DIR
from app.tools.filesystem import _safe_abspath

# Pfade für den Index
DB_PATH = str((ROOT_DIR / "data" / "rag_index").resolve())

# Embedding Funktion (Standard MiniLM-L6-v2, lokal und performant)
_emb_fn = None

def _get_embedding_fn():
    global _emb_fn
    if _emb_fn is None:
        # Initialisiert die Sentence-Transformers Instanz
        _emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    return _emb_fn

def fs_index_workspace(path: str = ".") -> Dict[str, Any]:
    """
    Indiziert den Workspace semantisch für die Code-Suche.
    Durchwandelt alle Textdateien, erstellt Chunks und speichert Embeddings in ChromaDB.
    """
    root = _safe_abspath(path)
    client = chromadb.PersistentClient(path=DB_PATH)
    
    # Collection erstellen (oder überschreiben falls bereits vorhanden)
    try:
        client.delete_collection("codebase")
    except:
        pass
    collection = client.create_collection(
        name="codebase", 
        embedding_function=_get_embedding_fn()
    )
    
    indexed_files = 0
    total_chunks = 0
    
    # Unterstützte Dateitypen
    EXTS = {'.py', '.js', '.ts', '.html', '.css', '.md', '.json', '.txt', '.cpp', '.h', '.cs', '.java'}
    
    for r, _, files in os.walk(root):
        # Ignore common garbage & temp outputs
        if any(x in r.lower() for x in {".git", "__pycache__", ".venv", "node_modules", "dist", "build", "rag_index", "tool_outputs"}):
            continue
            
        for f in files:
            p = Path(r) / f
            if p.suffix.lower() in EXTS:
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    if not content.strip(): continue
                    
                    # Chunker: 1000 Zeichen mit 200 Overlap
                    chunks = _chunk_text(content, 1000, 200)
                    
                    # 🚨 Verbesserung: Dateiname an den Anfang jedes Chunks, um Relevanz zu steigern
                    enriched_chunks = [f"File: {p.name}\n{c}" for c in chunks]
                    
                    ids = [f"{p.name}_{i}" for i in range(len(enriched_chunks))]
                    metadatas = [{"path": str(p), "chunk": i} for i in range(len(enriched_chunks))]
                    
                    collection.add(
                        documents=enriched_chunks,
                        ids=ids,
                        metadatas=metadatas
                    )
                    indexed_files += 1
                    total_chunks += len(chunks)
                except Exception:
                    continue
                    
    return {
        "ok": True,
        "indexed_files": indexed_files,
        "total_chunks": total_chunks,
        "message": f"Workspace indiziert: {indexed_files} Dateien, {total_chunks} Chunks gespeichert."
    }

def fs_search_codebase(query: str, top_k: int = 5) -> Dict[str, Any]:
    """
    Sucht semantisch in der indizierten Codebase nach dem besten Match für eine Anfrage.
    Gibt Code-Snippets und Pfade zurück.
    """
    client = chromadb.PersistentClient(path=DB_PATH)
    try:
        collection = client.get_collection(name="codebase", embedding_function=_get_embedding_fn())
    except:
        return {"ok": False, "error": "Index nicht gefunden. Bitte zuerst fs_index_workspace() ausfuehren."}
    
    results = collection.query(
        query_texts=[query],
        n_results=top_k
    )
    
    output = []
    if results and results.get("documents"):
        for i in range(len(results["documents"][0])):
            doc = results["documents"][0][i]
            meta = results["metadatas"][0][i]
            dist = results["distances"][0][i] if "distances" in results else 0
            
            output.append({
                "path": meta["path"],
                "snippet": doc,
                "score": round(1.0 - dist, 4) # Naive score conversion
            })
            
    return {"ok": True, "results": output}

def _chunk_text(text: str, size: int, overlap: int) -> List[str]:
    chunks = []
    if len(text) <= size:
        return [text]
        
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += size - overlap
    return chunks
