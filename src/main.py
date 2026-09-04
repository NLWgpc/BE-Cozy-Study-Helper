from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from src.db.database import init_db
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize database
init_db()

app = FastAPI(title="Cozy Study Guide API")

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup static files directory if available
public_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public")
for sub in ["css", "js", "assets"]:
    sub_dir = os.path.join(public_dir, sub)
    if os.path.isdir(sub_dir):
        app.mount(f"/{sub}", StaticFiles(directory=sub_dir), name=sub)

# Setup uploads directory
uploads_dir = os.getenv("UPLOAD_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads"))
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

from src.routes.auth_routes import router as auth_router
from src.routes.upload_routes import router as upload_router
from src.routes.gemini_routes import router as gemini_router

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(upload_router, prefix="/api/docs", tags=["docs"])
app.include_router(gemini_router, prefix="/api/gemini", tags=["gemini"])

from fastapi.responses import FileResponse

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/")
async def root():
    index_path = os.path.join(public_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "status": "online",
        "service": "Cozy Study Guide API",
        "docs": "/docs"
    }

@app.get("/login")
async def login_page():
    path = os.path.join(public_dir, "login.html")
    if os.path.exists(path):
        return FileResponse(path)
    return {"message": "API backend only"}

@app.get("/solve")
async def solve_page():
    path = os.path.join(public_dir, "solve.html")
    if os.path.exists(path):
        return FileResponse(path)
    return {"message": "API backend only"}

@app.get("/practice")
async def practice_page():
    path = os.path.join(public_dir, "practice.html")
    if os.path.exists(path):
        return FileResponse(path)
    return {"message": "API backend only"}

@app.get("/history")
async def history_page():
    path = os.path.join(public_dir, "history.html")
    if os.path.exists(path):
        return FileResponse(path)
    return {"message": "API backend only"}

@app.get("/api/config/google-client-id")
async def google_client_id():
    """Public endpoint: returns the Google OAuth Client ID for frontend use."""
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    return {"client_id": client_id}
