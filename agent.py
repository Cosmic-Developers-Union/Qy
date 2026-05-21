# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Models Description."""

import asyncio

import dotenv
from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk import ClaudeSDKClient
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
            print(message)


asyncio.run(main())
