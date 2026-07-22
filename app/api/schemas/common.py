from enum import Enum


class SessionStatus(str, Enum):
    AWAITING_REVIEW = "awaiting_review"            # paused at human_in_the_loop
    AWAITING_PERSONALIZE = "awaiting_personalize"  # paused at personalize
    REJECTED = "rejected"                          # schema gate: question not data-related -> END
    DONE = "done"                                  # personalize accepted -> END
