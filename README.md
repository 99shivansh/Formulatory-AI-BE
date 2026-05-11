# Support Agent - FastAPI AI Agent

A FastAPI-based AI customer support agent powered by OpenAI.

## Features

- **AI-Powered Responses**: Uses OpenAI GPT models for intelligent responses
- **Conversation Management**: Maintains conversation history for context
- **RESTful API**: Clean API endpoints for integration
- **Customizable Prompts**: Easy to modify system prompts
- **Production Ready**: Structured for scalability

## Project Structure

```
aiagent/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration settings
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── support_agent.py # AI agent implementation
│   │   └── prompts.py       # System prompts
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py        # API endpoints
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py       # Pydantic models
│   └── services/
│       ├── __init__.py
│       └── conversation_service.py
├── requirements.txt
├── .env.example
├── run.py
└── README.md
```

## Setup

### 1. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

```bash
cp .env.example .env
# Edit .env and add your OpenAI API key
```

### 4. Run the Application

```bash
python run.py
```

Or using uvicorn directly:

```bash
uvicorn app.main:app --reload
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Root endpoint |
| GET | `/docs` | Swagger documentation |
| GET | `/api/v1/health` | Health check |
| POST | `/api/v1/chat` | Chat with agent |
| POST | `/api/v1/conversation/new` | Create new conversation |
| DELETE | `/api/v1/conversation/{id}` | Delete conversation |
| POST | `/api/v1/conversation/{id}/clear` | Clear conversation |

## Usage Example

### Chat with the Agent

```bash
curl -X POST "http://localhost:8000/api/v1/chat" \
     -H "Content-Type: application/json" \
     -d '{"message": "How can I reset my password?"}'
```

### Response

```json
{
  "response": "I'd be happy to help you reset your password...",
  "conversation_id": "conv_abc123def456",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

## Customizing the System Prompt

Edit `app/agent/prompts.py` to customize the agent's behavior:

```python
SYSTEM_PROMPT = """Your custom prompt here..."""
```

## License

MIT
