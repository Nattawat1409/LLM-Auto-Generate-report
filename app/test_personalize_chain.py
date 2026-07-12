"""
Chain test: generate_report -> html_details -> personalize -> (maybe) regenerate.

Runs the 3 nodes back-to-back with real data flowing between them (not isolated
mocks), so you can see the actual before/after HTML files before wiring the
whole LangGraph. Run interactively:

    cd app
    uv run -m test_personalize_chain
"""
from langgraph.graph import END

from nodes.generate_report import generateReportNode
from nodes.html_details import html_details
from nodes.generate_pdf import generate_pdf
from nodes.personalize import personalize

# one case is enough to exercise the full loop; collection_payment gives the
# LLM the most interesting content to propose personalisation options on.
QUERY_STATE = {
    "report_type": "generic",
    "execute_sql": [
        ("Euro+ Shopping Channel", 227600, 200000, 27600),
        ("Mini Gifts Distributors", 210000, 210000, 0),
        ("Australian Collectors", 180000, 120000, 60000),
    ],
    "detail_verify_correctness": "Billed vs collected and outstanding balance per customer.",
    "human_notes": "Flag customers with large outstanding balances. and explain the relation in details as most as possible according to this data ",
}


def run():
    # ── Round 1: generate + render ────────────────────────────────────────
    print("\n=== Round 1: generate_report ===")
    gen1 = generateReportNode(QUERY_STATE)

    print("=== Round 1: html_details ===")
    html1 = html_details({**QUERY_STATE, **gen1}) # state['html_details]
    print("Saved:", html1["html_path"])
    # state carried forward — must keep execute_sql/detail/report_type so a
    # possible regenerate has the raw data again, not just the rendered HTML

    print("=== Round 3: generate PDF document ===")
    state = {**QUERY_STATE, **gen1, **html1} # state['html_path]
    try_generate_pdf = generate_pdf(state)

    # test generateReport -> html_details -> generate_pdf
    result = try_generate_pdf
    # print(f"Here is the result after generate pdf files : \n{result}")

    # test generateReport -> html_details -> generate_pdf -> personalize
    # personalize is a graph node: it RETURNS a Command, so read its outputs via
    # cmd.update[...], not cmd[...] (a Command is not subscriptable).
    latest_html = html1
    cmd = personalize({"html_detail": latest_html["html_detail"], "html_path": latest_html["html_path"]})

    # Regenerate loop: while the user is NOT satisfied (picked option 1-4),
    # feed their preference back into generate_report (the node that APPLIES it),
    # re-render, then ask personalize again — mirrors the graph's
    #   personalize -> generate_report -> html_details -> personalize  cycle.
    while cmd.update["is_satisfy_personalize_report"] is False:
        preference = cmd.update["personalize_report"]
        print(f"\n=== Regenerating report with user preference ===\n{preference}\n")

        # generate_report reads personalize_report + is_satisfy_personalize_report
        # to switch on its is_redo path and fold the preference into the prompt.
        regen_state = {
            **QUERY_STATE,
            "personalize_report": preference,
            "is_satisfy_personalize_report": False,
        }
        gen_n = generateReportNode(regen_state)                  # apply preference
        latest_html = html_details({**regen_state, **gen_n})     # re-render HTML
        print("Regenerated:", latest_html["html_path"])
        generate_pdf({**regen_state, **gen_n, **latest_html})    # keep the chain complete

        cmd = personalize({"html_detail": latest_html["html_detail"],
                           "html_path": latest_html["html_path"]})

    print(f"\nFinal personalize command:\n{cmd}")

if __name__ == "__main__":
    run()
