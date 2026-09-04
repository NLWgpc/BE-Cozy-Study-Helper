from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
import sqlite3
import os
import uuid
import datetime
from src.db.database import get_db
from src.middleware.auth import get_current_user

router = APIRouter()

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db)
):
    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/webp", "application/pdf"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    
    # Generate unique filename
    ext = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    
    # Save file
    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not save file")
    
    # Save to database
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO documents (user_id, title, original_filename, file_path, file_type, analysis_status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, file.filename, file.filename, file_path, file.content_type, "pending"))
    db.commit()
    document_id = cursor.lastrowid
    
    return {
        "message": "File uploaded successfully",
        "document_id": document_id
    }

@router.get("/history")
def get_history(
    user_id: int = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    cursor.execute("""
        SELECT d.id, d.title, d.uploaded_at, d.analysis_status, COUNT(q.id) as question_count
        FROM documents d
        LEFT JOIN questions q ON d.id = q.document_id
        WHERE d.user_id = ?
        GROUP BY d.id
        ORDER BY d.uploaded_at DESC
    """, (user_id,))
    
    history = [dict(row) for row in cursor.fetchall()]
    return {"history": history}

@router.get("/{document_id}")
def get_document(
    document_id: int,
    user_id: int = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    cursor.execute("SELECT id, title, file_path, analysis_status FROM documents WHERE id = ? AND user_id = ?", (document_id, user_id))
    doc = cursor.fetchone()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    doc_dict = dict(doc)
    doc_dict["file_url"] = f"/uploads/{os.path.basename(doc_dict['file_path'])}"
        
    cursor.execute("SELECT * FROM questions WHERE document_id = ? ORDER BY id ASC", (document_id,))
    questions = [dict(row) for row in cursor.fetchall()]
    
    return {
        "document": doc_dict,
        "questions": questions
    }
