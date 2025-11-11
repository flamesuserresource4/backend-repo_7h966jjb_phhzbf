import os
from datetime import datetime, date, time, timedelta, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Medication Assistant Backend Running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# ----------------------
# Schemas for requests
# ----------------------
class ConfirmDoseRequest(BaseModel):
    user_id: str
    medication_id: str
    scheduled_time_iso: str  # ISO datetime string for the scheduled dose


class TodayStatusResponse(BaseModel):
    user_id: str
    date: str
    total_doses: int
    taken: int
    missed: int
    upcoming: int
    items: list


# ----------------------
# Helper functions
# ----------------------

def _start_end_of_today_utc() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


# ----------------------
# Core Endpoints
# ----------------------

@app.get("/api/senior/today", response_model=TodayStatusResponse)
def get_today_status(user_id: str):
    """Return simplified status for today's doses for the given patient user_id"""
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    start, end = _start_end_of_today_utc()

    # Query dose events for today
    events = db["doseevent"].find({
        "user_id": user_id,
        "scheduled_time": {"$gte": start, "$lt": end}
    })

    items = []
    taken = missed = upcoming = 0

    for ev in events:
        status = ev.get("status", "scheduled")
        if status == "taken":
            taken += 1
        elif status == "missed":
            missed += 1
        else:
            upcoming += 1
        items.append({
            "dose_event_id": str(ev.get("_id")),
            "medication_id": ev.get("medication_id"),
            "scheduled_time": ev.get("scheduled_time").isoformat() if ev.get("scheduled_time") else None,
            "status": status
        })

    return TodayStatusResponse(
        user_id=user_id,
        date=datetime.now(timezone.utc).date().isoformat(),
        total_doses=len(items),
        taken=taken,
        missed=missed,
        upcoming=upcoming,
        items=items
    )


@app.post("/api/senior/confirm")
def confirm_dose(req: ConfirmDoseRequest):
    """Senior confirms they took a scheduled dose. Marks the dose as taken and updates timestamps."""
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    # Find the scheduled dose event
    try:
        scheduled = datetime.fromisoformat(req.scheduled_time_iso)
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=timezone.utc)
        else:
            scheduled = scheduled.astimezone(timezone.utc)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid scheduled_time_iso")

    ev = db["doseevent"].find_one({
        "user_id": req.user_id,
        "medication_id": req.medication_id,
        "scheduled_time": scheduled
    })

    if not ev:
        raise HTTPException(status_code=404, detail="Scheduled dose not found")

    db["doseevent"].update_one({"_id": ev["_id"]}, {"$set": {
        "status": "taken",
        "taken_time": datetime.now(timezone.utc)
    }})

    return {"status": "ok"}


@app.get("/api/caregiver/dashboard")
def caregiver_dashboard(patient_id: str):
    """
    Rich caregiver view:
    - medication history (last 30 days)
    - missed dose alerts (last 7 days)
    - low inventory reminders
    """
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")

    now = datetime.now(timezone.utc)
    start_30 = now - timedelta(days=30)
    start_7 = now - timedelta(days=7)

    # History: last 30 days dose events
    history = list(db["doseevent"].find({
        "user_id": patient_id,
        "scheduled_time": {"$gte": start_30}
    }).sort("scheduled_time", 1))

    # Missed last 7 days
    missed = list(db["doseevent"].find({
        "user_id": patient_id,
        "status": "missed",
        "scheduled_time": {"$gte": start_7}
    }).sort("scheduled_time", -1))

    # Inventory reminders
    meds = list(db["medication"].find({"user_id": patient_id}))
    inventory_alerts = []
    for m in meds:
        if int(m.get("inventory_count", 0)) <= int(m.get("low_threshold", 0)):
            inventory_alerts.append({
                "medication_id": str(m.get("_id")),
                "name": m.get("name"),
                "inventory_count": m.get("inventory_count"),
                "low_threshold": m.get("low_threshold"),
            })

    def _serialize_event(e):
        return {
            "id": str(e.get("_id")),
            "medication_id": e.get("medication_id"),
            "scheduled_time": e.get("scheduled_time").isoformat() if e.get("scheduled_time") else None,
            "taken_time": e.get("taken_time").isoformat() if e.get("taken_time") else None,
            "status": e.get("status"),
        }

    return {
        "history": [_serialize_event(e) for e in history],
        "missed": [_serialize_event(e) for e in missed],
        "inventory_alerts": inventory_alerts
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
