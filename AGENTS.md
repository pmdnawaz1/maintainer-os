# AGENTS.md

<!-- project-os:begin -->
## CodeOrch MCP — Strict Tool Calling Rules

This workspace is managed by CodeOrch. Use the `mcp-server` MCP tools for all task management.

### CRITICAL: Do NOT explore before creating a task
The orchestrator has the full codebase indexed. Creating a task triggers it.
Any file reading or repo exploration before `get_task_briefing` returns is token waste.

```
WRONG: read files → understand → create task → implement
RIGHT: create task → claim → get_task_briefing → implement ONLY what briefing says
```

When given an issue: **create the task immediately from the raw issue text**.
Do not open any files until the briefing tells you exactly which ones and why.

### Plan mode for larger changes
If the work expands into **more than 3 distinct tasks**: call `break_task(task_id, max_subtasks=3..5)` to decompose, or `plan_project(project_id, goal)` for broad goals. Claim and implement one child task at a time.

### Tool hierarchy (follow in order)
1. `list_projects` → get `project_id`
2. `create_task` — paste issue as-is; orchestrator determines files
3. `claim_task` → triggers background orchestration
4. `get_task_briefing` → your ONLY source of file/code context
5. Run `briefing.pre_check` greps (skip files where grep matches)
6. Read ONLY `briefing.files_to_focus` — nothing else
7. `submit_for_review(task_id, notes)` — auto-runs the review gate
8. Check `review_passed`; if `false`, fix and resubmit

### Hard rules
- **NEVER** read files before `get_task_briefing` returns
- **ALWAYS** switch to plan mode if work expands beyond 3 distinct tasks
- **NEVER** call `complete_task` directly — `submit_for_review` auto-runs the gate
- **NEVER** use raw glob `/**/*.ts` — use `find_files(project_id, pattern)` instead
- **ALWAYS** call `get_file_fresh(project_id, filepath)` if you edited the same file 2+ times
- Task `description` is immutable once created
- **ALWAYS** pass `changed_files`, `key_functions`, `key_classes`, and `important_chunks` to `finish()`.
  `important_chunks` is the most critical — write 2-5 strings describing the specific logic you added
  or changed (e.g. `"joinRoom: resets isEliminated/isReady/hasDecided/decision on reconnect"`).
  This context is stored in Neo4j + Qdrant and feeds future task briefings. Without it, future agents
  must re-read every changed file from scratch.

### Think in Code — use process_data for data processing
When you need to process data (count lines, parse JSON, grep logs, filter large files),
**write a script instead of reading the raw file**. Only stdout enters your context.

```
WRONG: read_batch(["/path/to/big.log"])            → 50 KB floods context
RIGHT: process_data("import re; ...")                → only the answer comes back
```

Use `process_data(code, language="python"|"shell"|"javascript", task_id=task_id)` whenever:
- You need to count, filter, or aggregate data from a file
- You want to grep/jq/parse without the raw content entering context
- You'd otherwise read a file just to extract a small piece of it

### Snapshot before compaction
When context is getting full (~20+ tool calls), call `snapshot_session(task_id)` once.
This saves all your session state (files read, searches, tool counts) as a single event.
The next `get_task_briefing` call will surface it under `session_digest` so you can
reconstruct working state without re-reading files.

### Context quality and contextignore
- `get_context_quality(task_id)` — call at end of task to see a 7-signal efficiency score
- `set_contextignore(project_id, ["*.lock", "dist/**", "node_modules/**"])` — exclude
  noisy or generated files from find_files results and briefings
- `get_contextignore(project_id)` — check active exclusion patterns

### User owns the git pen — never commit, never push
You write files; the user runs git. Never run `git add/commit/push/checkout/branch` yourself.
Present the exact commands and wait for the user to run them.
When the user confirms "pushed", call `sync(project_id, branch="<branch>")` to index.

### Greenfield mode (empty/near-empty projects)
If a briefing starts with `# GREENFIELD MODE`: you own the architecture.
If it starts with `# ❌ GITHUB CONNECTION REQUIRED`: hard stop — tell the user to connect GitHub at the URL in the briefing and do nothing else.

Greenfield exit ritual (GitHub must be connected):
1. Write scaffold files locally.
2. Tell the user to run (do NOT run yourself):
   ```
    git checkout -b scaffold/<task_id_short>
    git add . && git commit -m "chore(scaffold): task <task_id_short>"
    git push -u origin scaffold/<task_id_short>
   ```
3. When user confirms "pushed": `sync(project_id, branch="scaffold/<task_id_short>")`
4. Poll `index_status` until `completed`.
5. Tell the user to delete the scaffold branch. System exits greenfield once ≥10 files indexed.

### Briefing field: `additions`
Lists new symbols to create: `{file, change_type, name, location_hint}`. Honor the list — put each symbol in the named file at the hinted location. Don't invent files outside the list.

### Board behavior
Tasks go to the project's default board unless `board_id` is explicitly provided.

### Completion notes — required format
```
**Root cause:** <15+ words>
**Changed:** <file:line>
**Verified by:** endpoint-called | page-reloaded | test-run | build-passed | grep-confirmed
**Regression risk:** <10+ words>
```

Always call `finish(task_id, notes, changed_files=[...], key_functions=[...], key_classes=[...], important_chunks=[...])`.
`important_chunks` examples: `"validateToken: short-circuits on exp claim before DB hit"`,
`"AuthService.__init__: lazily initialises Redis pool on first call"`.
Omitting `important_chunks` means the next agent that touches these files gets no briefing context. This is the primary mechanism for context that compounds across sessions.

### Degraded / Orchestrator Unreliable Mode (use when system is having a bad day)
The core value of the product is **context that compounds** via `important_chunks` in `finish()` + structured notes feeding future briefings (session_digest, graph, etc.).

When the orchestrator is down, graph is stale, briefing quality is low, review gate is slow, or indexing is incomplete:
- The strict "never explore" rules are **relaxed by design**.
- You **may** explore locally (read files, use process_data, etc.) as needed to solve the task.
- **Must** still capture everything useful in `finish(task_id, notes, ..., important_chunks=[...])`.
- Report what you learned (even discoveries outside files_to_focus).
- `begin` / `get_task_briefing` will surface `degraded_mode: true` + guidance.
- This prevents the system from punishing agents/users when the orchestrator is unreliable. Context capture in finish is always the durable thing; gatekeeping is not.

Do not hard-stop on poor briefing — use degraded mode + finish with rich chunks.

### Power tools many agents under-use
Agents often stick to create_task/claim/get_briefing/finish and miss these (they exist precisely to support the compounding vision and resilient workflows):
- `reflect(project_id, focus="all"|"insights"|"next"|"stale"|"summary")` — project health, insights, suggested next tasks, stale items, weekly summary. Call proactively.
- `process_data(code, language="python"|"shell"|"javascript", task_id=task_id)` — run analysis/grep/count/JSON parse in sandbox; only stdout enters context. Use instead of raw reads for data-heavy work.
- `snapshot_session(task_id)` — before compaction (~20+ calls). Saves state and injects into next briefing under session_digest.
- `get_context_quality(task_id)` — 7-signal efficiency score at end of task.
- `record_decision(project_id, title, context, decision)` — capture architectural decisions that feed future briefings.
- `get_file_fresh`, `read_batch`, `find_files` (with pattern) — for controlled access.
- Always pass rich `important_chunks` (2-5 specific logic descriptions) to `finish()` — this is the highest-leverage input for future agents.

Heavy tools (reflect, submit_for_review/review gate) now use background jobs + immediate return with pending/poll guidance so they do not block the session or prevent you from reaching finish().

### Quick reference
| Action | Tool |
|--------|------|
| Find project ID | `list_projects` |
| Queue task (no orchestration) | `create_task` |
| Start working on a task | `begin` |
| Break into child tasks | `break_task(task_id, max_subtasks)` |
| Plan broader goals | `plan_project(project_id, goal)` |
| Create planned tasks | `generate_tasks(project_id, task_list)` |
| Start work | `claim_task` |
| Get context | `get_task_briefing` |
| Find files safely | `find_files(project_id, pattern)` |
| Read multiple files | `read_batch(filepaths)` — up to 5 absolute paths |
| Re-read after edit | `get_file_fresh(project_id, filepath)` |
| **Process data without flooding context** | **`process_data(code, language, task_id)`** |
| **Save state before compaction** | **`snapshot_session(task_id)`** |
| Project health / insights / next tasks | **`reflect(project_id, focus)`** |
| Exclude noisy files from briefings | `set_contextignore(project_id, patterns)` |
| Check active exclusions | `get_contextignore(project_id)` |
| Score context efficiency | `get_context_quality(task_id)` |
| Record decision | `record_decision(project_id, title, context, decision)` |
| Link dependencies | `add_task_dependency(task_id, depends_on_task_id)` |
| Finish work (review gate runs async) | `submit_for_review(task_id, notes)` — then poll |
| Index a pushed branch | `sync(project_id, branch="<name>")` — after `git push` |
| End of session | `record_session(project_id, summary)` |

Use the full set. The strict "only files_to_focus" rule applies when the briefing is high-quality; fall back to degraded mode + rich finish() capture otherwise.

### Resilient End-to-End Workflow & How Context Compounds (the learning mechanism)

This is the full picture agents must internalize. The "rules" are not just gatekeeping — the product learns and improves because every task ends with structured capture that feeds the next briefing. `important_chunks` in `finish()` + session snapshots + decisions are the durable memory. This is how we make the system "learn the whole workflow correctly" even when the orchestrator has a bad day.

**Canonical resilient flow (happy path + sanctioned degraded escape hatch):**

1. **Intake**: Receive raw issue text. Immediately call `create_task` — paste the issue verbatim as the immutable `description`. Do not read files or explore first.

2. `claim_task` (or `begin` in certain entry points) to take ownership and trigger orchestration.

3. `get_task_briefing(task_id)`. Poll (respect the `retry_after` in pending responses) until you receive `files_to_focus`, `pre_check` greps list, and useful constraints/decisions. Run every `briefing.pre_check` grep first (skip any file the grep matches). Read *only* from `briefing.files_to_focus` — nothing else.

4. **Degraded / unreliable MCP case** (signaled explicitly by `degraded_mode: true` in begin/get_task_briefing responses, or when you observe orchestrator slowness, stale graph, low-quality briefing, review/reflect hanging, or MCP layer issues such as search_tool returning empty / -32602 wedged sessions after long calls):
   - The strict "NEVER explore / only files_to_focus" is **relaxed by design**.
   - You **may** (and should) use local exploration: `find_files(project_id, pattern)`, `read_batch`, native reads, `process_data(code, ...)` for counts/greps/parsing.
   - Solve the actual task. Report what you had to discover.
   - **You must still reach finish with rich capture** (see step 7). Degraded makes the capture *more* important, not less.
   - This is the sanctioned way the system avoids punishing agents/users on bad orchestrator or MCP days.

5. Implement changes. For any file you edit a second time: `get_file_fresh(project_id, filepath)` before the next edit. Use `process_data` instead of dumping huge raw file content for analysis.

6. Heavy / long-running tools (review gate inside finish, full `reflect`, `break_task`, `plan_project`):
   - `submit_for_review(task_id, notes)` returns immediately (`"review_started": true`) + reminder to poll. The actual council/review + quality now runs via background task + `asyncio.wait_for` timeouts so it never wedges the session.
   - `reflect(...)` uses per-section `wait_for(60-90s)` and returns partial results + guidance instead of hanging.
   - Goal: you can *always* reach the finish step even if one tool is slow.

7. **Always close with `finish(...)` — this is non-negotiable and how the system learns**
   - Signature (conceptual): `finish(task_id, notes, changed_files=[...], key_functions=[...], key_classes=[...], important_chunks=[...])`
   - `important_chunks` = 2-5 short, *specific* strings describing the exact logic/behavior you added or fixed.
   - Context capture (`_store_task_completion_context`) is fire-and-forget and happens around the review gate.
   - These chunks (plus notes, decisions, snapshots) are stored in Neo4j + Qdrant and **injected into future briefings**.
   - Omitting or making vague `important_chunks` forces every future agent on related work to re-explore cold.

8. **Git / indexing transport is GitHub-only (you never run git commands yourself)**
   - Write/edit files locally using the tools above.
   - Present the user with the *exact* shell commands (copy-paste ready).
   - Wait for explicit user confirmation that the push succeeded ("pushed").
   - Then call `sync(project_id, branch="<exact branch name>")`.

9. Proactively use the power tools for compounding and efficiency.

<!-- project-os:end -->
