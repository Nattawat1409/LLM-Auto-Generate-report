from models.states import state
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from typing import Literal
from llm import llm


# === Report content schemas ===
# Each schema's fields match EXACTLY the variables its Jinja template expects
# (report/templates/{sales,customer,collection_payment}.html). Every leaf is a
# display-ready string so html_details can render it straight into the template.

# ---- Sales (sales.html) ----
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


# ---- Customer (customer.html) ----
class CustomerInfo(BaseModel):
    name: str = ""
    contact: str = ""
    city: str = ""
    country: str = ""
    phone: str = ""
    credit_limit: str = ""
    sales_rep: str = ""

class CustomerKPIs(BaseModel):
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


def generateReportNode(state: state) -> dict:
    """
    Build the report CONTENT from the fetched data, shaped for the template the
    user picked at human_in_the_loop (state['report_type']). Returns the matching
    structured object for html_details to render.
    """
    report_type = state.get("report_type") or "generic"
    data = state.get("execute_sql")                     # rows from execute_sql
    detail = state.get("detail_verify_correctness")     # data detail from verify_correctness
    human_notes = state.get("human_notes") or ""        # curator input from human_in_the_loop

    schema = REPORT_SCHEMAS[report_type]
    guidance = REPORT_GUIDANCE[report_type]
    structured_report_llm = llm.with_structured_output(schema)

    human_content = (
        f"Data to report on:\n{data}\n\n"
        f"Data detail:\n{detail}\n\n"
        f"Human emphasis / context to include:\n{human_notes or '(none)'}"
    )

    response = structured_report_llm.invoke([
        SystemMessage(content=(
            "You are a business report writer. Turn the fetched database rows into the CONTENT of a report.\n"
            f"{guidance}\n"
            "- Do NOT describe the database schema or column data types.\n"
            "- Every value must be a display-ready string. Only fill fields you have data for; leave the rest empty.\n"
            "- Honour the human's emphasis / context notes when deciding what to highlight."
        )),
        HumanMessage(content=human_content),
    ])

    return {"generate_report": response} # return pre-define format as python data (ready-to-use) in html file


# test standalone test function #
if __name__ == "__main__":
    result = generateReportNode({
        "report_type": "sales",
        "execute_sql": [('Classic Cars', 1929192, 950), ('Vintage Cars', 856245, 600),
                        ('Motorcycles', 573312, 400)],
        "detail_verify_correctness": "Revenue and quantity by product line in 2004.",
        "human_notes": "Highlight Classic Cars as the top line.",
    })
    report = result["generate_report"]
    print(report)
    print("TYPE:", type(report).__name__)
    print("TITLE:", report.report_title)
    print("KPIS:", report.kpis)
    print("BY_LINE:", report.by_line)