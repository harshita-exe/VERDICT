"""
Tools available to the agent.

Tool #1: run_static_checks()   -- pattern-based static analysis (unchanged)
Tool #2: retrieve_guidelines() -- Retrieval-Augmented Generation (RAG).

Why RAG here: instead of trusting the LLM to remember every best practice
from training, we keep a small local library of coding guidelines, embed
the submitted code, and pull back only the guidelines that are semantically
closest to *this specific code*. Those retrieved snippets are then injected
into the LLM's prompt in agent.py as grounding context. That's the RAG
pattern: retrieve relevant knowledge first, then generate an answer that's
conditioned on it -- the review isn't relying purely on the model's memory.
"""

import os
import math
import re
from dotenv import load_dotenv
from google import genai

load_dotenv()

_embed_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
EMBED_MODEL = "gemini-embedding-001"


def run_static_checks(code: str) -> list:
    findings = []
    lines = code.split("\n")

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Bare except clause (bad practice - hides errors)
        if re.match(r"^except\s*:", stripped):
            findings.append({
                "type": "bug",
                "severity": "high",
                "message": f"Line {i}: Bare 'except:' clause hides all errors. "
                           f"Catch specific exceptions instead."
            })

        # Use of eval() - security risk
        if "eval(" in stripped:
            findings.append({
                "type": "security",
                "severity": "critical",
                "message": f"Line {i}: Use of eval() can execute arbitrary code. "
                           f"Avoid it or sanitize input strictly."
            })

        # Hardcoded password/secret
        if re.search(r"(password|secret|api_key)\s*=\s*['\"]", stripped, re.IGNORECASE):
            findings.append({
                "type": "security",
                "severity": "critical",
                "message": f"Line {i}: Hardcoded credential detected. "
                           f"Use environment variables instead."
            })

        # Mutable default argument
        if re.search(r"def\s+\w+\(.*=\s*(\[\]|\{\})", stripped):
            findings.append({
                "type": "bug",
                "severity": "medium",
                "message": f"Line {i}: Mutable default argument can cause "
                           f"unexpected shared state between calls."
            })

        # Line too long
        if len(line) > 100:
            findings.append({
                "type": "style",
                "severity": "low",
                "message": f"Line {i}: Line exceeds 100 characters."
            })

        # TODO comments left in code
        if "TODO" in stripped or "FIXME" in stripped:
            findings.append({
                "type": "style",
                "severity": "low",
                "message": f"Line {i}: Unresolved TODO/FIXME comment."
            })

    return findings


# ---------------------------------------------------------------------------
# RAG knowledge base: a small, fixed library of coding guidelines.
# In a bigger project this would live in a vector database; for a one-day
# build, an in-memory list plus real embeddings is genuine RAG at a scale
# that's easy to explain and impossible to break during a demo.
# ---------------------------------------------------------------------------
GUIDELINES = [
    {"id": "secrets", "text": "Never hardcode passwords, API keys, or secrets "
     "in source code; load them from environment variables or a secret manager."},
    {"id": "eval", "text": "Avoid eval() and exec() on untrusted input; they "
     "allow arbitrary code execution and are a major security risk."},
    {"id": "bare_except", "text": "Avoid bare 'except:' clauses; catch specific "
     "exception types so real errors are not silently swallowed."},
    {"id": "mutable_default", "text": "Avoid mutable default arguments like "
     "lists or dicts in function signatures; they are shared across calls "
     "and cause hard-to-find bugs."},
    {"id": "sql_injection", "text": "Never build SQL queries with string "
     "formatting or concatenation of user input; use parameterized queries "
     "to prevent SQL injection."},
    {"id": "resource_leak", "text": "Always close files, sockets, and database "
     "connections, ideally using a 'with' statement, to avoid resource leaks."},
    {"id": "input_validation", "text": "Validate and sanitize all external "
     "input (user input, API responses, file contents) before using it."},
    {"id": "naming", "text": "Use clear, descriptive variable and function "
     "names; avoid single-letter names outside of short loop counters."},
    {"id": "complexity", "text": "Keep functions small and focused on one "
     "responsibility; break up long functions with deep nesting into "
     "smaller helper functions."},
    {"id": "error_handling", "text": "Handle expected failure cases explicitly "
     "(missing keys, network errors, bad input) instead of letting the "
     "program crash unhandled."},
]

_guideline_embeddings_cache = None


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _embed(text: str):
    response = _embed_client.models.embed_content(model=EMBED_MODEL, contents=text)
    return response.embeddings[0].values


def _get_guideline_embeddings():
    """Embed the guideline library once and cache it for the process lifetime."""
    global _guideline_embeddings_cache
    if _guideline_embeddings_cache is None:
        cache = []
        for g in GUIDELINES:
            try:
                cache.append(_embed(g["text"]))
            except Exception:
                cache.append(None)
        _guideline_embeddings_cache = cache
    return _guideline_embeddings_cache


# Simple keyword fallback so the demo still works even if the embeddings
# call fails (no network, rate limit, etc.) -- graceful degradation instead
# of a crash in front of judges.
_KEYWORD_MAP = {
    "secrets": ["password", "secret", "api_key", "token"],
    "eval": ["eval(", "exec("],
    "bare_except": ["except:"],
    "mutable_default": ["def ", "=[]", "={}"],
    "sql_injection": ["select ", "insert ", "cursor.execute"],
    "resource_leak": ["open(", ".close("],
    "input_validation": ["input(", "request."],
}


def retrieve_guidelines(code: str, top_k: int = 3) -> list:
    """
    Tool #2: RAG retrieval step. Embeds the submitted code and the guideline
    library, then returns the guidelines most semantically similar to this
    specific code. Falls back to keyword overlap if embeddings aren't
    available, so a bad connection doesn't take down the whole demo.
    """
    try:
        code_vec = _embed(code)
        guideline_vecs = _get_guideline_embeddings()
        scored = [
            (_cosine(code_vec, vec), g)
            for g, vec in zip(GUIDELINES, guideline_vecs)
            if vec is not None
        ]
        if not scored:
            raise RuntimeError("no guideline embeddings available")
        scored.sort(key=lambda x: x[0], reverse=True)
        return [g["text"] for _, g in scored[:top_k]]
    except Exception:
        code_lower = code.lower()
        scored = []
        for g in GUIDELINES:
            score = sum(1 for kw in _KEYWORD_MAP.get(g["id"], []) if kw in code_lower)
            scored.append((score, g))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [g["text"] for _, g in scored[:top_k]]
