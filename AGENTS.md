# Codex Instructions

This repository uses `.ai/` as the main source of truth for AI-assisted development.

Before making non-trivial changes:

1. Read `.ai/project-context.md`.
2. Read `.ai/commands.md`.
3. Pick the relevant workflow from `.ai/workflows/`.
4. Use the relevant role from `.ai/agents/`.
5. Inspect existing code before editing.
6. Keep changes small and reviewable.
7. Run relevant validation commands and report any command that could not be run.

Default role for complex work: `.ai/agents/tech-lead.md`.

Core rules:

- Distinguish repository facts from assumptions.
- Do not fabricate files, APIs, dependencies, or behavior.
- Prefer existing project patterns.
- Avoid unrelated refactoring.
- Never silently change public behavior.
- Add or update tests for important behavior changes.
- Never expose secrets or copy credentials into AI files.
- Record important decisions in `.ai/memory/decisions.md`.
- Record recurring issues in `.ai/memory/known-issues.md`.
- Record non-urgent cleanup in `.ai/memory/technical-debt.md`.

