# Repository Guidelines

## Project Structure & Module Organization

Keep application code in `src/` and organize it by feature or service rather than by technical layer alone. Place automated tests in `tests/`, mirroring the package paths they cover. Keep sample documents, evaluation fixtures, and other non-code inputs in a clearly named `data/` or `assets/` directory; do not mix generated indexes or local downloads into source control. Configuration examples belong in versioned templates such as `.env.example`.

## Build, Test, and Development Commands

Use the commands declared by the repository’s project configuration as the source of truth. Typical local workflow:

- `python -m venv .venv` creates an isolated Python environment.
- `.venv\\Scripts\\Activate.ps1` activates it in PowerShell.
- `pip install -r requirements.txt` installs runtime and development dependencies when that file is present.
- `pytest` runs the test suite; use `pytest tests/path_to_test.py -q` while iterating.

Document any new required service, environment variable, or startup command in the README and `.env.example`.

## Coding Style & Naming Conventions

Follow the existing formatter and linter configuration instead of introducing a competing style. Use four spaces for Python indentation, `snake_case` for functions, variables, and modules, and `PascalCase` for classes. Prefer explicit types at public interfaces and concise docstrings for modules or functions with non-obvious RAG, retrieval, or persistence behavior. Name tests after the behavior they verify, for example `test_retriever_returns_ranked_results`.

## Testing Guidelines

Add or update tests for every behavior change. Keep fixtures small and deterministic; mock external model, vector-store, and network calls so unit tests run without credentials. Test failures, empty retrieval results, and malformed input alongside successful paths. Run the relevant tests before opening a pull request.

## Commit & Pull Request Guidelines

Write short, imperative commit subjects that describe one change, such as `Add document chunk validation`. Keep commits focused. Pull requests should explain the user-facing or operational effect, link the related issue when available, list verification performed, and identify configuration or migration changes. Include screenshots or example API output when an interface or response format changes.

## Security & Configuration

Never commit API keys, tokens, private documents, generated embeddings, or `.env` files. Load secrets from environment variables and provide sanitized example values only.

Never run az or kubectl against live Azure. Never commit secrets. Infrastructure lives in infra/ as Bicep Run the test suite before proposing changes
