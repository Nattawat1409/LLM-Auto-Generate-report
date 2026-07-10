from typing_extensions import TypedDict, Literal
from typing import Optional

ReportType = Literal["generic", "sales", "customer", "collection_payment"] # generic fallback + 3 fixed
HITLAction = Literal["approve", "requery"]                                 # 2 actions depend on user satisfication
PersonalizeAction = Literal["accept", "regenerate_report"]                 # 2 options


class state(TypedDict):
    # Start node
    user_input: str

    # Schema node
    is_question_relate: bool

    # text to SQL 
    output_text2SQL: str

    # Exceute SQL node
    execute_sql: str
    execute_error: Optional[str]   # None on success, error string if the query failed
    sql_retry_count: int           # auto-retry counter when text2sql produces invalid SQL

    # Verify correctness + detail nodes
    is_correct_verify_correctness: bool # Verify correctness node as True or false
    detail_verify_correctness: str # erify correctness node as details

    # === Human-in-the-loop (curator/annotator) ===
    hitl_action: HITLAction        # "approve" or "requery"
    report_type: ReportType        # which of the 3 templates the user picked
    human_notes: str               # free-text: emphasis + context + exclude write by user
    requery_feedback: str          # ถ้ากด requery button

    # generate report node (python data)
    generate_report: str
    is_after_personalize: bool  # True if this report was regenerated from personalize feedback

    # html_details node (convert .py -> .html)
    html_detail: str          # rendered HTML string
    html_path: str            # show file path under output/html_output/ (for personalize few-shot)

    # Generate_pdf node (PDF)
    generate_pdf: str
    personalize_report: str

    # Define return route
    document_pdf: str 
    is_satisfy_personalize_report: bool # send to re-generate report if format not satisfy user input
    is_data_satisfied: bool # send to retry user input 

    