```mermaid
flowchart TD
    START([START · user_input]) --> SCHEMA{Schema Reader<br/>question relates to DB?}
    SCHEMA -->|not data-related| DONE([end])
    SCHEMA -->|data-related| T2S[text2sql]
    T2S --> EXEC[execute_sql · Postgres]
    EXEC --> VERIFY[verify_correctness · data details]
    VERIFY --> HITL{human_in_the_loop<br/>add emphasis / context / exclude rows}
    HITL -->|re-query · data doesn't match intent| T2S
    HITL -->|approve + emphasis| GEN[generate_report · LLM → report content]
    GEN --> HTMLD[html_details · render + apply theme, export .html]
    HTMLD --> PDF[generate_pdf · export .pdf]
    PDF --> PERS{personalize · review report}
    PERS -->|content only / content and style → regenerate content| GEN
    PERS -->|style only then skip generate_report → re-style| HTMLD
    PERS -->|everything satisfy| DONE
```