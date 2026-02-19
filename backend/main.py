"""VidKit — AI Video Editor Backend."""
from __future__ import annotations
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from backend.api.upload import router as upload_router
from backend.api.project import router as project_router
from backend.api.edit import router as edit_router
from backend.api.chat import router as chat_router
from backend.api.render import router as render_router
from backend.api.analyze import router as analyze_router
from backend.api.voice import router as voice_router
from backend.api.voiceover import router as voiceover_router

app = FastAPI(title="VidKit", version="0.1.0")

# CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check (before other routes)
@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}

# API routes
app.include_router(upload_router, prefix="/api", tags=["upload"])
app.include_router(project_router, prefix="/api", tags=["project"])
app.include_router(edit_router, prefix="/api", tags=["edit"])
app.include_router(chat_router, prefix="/api", tags=["chat"])
app.include_router(render_router, prefix="/api", tags=["render"])
app.include_router(analyze_router, prefix="/api", tags=["analyze"])
app.include_router(voice_router, prefix="/api", tags=["voice"])
app.include_router(voiceover_router, prefix="/api", tags=["voiceover"])

# Serve TTS output files
TTS_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "projects", "tts_output")
os.makedirs(TTS_OUTPUT_DIR, exist_ok=True)
app.mount("/tts_output", StaticFiles(directory=TTS_OUTPUT_DIR), name="tts_output")

# Serve frontend (catch-all MUST be last)
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.exists(FRONTEND_DIR):
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve the frontend SPA."""
        if full_path.startswith("api/"):
            return {"error": "not found"}
        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
