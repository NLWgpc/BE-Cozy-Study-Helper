# pyrefly: ignore [missing-import]
from fastapi import APIRouter, HTTPException, Depends
import sqlite3
import json
from pydantic import BaseModel
from src.db.database import get_db
from src.middleware.auth import get_current_user
from src.controllers.gemini_service import (
    analyze_document_with_gemini,
    chat_with_gemini_service,
    generate_practice_with_gemini,
)

router = APIRouter()


@router.post("/analyze-document/{document_id}")
def analyze_document(
    document_id: int,
    user_id: int = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    # Fetch document
    cursor.execute("SELECT * FROM documents WHERE id = ? AND user_id = ?", (document_id, user_id))
    doc = cursor.fetchone()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc["analysis_status"] == "completed":
        return {"message": "Document already analyzed", "document_id": document_id}

    file_path = doc["file_path"]
    mime_type = doc["file_type"]

    try:
        # Call Gemini service with automatic retry and model/port fallback
        result = analyze_document_with_gemini(file_path, mime_type)

        # Update document title
        cursor.execute(
            "UPDATE documents SET title = ?, analysis_status = 'completed' WHERE id = ?",
            (result.document_title, document_id)
        )

        # Insert extracted questions
        for q in result.questions:
            steps_json = json.dumps(q.steps)
            cursor.execute("""
                INSERT INTO questions (document_id, question_number, question_text, question_type, answer, steps)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (document_id, q.question_number, q.question_text, q.question_type, q.answer, steps_json))

        db.commit()
        return {"message": "Analysis completed successfully", "questions_extracted": len(result.questions)}

    except Exception as e:
        db.rollback()
        cursor.execute("UPDATE documents SET analysis_status = 'failed' WHERE id = ?", (document_id,))
        db.commit()
        raise HTTPException(status_code=500, detail=f"Gemini analysis failed: {str(e)}")


class ChatMessageReq(BaseModel):
    document_id: int
    question_id: int
    message: str


@router.post("/chat")
def chat_with_gemini(
    req: ChatMessageReq,
    user_id: int = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    # Verify document ownership
    cursor.execute("SELECT id FROM documents WHERE id = ? AND user_id = ?", (req.document_id, user_id))
    if not cursor.fetchone():
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Get question details
    cursor.execute(
        "SELECT question_text, steps, answer FROM questions WHERE id = ? AND document_id = ?",
        (req.question_id, req.document_id)
    )
    q_row = cursor.fetchone()
    if not q_row:
        raise HTTPException(status_code=404, detail="Question not found")

    # Construct context prompt
    context_prompt = f"""You are a helpful educational tutor. 
The user is working on the following question:
"{q_row['question_text']}"

The steps to solve it are:
{q_row['steps']}

The final answer is: {q_row['answer']}

The user is asking: "{req.message}"
Respond directly to the user in a friendly, concise, encouraging manner. Do not just give the answer if they ask for a hint. Use step-by-step reasoning.
"""

    try:
        reply = chat_with_gemini_service(context_prompt)
        return {"reply": reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class PracticeReq(BaseModel):
    document_id: int
    num_questions: int
    difficulty: str


@router.post("/generate-practice")
def generate_practice(
    req: PracticeReq,
    user_id: int = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    cursor.execute("SELECT id, title FROM documents WHERE id = ? AND user_id = ?", (req.document_id, user_id))
    if not cursor.fetchone():
        raise HTTPException(status_code=403, detail="Unauthorized")

    cursor.execute("SELECT question_text, steps FROM questions WHERE document_id = ?", (req.document_id,))
    questions = cursor.fetchall()

    if not questions:
        raise HTTPException(status_code=400, detail="No questions found in this document to base practice on.")

    context_data = "\n".join([f"Q: {q['question_text']}\nSteps: {q['steps']}" for q in questions[:5]])

    try:
        practice_qs = generate_practice_with_gemini(
            context_data=context_data,
            num_questions=req.num_questions,
            difficulty=req.difficulty,
        )

        # Save to DB
        cursor.execute(
            "INSERT INTO practice_sets (user_id, document_id, title) VALUES (?, ?, ?)",
            (user_id, req.document_id, f"Practice for Doc {req.document_id} - {req.difficulty}")
        )
        set_id = cursor.lastrowid

        for pq in practice_qs:
            cursor.execute("""
                INSERT INTO practice_questions (practice_set_id, question_text, answer, solution, question_type)
                VALUES (?, ?, ?, ?, ?)
            """, (set_id, pq.get("question_text"), pq.get("answer"), pq.get("solution"), pq.get("question_type")))

        db.commit()
        return {"practice_set_id": set_id, "questions": practice_qs}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
