"""Service for managing conversations."""

import uuid
from typing import Dict, Optional
from datetime import datetime
from loguru import logger

from app.models.schemas import Message, MessageRole, ConversationHistory
from app.config import get_settings


class ConversationService:
    """Service for managing conversation history."""
    
    def __init__(self):
        """Initialize the conversation service."""
        self.settings = get_settings()
        # In-memory storage (replace with Redis/DB for production)
        self._conversations: Dict[str, ConversationHistory] = {}
    
    def create_conversation(self) -> str:
        """
        Create a new conversation.
        
        Returns:
            New conversation ID
        """
        conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
        self._conversations[conversation_id] = ConversationHistory(
            conversation_id=conversation_id,
            messages=[],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        logger.info(f"Created new conversation: {conversation_id}")
        return conversation_id
    
    def get_conversation(self, conversation_id: str) -> Optional[ConversationHistory]:
        """
        Get a conversation by ID.
        
        Args:
            conversation_id: The conversation ID
            
        Returns:
            ConversationHistory or None if not found
        """
        return self._conversations.get(conversation_id)
    
    def add_message(
        self,
        conversation_id: str,
        role: MessageRole,
        content: str,
    ) -> None:
        """
        Add a message to a conversation.
        
        Args:
            conversation_id: The conversation ID
            role: Message role (user/assistant)
            content: Message content
        """
        if conversation_id not in self._conversations:
            self.create_conversation()
            self._conversations[conversation_id] = ConversationHistory(
                conversation_id=conversation_id,
                messages=[],
            )
        
        message = Message(
            role=role,
            content=content,
            timestamp=datetime.utcnow(),
        )
        self._conversations[conversation_id].messages.append(message)
        self._conversations[conversation_id].updated_at = datetime.utcnow()
        
        # Trim history if too long
        max_history = self.settings.max_conversation_history * 2  # User + Assistant pairs
        if len(self._conversations[conversation_id].messages) > max_history:
            self._conversations[conversation_id].messages = \
                self._conversations[conversation_id].messages[-max_history:]
    
    def get_history(self, conversation_id: str) -> list[Message]:
        """
        Get conversation history.
        
        Args:
            conversation_id: The conversation ID
            
        Returns:
            List of messages
        """
        conversation = self.get_conversation(conversation_id)
        if conversation:
            return conversation.messages
        return []
    
    def clear_conversation(self, conversation_id: str) -> bool:
        """
        Clear a conversation's history.
        
        Args:
            conversation_id: The conversation ID
            
        Returns:
            True if cleared, False if not found
        """
        if conversation_id in self._conversations:
            self._conversations[conversation_id].messages = []
            self._conversations[conversation_id].updated_at = datetime.utcnow()
            logger.info(f"Cleared conversation: {conversation_id}")
            return True
        return False
    
    def delete_conversation(self, conversation_id: str) -> bool:
        """
        Delete a conversation.
        
        Args:
            conversation_id: The conversation ID
            
        Returns:
            True if deleted, False if not found
        """
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
            logger.info(f"Deleted conversation: {conversation_id}")
            return True
        return False


# Singleton instance
_service_instance: Optional[ConversationService] = None


def get_conversation_service() -> ConversationService:
    """Get or create the conversation service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ConversationService()
    return _service_instance
