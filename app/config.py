"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Literal


GeminiReasoningEffort = Literal["none", "low", "medium", "high"]
FormularyPdfExtraction = Literal["library", "gemini"]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # App settings
    app_name: str = "Support Agent"
    app_env: str = "development"
    debug: bool = True
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    
    # LLM Provider settings
    # Options: "groq" (FREE cloud), "huggingface" (FREE cloud), "ollama" (FREE local), "azure_openai" (paid)
    llm_provider: Literal["groq", "huggingface", "ollama", "azure_openai"] = "groq"
    
    # ===========================================
    # GROQ SETTINGS (FREE - Recommended for deployment)
    # ===========================================
    # Get free API key at: https://console.groq.com
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"  # Options: llama-3.1-8b-instant, llama-3.1-70b-versatile, mixtral-8x7b-32768
    
    # ===========================================
    # HUGGINGFACE SETTINGS (FREE tier available)
    # ===========================================
    # Get free API key at: https://huggingface.co/settings/tokens
    huggingface_api_key: str = ""
    huggingface_model: str = "meta-llama/Llama-3.1-8B-Instruct"  # Or: mistralai/Mistral-7B-Instruct-v0.3
    
    # ===========================================
    # OLLAMA SETTINGS (FREE - runs locally)
    # ===========================================
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"  # Options: llama3.1, qwen2.5, mistral
    
    # ===========================================
    # AZURE OPENAI SETTINGS (paid)
    # ===========================================
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2024-08-01-preview"
    
    # Database settings
    database_url: str = "sqlite+aiosqlite:///./support_agent.db"
    
    # Redis settings (optional)
    redis_url: str = "redis://localhost:6379"
    
    # Agent settings
    max_conversation_history: int = 10
    agent_temperature: float = 0.7

    # Formulary PDF extraction: set to "gemini" (+ GOOGLE_API_KEY) for MultimodalParser; "library" uses pdfplumber/PyMuPDF only
    formulary_pdf_extraction: FormularyPdfExtraction = "library"
    google_api_key: str = ""
    gemini_pdf_model: str = "gemini-3.1-flash-lite-preview"
    gemini_pdf_reasoning_effort: GeminiReasoningEffort = "low"
    gemini_pdf_merge_tables: bool = True
    gemini_pdf_create_html: bool = True
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
