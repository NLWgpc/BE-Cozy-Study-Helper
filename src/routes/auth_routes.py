from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
import bcrypt
import sqlite3
from src.db.database import get_db
from src.middleware.auth import create_access_token, get_current_user
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import os

router = APIRouter()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

class UserRegister(BaseModel):
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class GoogleAuthRequest(BaseModel):
    credential: str

@router.post("/register")
def register(user: UserRegister, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    # Check if user exists
    cursor.execute("SELECT id FROM users WHERE email = ?", (user.email,))
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Hash password
    hashed_password = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    try:
        cursor.execute("INSERT INTO users (email, password_hash, auth_provider) VALUES (?, ?, 'local')", (user.email, hashed_password))
        db.commit()
        user_id = cursor.lastrowid
        token = create_access_token(user_id)
        return {"access_token": token, "token_type": "bearer"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/login")
def login(user: UserLogin, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT id, password_hash, auth_provider FROM users WHERE email = ?", (user.email,))
    row = cursor.fetchone()
    
    if not row:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    if row['auth_provider'] == 'google' and not row['password_hash']:
        raise HTTPException(status_code=400, detail="This account uses Google Sign-In. Please log in with Google.")
    
    if not bcrypt.checkpw(user.password.encode('utf-8'), row['password_hash'].encode('utf-8')):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    token = create_access_token(row['id'])
    return {"access_token": token, "token_type": "bearer"}

@router.post("/google")
def google_auth(req: GoogleAuthRequest, db: sqlite3.Connection = Depends(get_db)):
    """Verify a Google ID token and create or log in the user."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google Sign-In is not configured on the server. Set GOOGLE_CLIENT_ID in .env.")
    
    try:
        idinfo = id_token.verify_oauth2_token(
            req.credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID
        )
        
        email = idinfo.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="Could not retrieve email from Google account.")
        
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Google credential. Please try again.")
    
    cursor = db.cursor()
    cursor.execute("SELECT id, auth_provider FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    
    if row:
        # Existing user — log them in
        user_id = row['id']
    else:
        # New user — create account
        try:
            cursor.execute("INSERT INTO users (email, password_hash, auth_provider) VALUES (?, NULL, 'google')", (email,))
            db.commit()
            user_id = cursor.lastrowid
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))
    
    token = create_access_token(user_id)
    return {"access_token": token, "token_type": "bearer"}

@router.get("/me")
def get_me(user_id: int = Depends(get_current_user), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT id, email, created_at FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": row["id"], "email": row["email"]}

