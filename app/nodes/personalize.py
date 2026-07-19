from __future__ import annotations
from pathlib import Path
from typing import Literal , Optional
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command, interrupt
from langgraph.graph import END
from pydantic import BaseModel, Field
from llm import llm
from models import state


# ── 1. Parse classify free-text is "style" , "content" or "style and content" ────────────────
class Parse_type_personalize(BaseModel):
    check_type_refine:  Literal["content", "style", "content and style"] = Field(description = "check the user input from personalize report return only 3 type such as ,content,style, content and style which one is the most related to personalize report")

# ── 2. Parse text when user free-text = refine "style only"────────────────────────────────
class StyleOverride(BaseModel):
    is_style_change: bool
    text_color: Optional[str] = None
    header_color: Optional[str] = None
    footer_color: Optional[str] = None
    font_size: Optional[str] = None

# parse the user free-text refine (style , content, style and content)
llm_parse_type = llm.with_structured_output(Parse_type_personalize) 


_REFINE_PROMPT = """\
You classify a user's report personalisation feedback.
Return exactly one label:
- "content"           -> wording, structure, tone, or which data to emphasise
- "style"             -> colors, font size, or visual theme only
- "content and style" -> the feedback asks for BOTH
"""

# Pure EXTRACTION prompt: the caller has already decided style is involved, so this
# ONLY pulls out CSS-ready values. It must NOT null things out just because the user
# ALSO asked for content changes (that is what broke the "content and style" case).
_STYLE_PARSE_PROMPT = """\
Extract the visual/style values the user asked for. The user may ALSO ask for content
changes — ignore those; only capture styling here, and NEVER blank a style value just
because content edits are present.

Map to fields (fill only the ones the user mentions, leave the rest null):
- header_color -> the report header / title / H1 colour
- text_color   -> body text / H2 / general text colour
- footer_color -> the footer colour
- font_size    -> the text size

Colours as hex (e.g. "#2563eb") or a valid CSS colour name (e.g. "orange", "navy").
font_size must include a unit (e.g. "14px"). Set is_style_change=true whenever you
captured at least one value."""

# get user personalize Type = Style only
_style_parse_llm = llm.with_structured_output(StyleOverride)

# ── 2. Structured output schema ───────────────────────────────────────────────
class PersonalizationOptions(BaseModel):
    """Three distinct AI-proposed options to improve the report."""

    option1: str = Field(
        description=(
            "First option — e.g. change report tone "
            "(formal → executive summary style)."
        )
    )
    option2: str = Field(
        description=(
            "Second option — a different dimension, e.g. "
            "highlight key risk factors or add trend comparisons."
        )
    )
    option3: str = Field(
        description=(
            "Third option — another angle, e.g. "
            "restructure for a non-technical audience or add visual emphasis."
        )
    )

_structured_llm = llm.with_structured_output(PersonalizationOptions) 

# ── 3. System prompt Pydantic : Select option ──────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a senior report personalisation assistant.
You will receive the full HTML source of an auto-generated data report.
Propose exactly THREE distinct, actionable personalisation options.

Rules:
- Each option must be concise (≤ 2 sentences).
- Options must differ in approach: tone / structure / audience / focus.
- Describe only what CHANGES, not the current state.
"""

# ── 5. Node ───────────────────────────────────────────────────────────────────

def personalize(state: state) -> Command[Literal["generate_report", "html_details", "__end__"]]:
    """
    Human-in-the-loop personalisation node.

    Reads HTML from state['html_detail'], asks the LLM to propose
    3 personalisation options, then pauses via interrupt() so a UI can render
    them as radio choices: 1-3 (AI option), 4 (free text), or 5 (accept as-is).

    Routing
    -------
    choices 1-3, and 4 classified content/content+style  →  "generate_report"
    choice 4 classified style-only                       →  "html_details"
    choice  5                                             →  END (accept report)
    """

    # ── Load HTML from state (produced by html_details node) ─────────────
    html_content: str = state['html_detail']
    html_path: str = state['html_path']
    is_satisfy = False      # set default as not satisfy 
    
    if not html_content:
        # fallback: try reading from file path if node stored a path instead
        html_path = state['html_path']
        if html_path and Path(html_path).exists():
            html_content = Path(html_path).read_text(encoding="utf-8")
        else:
            raise ValueError(
                "State key 'html_detail' is empty. "
                "Ensure the html_details node ran before personalize."
            )

    # ── Ask LLM to propose 3 options ─────────────────────────────────────
    print("\n🤖  Analysing report — generating personalisation options …\n")

    options: PersonalizationOptions = _structured_llm.invoke(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    "Here is the HTML report. "
                    "Propose three personalisation options.\n\n"
                    f"<report>\n{html_content[:8000]}\n</report>"  # trim if huge
                )
            ),
        ]
    )

    # ── Options for the UI to render as radio choices ─────────────────────
    option_map = {
        "1": options.option1,
        "2": options.option2,
        "3": options.option3,
    }

    # ── Pause the graph: surface the report + options, resume with the choice ──
    response = interrupt({
        "html": html_content,
        "pdf_path": state.get("generate_pdf"),
        "options": option_map,
    })

    choice = (response.get("choice") or "").strip()
    user_input = (response.get("feedback") or "").strip()

    preference: str = ""
    goto: str
    is_satisfy = False

    if choice in option_map:                            # AI-proposed option
        preference = option_map[choice]
        goto = "generate_report"

    elif choice == "4":                                  # Free text
        if not user_input:
            raise ValueError("Choice 4 ('Describe my own change') requires non-empty feedback text.")

        # parse use_input "content" or "style"
        refine_type = llm_parse_type.invoke([
            SystemMessage(content=_REFINE_PROMPT),
            HumanMessage(content=user_input),
        ]).check_type_refine

        # parse CSS-ready style values whenever style is involved (cases 1 and 3)
        style = None
        if refine_type in ("style", "content and style"):
            style = _style_parse_llm.invoke([
                SystemMessage(content=_STYLE_PARSE_PROMPT),
                HumanMessage(content=user_input),
            ])

        # CASE 1 — style only: SKIP generate_report, restyle existing content in html_details
        if refine_type == "style":
            return Command(goto="html_details", update={
                "is_style_change": True,
                "is_content_change": False,
                "theme_text_color": style.text_color,
                "theme_header_color": style.header_color,
                "theme_footer_color": style.footer_color,
                "theme_font_size": style.font_size,
                "is_after_personalize": True,               # existed html_details files it under after_personalize/
                "is_satisfy_personalize_report": False,
            })

        # CASE 3 — content AND style: refine content in generate_report, then restyle in html_details
        if refine_type == "content and style":
            return Command(goto="generate_report", update={
                "is_content_change": True,
                "is_style_change": True,
                "personalize_report": user_input,   # content feedback for generate_report
                "theme_text_color": style.text_color,
                "theme_header_color": style.header_color,
                "theme_footer_color": style.footer_color,
                "theme_font_size": style.font_size,
                "is_satisfy_personalize_report": False,
            })

        # CASE 2 — content only: traditional refine through generate_report -> html_details
        return Command(goto="generate_report", update={
            "is_content_change": True,
            "is_style_change": False,
            "personalize_report": user_input,       # content feedback for generate_report
            "is_satisfy_personalize_report": False,
        })

    else:                                                # choice "5" (or anything else) — accept as-is
        is_satisfy = True
        preference = ""
        goto = END

    # ── Return Command with routing + state update ────────────────────────
    # AI options 1-3 are content edits (goto generate_report); choice 5 accepts (goto END).
    return Command(
        goto=goto,
        update={"personalize_report": preference,
                "is_satisfy_personalize_report": is_satisfy,
                "is_style_change": False,             # these paths never touch style
                "is_content_change": goto == "generate_report",
                },
    )


# UNIT TEST ------------------------------------------------------------------------------------

if __name__ == "__main__":
    # grab the most recently generated HTML report (any type)
    html_dir = Path(__file__).resolve().parents[2] / "output" / "html_output"
    html_files = sorted(html_dir.glob("report_*.html"), key=lambda p: p.name, reverse=True)

    if not html_files:
        raise SystemExit(
            f"No HTML reports found in {html_dir}. "
            "Run `uv run -m nodes.html_details` first to generate one."
        )

    sample_path = html_files[0]
    print("Using report:", sample_path.name)

    mock_state = {
        "html_detail": sample_path.read_text(encoding="utf-8"),
        "html_path": str(sample_path),
    }

    # minimal graph to exercise the interrupt()/resume contract in isolation.
    # generate_report/html_details are stand-ins so Command(goto=...) has a valid
    # target; the real graph (graph.py) wires the actual nodes.
    from langgraph.graph import StateGraph, START, END as GRAPH_END
    from langgraph.checkpoint.memory import InMemorySaver

    builder = StateGraph(state)
    builder.add_node("personalize", personalize)
    builder.add_node("generate_report", lambda s: {})
    builder.add_node("html_details", lambda s: {})
    builder.add_edge(START, "personalize")
    builder.add_edge("generate_report", GRAPH_END)
    builder.add_edge("html_details", GRAPH_END)
    test_graph = builder.compile(checkpointer=InMemorySaver())

    config = {"configurable": {"thread_id": "smoke-test-personalize"}}
    result = test_graph.invoke(mock_state, config=config)
    interrupt_payload = result["__interrupt__"][0].value
    print("\nOptions offered:", interrupt_payload["options"])

    resumed = test_graph.invoke(Command(resume={"choice": "5", "feedback": ""}), config=config)
    print("\nResumed (accept) →", resumed)