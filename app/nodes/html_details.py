import base64
from models import state
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from datetime import datetime

# templates live in app/report/templates (this file is app/nodes/html_details.py)
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "report" / "templates" # get location of 4 template
_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

# Embed the SCG logo as a base64 data URI so the HTML is self-contained: relative
# img paths break both in WeasyPrint (no base_url) and in the saved .html (lives in
# output/). Encoded once at import time.
_LOGO_PATH = Path(__file__).resolve().parent.parent / "report" / "images" / "Scg.png"
_LOGO_DATA_URI = (
    "data:image/png;base64," + base64.b64encode(_LOGO_PATH.read_bytes()).decode()
    if _LOGO_PATH.exists() else ""
)

# refer path 
# personalize node traverses this folder to reference the user's previous reports (few-shot).
HTML_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output" / "html_output"

TEST2 = Path(__file__).resolve().parents[2] 

def html_details(state: state) -> dict:
    """
    Deterministically render the structured report content from generate_report
    into HTML using the Jinja template the user picked (state['report_type']).
    No LLM here — generate_report already produced the data; this is templating.
    """
    
    report_type = state["report_type"]              # get report type
    report_data = state["generate_report"]          # generate_report details from pervious node 
    
    # pydantic model -> dict can access by Jinja for making template
    context = report_data.model_dump()

    # Inject all editable theme key into context 
    for key in ("theme_text_color", "theme_header_color","theme_footer_color", "theme_font_size"):
        context[key] = state.get(key)

    context.setdefault("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M"))
    context["logo_data_uri"] = _LOGO_DATA_URI   # self-contained SCG logo for the template

    template = _env.get_template(f"{report_type}.html")     # call jinja2 template
    html = template.render(**context)

    if state.get("is_after_personalize"): # if is_after_personalize = True 
        target_dir = HTML_OUTPUT_DIR / "after_personalize"  
    else:
        target_dir = HTML_OUTPUT_DIR # if is_after_personalize = False 

    target_dir.mkdir(parents=True, exist_ok=True)   # create parent folder if it doesn't exist yet

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")      # show current date time
    html_path = target_dir / f"report_{report_type}_{stamp}.html"
    html_path.write_text(html, encoding="utf-8")          # support thai text

    return {"html_detail": html,          # return html document as answer
            "html_path": str(html_path)}  # show the file path


# test standalone: build content with generate_report, then render it #
if __name__ == "__main__":
    from nodes.generate_report import generateReportNode    # generate_report node

    # TEST ALL OF 4 TEMPLATES FORMAT #
    CASES = {
        "generic": {
            "execute_sql": [('San Francisco', 'USA', 6), ('Boston', 'USA', 2),
                            ('Paris', 'France', 5), ('Tokyo', 'Japan', 2)],
            "detail_verify_correctness": "Employee headcount by office city/country.",
            "human_notes": "Highlight that San Francisco is the largest office.",
        },
        "sales": {
            "execute_sql": [('Classic Cars', 1929192, 950), ('Vintage Cars', 856245, 600),
                            ('Motorcycles', 573312, 400)],
            "detail_verify_correctness": "Revenue and quantity by product line in 2004.",
            "human_notes": "Highlight Classic Cars as the top line.",
        },
        "customer": {
            "execute_sql": {
                "customer": ('Euro+ Shopping Channel', 'Diego Freyre', 'Madrid', 'Spain',
                             '(91) 555 94 44', 227600),
                "orders": [('10222', '2004-09-01', 'Shipped', 52151),
                           ('10329', '2004-11-15', 'Shipped', 60483)],
                "payments": [('AB661578', '2004-09-05', 52151),
                             ('CN511354', '2004-11-20', 60483)],
            },
            "detail_verify_correctness": "Profile, orders and payments for Euro+ Shopping Channel.",
            "human_notes": "Note they are the highest-volume customer.",
        },
        "collection_payment": {
            "execute_sql": [('Euro+ Shopping Channel', 227600, 200000, 27600),
                            ('Mini Gifts Distributors', 210000, 210000, 0),
                            ('Australian Collectors', 180000, 120000, 60000)],
            "detail_verify_correctness": "Billed vs collected and outstanding balance per customer.",
            "human_notes": "Flag customers with large outstanding balances.",
        },
    }

    for report_type, data in CASES.items():
        gen = generateReportNode({"report_type": report_type, **data})
        result = html_details({"report_type": report_type,
                               "generate_report": gen["generate_report"]})
        print(f"\n=== {report_type} ===")
        print("HTML saved to:", result["html_path"])