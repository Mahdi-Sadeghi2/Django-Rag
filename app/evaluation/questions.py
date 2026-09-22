"""The evaluation question set: 10 real Django questions, each labeled
with the page(s) a correct answer must come from.

Labels were set from knowledge of the documentation (verified manually),
NOT from the system's own output — otherwise the evaluation would be
circular. Question 9 was chosen because it failed manual testing, and
question 10 is deliberately near-out-of-scope: together they probe the
system's honest failure modes, not just its successes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EvalQuestion:
    """One evaluation question with its ground-truth pages."""
    question: str
    expected_page_titles: list[str]   # pages a correct answer must come from
    note: str = ""                    # why this question was chosen


QUESTIONS: list[EvalQuestion] = [
    EvalQuestion(
        "How do I write a custom middleware?",
        ["Middleware"],
        "Classic technical question; the answer lives on the Middleware page",
    ),
    EvalQuestion(
        "How can I cache the output of a view?",
        ["Django’s cache framework"],
        "Should find per-view cache and cache_page",
    ),
    EvalQuestion(
        "What is the difference between select_related and prefetch_related?",
        ["Database access optimization", "Making queries"],
        "Comparative question — one of the hardest kinds for RAG",
    ),
    EvalQuestion(
        "How do database transactions work in Django?",
        ["Database transactions"],
    ),
    EvalQuestion(
        "How do I upload and handle file uploads in a form?",
        ["File Uploads", "Working with forms"],
    ),
    EvalQuestion(
        "What are Django signals and how do I connect to one?",
        ["Signals"],
    ),
    EvalQuestion(
        "How does password hashing work in Django?",
        ["Security in Django", "User authentication in Django"],
    ),
    EvalQuestion(
        "How do I write and run tests for my Django application?",
        ["Writing and running tests", "Testing in Django"],
    ),
    EvalQuestion(
        "What is get_absolute_url used for?",
        ["Models"],
        "Failed in manual testing — checking whether the evaluation confirms it",
    ),
    EvalQuestion(
        "How do I serve static files in development?",
        ["Managing files"],
        "Static files are not directly covered by the topics pages — probes "
        "behavior on a near-out-of-scope question",
    ),
]
