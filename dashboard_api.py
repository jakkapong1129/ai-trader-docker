import os
import json
import asyncio
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="AI Trader Command Deck API")
SHARED_DIR = "/app/shared"

def get_selected_account_type() -> str:
    """Read the account mode selected by the dashboard, defaulting safely to demo."""
    try:
        with open(os.path.join(SHARED_DIR, "account_type.txt"), "r") as account_file:
            account_type = account_file.read().strip().lower()
            if account_type in ("demo", "real"):
                return account_type
    except OSError:
        pass
    return "demo"

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared memory/in-memory state
state_db: Dict[str, Any] = {
    "balance": 0.0,
    "real_balance": 0.0,
    "demo_balance": 0.0,
    "active_assets": [],
    "bot_status": "Stopped",  # Running, Paused, Stopped
    "bot_phase": "Stopped",
    "next_scan_at": None,
    "open_positions": [],
    "mg_level": 0,
    "round_num": 0,
    "total_trades": 0,
    "total_wins": 0,
    "total_losses": 0,
    "account_type": get_selected_account_type(),
    "history": [],
    "assets": []
}

clients: List[asyncio.Queue] = []

class StateUpdate(BaseModel):
    balance: float
    real_balance: float
    demo_balance: float
    bot_status: str
    bot_phase: str
    next_scan_at: Optional[str] = None
    open_positions: List[Dict[str, Any]]
    mg_level: int
    round_num: int
    total_trades: int
    total_wins: int
    total_losses: int
    account_type: str
    history: List[Dict[str, Any]]
    assets: List[Dict[str, Any]]

@app.post("/api/update")
async def update_state(data: StateUpdate):
    """Called by the bot script to push latest status"""
    state_db.update(data.dict())
    
    # Broadcast to all SSE clients
    payload = json.dumps(state_db)
    for q in clients:
        await q.put(payload)
        
    return {"status": "ok"}

@app.get("/api/state")
async def get_state():
    """Direct JSON query for state"""
    state_db["account_type"] = get_selected_account_type()
    return state_db

@app.get("/api/trades")
async def get_trades(account_type: str, limit: int = 10):
    """Return trade history for the account selected in the dashboard."""
    if account_type not in ("demo", "real"):
        raise HTTPException(status_code=400, detail="account_type must be 'demo' or 'real'")

    try:
        from models import Database

        trades = Database().get_trades(limit=max(1, min(limit, 100)), account_type=account_type)
        return {
            "account_type": account_type,
            "history": [trade.to_dict() for trade in trades],
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Trade history is temporarily unavailable") from exc

@app.delete("/api/trades/{account_type}")
async def clear_trades(account_type: str):
    """Clear all trade history for one account, never both at once."""
    if account_type not in ("demo", "real"):
        raise HTTPException(status_code=400, detail="account_type must be 'demo' or 'real'")
    if state_db.get("bot_status") == "Running":
        raise HTTPException(status_code=409, detail="Stop or pause the bot before clearing trade history")

    try:
        from models import Database

        deleted_count = Database().delete_trades_for_account(account_type)
        if state_db.get("account_type") == account_type:
            state_db["history"] = []
        payload = json.dumps(state_db)
        for q in clients:
            await q.put(payload)
        return {"status": "success", "account_type": account_type, "deleted_count": deleted_count}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Trade history is temporarily unavailable") from exc

@app.post("/api/control")
async def bot_control(action_req: Dict[str, str]):
    """Receives buttons clicks from dashboard and updates local file/db settings"""
    action = action_req.get("action")
    if action in ("start", "stop", "pause", "restart", "real", "demo"):
        # We can write a control status file or db flag
        # Let's save a file that auto_loop.py reads on each round
        shared_dir = SHARED_DIR
        os.makedirs(shared_dir, exist_ok=True)
        control_path = os.path.join(shared_dir, "bot_control.txt")
        
        if action in ("real", "demo"):
            if state_db.get("bot_status") == "Running":
                raise HTTPException(
                    status_code=409,
                    detail="Stop or pause the bot before changing account mode",
                )
            # Update account type
            account_type_path = os.path.join(shared_dir, "account_type.txt")
            with open(account_type_path, "w") as f:
                f.write(action)
            state_db["account_type"] = action
            payload = json.dumps(state_db)
            for q in clients:
                await q.put(payload)
            return {"status": "success", "new_account_type": action}
            
        with open(control_path, "w") as f:
            f.write(action)
        
        if action == "restart":
            state_db["bot_status"] = "Restarting..."
            state_db["mg_level"] = 0
        else:
            state_db["bot_status"] = action.capitalize() + "ped" if action == "stop" else action.capitalize() + "d" if action == "pause" else "Running"
        
        # Broadcast the change
        payload = json.dumps(state_db)
        for q in clients:
            await q.put(payload)
            
        return {"status": "success", "new_status": state_db["bot_status"]}
    return {"status": "error", "message": "Invalid action"}

@app.get("/api/sse")
async def sse_endpoint(request: Request):
    """Server-Sent Events for real-time dashboard updates"""
    queue = asyncio.Queue()
    clients.append(queue)
    
    # Send current state immediately, including a selection made before a page reload.
    state_db["account_type"] = get_selected_account_type()
    await queue.put(json.dumps(state_db))
    
    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    # Keep-alive ping
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in clients:
                clients.remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# Host dashboard directly under root /
@app.get("/")
async def get_dashboard():
    return FileResponse("dashboard-command-deck.html")
