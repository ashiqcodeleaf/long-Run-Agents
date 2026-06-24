---
name: app-mvp-builder
description: "Build a small usable app MVP with files, verification, and a concise run summary."
version: 1.0.0
platforms: [windows, linux, macos]
---

# App MVP Builder

Use this skill when the user asks LongRun to build a small app, such as a todo app, notes app, calculator, dashboard, or CLI utility.

## Workflow

1. Inspect the current workspace before writing.
2. Choose the smallest working stack already present in the repo.
3. If no app stack exists, create a plain, dependency-light implementation first.
4. Use `file_write` for creating source files.
5. Use `terminal_run` for install, test, lint, or smoke commands.
6. Persist proof: created files, command output, and how to run it.

## Output

Return:

- what was created,
- exact file paths,
- commands run,
- verification result,
- remaining limitations.

Do not only describe an app. Actually create the files when the user asks to build.

