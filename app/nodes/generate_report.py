from app.models import state
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from typing import Literal
from app.llm import llm
from pathlib import Path

# === Report content schemas ===
# Define pydantic schema structure compat with Jinja2 template
# (report/templates/{sales,customer,collection_payment}.html) supported all of 4 templates

# ---- Sales template (sales.html) ----
class SalesKPIs(BaseModel):
    total_revenue: str = ""
    total_orders: str = ""
    avg_order_value: str = ""
    products_sold: str = ""

class SalesMonthly(BaseModel):
    month: str
    revenue: str
    orders: str

class SalesByLine(BaseModel):
    product_line: str
    revenue: str
    qty: str

class SalesTopProduct(BaseModel):
    product_name: str
    product_line: str
    qty: str
    revenue: str

class SalesByRep(BaseModel):
    rep_name: str
    office_city: str
    revenue: str
    orders: str

class SalesReportData(BaseModel):
    report_title: str = "Sales Report"
    period: str = ""
    kpis: SalesKPIs = Field(default_factory=SalesKPIs)
    monthly: list[SalesMonthly] = Field(default_factory=list)
    by_line: list[SalesByLine] = Field(default_factory=list)
    top_products: list[SalesTopProduct] = Field(default_factory=list)
    by_rep: list[SalesByRep] = Field(default_factory=list)


# ---- Customer template (customer.html) ----
class CustomerInfo(BaseModel):
    name: str = ""
    contact: str = ""
    city: str = ""
    country: str = ""
    phone: str = ""
    credit_limit: str = ""
    sales_rep: str = ""

class CustomerKPIs (BaseModel):
    total_purchased: str = ""
    total_paid: str = ""
    balance: str = ""
    order_count: str = ""

class CustomerOrder(BaseModel):
    order_number: str
    order_date: str
    status: str
    amount: str

class CustomerPayment(BaseModel):
    check_number: str
    payment_date: str
    amount: str

class CustomerReportData(BaseModel):
    report_title: str = "Customer Report"
    period: str = ""
    customer: CustomerInfo = Field(default_factory=CustomerInfo)
    kpis: CustomerKPIs = Field(default_factory=CustomerKPIs)
    orders: list[CustomerOrder] = Field(default_factory=list)
    payments: list[CustomerPayment] = Field(default_factory=list)


# ---- Collection / payment (collection_payment.html) ----
class CollectionKPIs(BaseModel):
    total_billed: str = ""
    total_collected: str = ""
    outstanding: str = ""
    overdue_customers: str = ""

class CollectionRow(BaseModel):
    customer_name: str
    billed: str
    paid: str
    balance: str
    status: Literal["paid", "outstanding"]

class CollectionReportData(BaseModel):
    report_title: str = "Collection / Payment Report"
    as_of: str = ""
    kpis: CollectionKPIs = Field(default_factory=CollectionKPIs)
    rows: list[CollectionRow] = Field(default_factory=list)


# ---- Generic (generic.html) — fallback for ad-hoc queries ----
class KPI(BaseModel):
    label: str = Field(description="Short metric label, e.g. 'Total Offices'.")
    value: str = Field(description="Display-ready value, e.g. '7'.")

class ReportTable(BaseModel):
    title: str = Field(description="Heading for this table.")
    columns: list[str] = Field(description="Column headers, left to right.")
    rows: list[list[str]] = Field(description="Rows; each row is a list of cell strings aligned to columns.")

class ReportSection(BaseModel):
    heading: str = Field(description="Section heading.")
    body: str = Field(description="Narrative analysis, in plain prose.")

class GenericReportData(BaseModel):
    report_title: str = "Report"
    summary: str = ""
    kpis: list[KPI] = Field(default_factory=list)
    tables: list[ReportTable] = Field(default_factory=list)
    sections: list[ReportSection] = Field(default_factory=list)

# for style , css , color
class style(BaseModel):
    color:str = Field("use the css component when user need to change the color of text or whatever contain in report")

# report_type -> (schema, guidance for the prompt)
REPORT_SCHEMAS = {
    "generic": GenericReportData,
    "sales": SalesReportData,
    "customer": CustomerReportData,
    "collection_payment": CollectionReportData,
}
REPORT_GUIDANCE = {
    "generic": "Produce a GENERIC report: a title, a short summary, headline KPI cards, table(s) of the actual rows, and narrative sections.",
    "sales": "Produce a SALES report: revenue KPIs, monthly breakdown, sales by product line, top products, and sales by rep.",
    "customer": "Produce a CUSTOMER report: the customer's profile, purchase/payment KPIs, their orders, and their payments.",
    "collection_payment": "Produce a COLLECTION/PAYMENT report: billed vs collected KPIs, and per-customer outstanding balances (status must be 'paid' or 'outstanding').",
}


_GENERATE_SYSTEM_PROMPT = (
    "You are a business report writer. Turn the fetched database rows into the CONTENT of a report.\n"
    "{guidance}\n"
    "- Do NOT describe the database schema or column data types.\n"
    "- Every value must be a display-ready string. Only fill fields you have data for; leave the rest empty.\n"
    "- If a column holds the SAME value on every row (e.g. a total customer count of 98 "
    "repeated across all rows), that is an aggregate SUMMARY, not per-row data: put it ONCE "
    "in a KPI card and do NOT repeat it as a table column.\n"
    "- Honour the human's emphasis / context notes when deciding what to highlight."
)


def generateReportNode(state: state) -> dict:
    """
    Build report CONTENT from the fetched data into the pydantic schema that
    matches state['report_type'], for html_details to render into HTML.

    Reached in two situations (STYLE-only edits never reach this node — personalize
    routes those straight to html_details):
      - first pass            : no personalize feedback -> fresh content
      - content / both edits  : personalize feedback present -> refine that content

    Style is NOT handled here; html_details applies the theme_* keys on every render.
    """

    report_type = state.get("report_type") or "generic"     # default = generic; else sales / customer / collection_payment
    data = state["execute_sql"]                             # rows from execute_sql (must have)
    detail = state["detail_verify_correctness"]             # data detail from verify_correctness (must have)
    human_notes = state.get("human_notes") or ""            # optional curator context
    personalize_feedback = state.get("personalize_report") or ""  # content feedback from personalize (empty on first pass)

    # pick schema + guidance for this report type, bind structured LLM
    schema = REPORT_SCHEMAS[report_type]
    guidance = REPORT_GUIDANCE[report_type]

    llm_generate_report = llm.model_copy(update={"temperature": 0})  # temp 0 -> deterministic content
    structured_report_llm = llm_generate_report.with_structured_output(schema)

    # fill the Human message with the data + curator context
    human_content = (
        f"Data to report on:\n{data}\n\n"
        f"Data detail:\n{detail}\n\n"
        f"Human emphasis / context to include:\n{human_notes or '(none)'}"
    )

    # content-refine pass: merge from personalize of user (cases 2 and 3)
    if personalize_feedback:
        prev_report = state.get('generate_report')          # get previous report details
        if prev_report is not None:                         # prevent from crashing by unit test function 
            human_content += (
                f"\n\nCurrent report content (PRESERVE everything unless the feedback "
                f"below explicitly asks to change it):\n{prev_report.model_dump_json()}\n"      # convert form Obj to Json string bind to system prompt
                )
    human_content += f"\nUser feedback (apply ONLY this change):\n{personalize_feedback}"


    response = structured_report_llm.invoke([
        SystemMessage(content=_GENERATE_SYSTEM_PROMPT.format(guidance=guidance)),
        HumanMessage(content=human_content),
    ])

    # feedback present => this render came from a personalize pass; html_details files it separately
    return {"generate_report": response,
            "is_after_personalize": bool(personalize_feedback)}



# test standalone test function #
if __name__ == "__main__":
    # check all types of document
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
        result = generateReportNode({"report_type": report_type, **data})
        report = result["generate_report"]
        print(f"\n=== {report_type} ===")
        print("TYPE :", type(report).__name__)
        print("TITLE:", report.report_title)
        print(report)
