import os
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from typing import Optional

from fastapi import HTTPException, UploadFile

MAX_UPLOAD_BYTES = 500 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024
SPREADSHEET_EXTS = (".xlsx", ".xlsm")


def list_sheet_names(path: str):
    with zipfile.ZipFile(path) as z:
        with z.open("xl/workbook.xml") as f:
            tree = ET.parse(f)
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    return [el.get("name") for el in tree.getroot().findall(".//main:sheets/main:sheet", ns)]


def resolve_sheet_names(path: str, sheet_names: Optional[str]):
    all_names = list_sheet_names(path)
    if not all_names:
        raise ValueError("Không tìm thấy sheet nào trong file")
    if not sheet_names:
        return [all_names[0]]
    normalized_all = {name.strip(): name for name in all_names}
    requested = [s.strip() for s in sheet_names.split(",") if s.strip()]
    resolved = []
    unmatched = []
    for name in requested:
        if name in normalized_all:
            resolved.append(normalized_all[name])
        else:
            unmatched.append(name)
    if unmatched:
        raise ValueError(f"Không tìm thấy sheet: {', '.join(unmatched)}")
    if not resolved:
        raise ValueError("Không có sheet hợp lệ nào được chọn")
    return resolved


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
