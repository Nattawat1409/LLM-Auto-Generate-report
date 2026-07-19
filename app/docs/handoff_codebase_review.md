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
| LangGraph graph wired (9 nodes) | ✅ `graph.py`, compiled with a `SqliteSaver` checkpointer (`output/checkpoints.sqlite`) |
| Text2SQL + schema injection + few-shot rules | ✅ passes 15 ground-truth eval cases |
| SQL self-retry loop (2 retries) | ✅ `executeSQL.py` |
| verify_correctness (LLM verdict + detail) | ✅ informational, non-blocking |
| human_in_the_loop (curator: approve/re-query) | ✅ uses `interrupt()` — works from both the CLI and the Gradio UI |
| generate_report → html_details → generate_pdf | ✅ 4 templates (generic/sales/customer/collection_payment) |
| personalize 3-way (content / style / both) | ✅ uses `interrupt()` — works from both the CLI and the Gradio UI |
| Style personalization (theme_* → base.html) | ✅ |
| Eval harness | ✅ `evalution_RAG.ipynb` (15 cases, execution-accuracy metric) |
| **Gradio web UI** (`ui/gradio_app.py`) | ✅ built per `docs/gradio_ui_spec.md`, all 4 screens working end-to-end |

### Phase 0 (interrupt/resume) — done, 2026-07-19

- `nodes/human_in_the_loop.py`: `input()` → `interrupt()`. Payload: `{sql, data, execute_error, is_correct, detail}`. Resume dict: `{"action": "approve", "report_type", "notes"}` or `{"action": "requery", "feedback"}`. Routing (`Command(goto=...)`) unchanged.
- `nodes/personalize.py`: `input()` → `interrupt()`. Payload: `{html, pdf_path, options: {"1","2","3"}}`. Resume dict: `{"choice": "1"-"5", "feedback"}`. The old CLI `while True` retry loop was removed — the node now branches once per resume, since the UI (radio buttons) only ever sends a valid choice.
- `graph.py`: `builder.compile(checkpointer=SqliteSaver(sqlite3.connect(...)))`, DB at `output/checkpoints.sqlite`. Added `langgraph-checkpoint-sqlite` to `pyproject.toml` (was missing — only `langgraph-checkpoint` (in-memory) was installed).
- Each node's `__main__` smoke test now spins up a minimal single-node (or single-node + stub-target) graph with `InMemorySaver` to exercise interrupt/resume in isolation — calling the node function directly no longer works, since `interrupt()` requires an active graph run.
- Verified with a real end-to-end run (live Postgres + LiteLLM): ask → interrupt at `human_in_the_loop` → resume approve → interrupt at `personalize` → resume accept → END. All assertions passed.

### Phase 1 (Gradio UI) — done, 2026-07-19

- `app/ui/gradio_app.py` (new; `app/ui/__init__.py` added so it's importable as `-m ui.gradio_app`). Single `gr.Blocks` page, 4 `gr.Group`s toggled by visibility per the spec's Screens 1–4. One shared `render(result) -> tuple` helper maps any `graph.invoke(...)` result to updates for every component, used by all three graph-calling handlers (`on_ask`, `on_continue_screen2`, `on_apply_screen3`) — avoids duplicating the interrupt-payload-parsing logic.
- Only UI state held client-side is `thread_state` (`gr.State`, the thread_id) + `options_state` (the last personalize payload's `{"1","2","3"}` map, needed to translate the clicked radio label back into a `choice` string on resume).
- **Run:** `cd app && uv run python -m ui.gradio_app` → http://127.0.0.1:7860 (Postgres must be up: `cd Postgre && docker compose up -d`).
- **Verified via `gradio_client`** (no Chrome extension available this session) driving the live server through the real HTTP/websocket API — same code path a browser hits: ask → screen 2 (SQL/data/verdict rendered) → approve+template → screen 3 (HTML preview + PDF + 3 AI options) → pick a content option → regenerated preview → accept → screen 4 (done). Also verified: non-DB question stays on screen 1 with a message; re-query loops back to screen 2 with a genuinely different SQL query; "describe my own change" with a style-only request (e.g. "make the header dark green") updates the preview without regenerating content.

### Two bugs found + fixed while wiring the UI

1. **Gradio blocked serving the PDF.** `output/pdf_output/` lives at the repo root, outside `app/` (the process cwd when run via `-m ui.gradio_app`) and outside the system temp dir — Gradio's `gr.File`/`gr.HTML` file-serving refuses paths outside cwd/tempdir for security and raised `InvalidPathError`. Fixed by passing `allowed_paths=[OUTPUT_DIR]` to `demo.launch()` (`ui/gradio_app.py`).
2. A test script bug (not a code bug): calling `graph.invoke(Command(resume=...), config=...)` with a `thread_id` that has no matching checkpoint (e.g. a fresh session that never asked a question) does *not* raise cleanly — it re-enters the graph from `START` with an empty state dict, and blows up several nodes downstream with a confusing Pydantic error (`HumanMessage content` = `None`). Not fixed (it shouldn't come up from the UI, since Apply/Continue buttons are only reachable after a `thread_id` exists) but worth knowing if a future checkpointer swap or multi-worker deployment loses that invariant.

## 3. What's pending / not done

| Item | Where |
|---|---|
| Phase 2 polish (`gr.Progress`, disable-buttons-while-running, restyle) | `docs/gradio_ui_spec.md` §8 Phase 2 — not started |
| FastAPI (`app/api/`) | stub only — **intentionally not used** for the POC (Gradio calls the graph in-process) |
| User memory / preference persistence | future / post-POC (Notion plan exists) |
| `app/ui/UI.py` | pre-existing throwaway `gr.ChatInterface` experiment, unrelated to `gradio_app.py` — left in place, safe to delete whenever |

### New minor risks to know about (found during Phase 0/1, not yet acted on)

- **`personalize` re-invokes the options-generating LLM call on every resume.** LangGraph replays a node from the top on each `Command(resume=...)`; only the `interrupt()` call itself returns the cached value, so the `_structured_llm.invoke(...)` for the 3 options runs again (wastes one LLM call, and — since it's not temperature-0 — could theoretically propose different options than what the payload the user actually saw). Harmless for the POC; would need moving the LLM call to before a *second* interrupt if this needs to be eliminated.
- **msgpack checkpoint warnings**: `Deserializing unregistered type sqlalchemy.engine.row.Row` and `...generate_report.SalesReportData` print on every resume. Non-fatal now (langgraph-checkpoint 4.1.1 just warns), but the warning says this will be **blocked in a future version**. If upgrading `langgraph-checkpoint`, either register these types via `allowed_msgpack_modules` or convert `execute_sql` rows / `generate_report` output to plain dicts before they hit state.
- **Sales/customer/collection_payment templates have no free-text field.** Their Pydantic schemas (`SalesReportData`, `CustomerReportData`, `CollectionReportData`) are rigid KPI/table structures with no narrative/summary slot (unlike `GenericReportData`, which has `summary` + `sections`). A personalize request like "add an executive summary" against a `sales` report has nowhere in the schema to land, so `generate_report` may return content that's effectively unchanged — this looks like a no-op bug in the UI but is actually a template-schema gap. Verified: the identical request against the `generic` template *does* change the rendered HTML.

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

~~Phase 0 (interrupt/resume + checkpointer) and Phase 1 (Gradio UI, `ui/gradio_app.py`) are both
done — see §2 above for what was built and how it was verified.~~

**Next up, in priority order:**
1. **Phase 2 polish** (`docs/gradio_ui_spec.md` §8 Phase 2): `gr.Progress` during `graph.invoke()`
   calls (they can take 10–30s live), disable buttons while running, restyle. None of this changes
   behavior, so it's safe to pick up any time.
2. Work through the §4 risks below (content-drift fix, personalize classification robustness,
   `state.py` hygiene, eval harness correctness, SQL casing) — none of these were touched this
   session; they predate the UI work and still need a reviewer.
3. Optionally address the three items in the "new minor risks" list in §2 (msgpack checkpoint
   warnings, personalize's duplicate LLM call on resume, sales/customer/collection_payment
   templates having no free-text field for narrative-style personalize requests).
