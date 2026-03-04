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

"""
File Explorer Agent — a generalizable ReAct subagent exposed as a single tool.

Unlike the hardcoded meeting_notes_search tool, this agent:
  1. Inspects the file naming convention at runtime via list_directory
  2. Reads a sample file to understand document format via read_file_sample
  3. Formulates its own grep strategy based on what it observes
  4. Executes the search via grep_files with an LLM-chosen pattern

This means it works on ANY document corpus without format-specific code.
The LLM does the format inference; the tool layer only provides raw primitives.

Exposed as a single tool that accepts a natural-language question:
    explore_files("How many meetings did Klein attend in 2022?")
"""

import logging
import re
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.framework_enum import LLMFrameworkEnum
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.component_ref import LLMRef
from nat.data_models.function import FunctionBaseConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level PDF text cache  {absolute_path_str -> full_text}
# Shared across all agent instances so a warm cache persists across questions.
# ---------------------------------------------------------------------------
_TEXT_CACHE: dict[str, str] = {}


def _get_text(pdf_path: Path) -> str:
    """Extract and cache all text from a PDF. Returns '' on failure."""
    key = str(pdf_path.resolve())
    if key not in _TEXT_CACHE:
        try:
            import pdfplumber

            with pdfplumber.open(pdf_path) as pdf:
                _TEXT_CACHE[key] = "\n".join(page.extract_text() or "" for page in pdf.pages)
        except Exception as exc:
            logger.debug("Could not read %s: %s", pdf_path.name, exc)
            _TEXT_CACHE[key] = ""
    return _TEXT_CACHE[key]


# ---------------------------------------------------------------------------
# System prompt for the internal ReAct loop
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a document analyst with access to a directory of files.
Your job is to answer quantitative questions by examining the files directly.

Choose your strategy based on the question type:

**Counting documents** (e.g. "how many X meetings were held in year Y?"):
  Use list_directory with a specific glob to count matching filenames directly.
  No need to open files — if the naming convention encodes the answer, use it.
  Example: list_directory("2023-*TypeA*.pdf") returns the count immediately.

**Searching content** (e.g. "how many meetings did person X attend?", "which meetings discussed topic Z?"):
  1. Call list_directory("*.pdf") to understand the file naming convention.
  2. Call read_file_sample on a representative file to see the document structure.
     Look for how the relevant information is recorded — field names, section headers, delimiters.
  3. Based on what you observe, formulate a regex pattern that targets the right section.
     Narrow patterns (e.g. matching only a specific section header) are more accurate than broad ones.
  4. Call grep_files with your pattern and an appropriate glob_filter.
  5. Return the exact count and list of matching files.

grep_files supports full Python regex (case-insensitive, DOTALL), so you can scope
your search to specific sections of each document based on what you saw in the sample.

Always inspect at least one sample file before grepping content — the right pattern
depends entirely on how the documents are structured.
"""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class FileExplorerAgentConfig(FunctionBaseConfig, name="file_explorer_agent"):
    """ReAct agent that inspects document format at runtime and formulates its own search strategy.

    Unlike hardcoded grep tools, this agent reads a sample file to understand structure,
    then decides what regex patterns to use. Works on any document corpus.
    """

    pdf_dir: str = Field(description="Path to the directory of document files to search")
    llm: LLMRef = Field(description="LLM to use for the internal reasoning loop")
    max_turns: int = Field(default=8, description="Maximum ReAct loop iterations")
    verbose: bool = Field(default=False, description="Log internal reasoning steps")


# ---------------------------------------------------------------------------
# NAT function
# ---------------------------------------------------------------------------


@register_function(config_type=FileExplorerAgentConfig, framework_wrappers=[LLMFrameworkEnum.LANGCHAIN])
async def file_explorer_agent(config: FileExplorerAgentConfig, builder: Builder):
    """Build and yield the file explorer agent as a callable NAT function."""

    llm = await builder.get_llm(config.llm, wrapper_type=LLMFrameworkEnum.LANGCHAIN)
    pdf_dir = Path(config.pdf_dir)

    # ------------------------------------------------------------------
    # Three raw primitives — closures over pdf_dir.
    # The LLM decides how to use them based on what it observes.
    # ------------------------------------------------------------------

    @tool
    def list_directory(glob_pattern: str = "*.pdf") -> str:
        """List files in the document directory matching a glob pattern.

        Call this first to understand the file naming convention.
        Returns up to 50 filenames so you can infer date/body/id encoding.

        Args:
            glob_pattern: Shell glob, e.g. "*.pdf", "2022-*.pdf", "*Council*.pdf"
        """
        files = sorted(pdf_dir.glob(glob_pattern))
        if not files:
            return f"No files found matching '{glob_pattern}' in {pdf_dir}"
        names = [f.name for f in files]
        shown = names[:50]
        result = f"Found {len(names)} files matching '{glob_pattern}':\n" + "\n".join(shown)
        if len(names) > 50:
            result += f"\n... and {len(names) - 50} more"
        return result

    @tool
    def read_file_sample(filename: str, max_chars: int = 2000) -> str:
        """Read the beginning of a document file to understand its format.

        Use this on 1-2 representative files before grepping so you can see
        what sections exist and how names/dates are formatted.

        Args:
            filename: Just the filename (not full path) — use list_directory first to get one.
            max_chars: How many characters to return (default 2000 is usually
                       enough to see the document structure)
        """
        path = pdf_dir / filename
        if not path.exists():
            return f"File not found: {filename}. Use list_directory first to get valid filenames."
        text = _get_text(path)
        if not text:
            return f"Could not extract text from {filename}."
        return text[:max_chars]

    @tool
    def grep_files(pattern: str, glob_filter: str = "*.pdf") -> str:
        """Search for a regex pattern across all files matching a glob filter.

        Returns the count and list of files where the pattern was found.
        The pattern is case-insensitive Python regex — you can use complex
        expressions to scope the match to a specific section of each document.

        Args:
            pattern: Python regex to search for. Read a sample file first to know
                     what format to target, e.g. a section header followed by a name.
            glob_filter: Which files to search, e.g. "*.pdf", "2023-*.pdf",
                         "*TypeA*.pdf", "2023-*TypeA*.pdf"
        """
        files = sorted(pdf_dir.glob(glob_filter))
        if not files:
            return f"No files found matching '{glob_filter}'"

        try:
            regex = re.compile(pattern, re.IGNORECASE | re.DOTALL)
        except re.error as e:
            return f"Invalid regex pattern '{pattern}': {e}"

        matched: list[str] = []
        for path in files:
            text = _get_text(path)
            if text and regex.search(text):
                matched.append(path.name)

        result = (
            f"Pattern '{pattern}' found in {len(matched)} / {len(files)} files"
            f" matching '{glob_filter}'.\n"
        )
        result += "\n".join(matched[:50])
        if len(matched) > 50:
            result += f"\n... and {len(matched) - 50} more"
        return result

    # ------------------------------------------------------------------
    # Internal ReAct agent
    # ------------------------------------------------------------------
    primitives = [list_directory, read_file_sample, grep_files]
    react_agent = create_react_agent(
        model=llm,
        tools=primitives,
        prompt=_SYSTEM_PROMPT,
    )

    # ------------------------------------------------------------------
    # Outer function — what the main agent sees as a single tool
    # ------------------------------------------------------------------
    async def explore_files(question: str) -> str:
        """Explore document files to answer quantitative questions requiring exhaustive counting.

        This agent inspects the document format at runtime and formulates its own
        search strategy — it is NOT hardcoded to any specific document structure.
        It will examine a sample file, determine the relevant patterns, then scan
        all matching files to return exact counts.

        Use for questions like:
          - "How many times did person X appear in documents from year Y?"
          - "How many documents of type A were created in year B?"
          - "Which documents mention topic Z?"

        Unlike semantic search, this reads every matching file and returns exact counts.

        Args:
            question: The natural-language question to answer.
        """
        if config.verbose:
            logger.info("[file_explorer_agent] question: %s", question)

        result = await react_agent.ainvoke(
            {"messages": [HumanMessage(content=question)]},
            config={"recursion_limit": config.max_turns * 2},
        )
        answer = result["messages"][-1].content
        if config.verbose:
            logger.info("[file_explorer_agent] answer: %s", answer)
        return answer

    yield FunctionInfo.from_fn(explore_files, description=explore_files.__doc__)
