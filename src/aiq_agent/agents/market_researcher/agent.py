# SPDX-FileCopyrightText: Copyright (c) 2025-2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Market researcher agent for competitive analysis and market intelligence."""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt import tools_condition

from aiq_agent.common import load_prompt
from aiq_agent.common import render_prompt_template

from ...common import LLMProvider
from ...common import LLMRole
from .models import MarketResearchAgentState

logger = logging.getLogger(__name__)

AGENT_DIR = Path(__file__).parent


class MarketResearcherAgent:
    """
    Market researcher agent for competitive analysis, market sizing, and industry trends.

    Uses a LangGraph StateGraph with tool-calling capabilities. Structured outputs
    (tables, comparisons, trend summaries) are emphasized via the system prompt.

    The agent is NAT-independent and receives all dependencies via constructor.

    Example:
        >>> from aiq_agent.common import LLMProvider, LLMRole
        >>> provider = LLMProvider()
        >>> provider.set_default(my_llm)
        >>>
        >>> agent = MarketResearcherAgent(
        ...     llm_provider=provider,
        ...     tools=[web_search_tool, knowledge_search_tool],
        ...     max_tool_iterations=8,
        ... )
        >>> state = MarketResearchAgentState(
        ...     messages=[HumanMessage(content="What is Google's ad market share?")]
        ... )
        >>> result = await agent.run(state)
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        tools: Sequence[BaseTool],
        *,
        system_prompt: str | None = None,
        max_llm_turns: int = 10,
        max_tool_iterations: int = 8,
        callbacks: list[Any] | None = None,
    ) -> None:
        self.llm_provider = llm_provider
        self.tools = list(tools)
        self.max_llm_turns = max_llm_turns
        self.max_tool_iterations = max_tool_iterations
        self.callbacks = callbacks or []
        self.system_prompt = system_prompt or self._load_system_prompt()
        self.tools_info = self._build_tools_info()
        self._graph = self._build_graph()

    def _load_system_prompt(self) -> str:
        try:
            return load_prompt(AGENT_DIR / "prompts", "researcher")
        except Exception:
            logger.warning("Market research prompt not found, using inline default")
            return (
                "You are a market research analyst. Answer the user's question using "
                "available tools. Present data in markdown tables. Cite sources.\n\n"
                "{% if tools %}Available tools: "
                "{{ tools | map(attribute='name') | join(', ') }}{% endif %}"
            )

    def _build_tools_info(self) -> list[dict[str, str]]:
        return [
            {"name": getattr(t, "name", str(t)), "description": getattr(t, "description", "")}
            for t in self.tools
        ]

    def _get_llm(self) -> BaseChatModel:
        return self.llm_provider.get(LLMRole.RESEARCHER)

    def _build_graph(self) -> CompiledStateGraph:
        """Build the LangGraph StateGraph."""

        async def agent_node(state: MarketResearchAgentState) -> dict[str, Any]:
            messages = state.messages
            user_info = state.user_info
            iterations = state.tool_iterations
            tools_info = state.tools_info if state.tools_info else self.tools_info
            available_documents = state.available_documents or []

            current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rendered_system_prompt = render_prompt_template(
                self.system_prompt,
                tools=tools_info,
                user_info=user_info,
                current_datetime=current_datetime,
                available_documents=[doc.model_dump() for doc in available_documents],
            )

            if os.environ.get("DEBUG_PROMPTS"):
                logger.debug("Market researcher rendered system prompt:\n%s", rendered_system_prompt)

            system_message = SystemMessage(content=rendered_system_prompt)

            try:
                if iterations >= self.max_tool_iterations:
                    logger.warning("Max iterations (%d) reached. Forcing synthesis.", iterations)
                    synthesis_anchor = HumanMessage(
                        content=(
                            "You have exhausted your research budget. Synthesize the final answer now "
                            "using all gathered data. Present results in clean markdown tables. "
                            "Include a ## Sources section. Do not make further tool calls."
                        )
                    )
                    full_messages = [system_message] + list(messages) + [synthesis_anchor]
                    response = await self._get_llm().ainvoke(full_messages)
                    return {"messages": [response], "tool_iterations": iterations}

                llm_with_tools = self._get_llm().bind_tools(self.tools, parallel_tool_calls=True)
                full_messages = [system_message] + list(messages)
                response = await llm_with_tools.ainvoke(full_messages)

                new_iterations = iterations
                if hasattr(response, "tool_calls") and response.tool_calls:
                    new_iterations += len(response.tool_calls)
                    logger.info("Market researcher: %d tool calls, total iterations: %d",
                                len(response.tool_calls), new_iterations)

                return {"messages": [response], "tool_iterations": new_iterations}

            except Exception as ex:
                logger.error("Failed in market_researcher agent_node: %s", ex)
                raise

        builder = StateGraph(MarketResearchAgentState)
        builder.set_entry_point("agent")
        builder.add_node("agent", agent_node)
        builder.add_node("tools", ToolNode(self.tools))
        builder.add_conditional_edges("agent", tools_condition, {"tools": "tools", "__end__": "__end__"})
        builder.add_edge("tools", "agent")
        return builder.compile()

    async def run(self, state: MarketResearchAgentState) -> MarketResearchAgentState:
        """Execute market research with tool-calling."""
        recursion_limit = (self.max_llm_turns * 2) + 10
        config: dict[str, Any] = {"recursion_limit": recursion_limit}
        if self.callbacks:
            config["callbacks"] = self.callbacks
        result = await self._graph.ainvoke(state, config=config)
        return MarketResearchAgentState.model_validate(result)

    @property
    def graph(self) -> CompiledStateGraph:
        return self._graph
