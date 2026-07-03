from typing_extensions import TypedDict

class state(TypedDict):
    # text to SQL 
    user_input: str
    output_text2SQL: str
    # Exceute SQL node
    execute_sql: str
    # Verify correctness + detail nodes
    is_correct_verify_correctness: bool # Verify correctness node as True or false
    detail_verify_correctness: str # erify correctness node as details
    # Human in the loop node
    human_in_the_loop: str
    # Generate report node
    generate_report: str
    html_detail: str
    generate_pdf: str
    personalize_report: str
    # Define return route
    is_satisfy_personalize_report: bool # send to re-generate report if format not satisfy user input
    is_data_satisfied: bool # send to retry user input 

    