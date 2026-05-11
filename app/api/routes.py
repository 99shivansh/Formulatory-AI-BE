"""API routes for the support agent."""

from fastapi import APIRouter, HTTPException, status
from loguru import logger

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ErrorResponse,
    MessageRole,
)
from app.agent.support_agent import get_agent
from app.services.conversation_service import get_conversation_service
from app import __version__

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Check if the API is running",
)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version=__version__,
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    summary="Chat with Support Agent",
    description="Send a message to the support agent and get a response",
)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Chat endpoint for interacting with the support agent.
    
    - **message**: The user's message
    - **conversation_id**: Optional conversation ID for maintaining context
    """
    try:
        agent = get_agent()
        conversation_service = get_conversation_service()
        
        # Get or create conversation
        conversation_id = request.conversation_id
        if not conversation_id:
            conversation_id = conversation_service.create_conversation()
        
        # Get conversation history
        history = conversation_service.get_history(conversation_id)
        
        # Add user message to history
        conversation_service.add_message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=request.message,
        )
        
        # Generate response
        response = await agent.chat(
            user_message=request.message,
            conversation_history=history,
            conversation_id=conversation_id,
        )
        
        # Add assistant response to history
        conversation_service.add_message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=response,
        )
        
        logger.info(f"Processed chat request for conversation: {conversation_id}")
        
        return ChatResponse(
            response=response,
            conversation_id=conversation_id,
        )
        
    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post(
    "/conversation/new",
    response_model=dict,
    summary="Create New Conversation",
    description="Start a new conversation session",
)
async def new_conversation() -> dict:
    """Create a new conversation session."""
    conversation_service = get_conversation_service()
    conversation_id = conversation_service.create_conversation()
    return {"conversation_id": conversation_id}


@router.delete(
    "/conversation/{conversation_id}",
    response_model=dict,
    summary="Delete Conversation",
    description="Delete a conversation and its history",
)
async def delete_conversation(conversation_id: str) -> dict:
    """Delete a conversation."""
    conversation_service = get_conversation_service()
    success = conversation_service.delete_conversation(conversation_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    
    return {"message": "Conversation deleted", "conversation_id": conversation_id}


@router.post(
    "/conversation/{conversation_id}/clear",
    response_model=dict,
    summary="Clear Conversation History",
    description="Clear the message history for a conversation",
)
async def clear_conversation(conversation_id: str) -> dict:
    """Clear conversation history."""
    conversation_service = get_conversation_service()
    success = conversation_service.clear_conversation(conversation_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    
    return {"message": "Conversation cleared", "conversation_id": conversation_id}
