"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

# Core application schemas for the dual-interface medication app

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: Optional[str] = Field(None, description="Email address")
    role: str = Field("patient", description="Role: patient or caregiver")
    patient_id: Optional[str] = Field(None, description="If caregiver, the patient this caregiver monitors")

class Medication(BaseModel):
    """
    Medications assigned to a patient
    Collection name: "medication"
    """
    user_id: str = Field(..., description="Patient user id")
    name: str = Field(..., description="Medication name")
    dosage: str = Field(..., description="Dosage description, e.g., '5mg' or '1 tablet'")
    schedule_times: List[str] = Field(..., description="List of HH:MM times the medication should be taken each day")
    inventory_count: int = Field(0, ge=0, description="Current pill count in inventory")
    low_threshold: int = Field(10, ge=0, description="Threshold to trigger low-inventory alert")

class DoseEvent(BaseModel):
    """
    Records scheduled and taken doses
    Collection name: "doseevent"
    """
    user_id: str = Field(..., description="Patient user id")
    medication_id: str = Field(..., description="Medication id")
    scheduled_time: datetime = Field(..., description="Scheduled date-time for this dose (UTC)")
    taken_time: Optional[datetime] = Field(None, description="When the dose was confirmed (UTC)")
    status: str = Field("scheduled", description="Status: scheduled|taken|missed|skipped")

# Note: The Flames database viewer will automatically:
# 1. Read these schemas from GET /schema endpoint
# 2. Use them for document validation when creating/editing
# 3. Handle all database operations (CRUD) directly
# 4. You don't need to create any database endpoints!
