# Gradio UI — Implementation Spec

Spec for turning the existing LangGraph pipeline into an interactive Gradio web UI.
Written for an implementing agent: read this top-to-bottom before writing code.

---

## 1. Goal

Replace the CLI (`input()`-driven) flow with a Gradio web UI where the user can:

1. Type a natural-language question about the `classicmodels` database.
2. **Review the fetched data + the correctness verdict** on screen before any report is generated.
3. **Decide via radio buttons** (Claude-style options) whether to approve or re-query.
4. **Preview the generated report** (HTML) in the browser.
5. **Personalize via radio buttons** — pick an AI-proposed option, type their own, or accept.
6. Loop back to regenerate until satisfied, then finish and download the PDF.

## 2. Architecture decision — no FastAPI

Gradio is Python and runs in the same process as the graph, so it **imports and calls the
compiled graph directly**. Do NOT introduce FastAPI for this POC:

```
ui/gradio_app.py  ──直接 import──►  graph.py (compiled LangGraph + checkpointer)
```

FastAPI is only justified when a non-Python client, a separate deployment, or multiple
frontends need the pipeline. Keep `app/api/` untouched as future work.

## 3. Current state vs. what must change

| Area | Current (CLI) | Required (UI) |
|---|---|---|
| `nodes/human_in_the_loop.py` | blocks on `input()` | must call `interrupt()` and read the resumed value |
| `nodes/personalize.py` | blocks on `input()` | must call `interrupt()` and read the resumed value |
| `graph.py` | `builder.compile()` — no checkpointer | `builder.compile(checkpointer=SqliteSaver(...))` |
| Entry point | `graph.invoke()` in `__main__` | Gradio event handlers |

**`interrupt()` + a checkpointer are mandatory.** Without a checkpointer, LangGraph cannot
pause and resume, and the UI cannot exist. This is Phase 0 and blocks everything else.

### 3.1 The interrupt/resume contract

```python
# inside a node — pauses the graph and surfaces `payload` to the caller
user_response = interrupt(payload_dict)

# in the UI — first call runs until the first interrupt
result = graph.invoke({"user_input": q}, config={"configurable": {"thread_id": tid}})
# result["__interrupt__"] holds the payload the node passed to interrupt()

# in the UI — resume: the value lands as the return of interrupt() inside the node
result = graph.invoke(Command(resume=answer_dict), config={"configurable": {"thread_id": tid}})
```

`thread_id` identifies one report session. Generate a fresh UUID per query and keep it in
`gr.State`; the checkpointer stores all graph state server-side, so the UI only holds this id.

## 4. Screens

The UI is a **single page with conditionally visible groups**, driven by the pipeline's
current status. Use `gr.Group(visible=...)` toggling, not tabs — the user is walked through
a linear flow with loops.

### Screen 1 — Ask

| Component | Spec |
|---|---|
| `gr.Textbox` | label "Ask about the classicmodels database", placeholder e.g. `"Total sales revenue by product line in 2004"`, `lines=2` |
| `gr.Button` | "Generate report", `variant="primary"` |
| `gr.Markdown` | status line, hidden until running |

**Behaviour:** on submit → new `thread_id` → `graph.invoke({"user_input": q}, config)`.

Two possible outcomes:
- The `schema` node judged the question **not DB-related** → graph runs to END with no data.
  Show a friendly message ("This question can't be answered from the database schema") and
  stay on Screen 1.
- Otherwise the graph pauses at `human_in_the_loop` → go to Screen 2.

### Screen 2 — Verify & curate (human_in_the_loop)

This screen shows everything the user needs to judge the data **before** an expensive
report generation runs.

| Component | Source | Spec |
|---|---|---|
| `gr.Code(language="sql")` | `state["output_text2SQL"]` | the generated SQL, read-only |
| `gr.Dataframe` | `state["execute_sql"]` | the fetched rows; `interactive=False` for POC |
| `gr.Markdown` | `state["is_correct_verify_correctness"]` + `state["detail_verify_correctness"]` | **verification verdict** — render a ✅/⚠️ badge from the bool, then the detail text below |
| `gr.Radio` | — | **Action**: `["✅ Approve — data is right", "🔄 Re-query — data doesn't match what I asked"]`, default = Approve |
| `gr.Radio` | — | **Report template**: `["generic", "sales", "customer", "collection_payment"]`, default `generic`. Visible only when Action = Approve |
| `gr.Textbox` | — | **Emphasis / context notes** (optional): "What should the report highlight? Any business context the database can't know?" Visible only when Action = Approve |
| `gr.Textbox` | — | **What was wrong?**: free text describing the mismatch. Visible only when Action = Re-query |
| `gr.Button` | — | "Continue" |

**Conditional visibility:** wire the Action radio's `.change()` to toggle the two lower
groups. Only ever show the fields relevant to the chosen action.

**Behaviour on Continue:**

```python
# Approve
Command(resume={"action": "approve", "report_type": report_type, "notes": notes})
# Re-query
Command(resume={"action": "requery", "feedback": feedback})
```

- Approve → the graph runs `generate_report → html_details → generate_pdf` and pauses at
  `personalize` → go to Screen 3.
- Re-query → the graph loops back to `text2sql`, re-runs, and pauses at `human_in_the_loop`
  again → **stay on Screen 2 with refreshed SQL/data/verdict.**

> Note: `verify_correctness` is *informational*. It never blocks the flow — the human makes
> the call. Surface its verdict prominently but do not gate the buttons on it.

### Screen 3 — Preview & personalize

| Component | Source | Spec |
|---|---|---|
| `gr.HTML` | `state["html_detail"]` | **live preview of the rendered report** |
| `gr.File` | `state["generate_pdf"]` | PDF download button |
| `gr.Radio` | the 3 LLM-proposed options from the interrupt payload | **Personalize options** — Claude-style choices. Labels are the AI's option text; append two fixed choices: `"✏️ Describe my own change"` and `"✅ Accept — finish"` |
| `gr.Textbox` | — | free-text preference. Visible only when "Describe my own change" is selected |
| `gr.Button` | — | "Apply" |

**The `personalize` node must pass its 3 generated options through `interrupt()`** so the UI
can render them as radio labels. Payload shape:

```python
interrupt({
    "html": state["html_detail"],
    "pdf_path": state["generate_pdf"],
    "options": {"1": options.option1, "2": options.option2, "3": options.option3},
})
```

**Behaviour on Apply** — resume with the user's choice:

```python
Command(resume={"choice": "1" | "2" | "3" | "4" | "5", "feedback": free_text_or_empty})
```

The node's existing logic then classifies the request (`content` / `style` / `content and style`)
and routes accordingly:
- **content / content+style** → `generate_report` → re-render → pause at `personalize` again
  → **stay on Screen 3 with the new preview.**
- **style only** → `html_details` (skips regeneration) → pause at `personalize` again → same.
- **accept (choice 5)** → END → go to Screen 4.

Each loop must visibly refresh the `gr.HTML` preview and the PDF file — this is the core
demo moment.

### Screen 4 — Done

| Component | Spec |
|---|---|
| `gr.Markdown` | "✅ Report finalized" |
| `gr.HTML` | final report |
| `gr.File` | final PDF download |
| `gr.Button` | "Start a new report" → resets all state, back to Screen 1 |

## 5. UI state

```python
thread_id = gr.State(None)   # identifies the graph session for the checkpointer
```

That is the **only** state the UI needs to hold. Everything else lives in the checkpointer
and is read from the value returned by `graph.invoke(...)`.

## 6. Handler contract

Every handler follows the same shape:

1. Call `graph.invoke(...)` (fresh input or `Command(resume=...)`) with the thread config.
2. Inspect the result:
   - `result.get("__interrupt__")` present → the graph paused; read the payload to know which
     screen to show and what to render.
   - absent → the graph reached END → Screen 4 (or the "not DB-related" case from Screen 1).
3. Return updated component values + `gr.update(visible=...)` for the screen groups.

Keep a single helper that maps a graph result to `(screen_to_show, component_values)` rather
than duplicating that logic in each handler.

## 7. Error handling

| Failure | UI behaviour |
|---|---|
| SQL fails after retries (`execute_error` set, `execute_sql` is None) | Screen 2 still renders — show the error in place of the dataframe and the verdict text explaining the failure. The user can Re-query. |
| Question not DB-related (`is_question_relate` False) | Stay on Screen 1 with an explanatory message. |
| LLM/network exception | Catch in the handler, show `gr.Warning`, keep the user on the current screen with their input intact. |
| WeasyPrint/PDF failure | Show the HTML preview anyway; disable the PDF download with a note. |

Never let an exception escape a handler — Gradio will render an unhelpful stack trace.

## 8. Implementation phases

**Phase 0 — Make the core web-ready (blocking).**
1. `nodes/human_in_the_loop.py`: replace `input()` with `interrupt()`; read `action`,
   `report_type`, `notes`, `feedback` from the resumed dict. Keep the existing `Command(goto=...)`
   routing untouched.
2. `nodes/personalize.py`: replace `input()` with `interrupt()`; pass the 3 generated options
   in the payload; read `choice` + `feedback` from the resumed dict. Keep the existing 3-way
   classification and routing.
3. `graph.py`: `builder.compile(checkpointer=SqliteSaver.from_conn_string("output/checkpoints.sqlite"))`.
4. Verify with a script: invoke → assert `__interrupt__` → resume → assert it advances.

**Phase 1 — Gradio UI.** Build Screens 1–4 and the handler mapping above.

**Phase 2 — Polish.** Loading indicators (`gr.Progress`), disable buttons while running,
`gr.Warning` on errors, restyle.

## 9. Acceptance criteria

- [ ] Asking a non-DB question shows a message and does not run Text2SQL.
- [ ] A valid question shows SQL + data table + correctness verdict before any report exists.
- [ ] Re-query with feedback loops back and shows **new** SQL/data on the same screen.
- [ ] Approve + template + notes produces a report preview and a downloadable PDF.
- [ ] The 3 personalize options shown are the ones the LLM generated for **this** report.
- [ ] Picking a content option regenerates and visibly updates the preview.
- [ ] Picking a style-only option updates the preview **without** regenerating content.
- [ ] Accept ends the session and offers the final PDF.
- [ ] Two browser sessions in parallel do not mix state (distinct `thread_id`s).

## 10. Out of scope (POC)

- FastAPI / REST layer, SSE streaming.
- Authentication, multi-user profiles, persisted user preferences.
- Editing the fetched data by hand in the dataframe.
- Replacing `streamlit_app.py` — it is superseded; leave it or delete it, do not maintain both.

## 11. Run

```bash
cd app
uv run python -m ui.gradio_app     # http://127.0.0.1:7860
```
Postgres must be up first: `cd app/Postgre && docker compose up -d`.
