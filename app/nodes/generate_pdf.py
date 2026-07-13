import os
from pathlib import Path
from datetime import datetime

# WeasyPrint needs Homebrew's native libs (pango/glib/cairo). On macOS + uv the
# dynamic loader can't find them unless this is set-up BEFORE weasyprint imported.
_BREW_LIB = "/opt/homebrew/lib"
if os.path.isdir(_BREW_LIB):
    os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", _BREW_LIB)

# After set-up dynamic loader able to find
from weasyprint import HTML   # noqa: E402  (must come after the env var above)
from models.states import state

# to reference path :  parents[2] = /Users/nattawat1409/Desktop/LLM-Auto-Generate-report
# PDFs mirror the HTML layout: output/pdf_output/ (+ /after_personalize for personalize passes)
PDF_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output" / "pdf_output"


def generate_pdf(state: state) -> dict:
    """
    Convert the rendered HTML (from html_details) into a PDF with WeasyPrint.
    No LLM — pure conversion. Writes the PDF to output/ and returns its path.
    """
    html_doc = state.get("html_detail")                 # full HTML string from html_details
    report_type = state.get("report_type") or "generic"

    # personalize passes go to output/pdf_output/after_personalize/, first pass to output/pdf_output/
    if state.get('is_after_personalize'):
        target_dir = PDF_OUTPUT_DIR / "after_personalize"
    else:
        target_dir = PDF_OUTPUT_DIR
    
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")        # get current Time
    pdf_path = target_dir / f"report_{report_type}_{stamp}.pdf"
    
    HTML(string=html_doc).write_pdf(str(pdf_path))

    return {"generate_pdf": str(pdf_path),
            "check_type" : type(pdf_path)}


# TEST STANDALONE: generate_report -> html_details -> generate_pdf #
if __name__ == "__main__":
    from nodes.generate_report import generateReportNode
    from nodes.html_details import html_details

    report_type = "generic"
    
    gen = generateReportNode({
        "report_type": report_type,
        "execute_sql": [('Classic Cars', 1929192, 950), ('Vintage Cars', 856245, 600),
                        ('Motorcycles', 573312, 400)],
        "detail_verify_correctness": "Revenue and quantity by product line in 2004.",
        "human_notes": "Highlight Classic Cars as the top line. and explain in details as most as possible",
    })
    rendered = html_details({"report_type": report_type, "generate_report": gen["generate_report"]})
    result = generate_pdf({"report_type": report_type, "html_detail": rendered["html_detail"]})

    print("PDF written to:", result["generate_pdf"]) # location of files   
    print("check path type :", result["check_type"]) # location of files   
    print("bytes:", os.path.getsize(result["generate_pdf"])) # get size of bytes
