"""
Agent core logic, shared by both the CLI (main.py) and the web app (app.py).

The agent loop, per review:
  1. PERCEIVE   -- read the submitted code.
  2. GATHER     -- call tools: run_static_checks() (deterministic rules) and
                   retrieve_guidelines() (RAG: pull relevant best-practice
                   snippets for this specific code), then llm_review() (LLM
                   reasoning grounded in what was retrieved).
  3. DECIDE     -- agent_decide() combines everything into a verdict.
  4. REFLECT    -- reflect_and_revise() re-checks the draft verdict against
                   the retrieved guidelines and corrects it if needed, before
                   anything is shown to the user.

This is a personal code-review assistant for individual programmers working
on their own code or projects -- it does not gate merges or make team
decisions, it just gives you an honest second opinion before you ship.
"""

import os
import json
from dotenv import load_dotenv
from google import genai
from tools import run_static_checks, retrieve_guidelines

load_dotenv()

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
MODEL = "gemini-3.6-flash"


def llm_review(code: str, static_findings: list, guidelines: list) -> dict:
    """
    Tool #3: LLM reasoning pass, grounded with retrieved guidelines (RAG).
    The guidelines list comes from tools.retrieve_guidelines() and is
    injected directly into the prompt as context the model should check
    the code against, on top of its own general reasoning.
    """
    prompt = f"""You are a senior software engineer giving a fellow developer
feedback on their own code, before they ship it.

Here is the code to review:
```
{code}
```

Automated static-analysis findings already collected:
{json.dumps(static_findings, indent=2)}

Relevant coding guidelines retrieved for this code (check the code against
these specifically, in addition to your own judgment):
{json.dumps(guidelines, indent=2)}

Analyze the code for:
- Logic bugs
- Security issues
- Performance issues
- Design/readability issues

Respond ONLY with valid JSON in this exact format, no other text:
{{
  "issues": [
    {{"type": "bug|security|performance|style", "severity": "low|medium|high|critical",
      "line_hint": "short description of where", "explanation": "1-2 sentence explanation",
      "suggestion": "1-2 sentence fix suggestion"}}
  ],
  "overall_quality": "poor|fair|good|excellent",
  "summary": "2-3 sentence overall summary"
}}
"""
    response = client.models.generate_content(model=MODEL, contents=prompt)
    text = response.text.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


def agent_decide(static_findings: list, llm_findings: dict) -> dict:
    """
    The agent's decision layer: combines both tool outputs, ranks issues by
    severity, and decides a final recommendation. No hardcoded single path --
    the decision depends on what the tools actually found.
    """
    all_issues = []

    for finding in static_findings:
        all_issues.append({
            "source": "static_checker",
            "type": finding.get("type", "style"),
            "severity": finding.get("severity", "low"),
            "detail": finding.get("message", ""),
        })

    for issue in llm_findings.get("issues", []):
        all_issues.append({
            "source": "llm_review",
            "type": issue.get("type"),
            "severity": issue.get("severity"),
            "detail": f"{issue.get('line_hint', '')}: {issue.get('explanation', '')} "
                      f"Suggestion: {issue.get('suggestion', '')}",
        })

    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    all_issues.sort(key=lambda x: severity_rank.get(x["severity"], 0), reverse=True)

    has_critical = any(i["severity"] == "critical" for i in all_issues)
    has_high = any(i["severity"] == "high" for i in all_issues)

    if has_critical:
        recommendation = "NEEDS REWORK"
        recommendation_detail = "Critical issue found -- fix this before moving on"
    elif has_high:
        recommendation = "NEEDS ATTENTION"
        recommendation_detail = "High severity issues found"
    elif all_issues:
        recommendation = "LOOKS GOOD WITH NOTES"
        recommendation_detail = "Minor issues found"
    else:
        recommendation = "LOOKS GOOD"
        recommendation_detail = "No significant issues found"

    return {
        "recommendation": recommendation,
        "recommendation_detail": recommendation_detail,
        "total_issues": len(all_issues),
        "issues_by_severity": all_issues,
        "overall_quality": llm_findings.get("overall_quality", "unknown"),
        "summary": llm_findings.get("summary", ""),
    }


def reflect_and_revise(code: str, draft_verdict: dict, guidelines: list) -> dict:
    """
    Self-reflection pass: the agent re-reads its own draft verdict against the
    retrieved guidelines and either confirms it or corrects the summary if it
    notices something inconsistent or missed. This is the "critique your own
    output before acting" pattern -- plan -> act -> reflect -> revise -- and
    it's what turns a one-shot LLM call into a small reasoning loop.
    """
    prompt = f"""You are checking a DRAFT code review for accuracy before it
is shown to the developer.

Draft review (JSON):
{json.dumps(draft_verdict, indent=2)}

Guidelines this review should be consistent with:
{json.dumps(guidelines, indent=2)}

Code that was reviewed:
```
{code}
```

Does the draft summary match the issues actually listed? Does it miss or
contradict any of the guidelines above? If it's accurate, return the summary
unchanged. If not, return a corrected summary.

Respond ONLY with valid JSON:
{{"summary": "confirmed or revised 2-3 sentence summary", "revised": true|false,
  "revision_note": "empty string if not revised, else one sentence on what changed"}}
"""
    try:
        response = client.models.generate_content(model=MODEL, contents=prompt)
        text = response.text.strip().replace("```json", "").replace("```", "").strip()
        reflection = json.loads(text)
        draft_verdict["summary"] = reflection.get("summary", draft_verdict["summary"])
        draft_verdict["was_revised"] = bool(reflection.get("revised", False))
        draft_verdict["reflection_note"] = reflection.get("revision_note", "")
    except Exception:
        draft_verdict["was_revised"] = False
        draft_verdict["reflection_note"] = ""
    return draft_verdict


def review_code(code: str) -> dict:
    """The main agent loop: perceive -> gather (tools) -> decide -> reflect -> act."""
    static_findings = run_static_checks(code)

    # Conditional tool use: there's nothing meaningful to reason about for a
    # near-empty snippet, so skip the (slower, costlier) RAG + LLM + reflection
    # steps entirely rather than always running the full pipeline regardless
    # of input. The path taken depends on the evidence gathered so far.
    if len([ln for ln in code.strip().splitlines() if ln.strip()]) < 2:
        return {
            "recommendation": "NOT ENOUGH CODE",
            "recommendation_detail": "Paste a fuller snippet for a meaningful review",
            "total_issues": len(static_findings),
            "issues_by_severity": [
                {"source": "static_checker", "type": f.get("type", "style"),
                 "severity": f.get("severity", "low"), "detail": f.get("message", "")}
                for f in static_findings
            ],
            "overall_quality": "unknown",
            "summary": "Too little code was submitted to run a full review.",
            "guidelines_used": [],
            "was_revised": False,
            "reflection_note": "",
        }

    guidelines = retrieve_guidelines(code)
    llm_findings = llm_review(code, static_findings, guidelines)
    verdict = agent_decide(static_findings, llm_findings)
    verdict = reflect_and_revise(code, verdict, guidelines)
    verdict["guidelines_used"] = guidelines
    return verdict


def review_project(files: list) -> dict:
    """
    Batch version of the agent for multiple files at once. 'files' is a list
    of {"filename": str, "content": str}. Runs the full agent loop per file,
    then aggregates into one project-level verdict -- this is the part a
    plain chatbot can't do for you: no one has to paste each file in one at
    a time.
    """
    file_results = []
    for f in files:
        try:
            verdict = review_code(f["content"])
            verdict["filename"] = f["filename"]
            verdict["error"] = None
        except Exception as e:
            verdict = {
                "filename": f["filename"],
                "error": str(e),
                "recommendation": "ERROR",
                "recommendation_detail": "Could not review this file",
                "total_issues": 0,
                "issues_by_severity": [],
                "overall_quality": "unknown",
                "summary": "",
                "guidelines_used": [],
                "was_revised": False,
                "reflection_note": "",
            }
        file_results.append(verdict)

    # Project-level aggregation: the agent looks across ALL files and
    # decides the overall project verdict on its own.
    total_issues = sum(f["total_issues"] for f in file_results)
    has_any_critical = any(
        any(i["severity"] == "critical" for i in f["issues_by_severity"])
        for f in file_results
    )
    has_any_high = any(
        any(i["severity"] == "high" for i in f["issues_by_severity"])
        for f in file_results
    )

    if has_any_critical:
        project_recommendation = "NEEDS REWORK"
        project_detail = "At least one file has a critical issue"
    elif has_any_high:
        project_recommendation = "NEEDS ATTENTION"
        project_detail = "High severity issues found in the project"
    elif total_issues > 0:
        project_recommendation = "LOOKS GOOD WITH NOTES"
        project_detail = "Minor issues found across the project"
    else:
        project_recommendation = "LOOKS GOOD"
        project_detail = "No significant issues found in any file"

    return {
        "project_recommendation": project_recommendation,
        "project_detail": project_detail,
        "total_files": len(file_results),
        "total_issues": total_issues,
        "files": file_results,
    }
