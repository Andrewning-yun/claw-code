"""Claude API Client for the bot.

This module provides a client for interacting with the Anthropic Claude API.
Supports streaming responses, error handling, and retry logic.
"""

import os
from dataclasses import dataclass
from typing import AsyncGenerator, Optional

import httpx
from anthropic import AsyncAnthropic
from anthropic.types import Message, MessageParam

from .config import Config


@dataclass
class ClaudeResponse:
    """Represents a response from Claude API."""
    content: str
    model: str
    usage: dict
    stop_reason: Optional[str] = None


class ClaudeClient:
    """Async client for Claude API with streaming support."""

    def __init__(self, config: Config):
        """Initialize the Claude client with configuration.
        
        Args:
            config: Configuration object with API settings.
        """
        self.config = config
        self._client: Optional[AsyncAnthropic] = None

    def _get_client(self) -> AsyncAnthropic:
        """Get or create the Anthropic client."""
        if self._client is None:
            self._client = AsyncAnthropic(
                api_key=self.config.anthropic_api_key,
                base_url=self.config.anthropic_base_url,
                max_retries=3,
                timeout=httpx.Timeout(60.0, connect=10.0),
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def send_message(
        self,
        messages: list[MessageParam],
        system: Optional[str] = None,
        stream: bool = False,
    ) -> Message | AsyncGenerator[str, None]:
        """Send a message to Claude and get response.
        
        Args:
            messages: List of message parameters.
            system: Optional system prompt.
            stream: Whether to stream the response.
            
        Returns:
            Message object or async generator for streaming.
        """
        client = self._get_client()
        
        params = {
            "model": self.config.anthropic_model,
            "max_tokens": self.config.anthropic_max_tokens,
            "temperature": self.config.anthropic_temperature,
            "messages": messages,
        }
        
        if system:
            params["system"] = system
            
        if stream:
            return client.messages.stream(**params)
        else:
            return await client.messages.create(**params)

    async def simple_chat(
        self,
        user_message: str,
        system: Optional[str] = None,
    ) -> ClaudeResponse:
        """Send a simple chat message and get response.
        
        Args:
            user_message: The user's message.
            system: Optional system prompt.
            
        Returns:
            ClaudeResponse with the assistant's reply.
        """
        messages = [{"role": "user", "content": user_message}]
        
        response = await self.send_message(messages, system=system, stream=False)
        
        content = ""
        for block in response.content:
            if hasattr(block, 'text'):
                content += block.text
        
        return ClaudeResponse(
            content=content,
            model=response.model,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            stop_reason=response.stop_reason,
        )

    async def stream_chat(
        self,
        user_message: str,
        system: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a chat response from Claude.
        
        Args:
            user_message: The user's message.
            system: Optional system prompt.
            
        Yields:
            Text deltas from the streaming response.
        """
        messages = [{"role": "user", "content": user_message}]
        
        stream = await self.send_message(messages, system=system, stream=True)
        
        async for event in stream:
            if event.type == "content_block_delta":
                if hasattr(event.delta, 'text'):
                    yield event.delta.text


async def create_claude_client() -> ClaudeClient:
    """Create and configure a Claude client.
    
    Returns:
        Configured ClaudeClient instance.
    """
    config = Config.load_from_env()
    return ClaudeClient(config)