"""Pydantic schemas for request/response models."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class MessageRole(str, Enum):
    """Message role enumeration."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(BaseModel):
    """Single message in a conversation."""
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str = Field(..., min_length=1, max_length=4000, description="User message")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for context")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "How can I reset my password?",
                "conversation_id": "conv_123456"
            }
        }


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    response: str = Field(..., description="Agent response")
    conversation_id: str = Field(..., description="Conversation ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "response": "I'd be happy to help you reset your password...",
                "conversation_id": "conv_123456",
                "timestamp": "2024-01-15T10:30:00Z"
            }
        }


class ConversationHistory(BaseModel):
    """Model for conversation history."""
    conversation_id: str
    messages: List[Message] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str = "healthy"
    version: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ErrorResponse(BaseModel):
    """Error response model."""
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
