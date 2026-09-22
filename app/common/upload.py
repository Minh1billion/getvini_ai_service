import os
import tempfile
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, UploadFile

MAX_UPLOAD_BYTES = 500 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024
SPREADSHEET_EXTS = (".xlsx", ".xlsm")


async def save_upload(upload: UploadFile):
    suffix = os.path.splitext(upload.filename or "")[1].lower()
    fd, path = tempfile.mkstemp(suffix=suffix)
    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = await upload.read(CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="file too large")
                out.write(chunk)
    except HTTPException:
        os.remove(path)
        raise
    except Exception as e:
        os.remove(path)
        raise HTTPException(status_code=400, detail=str(e))
    return path, suffix


async def save_upload_from_url(url: str):
    suffix = os.path.splitext(urlparse(url).path)[1].lower()
    fd, path = tempfile.mkstemp(suffix=suffix)
    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes(CHUNK_SIZE):
                        size += len(chunk)
                        if size > MAX_UPLOAD_BYTES:
                            raise HTTPException(status_code=413, detail="file too large")
                        out.write(chunk)
    except HTTPException:
        os.remove(path)
        raise
    except Exception as e:
        os.remove(path)
        raise HTTPException(status_code=400, detail=str(e))
    return path, suffix
