import os
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List, Optional

# We will initialize the client inside the function so it doesn't crash the server on startup if the API key is missing.

class ExtractedQuestion(BaseModel):
    question_number: str = Field(description="The number or letter of the question (e.g., '1', 'a', '2.1')")
    question_text: str = Field(description="The exact or faithfully transcribed text of the question")
    question_type: str = Field(description="Type of question: e.g., 'math', 'multiple-choice', 'short-answer', etc.")
    answer: Optional[str] = Field(description="The final answer to the question, if it can be determined")
    steps: List[str] = Field(description="A step-by-step educational explanation on how to solve it")

class DocumentAnalysisResult(BaseModel):
    document_title: str = Field(description="A short descriptive title for the document")
    questions: List[ExtractedQuestion]

def analyze_document_with_gemini(file_path: str, mime_type: str) -> DocumentAnalysisResult:
    """Uploads the file to Gemini and extracts questions according to the schema."""
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_gemini_api_key_here":
        raise ValueError("GEMINI_API_KEY environment variable is not set correctly.")
        
    client = genai.Client(api_key=api_key)
    
    # Upload file to Gemini using the Files API (required for multimodal)
    uploaded_file = client.files.upload(file=file_path, config={'mime_type': mime_type})
    
    prompt = """You are an educational question-paper analysis assistant.
Analyze the uploaded document carefully.
Your first task is to identify every individual question in the document.
Do not merge separate questions. Use numbering, lettering, spacing, visual grouping, page layout, indentation, and semantic context to determine question boundaries.
For example, '1 + 1 =' and '2 + 2 =' must become two separate questions.
Preserve subquestions as children of their parent question when appropriate, or label them clearly like '1a'.

For each question, extract the question number, exact text, question type, the final answer (if solvable), and a step-by-step educational explanation of how to solve it.
Do not skip questions. If the document is unclear, state what is unclear rather than inventing missing content.
"""

    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=[uploaded_file, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=DocumentAnalysisResult,
            temperature=0.2,
        ),
    )
    
    # Delete the file from Gemini storage after processing
    client.files.delete(name=uploaded_file.name)
    
    # Parse the result
    return DocumentAnalysisResult.model_validate_json(response.text)
