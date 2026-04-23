"""File upload/download + signature capture via object storage."""
import logging
from typing import Dict, Optional
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Response, Query, Header
from pydantic import BaseModel
import jwt

from core import db, new_id, now_utc, get_current_user, log_audit, JWT_SECRET, JWT_ALGORITHM
from storage import upload_bytes, get_object, decode_data_url

logger = logging.getLogger("cleantec.files")
router = APIRouter(tags=["files"])

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXT = {"jpg", "jpeg", "png", "webp", "gif", "pdf"}


class SignatureIn(BaseModel):
    data_url: str
    context: Optional[str] = "signature"


async def _register_file(user: Dict, file_info: dict, original_filename: str, context: str) -> dict:
    record = {
        "id": new_id(),
        "storage_path": file_info["path"],
        "original_filename": original_filename,
        "content_type": file_info["content_type"],
        "size": file_info["size"],
        "context": context,
        "uploaded_by": user["id"],
        "uploaded_by_name": user["name"],
        "is_deleted": False,
        "created_at": now_utc(),
        "url": file_info["url"],
    }
    await db.files.insert_one(record)
    record.pop("_id", None)
    return record


@router.post("/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    context: str = Query("misc"),
    user: Dict = Depends(get_current_user),
):
    ext = (file.filename or "").split(".")[-1].lower() if file.filename and "." in file.filename else "bin"
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"Estensione non ammessa: {ext}. Ammesse: {sorted(ALLOWED_EXT)}")

    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(400, f"File troppo grande (max {MAX_FILE_SIZE // 1024 // 1024} MB)")
    if not data:
        raise HTTPException(400, "File vuoto")

    try:
        info = upload_bytes(data, ext, folder=context, content_type=file.content_type)
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(500, "Upload fallito")

    record = await _register_file(user, info, file.filename or f"upload.{ext}", context)
    await log_audit(user, "UPLOAD", "file", record["id"], {"context": context, "size": info["size"]})
    return record


@router.post("/files/signature")
async def upload_signature(body: SignatureIn, user: Dict = Depends(get_current_user)):
    """Accept a canvas signature as base64 data URL and persist as PNG."""
    try:
        data, ext = decode_data_url(body.data_url)
    except Exception:
        raise HTTPException(400, "Data URL non valido")
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(400, "Firma troppo grande")
    try:
        info = upload_bytes(data, ext, folder=body.context or "signatures", content_type=f"image/{ext if ext != 'jpg' else 'jpeg'}")
    except Exception as e:
        logger.error(f"Signature upload failed: {e}")
        raise HTTPException(500, "Upload firma fallito")
    record = await _register_file(user, info, f"signature.{ext}", body.context or "signature")
    await log_audit(user, "UPLOAD", "signature", record["id"], {"context": body.context})
    return record


@router.get("/files/{path:path}")
async def download_file(
    path: str,
    authorization: Optional[str] = Header(None),
    auth: Optional[str] = Query(None),
):
    """Serve uploaded file. Supports Authorization: Bearer OR ?auth=<token> (for <img src>)."""
    # Resolve token from either header or query
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif auth:
        token = auth
    if not token:
        raise HTTPException(401, "Non autenticato")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
        if not user or not user.get("attivo", True):
            raise HTTPException(401, "Utente non valido")
    except jwt.PyJWTError:
        raise HTTPException(401, "Token non valido")

    record = await db.files.find_one({"storage_path": path, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(404, "File non trovato")

    try:
        data, content_type = get_object(path)
    except Exception as e:
        logger.error(f"Object fetch failed: {e}")
        raise HTTPException(500, "Errore lettura file")
    return Response(content=data, media_type=record.get("content_type", content_type))


@router.delete("/files/{file_id}")
async def soft_delete_file(file_id: str, user: Dict = Depends(get_current_user)):
    res = await db.files.update_one({"id": file_id}, {"$set": {"is_deleted": True, "deleted_at": now_utc(), "deleted_by": user["id"]}})
    if res.matched_count == 0:
        raise HTTPException(404, "File non trovato")
    await log_audit(user, "DELETE", "file", file_id)
    return {"ok": True}
