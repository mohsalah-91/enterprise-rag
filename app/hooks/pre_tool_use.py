"""
PreToolUse validation hook for the Enterprise RAG MCP server.

Runs before any MCP tool touches the database or an LLM: enforces input
length limits and rejects arguments that match common SQL-injection or
prompt-injection payload patterns. This is a policy/defense-in-depth layer,
not a replacement for parameterized SQL (already handled via psycopg %s
placeholders) or for prompt-level grounding instructions.
"""
import re
from dataclasses import dataclass

MAX_QUERY_LENGTH = 500

# Common SQL injection payload markers. Our SQL is already parameterized
# (psycopg %s placeholders), so this is a policy-level tripwire, not the
# primary defense against SQL injection.
_SQL_INJECTION_PATTERNS = [
    re.compile(r"(?i)\bunion\b\s+\bselect\b"),
    re.compile(r"(?i)\bdrop\s+table\b"),
    re.compile(r"(?i)\bdelete\s+from\b"),
    re.compile(r"(?i)\binsert\s+into\b"),
    re.compile(r"(?i)\bor\s+1\s*=\s*1\b"),
    re.compile(r"(?i)\bxp_cmdshell\b"),
    re.compile(r";\s*--"),
    re.compile(r"(?i)'\s*or\s*'.*'\s*=\s*'"),
]

# Common prompt injection markers aimed at overriding the system prompt
# that instructs Claude to answer strictly from retrieved context.
_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+instructions"),
    re.compile(r"(?i)disregard\s+(all\s+)?(previous|prior)\s+(instructions|prompts|rules)"),
    re.compile(r"(?i)you\s+are\s+now\s+(a|an)\b"),
    re.compile(r"(?i)reveal\s+(your|the)\s+(system\s+)?prompt"),
    re.compile(r"(?i)act\s+as\s+(if\s+you\s+are|a)\b"),
    re.compile(r"(?i)new\s+instructions\s*:"),
    re.compile(r"(?i)\bsystem\s*:\s*"),
]


@dataclass
class ValidationResult:
    is_valid: bool
    message: str


def validate_mcp_input(tool_name: str, arguments: dict) -> ValidationResult:
    """
    Validates the arguments an MCP tool is about to run with.

    Args:
        tool_name: Name of the MCP tool being invoked (for error context).
        arguments: The tool's call arguments, e.g. {"query": "...", "top_k": 3}.

    Returns:
        ValidationResult(is_valid, message) - message is "OK" on success,
        or a human-readable reason on failure.
    """
    query = arguments.get("query")

    if not isinstance(query, str) or not query.strip():
        return ValidationResult(False, f"[{tool_name}] 'query' must be a non-empty string.")

    if len(query) > MAX_QUERY_LENGTH:
        return ValidationResult(
            False,
            f"[{tool_name}] 'query' exceeds maximum length of {MAX_QUERY_LENGTH} "
            f"characters (got {len(query)})."
        )

    for pattern in _SQL_INJECTION_PATTERNS:
        if pattern.search(query):
            return ValidationResult(
                False,
                f"[{tool_name}] 'query' rejected: matched a SQL injection payload pattern."
            )

    for pattern in _PROMPT_INJECTION_PATTERNS:
        if pattern.search(query):
            return ValidationResult(
                False,
                f"[{tool_name}] 'query' rejected: matched a prompt injection payload pattern."
            )

    return ValidationResult(True, "OK")
