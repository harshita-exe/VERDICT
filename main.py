"""
AI Code Review Agent -- CLI
----------------------------
Reviews the code in sample_code.py and prints a report to the terminal.
This just calls the shared agent in agent.py -- the exact same loop the
web app (app.py) uses, so there's only one place the agent logic lives.
"""

from agent import review_code


def print_report(verdict: dict):
    print("\n" + "=" * 50)
    print("AI CODE REVIEW REPORT")
    print("=" * 50)
    print(f"Recommendation: {verdict['recommendation']}")
    print(f"  ({verdict.get('recommendation_detail', '')})")
    print(f"Overall Quality: {verdict['overall_quality']}")
    print(f"Total Issues Found: {verdict['total_issues']}")
    print(f"\nSummary: {verdict['summary']}")

    guidelines = verdict.get("guidelines_used") or []
    if guidelines:
        print("\nGuidelines checked against (retrieved via RAG):")
        for g in guidelines:
            print(f"  - {g}")

    if verdict.get("was_revised"):
        print(f"\n[Self-reflection revised the summary: {verdict.get('reflection_note', '')}]")

    print("\n" + "-" * 50)
    for i, issue in enumerate(verdict["issues_by_severity"], 1):
        print(f"{i}. [{issue['severity'].upper()}] ({issue['type']}) via {issue['source']}")
        print(f"   {issue['detail']}\n")


if __name__ == "__main__":
    with open("sample_code.py", "r") as f:
        code_to_review = f.read()

    print("Step 1: Running static checks...")
    print("Step 2: Retrieving relevant guidelines (RAG)...")
    print("Step 3: Running LLM reasoning review...")
    print("Step 4: Agent deciding a draft verdict...")
    print("Step 5: Reflecting on the draft against the guidelines...")

    result = review_code(code_to_review)
    print_report(result)
