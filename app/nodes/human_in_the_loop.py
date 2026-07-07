from typing import Literal
from langgraph.types import Command
from models.states import state

# the report templates the user can pick (report/templates/{name}.html)
# "generic" fallback for ad-hoc queries + 3 fixed formats
VALID_TEMPLATES = ("generic", "sales", "customer", "collection_payment")

    # define next node depend on user satisfication
def human_in_the_loop(state: state) -> Command[Literal["generate_report", "text2sql"]]:
    """
    HITL: user reviews fetched data, then either
      - approve + pick template + add emphasis/context notes  -> generate_report
      - requery + explain what was wrong                      -> text2sql
    """
    # show to user and let user review
    print(f"\n--- Detail ---\n{state.get('detail_verify_correctness')}")
    print(f"\n--- Data ---\n{state.get('execute_sql')}")

    # ถาม action ก่อน
    decision = input("\nApprove or Requery? [approve/requery]: ").strip().lower()

    if decision == "approve": # if user Approve
        # pick which of the 3 templates to render this report as
        report_type = input(f"Pick report template {VALID_TEMPLATES}: ").strip().lower()
        if report_type not in VALID_TEMPLATES:
            report_type = "generic"  # fallback default if user typed something invalid
        # ask human_notes if need by without any feedback
        notes = input("Emphasis / context to include in report (Enter to skip): ").strip()
        return Command(
            goto="generate_report", # return to next node #
            update={
                "hitl_action": "approve",
                "report_type": report_type, # which template generate_report / html_details will use
                "human_notes": notes, # add more additional details and context of SQL data let LLM know
            },
        )

    # decision == "requery" — ask for requery_feedback 
    feedback = input("What was wrong? Describe how to re-query: ").strip()
    return Command(
        goto="text2sql", # return to frist node #
        update={
            "hitl_action": "requery",
            "requery_feedback": feedback, # get feedback to refine actual user needed
        },
    )


if __name__ == "__main__":
    # result = human_in_the_loop({
    #     "execute_sql": [('Classic Cars', 1929192), ('Vintage Cars', 856245),('Motorcycles', 573312), ('Trucks and Buses', 549822),
    #                     ('Planes', 508881), ('Ships', 335113), ('Trains', 72802)],
    #     "detail_verify_correctness": """Total revenue by product line in 2004. 7 product lines returned.
    #                                 Top: Classic Cars ($1,929,192). Bottom: Trains ($72,802).""",
    # })
    # print("\nReturned:", result)

    resul2 = human_in_the_loop({
        "execute_sql": [(103, 'Atelier graphique', 'FR'), (112, 'Signal Gift Stores', 'US'),
                        (114, 'Australian Collectors, Co.', 'AU'), (119, 'La Rochelle Gifts', 'FR'),
                        (121, 'Baane Mini Imports', 'NO')],
        "detail_verify_correctness": """First 5 customer orders in 2004 by order number.""",
    })
    print("\nReturned:", resul2)
    print(f"check type {type(resul2)}")
    print(f"goto: {resul2.goto}")
    print(f"report type : {resul2.update['report_type']}")
    # print(f"action: {resul2.update['hitl_action']}")
    # print(f"notes: {resul2.update['human_notes']}")

