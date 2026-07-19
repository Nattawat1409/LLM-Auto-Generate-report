"""Gradio web UI for the LLM Auto-Generate Report pipeline.

Imports and calls the compiled LangGraph (`graph.graph`) directly — no FastAPI,
per docs/gradio_ui_spec.md. A single page with conditionally-visible groups
(gr.Group) walks the user through: Ask -> Verify & curate -> Preview &
personalize -> Done, looping back on re-query / regenerate as the graph itself
loops (via interrupt()/Command(resume=...)).

Run (Postgres must be up first: `cd Postgre && docker compose up -d`):
    cd app
    uv run python -m ui.gradio_app     # http://127.0.0.1:7860
"""
import base64
import html as html_lib
import uuid
from pathlib import Path

import gradio as gr
import pandas as pd
from langgraph.types import Command

from graph import graph

# PDFs/HTML are written under repo_root/output/ (outside app/, our cwd when run
# via `uv run python -m ui.gradio_app`) — Gradio refuses to serve files outside
# cwd/tempdir unless explicitly allow-listed.
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"

# Embed the logo as a base64 data URI (same pattern as report/html_details.py's SCG
# logo) — self-contained, and sidesteps Gradio's allowed_paths file-serving rules.
_LOGO_PATH = Path(__file__).resolve().parent / "logo" / "chang-chat-logo.png"
_LOGO_DATA_URI = (
    "data:image/png;base64," + base64.b64encode(_LOGO_PATH.read_bytes()).decode()
    if _LOGO_PATH.exists() else ""
)

VALID_TEMPLATES = ["generic", "sales", "customer", "collection_payment"]

ACTION_APPROVE = "✅ Approve — data is right"
ACTION_REQUERY = "🔄 Re-query — data doesn't match what I asked"
PERSONALIZE_OWN = "✏️ Describe my own change"
PERSONALIZE_ACCEPT = "✅ Accept — finish"


# ── Helpers ─────────────────────────────────────────────────────────────

def rows_to_dataframe(rows) -> pd.DataFrame:
    """SQLAlchemy Row objects (or None/empty) -> a display-ready DataFrame."""
    if not rows:
        return pd.DataFrame()
    try:
        columns = list(rows[0]._mapping.keys())
    except AttributeError:
        columns = None
    data = [list(r) for r in rows]
    return pd.DataFrame(data, columns=columns) if columns else pd.DataFrame(data)


def config_for(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def wrap_report_html(raw_html: str) -> str:
    """Sandbox the report in an iframe so Gradio's page theme (dark mode, its
    own CSS variables) can't bleed into the report's own colors — otherwise
    e.g. a dark KPI value on a light card can end up invisible when Gradio's
    dark-mode styling overrides it. This also makes the preview match exactly
    what WeasyPrint will print, since it's the same standalone HTML/CSS.
    """
    if not raw_html:
        return ""
    escaped = html_lib.escape(raw_html, quote=True)
    return (
        f'<iframe srcdoc="{escaped}" '
        'style="width:100%; height:80vh; border:1px solid #e4e7ec; '
        'border-radius:8px; background:white;" sandbox="allow-same-origin"></iframe>'
    )


def _stay_on_screen1(message: str) -> tuple:
    """The 19-item `render()`-shaped tuple for staying on screen 1 with a message
    (schema-gate rejection, or a caught exception from on_ask)."""
    return (
        gr.update(value=message),
        gr.update(visible=True),    # screen1
        gr.update(visible=False),   # screen2
        gr.update(visible=False),   # screen3
        gr.update(visible=False),   # screen4
        *((gr.update(),) * 7),      # screen2 fields
        *((gr.update(),) * 5),      # screen3 fields
        *((gr.update(),) * 2),      # screen4 fields
    )


def render(result: dict) -> tuple:
    """Map a graph.invoke(...)/interrupt() result to updates for every
    screen-2/3/4 component, plus which screen group should be visible.

    Returns a fixed-length tuple (19 items) so every caller can just prepend
    the thread_id and pass the result straight to `outputs=`, regardless of
    which screen the graph actually landed on.
    """
    noop7 = (gr.update(),) * 7   # screen2 fields
    noop5 = (gr.update(),) * 5   # screen3 fields
    noop2 = (gr.update(),) * 2   # screen4 fields

    if "__interrupt__" not in result:
        if result.get("is_question_relate") is False:
            # schema gate rejected the question -> stay on screen 1
            return _stay_on_screen1(
                "⚠️ This question doesn't look answerable from the "
                "`classicmodels` database schema. Try rephrasing it."
            )

        # graph reached END -> screen 4 (accepted / finalized)
        html = result.get("html_detail") or ""
        pdf_path = result.get("generate_pdf")
        return (
            gr.update(value=""),
            gr.update(visible=False),   # screen1
            gr.update(visible=False),   # screen2
            gr.update(visible=False),   # screen3
            gr.update(visible=True),    # screen4
            *noop7, *noop5,
            gr.update(value=wrap_report_html(html)),
            gr.update(value=pdf_path, visible=bool(pdf_path)),
        )

    payload = result["__interrupt__"][0].value

    if "options" in payload:
        # personalize interrupt -> screen 3
        html = payload.get("html") or ""
        pdf_path = payload.get("pdf_path")
        options = payload.get("options") or {}
        choices = list(options.values()) + [PERSONALIZE_OWN, PERSONALIZE_ACCEPT]
        return (
            gr.update(value=""),
            gr.update(visible=False),   # screen1
            gr.update(visible=False),   # screen2
            gr.update(visible=True),    # screen3
            gr.update(visible=False),   # screen4
            *noop7,
            gr.update(value=wrap_report_html(html)),
            gr.update(value=pdf_path, visible=bool(pdf_path)),
            gr.update(choices=choices, value=None),
            gr.update(value="", visible=False),
            options,
            *noop2,
        )

    # human_in_the_loop interrupt -> screen 2
    sql = payload.get("sql") or ""
    rows = payload.get("data")
    execute_error = payload.get("execute_error")
    is_correct = payload.get("is_correct")
    detail = payload.get("detail") or ""

    if execute_error:
        df = pd.DataFrame({"error": [execute_error]})
        verdict_md = f"### Validate fetched data\n\n⚠️ **SQL execution failed** — you can re-query below.\n\n{detail}"
        default_action = ACTION_REQUERY
    else:
        df = rows_to_dataframe(rows)
        badge = "✅" if is_correct else "⚠️"
        verdict_md = f"### Validate fetched data\n\n{badge} **Verdict:** {detail}"
        default_action = ACTION_APPROVE

    is_approve = default_action == ACTION_APPROVE
    return (
        gr.update(value=""),
        gr.update(visible=False),   # screen1
        gr.update(visible=True),    # screen2
        gr.update(visible=False),   # screen3
        gr.update(visible=False),   # screen4
        gr.update(value=sql),
        gr.update(value=df),
        gr.update(value=verdict_md),
        gr.update(value=default_action),
        gr.update(value="generic", visible=is_approve),
        gr.update(value="", visible=is_approve),
        gr.update(value="", visible=not is_approve),
        *noop5,
        *noop2,
    )


# ── Event handlers ──────────────────────────────────────────────────────

def on_ask_loading():
    """Fires instantly (queue=False) on click, before the slow graph call, so
    the button visibly shows it's working. on_ask always resets it afterwards —
    including on error — since on_ask never raises (see below)."""
    return gr.update(value="⏳ Loading data...", interactive=False)


def on_ask(question: str):
    reset_btn = gr.update(value="Generate report", interactive=True)

    if not question or not question.strip():
        return (None,) + _stay_on_screen1("⚠️ Please enter a question first.") + (reset_btn,)

    thread_id = str(uuid.uuid4())
    try:
        result = graph.invoke({"user_input": question}, config=config_for(thread_id))
    except Exception as e:
        return (thread_id,) + _stay_on_screen1(f"⚠️ Failed to process your question: {e}") + (reset_btn,)

    return (thread_id,) + render(result) + (reset_btn,)


def on_action_change(action: str):
    is_approve = action == ACTION_APPROVE
    return (
        gr.update(visible=is_approve),      # template_radio
        gr.update(visible=is_approve),      # notes_tb
        gr.update(visible=not is_approve),  # wrong_tb
    )


def on_continue_screen2(thread_id, action, report_type, notes, wrong_text):
    if action == ACTION_APPROVE:
        resume = {"action": "approve", "report_type": report_type or "generic", "notes": notes or ""}
    else:
        resume = {"action": "requery", "feedback": wrong_text or ""}

    try:
        result = graph.invoke(Command(resume=resume), config=config_for(thread_id))
    except Exception as e:
        raise gr.Error(f"Failed to continue: {e}")

    return (thread_id,) + render(result)


def on_personalize_radio_change(selected: str):
    return gr.update(visible=(selected == PERSONALIZE_OWN))


def on_apply_screen3(thread_id, selected, own_text, options):
    options = options or {}

    if selected == PERSONALIZE_ACCEPT:
        choice, feedback = "5", ""
    elif selected == PERSONALIZE_OWN:
        if not own_text or not own_text.strip():
            raise gr.Error("Please describe your preferred change first.")
        choice, feedback = "4", own_text.strip()
    else:
        choice = next((k for k, v in options.items() if v == selected), None)
        if choice is None:
            raise gr.Error("Please select a personalisation option first.")
        feedback = ""

    try:
        result = graph.invoke(Command(resume={"choice": choice, "feedback": feedback}), config=config_for(thread_id))
    except Exception as e:
        raise gr.Error(f"Failed to apply your change: {e}")

    return (thread_id,) + render(result)


def on_new_report():
    return (
        None,                        # thread_state
        "",                           # question_tb
        "",                           # status_md
        gr.update(visible=True),     # screen1
        gr.update(visible=False),    # screen2
        gr.update(visible=False),    # screen3
        gr.update(visible=False),    # screen4
    )


# ── Layout ──────────────────────────────────────────────────────────────

# Dark mode defaults to flat black — replace it with a fading black -> dark-grey
# gradient. Gradio 6 renders inside a `<gradio-app>` custom element with its own
# shadow DOM, so `.gradio-container` alone only paints the centered inner box —
# the `:host`/`gradio-app` rules here are what paint the full-viewport area
# around it (the previous version left that area flat black). Covers every
# selector Gradio might use to flag dark mode (data-theme attr, .dark class, the
# OS-level prefers-color-scheme, and the shadow host itself) so it applies
# regardless of how dark mode got toggled on.
_GRADIENT = "linear-gradient(160deg, #000000 0%, #161616 45%, #2b2b2f 100%)"
_DARK_GRADIENT_CSS = f"""
:host,
gradio-app,
html, body,
:root[data-theme="dark"] .gradio-container,
:root[data-theme="dark"] body,
.dark .gradio-container,
.dark body {{
    background: {_GRADIENT} !important;
    background-attachment: fixed !important;
    min-height: 100vh !important;
}}
@media (prefers-color-scheme: dark) {{
    :host, gradio-app, html, body, .gradio-container {{
        background: {_GRADIENT} !important;
        background-attachment: fixed !important;
        min-height: 100vh !important;
    }}
}}
"""

# Layout/typography polish only — no color/theme changes here, just spacing,
# card framing for each screen, and the header treatment for the logo.
_POLISH_CSS = """
.gradio-container { max-width: min(1400px, 92vw) !important; width: 100% !important; margin: 0 auto !important; }

.app-header {
    display: flex; align-items: center; gap: 22px;
    padding: 4px 4px 18px 4px; margin-bottom: 6px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
}
.app-header img {
    height: 64px; width: auto; border-radius: 12px;
    filter: drop-shadow(0 6px 18px rgba(236,28,36,0.35));
}
.app-header .app-title {
    font-size: 26px; font-weight: 800; letter-spacing: -0.3px; line-height: 1.15;
}
.app-header .app-subtitle {
    font-size: 14px; opacity: 0.7; margin-top: 4px;
}

.app-card {
    border-radius: 16px !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    background: rgba(255,255,255,0.035) !important;
    box-shadow: 0 10px 30px rgba(0,0,0,0.25) !important;
    padding: 22px 24px !important;
    margin-bottom: 18px !important;
}
.app-card h2 { margin-top: 0 !important; }

.app-footer {
    text-align: center; opacity: 0.45; font-size: 12px;
    padding: 18px 0 8px 0;
}
"""

with gr.Blocks(title="Chang Chat — LLM Auto-Generate Report") as demo:
    thread_state = gr.State(None)
    options_state = gr.State({})

    gr.HTML(
        f"""
        <div class="app-header">
            <img src="{_LOGO_DATA_URI}" alt="Chang Chat logo">
            <div>
                <div class="app-title">Chang Chat</div>
                <div class="app-subtitle">AI-powered report generation for the <code>classicmodels</code> database</div>
            </div>
        </div>
        """
    )

    # Screen 1 — Ask
    with gr.Group(visible=True, elem_classes=["app-card"]) as screen1_group:
        question_tb = gr.Textbox(
            label="Ask about the classicmodels database",
            placeholder="Total sales revenue by product line in 2004",
            lines=2,
        )
        ask_btn = gr.Button("Generate report", variant="primary")
        status_md = gr.Markdown("")

    # Screen 2 — Verify & curate (human_in_the_loop)
    with gr.Group(visible=False, elem_classes=["app-card"]) as screen2_group:
        gr.Markdown("## Review the fetched data")
        sql_code = gr.Code(language="sql", label="Generated SQL", interactive=False)
        data_df = gr.Dataframe(label="Fetched rows", interactive=False, wrap=True)
        verdict_md = gr.Markdown("")
        action_radio = gr.Radio(
            choices=[ACTION_APPROVE, ACTION_REQUERY],
            value=ACTION_APPROVE,
            label="Action",
        )
        template_radio = gr.Radio(
            choices=VALID_TEMPLATES,
            value="generic",
            label="Report template",
            visible=True,
        )
        notes_tb = gr.Textbox(
            label="Emphasis / context notes (optional)",
            placeholder="What should the report highlight? Any business context the database can't know?",
            visible=True,
        )
        wrong_tb = gr.Textbox(
            label="What was wrong?",
            placeholder="Describe how the data doesn't match what you asked.",
            visible=False,
        )
        continue_btn = gr.Button("Continue", variant="primary")

    # Screen 3 — Preview & personalize
    with gr.Group(visible=False, elem_classes=["app-card"]) as screen3_group:
        gr.Markdown("## Preview & personalize")
        html_preview = gr.HTML()
        pdf_file = gr.File(label="Download PDF")
        personalize_radio = gr.Radio(choices=[], label="Personalize options")
        personalize_own_tb = gr.Textbox(
            label="Describe your own change",
            visible=False,
        )
        apply_btn = gr.Button("Apply", variant="primary")

    # Screen 4 — Done
    with gr.Group(visible=False, elem_classes=["app-card"]) as screen4_group:
        gr.Markdown("## ✅ Report finalized")
        done_html = gr.HTML()
        done_pdf_file = gr.File(label="Download final PDF")
        new_report_btn = gr.Button("Start a new report")

    gr.HTML('<div class="app-footer">Chang Chat · LLM Auto-Generate Report — SCG internship POC</div>')

    # ── Wiring ────────────────────────────────────────────────────────
    master_outputs = [
        status_md, screen1_group, screen2_group, screen3_group, screen4_group,
        sql_code, data_df, verdict_md, action_radio, template_radio, notes_tb, wrong_tb,
        html_preview, pdf_file, personalize_radio, personalize_own_tb, options_state,
        done_html, done_pdf_file,
    ]

    ask_btn.click(
        on_ask_loading,
        inputs=[],
        outputs=[ask_btn],
        queue=False,
    ).then(
        on_ask,
        inputs=[question_tb],
        outputs=[thread_state] + master_outputs + [ask_btn],
    )

    action_radio.change(
        on_action_change,
        inputs=[action_radio],
        outputs=[template_radio, notes_tb, wrong_tb],
    )

    continue_btn.click(
        on_continue_screen2,
        inputs=[thread_state, action_radio, template_radio, notes_tb, wrong_tb],
        outputs=[thread_state] + master_outputs,
    )

    personalize_radio.change(
        on_personalize_radio_change,
        inputs=[personalize_radio],
        outputs=[personalize_own_tb],
    )

    apply_btn.click(
        on_apply_screen3,
        inputs=[thread_state, personalize_radio, personalize_own_tb, options_state],
        outputs=[thread_state] + master_outputs,
    )

    new_report_btn.click(
        on_new_report,
        inputs=[],
        outputs=[thread_state, question_tb, status_md, screen1_group, screen2_group, screen3_group, screen4_group],
    )


if __name__ == "__main__":
    demo.launch(
        allowed_paths=[str(OUTPUT_DIR)],
        theme=gr.themes.Default(primary_hue="red"),
        css=_DARK_GRADIENT_CSS + _POLISH_CSS,
    )


