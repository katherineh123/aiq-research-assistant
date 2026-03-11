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

"""Python REPL tool for data analysis and computation."""

import asyncio
import io
import logging
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import Field

from nat.builder.builder import Builder
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

logger = logging.getLogger(__name__)

# Single shared executor — avoids spawning a new thread pool per tool call
_executor = ThreadPoolExecutor(max_workers=4)


class PythonReplConfig(FunctionBaseConfig, name="python_repl"):
    """
    Tool that executes Python code and returns stdout output.

    Pre-injects pandas (pd), numpy (np), Path, and a DATA_DIR variable
    pointing to the equity-research data directory so the agent can load
    CSVs and run calculations without boilerplate.

    Example agent usage:
        df = pd.read_csv(f"{DATA_DIR}/online_advertising_mock_data.csv", comment='#')
        print(df.groupby('company')['ad_market_share_pct'].last())
    """

    data_dir: str = Field(
        default="./equity-research/data",
        description="Path to the data directory, injected as DATA_DIR in the execution environment.",
    )
    output_dir: str = Field(
        default="./equity-research/outputs/claude",
        description="Path to the output directory, injected as OUTPUT_DIR in the execution environment.",
    )
    timeout: float = Field(
        default=30.0,
        description="Maximum execution time in seconds before the code is aborted.",
    )
    max_output_chars: int = Field(
        default=8000,
        description="Truncate output to this many characters to avoid flooding the context window.",
    )


@register_function(config_type=PythonReplConfig)
async def python_repl(tool_config: PythonReplConfig, builder: Builder):
    data_dir = str(Path(tool_config.data_dir).resolve())
    output_dir = str(Path(tool_config.output_dir).resolve())
    timeout = tool_config.timeout
    max_output_chars = tool_config.max_output_chars

    # Ensure output dir exists at startup
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    async def _run_python(code: str) -> str:
        """Execute Python code and return the output.

        Runs arbitrary Python code in an isolated namespace with pandas (pd),
        numpy (np), Path, DATA_DIR, and OUTPUT_DIR pre-injected. Returns
        all printed output (stdout). Exceptions are caught and returned as
        error text so the agent can self-correct.

        Use DATA_DIR to load CSV data files, OUTPUT_DIR to write results.

        Args:
            code (str): Python code to execute. Use print() to produce output.

        Returns:
            str: All stdout output from the code, or a traceback on error.
        """

        def _execute() -> str:
            stdout_capture = io.StringIO()
            old_stdout = sys.stdout
            sys.stdout = stdout_capture

            # Build execution namespace with pre-injected helpers
            exec_globals: dict = {
                "__builtins__": __builtins__,
                "DATA_DIR": data_dir,
                "OUTPUT_DIR": output_dir,
                "Path": Path,
            }

            # Pre-import common data analysis libraries
            try:
                import numpy as np
                import pandas as pd
                exec_globals["pd"] = pd
                exec_globals["np"] = np
            except ImportError as e:
                logger.warning("Could not pre-import data libraries: %s", e)

            try:
                exec(code, exec_globals)  # noqa: S102
                output = stdout_capture.getvalue()
                return output if output.strip() else "(code executed successfully, no output)"
            except Exception:
                return f"Error:\n{traceback.format_exc()}"
            finally:
                sys.stdout = old_stdout

        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(_executor, _execute),
                timeout=timeout,
            )
        except TimeoutError:
            result = f"Error: code execution timed out after {timeout}s"

        # Truncate to avoid flooding context window
        if len(result) > max_output_chars:
            result = result[:max_output_chars] + f"\n... (truncated at {max_output_chars} chars)"

        return result

    yield FunctionInfo.from_fn(_run_python, description=_run_python.__doc__)
