"""Support Agent implementation with multiple LLM provider support.

Supported providers:
- Groq (FREE cloud API - recommended for deployment)
- HuggingFace (FREE cloud API)
- Ollama (FREE local inference)
- Azure OpenAI (paid)
"""

import json
from typing import List, Optional
from loguru import logger

from app.config import get_settings
from app.models.schemas import Message
from app.agent.prompts import get_system_prompt
from app.agent.tools import TOOLS, OLLAMA_TOOLS, execute_tool


class SupportAgent:
    """AI Support Agent with multi-provider LLM support."""
    
    def __init__(self):
        """Initialize the support agent based on configured provider."""
        self.settings = get_settings()
        self.temperature = self.settings.agent_temperature
        self.system_prompt = get_system_prompt()
        self.provider = self.settings.llm_provider
        
        # Initialize the appropriate provider
        init_methods = {
            "groq": self._init_groq,
            "huggingface": self._init_huggingface,
            "ollama": self._init_ollama,
            "azure_openai": self._init_azure_openai,
        }
        
        init_method = init_methods.get(self.provider)
        if init_method:
            init_method()
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")
    
    # ==========================================
    # PROVIDER INITIALIZATION
    # ==========================================
    
    def _init_groq(self):
        """Initialize Groq client (FREE cloud API - great for deployment)."""
        from groq import AsyncGroq
        self.client = AsyncGroq(api_key=self.settings.groq_api_key)
        self.model = self.settings.groq_model
        logger.info(f"Initialized Groq with model: {self.model}")
    
    def _init_huggingface(self):
        """Initialize HuggingFace Inference client (FREE tier available)."""
        from huggingface_hub import AsyncInferenceClient
        self.client = AsyncInferenceClient(
            model=self.settings.huggingface_model,
            token=self.settings.huggingface_api_key,
        )
        self.model = self.settings.huggingface_model
        logger.info(f"Initialized HuggingFace with model: {self.model}")
    
    def _init_ollama(self):
        """Initialize Ollama client (FREE - runs locally)."""
        import ollama
        self.ollama_client = ollama.AsyncClient(host=self.settings.ollama_base_url)
        self.model = self.settings.ollama_model
        logger.info(f"Initialized Ollama with model: {self.model}")
    
    def _init_azure_openai(self):
        """Initialize Azure OpenAI client (paid)."""
        from openai import AsyncAzureOpenAI
        self.client = AsyncAzureOpenAI(
            api_key=self.settings.azure_openai_api_key,
            azure_endpoint=self.settings.azure_openai_endpoint,
            api_version=self.settings.azure_openai_api_version,
        )
        self.model = self.settings.azure_openai_deployment
        logger.info(f"Initialized Azure OpenAI with deployment: {self.model}")
    
    # ==========================================
    # CHAT METHODS
    # ==========================================
        
    async def chat(
        self,
        user_message: str,
        conversation_history: Optional[List[Message]] = None,
        conversation_id: Optional[str] = None,
    ) -> str:
        """
        Process a user message and generate a response.
        Supports function calling for ticket management.
        """
        chat_methods = {
            "groq": self._chat_groq,
            "huggingface": self._chat_huggingface,
            "ollama": self._chat_ollama,
            "azure_openai": self._chat_openai_compatible,
        }
        
        chat_method = chat_methods.get(self.provider)
        return await chat_method(user_message, conversation_history, conversation_id)
    
    def _parse_failed_tool_call(self, failed_generation: str) -> Optional[tuple]:
        """
        Parse a failed tool call from text format.
        Handles multiple formats:
        - <function=tool_name{"arg": "value"}</function>
        - <function=tool_name({"arg": "value"})></function>
        - <function=tool_name>{"arg": "value"}</function>
        Returns: (function_name, arguments_dict) or None
        """
        import re
        
        # Multiple patterns to handle different LLM output formats
        patterns = [
            # Format: <function=name({"key": "value"})></function>
            r'<function=(\w+)\(\s*(\{.+?\})\s*\)>?</function>',
            # Format: <function=name{"key": "value"}></function>
            r'<function=(\w+)(\{.+?\})>?</function>',
            # Format: <function=name>{"key": "value"}</function>
            r'<function=(\w+)>\s*(\{.+?\})\s*</function>',
            # Format: <function=name>{...}</function> (original)
            r'<function=(\w+)\{(.+?)\}</function>',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, failed_generation, re.DOTALL)
            if match:
                func_name = match.group(1)
                args_str = match.group(2)
                
                # Ensure it's wrapped in braces
                if not args_str.startswith('{'):
                    args_str = '{' + args_str + '}'
                
                try:
                    args = json.loads(args_str)
                    logger.info(f"Parsed failed tool call: {func_name} with args: {args}")
                    return (func_name, args)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse tool args: {args_str}, error: {e}")
        
        return None
    
    async def _chat_groq(
        self,
        user_message: str,
        conversation_history: Optional[List[Message]] = None,
        conversation_id: Optional[str] = None,
    ) -> str:
        """Process chat using Groq (FREE cloud API with tool calling)."""
        try:
            messages = self._build_messages(user_message, conversation_history)
            
            # Groq supports OpenAI-compatible tool calling
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=self.temperature,
                max_tokens=1000,
            )
            
            response_message = response.choices[0].message
            
            if response_message.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": response_message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            }
                        }
                        for tc in response_message.tool_calls
                    ]
                })
                
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    logger.info(f"Executing tool: {function_name} with args: {function_args}")
                    
                    tool_result = execute_tool(
                        tool_name=function_name,
                        arguments=function_args,
                        conversation_id=conversation_id,
                    )
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    })
                
                final_response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=1000,
                )
                
                assistant_message = final_response.choices[0].message.content
            else:
                assistant_message = response_message.content
            
            logger.info(f"Generated response for user message: {user_message[:50]}...")
            return assistant_message
            
        except Exception as e:
            error_str = str(e)
            
            # Handle tool_use_failed error by parsing and executing manually
            if "tool_use_failed" in error_str and "failed_generation" in error_str:
                logger.warning("Tool call failed - attempting to parse and execute manually")
                
                # Extract failed_generation from error
                import re
                failed_match = re.search(r"'failed_generation':\s*'([^']+)'", error_str)
                if failed_match:
                    failed_gen = failed_match.group(1)
                    parsed = self._parse_failed_tool_call(failed_gen)
                    
                    if parsed:
                        func_name, func_args = parsed
                        
                        # Execute the tool manually
                        tool_result = execute_tool(
                            tool_name=func_name,
                            arguments=func_args,
                            conversation_id=conversation_id,
                        )
                        
                        # Build response with tool result
                        messages = self._build_messages(user_message, conversation_history)
                        messages.append({
                            "role": "assistant",
                            "content": f"I found the following information:"
                        })
                        messages.append({
                            "role": "user", 
                            "content": f"Here is the data from the system: {tool_result}\n\nPlease summarize this information for the user in a clear, friendly way."
                        })
                        
                        # Get final response
                        try:
                            final_response = await self.client.chat.completions.create(
                                model=self.model,
                                messages=messages,
                                temperature=self.temperature,
                                max_tokens=1000,
                            )
                            return final_response.choices[0].message.content
                        except Exception as retry_error:
                            logger.error(f"Retry also failed: {retry_error}")
                            # Return the raw tool result as fallback
                            return f"Here's what I found: {tool_result}"
            
            logger.error(f"Error generating response with Groq: {error_str}")
            raise
    
    async def _chat_huggingface(
        self,
        user_message: str,
        conversation_history: Optional[List[Message]] = None,
        conversation_id: Optional[str] = None,
    ) -> str:
        """Process chat using HuggingFace Inference API (FREE tier)."""
        try:
            messages = self._build_messages(user_message, conversation_history)
            
            # HuggingFace chat completion with tools
            response = await self.client.chat.completions.create(
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=self.temperature,
                max_tokens=1000,
            )
            
            response_message = response.choices[0].message
            
            if response_message.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": response_message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            }
                        }
                        for tc in response_message.tool_calls
                    ]
                })
                
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    logger.info(f"Executing tool: {function_name} with args: {function_args}")
                    
                    tool_result = execute_tool(
                        tool_name=function_name,
                        arguments=function_args,
                        conversation_id=conversation_id,
                    )
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    })
                
                final_response = await self.client.chat.completions.create(
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=1000,
                )
                
                assistant_message = final_response.choices[0].message.content
            else:
                assistant_message = response_message.content
            
            logger.info(f"Generated response for user message: {user_message[:50]}...")
            return assistant_message
            
        except Exception as e:
            logger.error(f"Error generating response with HuggingFace: {str(e)}")
            raise
    
    async def _chat_ollama(
        self,
        user_message: str,
        conversation_history: Optional[List[Message]] = None,
        conversation_id: Optional[str] = None,
    ) -> str:
        """Process chat using Ollama (FREE local inference)."""
        try:
            messages = self._build_messages(user_message, conversation_history)
            
            response = await self.ollama_client.chat(
                model=self.model,
                messages=messages,
                tools=OLLAMA_TOOLS,
                options={"temperature": self.temperature},
            )
            
            response_message = response["message"]
            
            if response_message.get("tool_calls"):
                messages.append(response_message)
                
                for tool_call in response_message["tool_calls"]:
                    function_name = tool_call["function"]["name"]
                    function_args = tool_call["function"]["arguments"]
                    
                    if isinstance(function_args, str):
                        function_args = json.loads(function_args)
                    
                    logger.info(f"Executing tool: {function_name} with args: {function_args}")
                    
                    tool_result = execute_tool(
                        tool_name=function_name,
                        arguments=function_args,
                        conversation_id=conversation_id,
                    )
                    
                    messages.append({
                        "role": "tool",
                        "content": tool_result,
                    })
                
                final_response = await self.ollama_client.chat(
                    model=self.model,
                    messages=messages,
                    options={"temperature": self.temperature},
                )
                
                assistant_message = final_response["message"]["content"]
            else:
                assistant_message = response_message["content"]
            
            logger.info(f"Generated response for user message: {user_message[:50]}...")
            return assistant_message
            
        except Exception as e:
            logger.error(f"Error generating response with Ollama: {str(e)}")
            raise
    
    async def _chat_openai_compatible(
        self,
        user_message: str,
        conversation_history: Optional[List[Message]] = None,
        conversation_id: Optional[str] = None,
    ) -> str:
        """Process chat using OpenAI-compatible API (Azure OpenAI)."""
        try:
            messages = self._build_messages(user_message, conversation_history)
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=self.temperature,
                max_tokens=1000,
            )
            
            response_message = response.choices[0].message
            
            if response_message.tool_calls:
                messages.append(response_message)
                
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    logger.info(f"Executing tool: {function_name} with args: {function_args}")
                    
                    tool_result = execute_tool(
                        tool_name=function_name,
                        arguments=function_args,
                        conversation_id=conversation_id,
                    )
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    })
                
                final_response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=1000,
                )
                
                assistant_message = final_response.choices[0].message.content
            else:
                assistant_message = response_message.content
            
            logger.info(f"Generated response for user message: {user_message[:50]}...")
            return assistant_message
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            raise
    
    # ==========================================
    # HELPER METHODS
    # ==========================================
    
    def _build_messages(
        self,
        user_message: str,
        conversation_history: Optional[List[Message]] = None,
    ) -> List[dict]:
        """Build the messages list for the API call."""
        messages = [{"role": "system", "content": self.system_prompt}]
        
        if conversation_history:
            max_history = self.settings.max_conversation_history
            recent_history = conversation_history[-max_history:]
            
            for msg in recent_history:
                messages.append({
                    "role": msg.role.value,
                    "content": msg.content
                })
        
        messages.append({"role": "user", "content": user_message})
        return messages
    
    def update_system_prompt(self, new_prompt: str) -> None:
        """Update the system prompt."""
        self.system_prompt = new_prompt
        logger.info("System prompt updated")


# Singleton instance
_agent_instance: Optional[SupportAgent] = None


def get_agent() -> SupportAgent:
    """Get or create the support agent instance."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = SupportAgent()
    return _agent_instance


def reset_agent() -> None:
    """Reset the agent instance (useful when changing settings)."""
    global _agent_instance
    _agent_instance = None
