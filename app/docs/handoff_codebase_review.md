# Handoff — Codebase Review

Paste this into a new Claude Code session (suggested title: **"LLM-Auto-Generate codebase review"**).
`CLAUDE.md` auto-loads and gives the full architecture; this file says **what's done, what's
pending, and what to scrutinize** so the review starts productive.

---

## 1. What this project is

Internship POC @ SCG: turn a natural-language question into a formatted business report.
Pipeline (LangGraph):

```
user prompt → schema gate → Text2SQL → run SQL (Postgres, read-only) → verify correctness
→ human-in-the-loop (approve + template + notes) → generate report content
→ Jinja render HTML → PDF → personalize (content / style / both) → END
```

Full design: `docs/graph_draft.md`. Scope, stack, conventions, guardrails: `CLAUDE.md`.
**Deadline: 22 Jul 2026.**

## 2. Current status (what works)

| Area | Status |
|---|---|
| LangGraph graph wired (9 nodes) | ✅ `graph.py`, runs via `cd app && uv run -m graph` (CLI) |
| Text2SQL + schema injection + few-shot rules | ✅ passes 15 ground-truth eval cases |
| SQL self-retry loop (2 retries) | ✅ `executeSQL.py` |
| verify_correctness (LLM verdict + detail) | ✅ informational, non-blocking |
| human_in_the_loop (curator: approve/re-query) | ✅ but uses `input()` (CLI-only) |
| generate_report → html_details → generate_pdf | ✅ 4 templates (generic/sales/customer/collection_payment) |
| personalize 3-way (content / style / both) | ✅ but uses `input()` (CLI-only) |
| Style personalization (theme_* → base.html) | ✅ |
| Eval harness | ✅ `evalution_RAG.ipynb` (15 cases, execution-accuracy metric) |

## 3. What's pending / not done

| Item | Where |
|---|---|
| **Gradio web UI** | not started — spec in `docs/gradio_ui_spec.md` |
| **`input()` → `interrupt()`** in `human_in_the_loop.py` + `personalize.py` | Phase 0, blocks the UI |
| **Checkpointer** in `graph.py` (`SqliteSaver`) | Phase 0, blocks the UI |
| FastAPI (`app/api/`) | stub only — **intentionally not used** for the POC (Gradio calls the graph in-process) |
| User memory / preference persistence | future / post-POC (Notion plan exists) |

## 4. Known issues / risks to scrutinize first

1. **content-drift fix — verify it actually holds.**
   `generate_report.py` should feed the *previous* report back into the prompt on a personalize
   pass (so "rewrite for HR" edits wording, not the KPI numbers). Confirm the previous-content
   injection is present and that `state.get("generate_report")` is guarded for standalone calls.

2. **personalize 3-way classification robustness.**
   `personalize.py` uses an LLM to label free text as `content` / `style` / `content and style`.
   Check the ambiguous cases (e.g. "make it better", "red") route sanely and that the
   `StyleOverride` extraction never blanks a style value when content edits are also present.

3. **`state.py` hygiene.**
   The state TypedDict grew organically — check for dead/duplicate fields
   (e.g. `is_data_satisfied` vs the HITL action, `is_style_and_content` unused, `generate_pdf`
   vs `document_pdf`). Trim what nothing reads.

4. **eval comparison correctness.**
   `evalution_RAG.ipynb` `same_result` must be order-independent and tolerate `Decimal` vs
   `float` (rounded), or accuracy under-reports. Confirm the fixed version is in place.

5. **Postgres identifier casing.**
   All SQL must use lowercase column names (`customernumber`, not `customerNumber`) — Postgres
   folds unquoted identifiers. Spot-check prompts/examples.

## 5. Files worth reading (in order)

```
CLAUDE.md                          # architecture, conventions, guardrails
docs/graph_draft.md                # pipeline design + node responsibilities
docs/gradio_ui_spec.md             # the UI to build (+ why no FastAPI)
app/graph.py                       # how nodes are wired
app/models/states/state.py         # the shared state schema
app/nodes/text2sql.py              # prompt rules that came from real bugs
app/nodes/generate_report.py       # content shaping + content-drift fix
app/nodes/personalize.py           # 3-way routing
app/nodes/executeSQL.py            # retry loop
```

## 6. Conventions the reviewer must respect

- `app/` is the **source root** — bare imports (`from nodes.x import ...`), never `from app.x`.
  Run modules from inside `app/`. No `app/__init__.py`.
- LLM calls always go through `llm.with_structured_output(PydanticModel)`.
- `generate_report` never touches style; `html_details` never touches content.
- Two-layer SQL guardrail: app parses + DB role `normal_user` is SELECT-only.

## 7. Suggested kickoff prompt for the new session

> Review this codebase against `CLAUDE.md` and `docs/graph_draft.md`. Start with the 5 risks in
> `docs/handoff_codebase_review.md` §4 — for each, trace the actual code path (not just read the
> diff) and tell me whether it holds, with a concrete failure input if it doesn't. Then give me
> the top 3 things to fix before the 22 Jul deadline, ranked by risk. Don't change code yet —
> report first. (If `/scrutinize` is installed, use it.)

## 8. Immediate next build step (after review)

**Phase 0** — make the core web-ready (see `docs/gradio_ui_spec.md` §3, §8):
1. `human_in_the_loop.py`: `input()` → `interrupt()`, read `action`/`report_type`/`notes`/`feedback` from the resumed dict.
2. `personalize.py`: `input()` → `interrupt()`, pass the 3 generated options in the payload, read `choice`/`feedback`.
3. `graph.py`: `compile(checkpointer=SqliteSaver.from_conn_string("output/checkpoints.sqlite"))`.
4. Verify: invoke → assert `__interrupt__` → `Command(resume=...)` → assert it advances.

Only after Phase 0 passes: build the Gradio UI (`docs/gradio_ui_spec.md` §4).
