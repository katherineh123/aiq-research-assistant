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

"""NAT register function for market researcher agent."""

import logging

from pydantic import Field

from aiq_agent.common import LLMProvider
from aiq_agent.common import VerboseTraceCallback
from aiq_agent.common import filter_tools_by_sources
from aiq_agent.common import is_verbose
from nat.builder.builder import Builder
from nat.builder.framework_enum import LLMFrameworkEnum
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.component_ref import FunctionGroupRef
from nat.data_models.component_ref import FunctionRef
from nat.data_models.component_ref import LLMRef
from nat.data_models.function import FunctionBaseConfig

from .agent import MarketResearcherAgent
from .models import MarketResearchAgentState

logger = logging.getLogger(__name__)


class MarketResearchAgentConfig(FunctionBaseConfig, name="market_research_agent"):
    """Configuration for the market researcher agent."""

    llm: LLMRef = Field(..., description="LLM to use")
    tools: list[FunctionRef | FunctionGroupRef] = Field(default_factory=list, description="Tools to use")
    max_llm_turns: int = Field(default=10, description="Maximum number of LLM turns")
    max_tool_iterations: int = Field(default=8, description="Maximum tool-calling iterations before forcing synthesis")
    verbose: bool = Field(default=False, description="Whether to enable verbose logging")


@register_function(config_type=MarketResearchAgentConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def market_research_agent(config: MarketResearchAgentConfig, builder: Builder):
    """Market researcher agent for competitive analysis, market sizing, and industry trends."""
    llm = await builder.get_llm(config.llm, wrapper_type=LLMFrameworkEnum.LANGCHAIN)
    tools = await builder.get_tools(tool_names=config.tools, wrapper_type=LLMFrameworkEnum.LANGCHAIN)

    provider = LLMProvider()
    provider.set_default(llm)

    verbose = is_verbose(config.verbose)
    callbacks = [VerboseTraceCallback()] if verbose else []

    agent = MarketResearcherAgent(
        llm_provider=provider,
        tools=tools,
        max_llm_turns=config.max_llm_turns,
        max_tool_iterations=config.max_tool_iterations,
        callbacks=callbacks,
    )

    async def _run(state: MarketResearchAgentState) -> MarketResearchAgentState:
        try:
            data_sources = state.data_sources
            selected_tools = filter_tools_by_sources(tools, data_sources)
            active_agent = agent
            if data_sources is not None and selected_tools != tools:
                active_agent = MarketResearcherAgent(
                    llm_provider=provider,
                    tools=selected_tools,
                    max_llm_turns=config.max_llm_turns,
                    max_tool_iterations=config.max_tool_iterations,
                    callbacks=callbacks,
                )
            result = await active_agent.run(state)
            return result
        except Exception:
            logger.exception("Error in market research execution.")
            raise

    yield FunctionInfo.from_fn(_run, description="Market researcher agent for competitive analysis and market intelligence.")
