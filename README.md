# Multimodal Telegram Expense Tracker Bot

An intelligent, self-hosted personal finance assistant for Telegram built with Python. The bot supports multimodal ingestion (voice notes, receipt images, natural text), dynamic category management, agentic deletion, and automated monthly budget threshold monitoring using SQLite and SQLAlchemy.

---

## Features

- **Multimodal Ingestion**:
  - **Voice Notes**: Transcribed via Groq Whisper API (`whisper-large-v3`).
  - **Receipts & Invoices**: Vision-based OCR and extraction powered by NVIDIA NIM vision models.
  - **Natural Language Text**: Understands casual inputs like *"Spent 45 on coffee"* or *"Paid 1200 for electricity bill yesterday"*.
- **Interactive Confirmations**: Inline Telegram buttons to confirm, modify, or cancel detected expense items before saving.
- **Budgeting & Monitoring**:
  - Set category-specific and overall monthly spending limits.
  - Automated threshold alerts when approaching or exceeding limits.
- **Agentic Actions & Deletion**: Natural conversational commands to query, modify, or delete past logged transactions.
- **Persistent Storage**: Local or cloud-mounted SQLite database managed via SQLAlchemy ORM.
- **Access Control**: Restricted strictly to authorized Telegram User IDs for personal data privacy.

---

## Tech Stack

- **Language**: Python 3.11+
- **Bot Framework**: `python-telegram-bot` (v21+, asynchronous)
- **Database & ORM**: SQLite, SQLAlchemy
- **AI / LLM Microservices**:
  - Groq API (Whisper Audio Transcription & Fast Text Ingestion)
  - NVIDIA NIM (Multimodal Vision OCR)
- **Configuration & Validation**: `pydantic-settings`, `python-dotenv`

---

## Project Structure

```text
├── src/
│   └── expense_bot/
│       ├── bot/
│       │   ├── handlers.py          # Telegram command and message handlers
│       │   └── keyboards.py         # Inline keyboards and UI callbacks
│       ├── db/
│       │   ├── base.py              # DeclarativeBase and metadata
│       │   └── session.py           # Engine creation and sessionmaker
│       ├── models/
│       │   ├── base.py              # Base model class
│       │   ├── expense.py           # Expense transactions table
│       │   ├── category.py          # Dynamic categories table
│       │   └── budget.py            # Monthly budget thresholds table
│       ├── repositories/
│       │   └── expense_repo.py      # CRUD, aggregation, and threshold queries
│       ├── services/
│       │   ├── groq_service.py      # Audio transcription and natural language parsing
│       │   └── nvidia_service.py    # Receipt image vision analysis
│       └── main.py                  # Bot bootstrap and polling runner
├── run.py                           # Root entry point with auto-migration
├── requirements.txt                 # Pinned dependencies
├── .env.example                     # Environment template
└── README.md
