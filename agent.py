# -*- coding: utf-8 -*-
# Copyright (C) 2025 Cosmic-Developers-Union (CDU), All rights reserved.

"""Models Description."""

import asyncio
import contextlib
import dataclasses
import datetime
import json
import os
import pathlib
from typing import Any
from typing import cast

import click
import dotenv
import httpx
from claude_agent_sdk import AssistantMessage
from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk import PermissionResult
from claude_agent_sdk import PermissionResultAllow
from claude_agent_sdk import PermissionResultDeny
from claude_agent_sdk import RateLimitEvent
from claude_agent_sdk import ResultMessage
from claude_agent_sdk import ServerToolResultBlock
from claude_agent_sdk import ServerToolUseBlock
from claude_agent_sdk import StreamEvent
from claude_agent_sdk import SystemMessage
from claude_agent_sdk import TextBlock
from claude_agent_sdk import ThinkingBlock
from claude_agent_sdk import ToolPermissionContext
from claude_agent_sdk import ToolResultBlock
from claude_agent_sdk import ToolUseBlock
from claude_agent_sdk import UserMessage
from langfuse import get_client
from loguru import logger
from openinference.instrumentation.claude_agent_sdk import ClaudeAgentSDKInstrumentor
from pydantic import BaseModel

dotenv.load_dotenv()
langfuse = get_client()

# Verify connection
if langfuse.auth_check():
    print("Langfuse client is authenticated and ready!")
else:
    print("Authentication failed. Please check your credentials and host.")
    raise SystemExit(1)

ClaudeAgentSDKInstrumentor().instrument()


def print_message_content(
    it: TextBlock
    | ThinkingBlock
    | ToolUseBlock
    | ToolResultBlock
    | ServerToolUseBlock
    | ServerToolResultBlock,
):
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


def long_string(content: str) -> str:
    contents = content.strip().split("\n")
    contents = [i.strip() for i in contents if i.strip()]
    return "\n".join(contents)


async def can_use_tool(
    tool_name: str, input_data: dict[str, Any], context: ToolPermissionContext
) -> PermissionResult:
    if tool_name == "AskUserQuestion":
        return PermissionResultDeny(
            message=long_string("""
            当前用户无法回答该问题, 如果该问题必须作出选择, 则你终止任务并向用户报告, 如果该问题并不影响最终结果,
            just 影响路线选择, 则你按照 `第一性原理` `长期主义` `奥卡姆剃刀` 原则, 自主选择一个最优的方案.
            记住, 简单胜于复杂, 统一高于例外, 在完成目标的基础上, 以低熵为目标.
            """),
        )
    return PermissionResultAllow()


async def run_task(task: "Task", pm: "PM", pid: str):
    options = ClaudeAgentOptions(
        permission_mode="bypassPermissions",
        tools={"type": "preset", "preset": "claude_code"},
        system_prompt={"type": "preset", "preset": "claude_code"},
        allowed_tools=[],
        max_turns=None,
        max_budget_usd=None,
        can_use_tool=can_use_tool,
        resume=task.session,
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query(task.prompt)
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
                await pm.log(
                    pid,
                    task.id,
                    {"type": message.__class__.__name__, "content": dataclasses.asdict(message)},
                )

                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if hasattr(block, "text"):
                            text = cast(str, block.text)
                            await pm.log(
                                pid,
                                task.id,
                                {"type": "log", "content": f"Thinking: {text.strip()}"},
                            )

                            logger.info("Thinking: " + text.strip())  # Claude's reasoning
                        elif hasattr(block, "name"):
                            logger.info(f"tool: {block.name}, {getattr(block, 'input', {})}")
                            await pm.log(
                                pid,
                                task.id,
                                {
                                    "type": "log",
                                    "content": f"ToolUse: {block.name}, {getattr(block, 'input', {})}",
                                },
                            )
                elif isinstance(message, ResultMessage):
                    await pm.log(
                        pid, task.id, {"type": "log", "content": f"Done: {message.subtype}"}
                    )
                    logger.success(f"Done: {message.subtype}")


HELLO_FILE = pathlib.Path(__file__).parent / "examples/hello.qy"
HELLO_CONTENT = HELLO_FILE.read_text()


async def clean_task():
    # 保持文件一致，避免不必要的变动
    if HELLO_FILE.read_text(errors="ignore") != HELLO_CONTENT:
        HELLO_FILE.write_text(HELLO_CONTENT)
    for file in pathlib.Path(__file__).parent.iterdir():
        if file.is_dir():
            continue
        if file.suffix.lower() == ".md" and file.name not in [
            "bytecode.md",
            "README.md",
            "LANGUAGE.md",
            "CLAUDE.md",
            "AGENTS.md",
            "todo.md",
            "README.zh-Hans.md",
        ]:
            print(file.name)
            logger.info(f"del {file}")
            logger.debug(file.read_text(errors="ignore"))
            file.unlink()


class Task(BaseModel):
    id: int
    prompt: str
    session: str | None
    has_completed: bool
    create_at: datetime.datetime
    update_at: datetime.datetime


class PM:
    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url="http://host.docker.internal:5555", follow_redirects=True
        )

    async def ping(self):
        return (await self.client.get("/api/ping")).json()

    async def ensure_project(self, name: str):
        resp = await self.client.post("/api/projects", json={"name": name})
        return resp.json()

    async def get_tasks(self, project_id: str) -> list[Task]:
        resp = await self.client.get(f"/api/projects/{project_id}/tasks/pending")
        return [Task.model_validate(t) for t in resp.json()]

    async def log(
        self, project_id: str | int, task_id: str | int, content: str | dict, level: str = "info"
    ):
        try:
            if isinstance(content, dict):
                content = json.dumps(content)
            resp = await self.client.post(
                f"/api/projects/{project_id}/tasks/{task_id}/logs",
                json={
                    "content": content,
                    "level": level,
                },
            )
            return resp.json()
        except Exception as e:
            logger.error(e)
            return {"error": e}

    async def complete(self, project_id: str | int, task_id: str | int):
        try:
            resp = await self.client.patch(
                f"/api/projects/{project_id}/tasks/{task_id}/complete",
            )
            return resp.json()
        except Exception as e:
            logger.error(e)
            return {"error": e}


@click.command()
@click.option("--dry-run", is_flag=True, default=False)
async def main(dry_run: bool = False):
    pm_client = PM()
    print(await pm_client.ping())
    while True:
        project = await pm_client.ensure_project("qy")
        pid = project["id"]
        tasks = await pm_client.get_tasks(pid)
        await clean_task()
        for task in tasks:
            logger.info(task)
            if dry_run:
                continue
            try:
                await pm_client.log(pid, task.id, {"type": "log", "content": "read the task"})
                await run_task(task, pm_client, pid)
                logger.info(await pm_client.complete(pid, task.id))
                try:
                    await clean_task()
                    os.system("make lint-fix")
                    os.system('git add . && git commit -m "测试提交" --no-verify')
                except Exception as e:
                    logger.error(e)
            except Exception as e:
                logger.error(e)
        await asyncio.sleep(15)


if __name__ == "__main__":
    logger.add("agent.log")
    asyncio.run(main())
