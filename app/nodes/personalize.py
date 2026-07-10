from __future__ import annotations
from pathlib import Path
from typing import Literal
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command
from langgraph.graph import END
from pydantic import BaseModel, Field
from llm import llm
from models import state

# ── 1. Structured output schema ───────────────────────────────────────────────

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

# ── 2. System prompt ──────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a senior report personalisation assistant.
You will receive the full HTML source of an auto-generated data report.
Propose exactly THREE distinct, actionable personalisation options.

Rules:
- Each option must be concise (≤ 2 sentences).
- Options must differ in approach: tone / structure / audience / focus.
- Describe only what CHANGES, not the current state.
"""

# ── 3. Node ───────────────────────────────────────────────────────────────────

def personalize(state: state) -> Command[Literal["generate_report", "__end__"]]:
    """
    Human-in-the-loop personalisation node.

    Reads HTML from state['html_detail'], asks the LLM to propose
    3 personalisation options, then lets the user choose 1-3 (AI option),
    4 (free text), or 5 (accept as-is).

    Routing
    -------
    choices 1-4  →  "generate_report"   (regenerate with preference)
    choice  5    →  END                 (accept report)
    """

    # ── Load HTML from state (produced by html_details node) ─────────────
    html_content: str = state.get("html_detail", "").strip()
    is_satisfy = False      # set default preference not satisfy 
    
    if not html_content:
        # fallback: try reading from file path if node stored a path instead
        html_path = state.get("html_path", "")
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

    # ── Display options ───────────────────────────────────────────────────
    option_map = {
        "1": options.option1,
        "2": options.option2,
        "3": options.option3,
    }

    print("─" * 65)
    print("  📝  How would you like to personalise the report?\n")
    for key, text in option_map.items():
        print(f"  [{key}]  {text}")
    print(f"  [4]  ✏️   Enter your own preference (free text)")
    print(f"  [5]  ✅  Accept report as-is  →  finish")
    print("─" * 65)

    # ── Collect user choice (loop until valid) ────────────────────────────
    preference: str = ""
    goto: str

    while True:
        choice = input("\nEnter your choice (1-5): ").strip()

        if choice in option_map:                        # AI-proposed option
            preference = option_map[choice]
            goto = "generate_report"
            print(f"\n✔  Selected: {preference}")
            break

        elif choice == "4":                             # Free text
            user_input = input("Describe your preference: ").strip()
            if not user_input:
                print("  ⚠  Cannot be empty. Try again.")
                continue
            preference = user_input
            goto = "generate_report"
            print(f"\n✔  Custom preference saved.")
            break

        elif choice == "5":                             # Accept as-is
            is_satisfy = True     # if satisfy return true
            preference = ""
            goto = END
            print("\n✔  Report accepted.")
            break

        else:
            print("  ⚠  Invalid. Please enter 1, 2, 3, 4, or 5.")

    # ── Return Command with routing + state update ────────────────────────
    return Command(
        goto=goto,
        update={"personalize_report": preference,
                "is_satisfy_personalize_report": is_satisfy
                },
    )


# ── Smoke test ────────────────────────────────────────────────────────────────

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
    }

    result = personalize(mock_state)
    print("\nCommand →", result)