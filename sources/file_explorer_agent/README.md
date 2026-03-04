# file_explorer_agent

A generalizable ReAct subagent that answers quantitative questions over a corpus
of documents by inspecting files.

Designed to solve the aggregation failure mode in vanilla AIQ: questions like
"how many meetings did X attend?" require search across hundreds of
documents, which top-K semantic search is not suited to do.

## How it works

Given a natural-language question, it runs an internal ReAct loop with
three primitive tools:

1. `list_directory(glob)` — lists files to understand naming convention
2. `read_file_sample(filename)` — reads a sample file to understand document structure
3. `grep_files(pattern, glob_filter)` — scans all matching files with a regex

The LLM observes the file format and constructs its own search patterns.

Existing agents can access this subagent as a tool.

## Adding to an existing AIQ project

### 1. Download your document corpus

Place your documents in a directory, e.g. `sunnyvale_city_meeting_notes/`.

### 2. Install the package

```bash
uv pip install -e sources/file_explorer_agent
```

### 3. Set the environment variable

In `deploy/.env`:

```
MEETING_NOTES_DIR=path/to/your/folder/of/documents
```

### 4. Add the tool to your config

In your existing config YAML, add a `file_explorer` entry under `functions`, then
add it to the `tools` list of whichever agents should have access to it (in this case, it should probably be just the `shallow_research_agent`):

```yaml
functions:
  # ... your existing functions (knowledge_search, etc.) ...

  file_explorer:
    _type: file_explorer_agent
    pdf_dir: ${MEETING_NOTES_DIR:-sunnyvale_city_meeting_notes}
    llm: <your_llm_name>    # reference an LLM already defined in this config
    max_turns: 8
    verbose: true

  shallow_research_agent:
    _type: shallow_research_agent
    llm: <your_llm_name>
    tools:
      - knowledge_search    # your existing tools
      - file_explorer       # add this
```

`qwen3-next-80b-a3b-instruct` worked well in my initial tests. You can add it as an llm in the config by adding this section under `llms`:

```
_type: openai
model_name: qwen/qwen3-next-80b-a3b-instruct
base_url: "https://integrate.api.nvidia.com/v1"
api_key: ${NVIDIA_API_KEY}
temperature: 0.3
top_p: 0.9
max_tokens: 8192
```

See `configs/file_explorer_test.yml` for a minimal working example (no RAG, file
explorer only).

### 5. Run

```bash
nat run --config_file configs/your_config.yml --input "How many meetings did Mayor Larry Klein attend in 2022?"
```

## Example results

See `example_logs/` in the repo root for traced runs on Sunnyvale city meeting
minutes showing the agent solving questions that vanilla RAG was unable to solve.
