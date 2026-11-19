"""What the simulated users say: a researcher's first questions to the orchestrator, and the
salutation `example.hello` takes for direct runs. Varied so that no cache answers every turn."""

from __future__ import annotations

from typing import Any

PROMPTS = (
    "I have survey data from 400 participants. Where should I deposit it?",
    "Can you check my data management plan for gaps?",
    "What metadata do I need to describe a set of CSV files?",
    "Do I need ethics approval to share interview transcripts?",
    "Which licence should I choose for my dataset?",
    "How do I make my data more FAIR?",
    "What documentation should accompany my code and data?",
    "My files include personal data. What should I do before sharing them?",
)

SALUTATION: dict[str, Any] = {
    "schema_class": "Salutation",
    "greeted_name": "load test",
    "language": "en",
}
