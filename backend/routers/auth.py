"""Auth routes."""
from typing import Dict
from fastapi import APIRouter, HTTPException, Depends, Response
from core import db, verify_password, create_access_token, clean_doc, get_current_user
from schemas import LoginIn

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(body: LoginIn, response: Response):
    email = body.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    if not user.get("attivo", True):
        raise HTTPException(status_code=403, detail="Utente disattivato")
    token = create_access_token(user["id"], user["email"], user["role"])
    response.set_cookie(
        key="access_token", value=token, httponly=True, secure=False,
        samesite="lax", max_age=43200, path="/",
    )
    clean_doc(user)
    return {"user": user, "token": token}


@router.post("/logout")
async def logout(response: Response, user: Dict = Depends(get_current_user)):
    response.delete_cookie(key="access_token", path="/")
    return {"ok": True}


@router.get("/me")
async def auth_me(user: Dict = Depends(get_current_user)):
    return user
