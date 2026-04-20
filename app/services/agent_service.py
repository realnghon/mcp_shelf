"""Agent service - orchestrates LangGraph runtime with session persistence."""

import asyncio
import logging
import re
import time
from collections.abc import AsyncGenerator
from typing import Any, cast

from langchain_core.messages import AIMessage, AIMessageChunk

from app.runtime.adapters.models import get_chat_model
from app.runtime.session_runtime import prepare_session_runtime
from app.runtime.nodes.call_model import _lc_message_to_dict, _normalize_model_error, _to_lc_messages
from app.runtime.nodes.execute_tool import execute_tool_node
from app.runtime.state import AgentState
from app.repositories.capability_repo import CapabilityRepo
from app.schemas.runtime import RuntimeEvent
from app.schemas.session import MessageCreate, SessionCreate
from app.services.session_service import SessionService

logger = logging.getLogger(__name__)


class AgentService:
    def __init__(self):
        self.session_service = SessionService()
        self.capability_repo = CapabilityRepo()
        self._running_sessions: dict[str, asyncio.Task] = {}
        self._skill_catalog_cache_text: str | None = None
        self._skill_catalog_cache_ts: float = 0.0

    async def create_session(self, data: SessionCreate, actor_id: str | None = None) -> dict:
        """Create a new session for multi-turn conversation."""
        return await self.session_service.create_session(data, actor_id)

    async def send_message(self, session_id: str, content: str) -> dict:
        """Add a user message to the session and return it."""
        msg = await self.session_service.add_message(
            session_id, MessageCreate(role="user", content=content)
        )
        return msg

    async def run_session(self, session_id: str) -> AsyncGenerator[RuntimeEvent, None]:
        """Run the LangGraph agent and yield SSE events.

        This is the core multi-turn conversation engine:
        1. Load session and binding config
        2. Load conversation history from DB
        3. Build initial state
        4. Execute graph
        5. Save results back to DB
        6. Stream events to client
        """
        session = await self.session_service.get_session(session_id)
        if not session:
            yield RuntimeEvent(event_type="error", data={"message": "Session not found"})
            return

        # Update session status
        await self.session_service.update_session_status(session_id, "running")

        try:
            # Load existing messages for multi-turn context
            db_messages = await self.session_service.list_messages(session_id)
            slash = await self._resolve_slash_command(db_messages)
            if slash and slash.get("mode") == "skills_list":
                skills_text = str(slash.get("content") or "")
                await self.session_service.add_message(
                    session_id,
                    MessageCreate(
                        role="assistant",
                        content=skills_text,
                    ),
                )
                yield RuntimeEvent(event_type="start", data={"session_id": session_id})
                yield RuntimeEvent(event_type="done", data={"content": skills_text})
                await self.session_service.update_session_status(session_id, "idle")
                return

            db_messages_for_run = db_messages
            ad_hoc_capabilities: list[dict[str, Any]] = []
            if slash and slash.get("mode") == "skill_invoke":
                db_messages_for_run = cast(list[dict[str, Any]], slash.get("messages") or db_messages)
                ad_hoc_capabilities = cast(list[dict[str, Any]], slash.get("ad_hoc_capabilities") or [])
            else:
                auto_skill = await self._resolve_auto_skill_for_message(db_messages_for_run)
                if auto_skill:
                    ad_hoc_capabilities = [auto_skill]

            base_messages = [
                {
                    "role": m["role"],
                    "content": m["content"],
                    "tool_event_type": m.get("tool_event_type"),
                    "tool_name": m.get("tool_name"),
                    "tool_call_id": m.get("tool_call_id"),
                    "tool_args": m.get("tool_args"),
                    "tool_result": m.get("tool_result"),
                }
                for m in db_messages_for_run
                if not (
                    m.get("role") == "tool"
                    and (m.get("tool_event_type") or "result") != "result"
                )
            ]
            skill_catalog_prompt = await self._build_skill_catalog_prompt()
            if skill_catalog_prompt:
                base_messages = [{"role": "system", "content": skill_catalog_prompt}] + base_messages

            # Build initial state
            initial_state: AgentState = {
                "thread_id": session["thread_id"],
                "session_id": session_id,
                "binding_id": session.get("binding_id"),
                "model_key": session.get("model_key"),
                "messages": base_messages,
                "selected_capabilities": [],
                "ad_hoc_capabilities": ad_hoc_capabilities,
                "available_tools": [],
                "max_steps": 8,
                "current_step": 0,
                "final_output": None,
                "error": None,
            }

            yield RuntimeEvent(event_type="start", data={"session_id": session_id})
            async for event in self._run_streaming_loop(session_id, initial_state):
                yield event

            await self.session_service.update_session_status(session_id, "idle")

        except Exception as e:
            logger.exception(f"Agent execution failed for session {session_id}")
            message = _normalize_model_error(str(e).strip() or e.__class__.__name__)
            await self.session_service.update_session_status(session_id, "error", message)
            yield RuntimeEvent(event_type="error", data={"message": message})

    async def stop_session(self, session_id: str) -> bool:
        """Stop a running session."""
        task = self._running_sessions.pop(session_id, None)
        if task and not task.done():
            task.cancel()
        await self.session_service.update_session_status(session_id, "idle")
        return True

    async def get_conversation(self, session_id: str) -> list[dict]:
        """Get all messages for a session (for multi-turn display)."""
        return await self.session_service.list_messages(session_id)

    async def _resolve_slash_command(self, db_messages: list[dict[str, Any]]) -> dict[str, Any] | None:
        idx = self._latest_user_message_index(db_messages)
        if idx is None:
            return None

        raw_content = str(db_messages[idx].get("content") or "").strip()
        if not raw_content.startswith("/"):
            return None

        if re.fullmatch(r"/skills?", raw_content, flags=re.IGNORECASE):
            skills, _ = await self.capability_repo.list_all(
                kind="skill",
                status="active",
                page=1,
                page_size=500,
                sort_by="name",
                sort_order="asc",
            )
            if not skills:
                return {"mode": "skills_list", "content": "当前没有可用的 Skill。"}
            groups: dict[str, list[dict[str, Any]]] = {}
            for skill in skills:
                source_id = str(skill.get("source_id") or "")
                pack = "skills"
                if source_id.startswith("skill."):
                    parts = source_id.split(".")
                    if len(parts) >= 3 and parts[1]:
                        pack = parts[1]
                else:
                    slug = str(skill.get("slug") or "")
                    if "-" in slug:
                        pack = slug.split("-", 1)[0]
                groups.setdefault(pack, []).append(skill)

            lines = ["可用 Skills（按分组）："]
            for pack in sorted(groups.keys()):
                lines.append(f"- {pack} ({len(groups[pack])})")
                for skill in groups[pack][:12]:
                    slug = str(skill.get("slug") or "")
                    short_slug = slug.split("-", 1)[1] if slug.startswith(f"{pack}-") else slug
                    lines.append(f"  - {pack}/{short_slug} ({skill['name']})")
            lines.append("\n快速调用：/skill <pack>/<skill> <你的任务>")
            return {"mode": "skills_list", "content": "\n".join(lines)}

        match = re.match(r"^/skill\s+(.+)$", raw_content, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return None

        body = match.group(1).strip()
        if not body:
            return {
                "mode": "skills_list",
                "content": "用法：/skill <slug> <你的任务>\n示例：/skill superpowers-using-superpowers 帮我规划一个开发流程",
            }

        query, objective = self._split_skill_command_body(body)
        resolved = await self._find_skill_by_query(query)
        if not resolved:
            return {
                "mode": "skills_list",
                "content": f"未找到 skill: {query}\n可先输入 /skills 查看全部可用技能。",
            }

        user_content = objective or f"请按技能 {resolved['slug']} 的方法处理这个任务。"
        mutated_messages = list(db_messages)
        mutated = dict(mutated_messages[idx])
        mutated["content"] = user_content
        mutated_messages[idx] = mutated

        ad_hoc = {
            "capability_id": resolved["id"],
            "kind": "skill",
            "slug": resolved["slug"],
            "is_enabled": True,
            "runtime_overrides": {},
        }
        return {
            "mode": "skill_invoke",
            "messages": mutated_messages,
            "ad_hoc_capabilities": [ad_hoc],
        }

    @staticmethod
    def _latest_user_message_index(db_messages: list[dict[str, Any]]) -> int | None:
        for idx in range(len(db_messages) - 1, -1, -1):
            if str(db_messages[idx].get("role") or "") == "user":
                return idx
        return None

    @staticmethod
    def _split_skill_command_body(body: str) -> tuple[str, str]:
        # Preferred split: "/skill <slug> -- <task>"
        if " -- " in body:
            left, right = body.split(" -- ", 1)
            return left.strip(), right.strip()

        parts = body.split(maxsplit=1)
        if not parts:
            return "", ""
        if len(parts) == 1:
            return parts[0].strip(), ""
        return parts[0].strip(), parts[1].strip()

    async def _find_skill_by_query(self, query: str) -> dict[str, Any] | None:
        needle = query.strip().lower()
        if not needle:
            return None
        if needle.endswith("/"):
            needle = needle[:-1].strip()
            if not needle:
                return None
        slash_needle = ""
        if "/" in needle:
            pack, child = needle.split("/", 1)
            pack = pack.strip()
            child = child.strip()
            if pack and child:
                slash_needle = f"{pack}-{child}"
            elif pack:
                slash_needle = pack
        skills, _ = await self.capability_repo.list_all(
            kind="skill",
            status="active",
            page=1,
            page_size=500,
            sort_by="name",
            sort_order="asc",
        )
        if not skills:
            return None

        for skill in skills:
            if str(skill.get("slug") or "").lower() == needle:
                return skill
        if slash_needle:
            for skill in skills:
                if str(skill.get("slug") or "").lower() == slash_needle:
                    return skill
        for skill in skills:
            slug = str(skill.get("slug") or "").lower()
            if slug.endswith(f"-{needle}"):
                return skill
        if slash_needle:
            for skill in skills:
                slug = str(skill.get("slug") or "").lower()
                if slug.endswith(f"-{slash_needle}"):
                    return skill
        for skill in skills:
            if str(skill.get("name") or "").lower() == needle:
                return skill
        for skill in skills:
            slug = str(skill.get("slug") or "").lower()
            name = str(skill.get("name") or "").lower()
            if needle in slug or needle in name:
                return skill
        # Pack-level fallback, e.g. "/skill superpowers <task>"
        if needle:
            pack_prefix = f"{needle}-"
            pack_skills = [
                s for s in skills if str(s.get("slug") or "").lower().startswith(pack_prefix)
            ]
            if pack_skills:
                for s in pack_skills:
                    if str(s.get("slug") or "").lower() == f"{needle}-using-superpowers":
                        return s
                return pack_skills[0]
        return None

    async def _build_skill_catalog_prompt(self, ttl_seconds: float = 60.0) -> str | None:
        now = time.time()
        if self._skill_catalog_cache_text and now - self._skill_catalog_cache_ts < ttl_seconds:
            return self._skill_catalog_cache_text

        skills, _ = await self.capability_repo.list_all(
            kind="skill",
            status="active",
            page=1,
            page_size=500,
            sort_by="name",
            sort_order="asc",
        )
        if not skills:
            self._skill_catalog_cache_text = None
            self._skill_catalog_cache_ts = now
            return None

        lines = [
            "You can use mounted Skills (SOP-style guidance).",
            "When user intent clearly matches a skill, follow that skill workflow automatically.",
            "Available skills:",
        ]
        for skill in skills[:80]:
            slug = str(skill.get("slug") or "")
            name = str(skill.get("name") or slug)
            desc = str(skill.get("description") or "").strip()
            desc_text = f" - {desc}" if desc else ""
            lines.append(f"- {slug}: {name}{desc_text}")
        lines.append("User can explicitly invoke with '/skill <slug> <task>' or '/skills'.")
        text = "\n".join(lines)
        self._skill_catalog_cache_text = text
        self._skill_catalog_cache_ts = now
        return text

    async def _resolve_auto_skill_for_message(self, db_messages: list[dict[str, Any]]) -> dict[str, Any] | None:
        idx = self._latest_user_message_index(db_messages)
        if idx is None:
            return None
        content = str(db_messages[idx].get("content") or "").strip()
        if not content or content.startswith("/"):
            return None
        lower = content.lower()
        if re.search(r"(what|which|list|有哪些|什么).*(skill|skills|技能)", lower):
            return None

        skills, _ = await self.capability_repo.list_all(
            kind="skill",
            status="active",
            page=1,
            page_size=500,
            sort_by="name",
            sort_order="asc",
        )
        if not skills:
            return None

        keyword_map: dict[str, list[str]] = {
            "superpowers-brainstorming": ["brainstorm", "头脑风暴", "想法", "需求梳理", "需求澄清", "设计思路"],
            "superpowers-writing-plans": ["plan", "规划", "方案", "技术方案", "实施计划"],
            "superpowers-executing-plans": ["execute plan", "执行计划", "按计划做", "落地计划"],
            "superpowers-test-driven-development": ["tdd", "测试先行", "测试驱动", "red green"],
            "superpowers-systematic-debugging": ["debug", "排查", "定位问题", "修复bug", "bug"],
            "superpowers-requesting-code-review": ["code review", "审查代码", "代码评审"],
            "superpowers-receiving-code-review": ["review feedback", "评审意见", "处理review"],
            "superpowers-verification-before-completion": ["验证完成", "before completion", "verify fix"],
            "superpowers-using-git-worktrees": ["worktree", "多分支并行", "git worktree"],
        }

        def token_score(text: str, token: str, weight: int) -> int:
            if not token:
                return 0
            return weight if token in text else 0

        best_skill: dict[str, Any] | None = None
        best_score = 0

        for skill in skills:
            slug = str(skill.get("slug") or "").lower()
            name = str(skill.get("name") or "").lower()
            desc = str(skill.get("description") or "").lower()
            short = slug.split("-", 1)[1] if "-" in slug else slug
            score = 0
            score += token_score(lower, slug, 12)
            score += token_score(lower, short, 9)
            score += token_score(lower, name, 7)
            for part in re.split(r"[-_\s/]+", short):
                if len(part) >= 4:
                    score += token_score(lower, part, 2)
            for part in re.split(r"[-_\s/]+", name):
                if len(part) >= 4:
                    score += token_score(lower, part, 1)
            for kw in keyword_map.get(slug, []):
                score += token_score(lower, kw.lower(), 6)
            if desc:
                for part in re.split(r"[-_\s/]+", desc):
                    if len(part) >= 5:
                        score += token_score(lower, part, 1)

            if score > best_score:
                best_score = score
                best_skill = skill

        if not best_skill or best_score < 6:
            return None
        return {
            "capability_id": best_skill["id"],
            "kind": "skill",
            "slug": best_skill.get("slug"),
            "is_enabled": True,
            "runtime_overrides": {},
        }

    async def _run_streaming_loop(
        self,
        session_id: str,
        initial_state: AgentState,
    ) -> AsyncGenerator[RuntimeEvent, None]:
        state = await prepare_session_runtime(initial_state)

        while True:
            if state.get("error"):
                raise RuntimeError(state["error"])
            if int(state["current_step"]) >= int(state["max_steps"]):
                raise RuntimeError("Max steps reached")

            state["current_step"] = int(state["current_step"]) + 1
            model: Any = await get_chat_model(
                binding_id=cast(str | None, state.get("binding_id")),
                model_key_override=cast(str | None, state.get("model_key")),
            )

            tools = cast(list[Any], state.get("available_tools", []))
            if tools:
                model = model.bind_tools(tools)

            lc_messages = _to_lc_messages(cast(list[dict[str, Any]], state.get("messages", [])))
            merged_chunk: AIMessageChunk | None = None
            merged_message: AIMessage | None = None
            streamed_any = False
            response_msg: AIMessageChunk | AIMessage | None = None

            try:
                async for chunk in model.astream(lc_messages):
                    if isinstance(chunk, AIMessageChunk):
                        token = _extract_chunk_text(chunk)
                        if token:
                            streamed_any = True
                            yield RuntimeEvent(
                                event_type="token",
                                data={"content": token, "role": "assistant"},
                            )
                        merged_chunk = chunk if merged_chunk is None else merged_chunk + chunk
                        continue

                    # Some providers return a full AIMessage in astream (no token chunks).
                    if isinstance(chunk, AIMessage):
                        merged_message = chunk
            except ValueError as stream_err:
                # Some OpenAI-compatible endpoints do not return generation chunks
                # even when the SDK enters streaming mode.
                if "No generation chunks were returned" not in str(stream_err):
                    raise
                logger.warning(
                    "Streaming yielded no generation chunks for session %s, falling back to non-streaming ainvoke.",
                    session_id,
                )
                response_msg = await model.ainvoke(lc_messages)

            if response_msg is None:
                response_msg = merged_chunk or merged_message
            if response_msg is None:
                response_msg = await model.ainvoke(lc_messages)

            response_dict = _lc_message_to_dict(response_msg)
            state["messages"] = [*cast(list[dict[str, Any]], state.get("messages", [])), response_dict]
            tool_calls = response_dict.get("tool_calls") or []
            assistant_content = _stringify_content(response_dict.get("content"))
            if assistant_content or not tool_calls:
                await self.session_service.add_message(
                    session_id,
                    MessageCreate(
                        role="assistant",
                        content=assistant_content,
                    ),
                )

            if tool_calls:
                for tc in tool_calls:
                    tc_name = tc.get("name", "")
                    tc_args = tc.get("args", {})
                    tc_id = tc.get("id", "")
                    yield RuntimeEvent(
                        event_type="tool_call",
                        data={
                            "tool_name": tc_name,
                            "tool_args": tc_args,
                            "tool_call_id": tc_id,
                        },
                    )
                    await self.session_service.add_message(
                        session_id,
                        MessageCreate(
                            role="tool",
                            content=None,
                            tool_event_type="call",
                            tool_name=tc_name,
                            tool_call_id=tc_id,
                            tool_args=tc_args,
                            tool_result=None,
                        ),
                    )

                before_count = len(cast(list[dict[str, Any]], state["messages"]))
                tool_output = await execute_tool_node(state)
                state.update(tool_output)
                new_tool_msgs = cast(list[dict[str, Any]], state["messages"])[before_count:]

                for msg in new_tool_msgs:
                    yield RuntimeEvent(
                        event_type="tool_result",
                        data={
                            "tool_name": msg.get("tool_name", ""),
                            "tool_result": msg.get("tool_result", msg.get("content", "")),
                        },
                    )
                    await self.session_service.add_message(
                        session_id,
                        MessageCreate(
                            role="tool",
                            content=msg.get("content"),
                            tool_event_type=msg.get("tool_event_type") or "result",
                            tool_name=msg.get("tool_name"),
                            tool_call_id=msg.get("tool_call_id"),
                            tool_args=msg.get("tool_args"),
                            tool_result=msg.get("tool_result", msg.get("content")),
                        ),
                    )

                if state.get("error"):
                    raise RuntimeError(state["error"])
                continue

            content = assistant_content
            if not streamed_any and content:
                async for part in _chunk_text_stream(content):
                    yield RuntimeEvent(
                        event_type="token",
                        data={"content": part, "role": "assistant"},
                    )
            yield RuntimeEvent(event_type="done", data={"content": content})
            return


def _extract_chunk_text(chunk: AIMessageChunk) -> str:
    content = chunk.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    # Fallback for provider-specific chunk payloads (OpenAI-compatible gateways).
    kw = getattr(chunk, "additional_kwargs", None)
    if isinstance(kw, dict):
        delta = kw.get("delta")
        if isinstance(delta, dict):
            text = delta.get("content")
            if isinstance(text, str):
                return text
        choices = kw.get("choices")
        if isinstance(choices, list):
            parts: list[str] = []
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                d = choice.get("delta")
                if isinstance(d, dict):
                    text = d.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            if parts:
                return "".join(parts)
    return ""


def _stringify_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return "" if content is None else str(content)


async def _chunk_text_stream(content: str, chunk_size: int = 16) -> AsyncGenerator[str, None]:
    for i in range(0, len(content), chunk_size):
        yield content[i:i + chunk_size]
        await asyncio.sleep(0.01)
