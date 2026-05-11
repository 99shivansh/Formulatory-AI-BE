"""Ticket models and schemas."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class TicketStatus(str, Enum):
    """Ticket status enumeration."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(str, Enum):
    """Ticket priority enumeration."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Ticket(BaseModel):
    """Ticket model."""
    ticket_id: str
    title: str
    description: str
    status: TicketStatus = TicketStatus.OPEN
    priority: TicketPriority = TicketPriority.MEDIUM
    category: Optional[str] = None
    conversation_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None


class TicketCreate(BaseModel):
    """Schema for creating a ticket."""
    title: str = Field(..., description="Brief title of the issue")
    description: str = Field(..., description="Detailed description of the issue")
    priority: TicketPriority = Field(default=TicketPriority.MEDIUM, description="Ticket priority")
    category: Optional[str] = Field(None, description="Category of the issue")


class TicketResponse(BaseModel):
    """Response schema for ticket operations."""
    ticket_id: str
    title: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    category: Optional[str]
    created_at: datetime
    message: Optional[str] = None
