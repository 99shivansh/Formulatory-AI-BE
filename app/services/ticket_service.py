"""Service for managing support tickets."""

import uuid
from typing import Dict, Optional, List
from datetime import datetime
from loguru import logger

from app.models.ticket import Ticket, TicketStatus, TicketPriority


class TicketService:
    """Service for managing support tickets."""
    
    def __init__(self):
        """Initialize the ticket service."""
        # In-memory storage (replace with DB for production)
        self._tickets: Dict[str, Ticket] = {}
    
    def create_ticket(
        self,
        title: str,
        description: str,
        priority: str = "medium",
        category: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Ticket:
        """
        Create a new support ticket.
        
        Args:
            title: Brief title of the issue
            description: Detailed description of the issue
            priority: Ticket priority (low, medium, high, urgent)
            category: Category of the issue
            conversation_id: Associated conversation ID
            
        Returns:
            Created ticket
        """
        ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
        
        # Parse priority
        try:
            ticket_priority = TicketPriority(priority.lower())
        except ValueError:
            ticket_priority = TicketPriority.MEDIUM
        
        ticket = Ticket(
            ticket_id=ticket_id,
            title=title,
            description=description,
            status=TicketStatus.OPEN,
            priority=ticket_priority,
            category=category,
            conversation_id=conversation_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        
        self._tickets[ticket_id] = ticket
        logger.info(f"Created ticket: {ticket_id} - {title}")
        
        return ticket
    
    def get_ticket(self, ticket_id: str) -> Optional[Ticket]:
        """
        Get a ticket by ID.
        
        Args:
            ticket_id: The ticket ID
            
        Returns:
            Ticket or None if not found
        """
        # Normalize ticket ID format
        ticket_id = ticket_id.upper()
        if not ticket_id.startswith("TKT-"):
            ticket_id = f"TKT-{ticket_id}"
        
        ticket = self._tickets.get(ticket_id)
        if ticket:
            logger.info(f"Retrieved ticket: {ticket_id}")
        else:
            logger.warning(f"Ticket not found: {ticket_id}")
        return ticket
    
    def update_ticket_status(
        self,
        ticket_id: str,
        status: str,
    ) -> Optional[Ticket]:
        """
        Update a ticket's status.
        
        Args:
            ticket_id: The ticket ID
            status: New status
            
        Returns:
            Updated ticket or None if not found
        """
        ticket = self.get_ticket(ticket_id)
        if not ticket:
            return None
        
        try:
            ticket.status = TicketStatus(status.lower())
            ticket.updated_at = datetime.utcnow()
            
            if ticket.status == TicketStatus.RESOLVED:
                ticket.resolved_at = datetime.utcnow()
            
            logger.info(f"Updated ticket {ticket_id} status to: {status}")
            return ticket
        except ValueError:
            logger.error(f"Invalid status: {status}")
            return None
    
    def list_tickets(
        self,
        status: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> List[Ticket]:
        """
        List tickets with optional filters.
        
        Args:
            status: Filter by status
            conversation_id: Filter by conversation ID
            
        Returns:
            List of tickets
        """
        tickets = list(self._tickets.values())
        
        if status:
            try:
                status_filter = TicketStatus(status.lower())
                tickets = [t for t in tickets if t.status == status_filter]
            except ValueError:
                pass
        
        if conversation_id:
            tickets = [t for t in tickets if t.conversation_id == conversation_id]
        
        return sorted(tickets, key=lambda t: t.created_at, reverse=True)


# Singleton instance
_service_instance: Optional[TicketService] = None


def get_ticket_service() -> TicketService:
    """Get or create the ticket service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = TicketService()
    return _service_instance
