"""Attacker webhook server -- receives and displays exfiltrated data."""

from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Attacker Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Reason: In-memory store -- no persistence needed for a demo
received_data: list[dict] = []


class ExfilPayload(BaseModel):
    """Schema for received exfiltration data."""

    title: str = ""
    body: str = ""


@app.post("/exfil")
async def receive_exfil(payload: ExfilPayload):
    """Receive exfiltrated data and store it for display."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "title": payload.title,
        "body": payload.body,
        "size_bytes": len(payload.body.encode()),
    }
    received_data.append(entry)
    return {"status": "received", "id": len(received_data)}


@app.get("/exfil")
async def list_exfil():
    """List all received exfiltration payloads."""
    return {"count": len(received_data), "entries": received_data}


@app.delete("/exfil")
async def clear_exfil():
    """Clear all received data (used by demo reset)."""
    received_data.clear()
    return {"status": "cleared"}


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "ok"}
