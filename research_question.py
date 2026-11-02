"""Answer shapes, never a subject allowlist."""
import re


def answer_style(question):
    if re.search(r'\b(tutorial|step.by.step|instructions?|recipe|how\s+(?:(?:do|can|should|would)\s+(?:i|we|you)|to\b))\b',question,re.I):
        return 'instructions'
    if re.search(r'\b(who\s+(is|was)|biograph(?:y|ical))',question,re.I):return 'person'
    if re.search(r'\b(when|dates?|released|born|died|latest|current|today)\b',question,re.I):return 'dates'
    return 'facts'
