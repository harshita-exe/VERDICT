# Verdict — AI Code Review Agent

A personal code-review agent: paste in a snippet or a whole project, and it
gives you an honest second opinion the way a senior developer would — before
you ship, not as a merge gatekeeper. It's built for individual programmers
reviewing their own code, not a team approval workflow.

Available two ways:
- **Web app** (`app.py`) — a browser page where you paste code and get a
  live review. Best for your presentation demo.
- **CLI** (`main.py`) — runs in the terminal against `sample_code.py`.
  Good for quick testing. Reuses the exact same agent as the web app.

## Why this counts as "Agentic AI" (for your presentation)

A plain script or chatbot takes one input and gives one output, every time,
the same way. This project has five things that define an agent:

1. **Tool use** — it calls three separate tools to gather information:
   - `run_static_checks()` — pattern-based static analysis (deterministic)
   - `retrieve_guidelines()` — **RAG (Retrieval-Augmented Generation)**:
     embeds the submitted code, embeds a small library of coding
     guidelines, and retrieves only the ones most relevant to *this*
     code, before the LLM ever sees it
   - `llm_review()` — an LLM reasoning pass, grounded in the retrieved
     guidelines rather than just the model's own memory
2. **Autonomous decision-making** — `agent_decide()` combines all tool
   outputs itself and decides the severity ranking and recommendation
   without a human choosing that in advance.
3. **Self-reflection** — `reflect_and_revise()` re-reads the draft verdict
   against the retrieved guidelines and corrects the summary if it notices
   something inconsistent or missed, before anything is shown to you. This
   is the plan → act → critique → revise loop that separates an agent from
   a single LLM call.
4. **Conditional tool use** — for a near-empty snippet, `review_code()`
   skips the RAG + LLM + reflection steps entirely and says so, instead of
   always running the same fixed pipeline regardless of input.
5. **Multi-step reasoning loop** — perceive (read code) → gather (tools,
   including retrieval) → reason (combine + rank) → reflect (self-check) →
   act (structured report).

### What RAG actually means here

RAG = *retrieve relevant information first, then generate an answer
grounded in it* — instead of trusting the LLM's training data alone. In
`tools.py`, `GUIDELINES` is a small fixed library of best-practice snippets
(hardcoded secrets, eval/exec, bare except, mutable defaults, SQL
injection, resource leaks, etc.). Each guideline is embedded once with
Gemini's embedding model (`gemini-embedding-001`); the submitted code is
embedded too, and cosine similarity picks the top 3 most relevant
guidelines for *that specific code*. Those get injected into the LLM
prompt as context. If the embeddings call fails (no network, rate limit),
it falls back to simple keyword matching so a live demo never just crashes.

This is deliberately **not** built with LangChain. With one day to build
and present this, hand-rolling the retrieval and reasoning loop directly
means every line can be explained on the spot — see the judge Q&A below.

## Setup on your laptop (VS Code)

1. Install Python from python.org/downloads (check "Add Python to PATH" on
   Windows) — you may already have it, check with `python --version`.
2. Install VS Code from code.visualstudio.com, plus its Python extension.
3. Put ALL these files/folders in one project folder:
   `app.py`, `agent.py`, `main.py`, `tools.py`, `sample_code.py`,
   `requirements.txt`, and the `templates` folder (with `index.html` inside it).
   **Important:** `templates` must stay as a folder named exactly `templates`,
   with `index.html` inside it — Flask looks for it by that exact name.
4. Open that folder in VS Code, open a terminal (Terminal > New Terminal), run:
   ```
   pip install -r requirements.txt
   ```
5. Get a FREE API key from https://aistudio.google.com (sign in with any
   Google account, click "Get API key" > "Create API key"). The same key
   is used for both the review model and the embedding model — no extra
   sign-up needed for RAG.
6. Create a file named `.env` in the project folder with one line:
   ```
   GEMINI_API_KEY=your_key_here
   ```

## Running the web app (recommended for your demo)

```
python app.py
```

Then open your browser to **http://127.0.0.1:5000** — you'll see the
Verdict web page. Paste any code into the box and click "Run Review". The
results panel shows the recommendation, the guidelines retrieved for that
specific code, and a note if the self-reflection step revised the summary
— so the RAG and reflection steps are visible, not just claimed.

## Running the CLI version

```
python main.py
```

This reviews whatever is in `sample_code.py` and prints the full report,
including retrieved guidelines and any reflection revision, to the terminal.

## Do you need to deploy this online?

No — for a presentation, running `python app.py` and showing the browser
page live on your laptop is completely normal and looks great, since
judges can see it work in real time and even hand you code to paste in.
If you want a public link later, free options are Render.com or
PythonAnywhere.com — ask if you want that set up.

## What to say if judges ask questions

- **"What makes this agentic vs just an API call?"** — It calls multiple
  tools (static checker, retrieval, LLM reasoning), the retrieval step
  changes what the LLM even sees based on the code's content, the decision
  logic runs in code based on what the tools return, and a final
  self-reflection pass checks and can revise the draft before it's shown —
  none of that path is fixed in advance.
- **"Did you use LangChain / a RAG framework?"** — No, on purpose. I built
  the retrieval and reasoning loop myself with raw embedding calls and
  cosine similarity, so I can explain exactly what every piece does. A
  framework like LangChain would be the natural next step for a
  production version once the guideline library needs to be much bigger
  (a real vector database, hundreds of guidelines).
- **"Why not just one LLM call?"** — Three reasons, layered: the static
  checker always catches known bad patterns (hardcoded secrets, eval,
  bare except) even if the LLM misses them; RAG grounds the LLM's
  reasoning in a fixed set of guidelines instead of relying purely on
  what it remembers; and the reflection pass catches cases where the
  LLM's own summary doesn't actually match the issues it found.
- **"What would you add with more time?"** — A real vector database for a
  much larger guideline library, support for more languages, a proper
  memory of past reviews on the same file so the agent notices recurring
  issues, and letting the agent ask a follow-up question when it's unsure
  of severity instead of just guessing.
- **"How does this relate to your ML background?"** — the static checker
  could be swapped for a trained classifier that predicts bug likelihood
  per line instead of hand-written rules, and the guideline library could
  be swapped for a proper vector index — both natural extensions.

## VS Code extension (demo prototype)

There's also a minimal VS Code extension in `verdict-vscode-extension/` that
lets you review your current file without leaving the editor. Right-click
in any open file → **"Verdict: Review Current File"** → it sends that
file's code to your running Flask server (`python app.py`) and shows the
results as inline squiggly underlines on the exact lines with issues, plus
a full report in VS Code's Output panel (recommendation, RAG guidelines
used, self-reflection note, everything).

It's not published to the Marketplace — you run it via VS Code's built-in
Extension Development Host (open the `verdict-vscode-extension` folder in
VS Code and press **F5**), which is the standard way to test an extension
before publishing. See `verdict-vscode-extension/README.md` for full setup
steps, including how to package it as an installable `.vsix` file if you
want that for your demo.

## File overview

- `app.py` — Flask web server, serves the web page and the review API
- `agent.py` — the agent loop (perceive/gather/decide/reflect/act), shared
  by both interfaces
- `main.py` — CLI version, reviews `sample_code.py` in the terminal by
  calling the same agent as the web app
- `templates/index.html` — the web page (paste box + live results,
  including retrieved guidelines and reflection notes)
- `tools.py` — the static analysis tool and the RAG guideline-retrieval tool
- `sample_code.py` — demo code with planted issues (for the CLI)
- `requirements.txt` — dependencies
- `verdict-vscode-extension/` — prototype VS Code extension (see above)
