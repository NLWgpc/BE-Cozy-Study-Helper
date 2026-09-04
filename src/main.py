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

# Setup static files directory
public_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public")
app.mount("/css", StaticFiles(directory=os.path.join(public_dir, "css")), name="css")
app.mount("/js", StaticFiles(directory=os.path.join(public_dir, "js")), name="js")
app.mount("/assets", StaticFiles(directory=os.path.join(public_dir, "assets")), name="assets")
app.mount("/uploads", StaticFiles(directory=os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")), name="uploads")

from src.routes.auth_routes import router as auth_router
from src.routes.upload_routes import router as upload_router
from src.routes.gemini_routes import router as gemini_router

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(upload_router, prefix="/api/docs", tags=["docs"])
app.include_router(gemini_router, prefix="/api/gemini", tags=["gemini"])

from fastapi.responses import FileResponse

@app.get("/")
async def root():
    return FileResponse(os.path.join(public_dir, "index.html"))

@app.get("/login")
async def login_page():
    return FileResponse(os.path.join(public_dir, "login.html"))

@app.get("/solve")
async def solve_page():
    return FileResponse(os.path.join(public_dir, "solve.html"))

@app.get("/practice")
async def practice_page():
    return FileResponse(os.path.join(public_dir, "practice.html"))

@app.get("/history")
async def history_page():
    return FileResponse(os.path.join(public_dir, "history.html"))

@app.get("/api/config/google-client-id")
async def google_client_id():
    """Public endpoint: returns the Google OAuth Client ID for frontend use."""
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    return {"client_id": client_id}
