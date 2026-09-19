import os
import tempfile

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
