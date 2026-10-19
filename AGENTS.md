# Repository Guidelines

## Project Structure & Module Organization

- `app/` — FastAPI service: `main.py` (app, `/` and `/health`), `router.py` (ingest/search/answer endpoints), `database.py` (connection pool and startup migrations), `config.py` (settings loaded from environment), `ingest.py` (chunking).
- `mcp_server.py` — MCP server exposing the RAG pipeline as tools; exercised by CI in `.github/workflows/rag-ci.yml`.
- `migrations/` — SQL files applied in order on startup.
- `tests/` — unit tests, mirroring the module paths they cover.
- `scripts/` — corpus ingestion and CI seeding; `eval/` — golden set and `run_eval.py`.
- `corpus/` — local source documents (git-ignored).
- `infra/` — Azure infrastructure as Bicep.

Configuration examples belong in `.env.example`; never commit generated indexes or local downloads.

## Build, Test, and Development Commands

Typical local workflow:

- `python -m venv venv` creates an isolated Python environment (git-ignored).
- `venv\Scripts\Activate.ps1` activates it in PowerShell.
- `pip install -r requirements.txt` installs dependencies.
- `docker compose up -d` starts local Postgres with `pgvector` (requires `POSTGRES_PASSWORD` in `.env`).
- `uvicorn app.main:app --reload` runs the API at `http://127.0.0.1:8000`.
- `python -m unittest discover -s tests -v` runs the test suite; use `python -m unittest tests.test_health -v` while iterating.
- `docker build -t enterprise-rag-mcp .` builds the deployable MCP image.

Document any new required service, environment variable, or startup command in the README and `.env.example`. The container serves MCP over Streamable HTTP on `MCP_HOST=0.0.0.0` and `MCP_SERVER_PORT=8765`; the local MCP server defaults to `127.0.0.1:8765`.

## Coding Style & Naming Conventions

No formatter or linter is configured; match the surrounding code. Use four spaces for Python indentation, `snake_case` for functions, variables, and modules, and `PascalCase` for classes. Prefer explicit types at public interfaces and concise docstrings for modules or functions with non-obvious RAG, retrieval, or persistence behavior. Name tests after the behavior they verify, for example `test_retriever_returns_ranked_results`.

## Testing Guidelines

Tests use the standard-library `unittest` with `httpx.ASGITransport` for HTTP endpoints. Add or update tests for every behavior change. Keep fixtures small and deterministic; mock external model, vector-store, and network calls so unit tests run without credentials. Test failures, empty retrieval results, and malformed input alongside successful paths. Run the relevant tests before opening a pull request.

## Commit & Pull Request Guidelines

Write short, imperative commit subjects that describe one change, such as `Add document chunk validation`. Keep commits focused. Pull requests should explain the user-facing or operational effect, link the related issue when available, list verification performed, and identify configuration or migration changes. Include screenshots or example API output when an interface or response format changes.

## Security & Configuration

Never commit API keys, tokens, private documents, generated embeddings, or `.env` files. Load secrets from environment variables and provide sanitized example values only.

Never run `az` or `kubectl` against live Azure. Infrastructure lives in `infra/` as Bicep. Run the test suite before proposing changes.
