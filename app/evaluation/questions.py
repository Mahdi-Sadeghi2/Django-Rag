from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EvalQuestion:
    question: str
    expected_page_titles: list[str]   # صفحاتی که پاسخ درست باید از آن‌ها بیاید
    note: str = ""                    # چرا این پرسش انتخاب شد


QUESTIONS: list[EvalQuestion] = [
    EvalQuestion(
        "How do I write a custom middleware?",
        ["Middleware"],
        "پرسش فنی کلاسیک؛ جواب در صفحه‌ی Middleware است",
    ),
    EvalQuestion(
        "How can I cache the output of a view?",
        ["Django’s cache framework"],
        "باید per-view cache و cache_page را پیدا کند",
    ),
    EvalQuestion(
        "What is the difference between select_related and prefetch_related?",
        ["Database access optimization", "Making queries"],
        "پرسش مقایسه‌ای — یکی از سخت‌ترین انواع پرسش برای RAG",
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
        "پرسشی که در جست‌وجوی دستی ضعیف جواب داد — می‌خواهیم ببینیم ارزیابی هم تأیید می‌کند",
    ),
    EvalQuestion(
        "How do I serve static files in development?",
        ["Managing files"],
        "static files در صفحات topics مستقیم پوشش داده نشده — بررسی رفتار سیستم روی پرسش خارج از حوزه",
    ),
]
