# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Models Description."""

import asyncio
import contextlib
from typing import cast

import dotenv
from claude_agent_sdk import AssistantMessage
from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk import RateLimitEvent
from claude_agent_sdk import ResultMessage
from claude_agent_sdk import ServerToolResultBlock
from claude_agent_sdk import ServerToolUseBlock
from claude_agent_sdk import StreamEvent
from claude_agent_sdk import SystemMessage
from claude_agent_sdk import TextBlock
from claude_agent_sdk import ThinkingBlock
from claude_agent_sdk import ToolResultBlock
from claude_agent_sdk import ToolUseBlock
from claude_agent_sdk import UserMessage
from langfuse import get_client
from openinference.instrumentation.claude_agent_sdk import ClaudeAgentSDKInstrumentor

dotenv.load_dotenv()
langfuse = get_client()

# Verify connection
if langfuse.auth_check():
    print("Langfuse client is authenticated and ready!")
else:
    print("Authentication failed. Please check your credentials and host.")
    raise SystemExit(1)

ClaudeAgentSDKInstrumentor().instrument()


async def main():
    options = ClaudeAgentOptions(
        permission_mode="bypassPermissions",
        tools={"type": "preset", "preset": "claude_code"},
        system_prompt={"type": "preset", "preset": "claude_code"},
        allowed_tools=[],
        max_turns=None,
        max_budget_usd=None,
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query("What's the weather like in Berlin and New York?")
        async for message in client.receive_response():
            with contextlib.suppress(Exception):
                message = cast(
                    UserMessage
                    | AssistantMessage
                    | SystemMessage
                    | ResultMessage
                    | StreamEvent
                    | RateLimitEvent,
                    message,
                )
                if isinstance(message, SystemMessage):
                    print("System:", message.data)
                elif isinstance(message, ResultMessage):
                    print("Result:", message)
                elif isinstance(message, StreamEvent):
                    print("StreamEvent:", message)
                elif isinstance(message, RateLimitEvent):
                    print("RateLimitEvent:", message)
                elif isinstance(message, UserMessage):
                    print("User:", message.content)
                elif isinstance(message, AssistantMessage):
                    for it in message.content:
                        it = cast(
                            TextBlock
                            | ThinkingBlock
                            | ToolUseBlock
                            | ToolResultBlock
                            | ServerToolUseBlock
                            | ServerToolResultBlock,
                            it,
                        )
                        if isinstance(it, TextBlock):
                            print(it.text)
                        elif isinstance(it, ThinkingBlock):
                            print(it.thinking)
                        elif isinstance(it, ToolUseBlock):
                            print(it.name, it.id)
                            print(it.input)
                        elif isinstance(it, ToolResultBlock):
                            print(it.tool_use_id, it.is_error)
                            print(it.content)
                        elif isinstance(it, ServerToolUseBlock):
                            print(it.name, it.id)
                            print(it.input)
                        elif isinstance(it, ServerToolResultBlock):
                            print(it.tool_use_id)
                            print(it.content)
                        else:
                            print(it)

                else:
                    print(message)


asyncio.run(main())
