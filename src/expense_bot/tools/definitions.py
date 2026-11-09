"""
Standard OpenAI-compatible tool definitions compatible with both Groq and NVIDIA NIM.
"""

ROUTER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "log_expense",
            "description": (
                "Call this ONLY when the user explicitly spent money or committed an expense. "
                "Resolve relative dates (e.g., 'yesterday', 'last friday') into exact YYYY-MM-DD. "
                "Never call this for jokes, pranks, hypothetical questions, or casual banter."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expenses": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "amount": {
                                    "type": "number",
                                    "description": "Positive spent amount in INR",
                                },
                                "category": {
                                    "type": "string",
                                    "description": "Category name chosen from existing list or created if new",
                                },
                                "is_new_category": {
                                    "type": "boolean",
                                    "description": "True if proposed category is absent from existing list",
                                },
                                "merchant": {
                                    "type": ["string", "null"],
                                    "description": "Store, platform, or vendor name",
                                },
                                "spent_on": {
                                    "type": "string",
                                    "description": "Date formatted as YYYY-MM-DD",
                                },
                                "note": {
                                    "type": ["string", "null"],
                                    "description": "Specific items or additional details",
                                },
                            },
                            "required": ["amount", "category", "spent_on"],
                        },
                    }
                },
                "required": ["expenses"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_analytics",
            "description": (
                "Call this when the user asks for historical spending, summaries, totals, or stats. "
                "Compute exact start_date and end_date (YYYY-MM-DD) based on today's reference date."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "Inclusive start date (YYYY-MM-DD)",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Inclusive end date (YYYY-MM-DD)",
                    },
                    "category_name": {
                        "type": ["string", "null"],
                        "description": "Optional category name if filtering by a single category",
                    },
                    "period_label": {
                        "type": "string",
                        "description": "Human-friendly period name, e.g., 'Jan 2026', 'Last Week'",
                    },
                },
                "required": ["start_date", "end_date", "period_label"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_or_undo_expense",
            "description": "Delete the most recently logged expense or an expense matching specific criteria (date, amount, merchant).",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "enum": ["last", "specific"],
                        "description": "'last' to undo recent entry, 'specific' if criteria provided"
                    },
                    "amount": {"type": ["number", "null"]},
                    "merchant": {"type": ["string", "null"]},
                    "spent_on": {"type": ["string", "null"], "description": "YYYY-MM-DD"}
                },
                "required": ["target"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "plan_deletion",
            "description": (
                "Call this whenever the user wants to delete, undo, or clear any expenses. "
                "The system will show the user a preview of matching records for confirmation before deleting."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql_where_clause": {
                        "type": "string",
                        "description": (
                            "SQL condition filtering table 'e'. Use column names: e.spent_on (YYYY-MM-DD), "
                            "e.amount, e.merchant, e.note, c.name (category name). "
                            "Examples: \"e.spent_on BETWEEN '2026-01-01' AND '2026-01-31'\", "
                            "\"e.id = (SELECT id FROM expenses WHERE user_id = :user_id ORDER BY id DESC LIMIT 1)\", "
                            "or \"1=1\" to clear everything."
                        ),
                    },
                    "explanation": {
                        "type": "string",
                        "description": "Short explanation of the deletion scope, e.g., 'all expenses from January 2026'.",
                    },
                },
                "required": ["sql_where_clause", "explanation"],
            },
        },
    }
]