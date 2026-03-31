from __future__ import annotations

import functools
import time
import traceback
from typing import Any, Callable, Dict, Type, Optional

from pydantic import BaseModel, ValidationError

from app.tool_engine import tool_store


def validated_tool(tool_name: str, model: Type[BaseModel] | None):
    """Decorator factory to validate kwargs against a pydantic model and log calls.

    Assumes callers use keyword arguments or a single dict positional arg.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # normalize inputs to a dict using the target function signature
            data: Dict[str, Any] = {}
            try:
                import inspect

                sig = inspect.signature(func)
                bound = sig.bind_partial(*args, **kwargs)
                data = dict(bound.arguments)
            except Exception:
                # fallback: if single dict positional provided, use it; otherwise use kwargs
                if len(args) == 1 and isinstance(args[0], dict) and not kwargs:
                    data = dict(args[0])
                else:
                    data = dict(kwargs)

            validated = None
            if model is not None:
                try:
                    validated = model(**data)
                    data = validated.model_dump()
                except ValidationError as e:
                    tool_store.log(tool_name, f"validation_error: {e}")
                    raise

            tool_store.log(tool_name, f"call args: { {k: (str(v)[:200]) for k,v in data.items()} }")
            start = time.time()
            try:
                result = func(**data)
                dur = time.time() - start
                tool_store.log(tool_name, f"ok ({dur:.3f}s)")
                return result
            except Exception as exc:  # pragma: no cover - runtime failure logging
                tb = traceback.format_exc()
                tool_store.log(tool_name, f"exception: {exc}; tb: {tb}")
                raise

        return wrapper

    return decorator


# Common pydantic models for tool args
class RunPythonModel(BaseModel):
    code: str
    timeout: int = 120


class RunPowershellModel(BaseModel):
    script: str
    timeout: int = 120


class ListEntriesModel(BaseModel):
    path: str
    want: str = "files"
    recursive: bool = False
    ext: Optional[str] = None
    max_items: Optional[int] = None


class ScreenshotModel(BaseModel):
    target_path: str


# Filesystem-related models
class ReadFileModel(BaseModel):
    path: str


class WriteFileModel(BaseModel):
    path: str
    content: str


class AppendFileModel(BaseModel):
    path: str
    content: str


class DeletePathModel(BaseModel):
    path: str
    use_trash: bool = True


class CopyMoveModel(BaseModel):
    src: str
    dst: str


class CopyAllFilesModel(BaseModel):
    src_dir: str
    dst_dir: str
    ext: Optional[str] = None
    recursive: bool = True
    """True = alle Unterordner einschliessen (Standard). False = nur Dateien direkt im src_dir."""


class MoveAllFilesModel(BaseModel):
    src_dir: str
    dst_dir: str
    ext: Optional[str] = None
    recursive: bool = True
    """True = alle Unterordner einschliessen (Standard). False = nur Dateien direkt im src_dir."""


class BulkDeleteExtModel(BaseModel):
    folder: str
    ext: str
    recursive: bool = False
    use_trash: bool = True


class CreateZipModel(BaseModel):
    src_path: str
    archive_path: str
    recursive: bool = True


class ExtractZipModel(BaseModel):
    archive_path: str
    target_dir: str


class ExportEntriesModel(BaseModel):
    path: str
    out_path: str
    want: str = "files"
    recursive: bool = True
    ext: Optional[str] = None
