from models.states import state
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from datetime import datetime

# templates live in app/report/templates (this file is app/nodes/Html_details.py)
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "report" / "templates" # get location of 4 template 
_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))


def html_details(state: state) -> dict:
    """
    Deterministically render the structured report content from generate_report
    into HTML using the Jinja template the user picked (state['report_type']).
    No LLM here — generate_report already produced the data; this is templating.
    """
    report_type = state.get("report_type") or "generic"
    report_data = state.get("generate_report")   # pydantic model from generate_report

    # pydantic model -> plain dict so Jinja can access fields as template vars
    context = report_data.model_dump()
    context.setdefault("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M"))

    template = _env.get_template(f"{report_type}.html")     # call jinja2 template
    html = template.render(**context)

    return {"html_detail": html}  # return html document as answer 


# test standalone: build content with generate_report, then render it #
if __name__ == "__main__":
    from nodes.generate_report import generateReportNode

    gen = generateReportNode({
        "report_type": "sales",
        "execute_sql": [('Classic Cars', 1929192, 950), ('Vintage Cars', 856245, 600),
                        ('Motorcycles', 573312, 400)],
        "detail_verify_correctness": "Revenue and quantity by product line in 2004.",
        "human_notes": "Highlight Classic Cars as the top line.",
    })

    result = html_details({
        "report_type": "sales",
        "generate_report": gen["generate_report"],
    })
    print(result["html_detail"])
