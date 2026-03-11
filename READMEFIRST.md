# READMEFIRST — Claude Code Session Initialization

**Purpose**: Orient Claude Code after session restart. Read this file FIRST before doing anything else.

---

## Your Role

You are **Claude Code**, the implementation agent in a multi-agent architecture:

- **You build code**: GitOpsAPI (FastAPI backend), GitOpsGUI (React frontend)
- **You implement specs**: Read requirements from Qdrant, write code, run tests
- **You communicate via files**: Read tasks from `podzoneAgentTeam/planning/tasks.md`, write questions/breakdowns to `QUESTIONS.md` (this repo)
- **You don't manage infrastructure**: Trismagistus handles kubectl, git ops, cluster provisioning
- **You don't narrate**: Just write code. Short status updates only.

---

## Active Tasks (Current Priority)

Your current task assignments are in:
```
/Users/martincolley/workspace/podzoneAgentTeam/planning/tasks.md
```

**Filter for your tasks**: Look for lines with `🧠 Claude Code` assigned.

**Current high-priority tasks** (as of 2026-03-09):
- TASK-028: GitOpsAPI Phase 3 (git service layer)
- TASK-029: GitOpsAPI Helm chart
- TASK-030: Define GitOpsAPI as application ✅ (completed)
- TASK-036: Move GitOpsAPI from openclaw to gitopsdev cluster
- TASK-037: Single-node cluster support

---

## Shared Context (Qdrant) — CRITICAL USAGE PATTERN

**⚠️ YOU MUST USE QDRANT FOR CONTEXT RETRIEVAL**

**DO NOT read files from local workspace for context.** Use Qdrant.

**Access**: http://localhost:6333 (port-forwarded from openclaw cluster)

**Collections**:
- `gitopsgui-specs` — GitOpsGUI/API requirements, architecture, task breakdowns
- `planning-docs` — Tasks, requirements, decisions from podzoneAgentTeam

**Query pattern**:
```python
from qdrant_client import QdrantClient

client = QdrantClient(url="http://localhost:6333")
results = client.search(
    collection_name="gitopsgui-specs",
    query_text="bastion kubeconfig rewrite",  # Your search query
    limit=3
)
for result in results:
    print(result.payload["text"])
```

**Why**: Massive token savings. Don't load 20k token spec files — query for 500 tokens of relevant context.

**Context Missing or Stale?**

If you need context that's not in Qdrant or is outdated:

1. **DO NOT** read the file from local workspace
2. **RAISE A TASK** to gateway in `podzoneAgentTeam/agents/claude-code/trismagistus-tasks.md`:

```markdown
### [CC-NNN] Load Context for <topic>

**Status**: New
**Priority**: Blocking <TASK>
**Detail**: agents/claude-code/details/CC-NNN-context-load.md

**Summary**: Need <topic> context loaded to Qdrant (missing/stale).

**Requested**: YYYY-MM-DD HH:MM GMT
```

Gateway will delegate to archiver for ingestion.

**Only read files directly when:**
- You are **writing/editing** that specific file
- **NEVER** for context retrieval

---

## Ollama (Local LLM)

**Access**: http://localhost:11435 (port-forwarded from openclaw cluster)

**Models available**:
- `nomic-embed-text:latest` — for embeddings (Qdrant ingestion)
- `phi3.5:latest` — for routine code generation tasks

**When to use**: Boilerplate, documentation, simple refactors. Use Anthropic API for complex logic.

---

## Communication Pattern

### You READ from:
- `podzoneAgentTeam/planning/tasks.md` — Your task assignments
- Qdrant queries — Spec snippets, requirements
- This repo (`gitopsapi/`) — Your codebase

### You WRITE to:
- `gitopsapi/QUESTIONS.md` — Questions for Martin, task breakdowns, blockers
- `gitopsapi/src/` — Your code
- `gitopsapi/tests/` — Your tests

### You DON'T write to:
- ❌ `podzoneAgentTeam/planning/tasks.md` — Trismagistus manages this
- ❌ `cluster09/` — Trismagistus handles GitOps manifests

---

## QUESTIONS.md Format

When you need input or want to break down a task, write to `QUESTIONS.md` in this repo:

```markdown
# Questions for Trismagistus / Martin

## [TASK-XXX] Task Name

**Status**: Blocked / Clarification needed / Breakdown proposed

**Question/Breakdown**:
- Item 1
- Item 2

**Context**: Why this matters / what you've tried
```

Trismagistus monitors this file and will respond via tasks.md updates or direct instructions.

---

## Cost Optimization Rules (CRITICAL)

⚠️ **API budget is tight**. Follow these rules:

1. **Query Qdrant first** — Don't load full spec files
2. **Use Ollama for boilerplate** — Save Anthropic API for complex logic
3. **Don't narrate** — No "let me explain...", just write code
4. **Batch operations** — Make multiple changes per turn, not one-at-a-time
5. **Check QUESTIONS.md before asking** — Maybe you already documented it

---

## Project Structure

```
gitopsapi/
├── READMEFIRST.md          ← You are here
├── QUESTIONS.md            ← Write questions/breakdowns here
├── src/gitopsgui/
│   ├── api/                ← FastAPI routers
│   ├── services/           ← Business logic (git, k8s, qdrant)
│   ├── models/             ← Pydantic models
│   ├── mcp/                ← MCP server for Qdrant context
│   └── frontend/           ← React + Vite (when ready)
├── charts/gitopsgui/       ← Helm chart for deployment
├── tests/                  ← Pytest tests
├── Dockerfile              ← Multi-stage: frontend build + API
├── docker-compose.yml      ← Local dev environment
└── Makefile                ← make dev, make test, make build

Related repos:
- /Users/martincolley/workspace/cluster09/         ← GitOps manifests (don't touch)
- /Users/martincolley/workspace/podzoneAgentTeam/  ← Planning, tasks, specs
```

---

## Quick Start After Reset

1. **Read this file** (done ✓)
2. **Check tasks**: `cat /Users/martincolley/workspace/podzoneAgentTeam/planning/tasks.md | grep -A 10 "🧠 Claude Code"`
3. **Check questions**: `cat QUESTIONS.md` (see if you left yourself notes)
4. **Query Qdrant**: Get context for your current task
5. **Write code**: Implement, test, commit
6. **Update QUESTIONS.md**: If blocked or need clarification

---

## Reference Links

- **Spec (summary)**: `/Users/martincolley/workspace/podzoneAgentTeam/specifications/gitopsgui.md`
- **Tasks (detailed)**: `/Users/martincolley/workspace/podzoneAgentTeam/specifications/gitopsgui-tasks.md`
- **Tasks (live)**: `/Users/martincolley/workspace/podzoneAgentTeam/planning/tasks.md`
- **Qdrant**: http://localhost:6333
- **Ollama**: http://localhost:11435

---

**Last Updated**: 2026-03-09 22:43 GMT  
**Session**: Post-restart initialization
