# Prism

**Prism turns opaque AI-agent work into an Execution Story.**

Agents can plan, research, call tools, write code, and fail in seconds. Their work is usually reduced to a long transcript or a final answer. Prism makes that work inspectable: see the execution graph, replay it in time, open any step, and understand why a decision was made.

Built for the OpenAI Build Week **Developer Tools** track.

> Prism is a local-first trust layer for AI agents: it turns an opaque agent run into an inspectable decision, lets a reviewer challenge its evidence, and blocks unsafe action when the proof collapses.

## The demo story

An operations agent investigates a sharp EU checkout-conversion drop. Prism shows how it:

1. Validates that the problem is a checkout-completion failure, not traffic loss.
2. Correlates the first affected minute with an EU pricing release.
3. Finds and reproduces `VAT_COUNTRY_MISMATCH`.
4. Explains the root cause: the client sends `UK` rather than ISO alpha-2 `GB`.
5. Recommends a narrow rollback and a safe permanent fix.

This is a curated run, not a fake chat UI: it is persisted in SQLite and served through the same trace API Prism will use for imported agent runs.

## Features

- **Execution Story** — React Flow graph showing how the work unfolded.
- **Timeline replay** — step through a recorded run at the agent’s pace.
- **Deep inspector** — prompt, input, output, tools, latency, tokens, and model for every step.
- **Decision intelligence** — evidence-backed explanations of key decisions and root causes.
- **Decision Proofs** — a causal chain from a recommendation to source events, rejected alternatives, and a verification level.
- **Prism Challenge + Action Gates** — dispute an evidence link, see verification degrade, and persist an approve/reject decision with its review context.
- **Branch re-runs + trace diff** — re-run a task with one changed assumption and compare observable status, outcomes, and tool activity against its baseline.
- **Local-first** — SQLite plus local JSON traces; no account, cloud service, or vector database.
- **Export** — download a self-contained execution-story JSON report.

## Architecture

```text
Curated trace / future agent adapter
              ↓
       FastAPI trace service
       ├─ SQLite: runs, events, analyses
       └─ JSON: portable source traces
              ↓
         Next.js workspace
       graph · timeline · replay · inspector
```

## Run locally

Requirements: Python 3.11+ and Node.js 20+ with pnpm.

Supported platform: macOS and Linux desktop environments. Prism runs entirely on localhost; it requires no login, cloud deployment, or external database.

```bash
# API
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

If you installed an earlier Prism version, refresh the OpenAI dependencies before running an OpenAI agent:

```bash
.venv/bin/python -m pip install --upgrade -r requirements.txt
```

In another terminal:

```bash
# Frontend
pnpm install
pnpm dev
```

Open `http://localhost:3000`. The API documentation is available at `http://127.0.0.1:8000/docs`.

The backend seeds `sample_runs/checkout-conversion-drop.json` into `backend/data/prism.db` at startup.

### Judge path: no API key required

After starting the API and frontend, open `http://localhost:3000`. The launcher includes two reproducible, key-free execution stories:

- **Verified checkout investigation** — inspect a reproduced root cause, its Decision Proof, and a safe remediation.
- **Weak-evidence action** — see Prism refuse to approve an operational action supported by only one alert.

These stories are persisted through the same FastAPI and SQLite trace path as live runs. No provider account or API key is required to evaluate the core product workflow.

### Run a real autonomous agent

With `OPENAI_API_KEY` exported and backend requirements installed, Prism can run a real OpenAI Agents SDK research agent. The agent can autonomously use web search, complete the task, and return a normal Prism execution trace.

```bash
curl -X POST http://127.0.0.1:8000/api/agent-runs \
  -H 'Content-Type: application/json' \
  -d '{"task":"Research the main risks of adopting a new payments provider and summarize the evidence.","tools":["web_search"]}'
```

The response contains a `poll_url`; request it until the run status changes from `running` to `completed` or `failed`.

### Challenge and branch a decision

The landing page includes two key-free curated stories: a reproduced checkout failure and a weak-evidence action that Prism blocks. In any completed run, use **Branch re-run** in the inspector to state one changed assumption. Prism starts a new agent execution, records a `prism.branch.v1` provenance artifact, and opens it against its baseline with a deterministic trace diff.

### Import another agent workflow

`POST /api/traces/import` accepts either a validated Prism trace (`adapter: "prism.v1"`) or a generic ordered event list (`adapter: "generic.events.v1"`). The original JSON is retained as an immutable raw artifact alongside normalized events.

### Verify the core trace services

```bash
cd backend
.venv/bin/python -m unittest discover -s tests -v
```

The suite covers trace persistence, generic import normalization, proof compilation, evidence challenge gates, weak-evidence blocking, approval snapshots, pending agent lifecycle, and trace comparison. `pnpm build` provides the frontend type and production-build verification.

For the complete local verification pass:

```bash
cd backend
.venv/bin/python -m unittest discover -s tests -v

cd ../frontend
pnpm build
```

### Optional live GPT-5.6 explanations

Prism is fully usable without a key. It uses a deterministic, evidence-only local explanation so the curated demo is reliable.

To enable live GPT-5.6 generation, export a key before starting the API:

```bash
export OPENAI_API_KEY="your_key"
export OPENAI_MODEL="gpt-5.6-terra"
```

When present, Prism uses the Responses API to generate a concise structured explanation, then caches it in SQLite. Keys are never sent to the browser or stored in the database.

## Decision Proofs

For major decisions, Prism compiles a proof rather than merely restating the agent's answer. A proof contains:

- an explicit claim;
- evidence links that navigate to the original metric, release, log, or reproduction step;
- alternatives ruled out by the trace; and
- a verification level: **signal**, **correlated**, or **reproduced**.

This is the product's core trust primitive: reviewers can audit *why* an agent acted, not just what it did.

## Project structure

```text
frontend/       Next.js visual workspace
backend/        FastAPI, SQLite models, trace and analysis services
shared/         Trace contracts
sample_runs/    Curated demo execution
```

## Built with Codex and GPT-5.6

Codex was used throughout Prism’s Build Week implementation: product architecture, the provider-neutral trace contract, FastAPI/SQLite boundaries, React Flow interaction model, visual system, automated tests, and runtime QA.

Prism’s live OpenAI agent path uses the OpenAI Agents SDK with the configured `gpt-5.6-terra` model and web search. It records the resulting plan, tool actions, reasoning, and final answer as a normalized execution story. GPT-5.6 is also available for concise, evidence-grounded decision and failure explanations through the Responses API; deterministic evidence-only explanations keep the no-key demo reproducible.

The Build Week submission includes the Codex `/feedback` session ID for the project thread and a narrated live run in the demonstration video.

The submission video demonstrates the curated proof workflow, a live OpenAI run, and a branch comparison.

## License

[MIT](LICENSE)
