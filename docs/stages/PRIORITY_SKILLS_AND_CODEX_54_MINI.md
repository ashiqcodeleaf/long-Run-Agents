# Priority Slice - Skills Import And Codex 5.4 Mini Auth

This slice was done before continuing the normal Stage 8 work because the user
asked to import/copy MyAgent skills and wire Codex 5.4 Mini auth first.

## Implemented Files

- `skills/`
- `longrun_agent/tools/skills.py`
- `longrun_agent/auth.py`
- `longrun_agent/agent/transports/codex.py`
- `longrun_agent/agent/model_metadata.py`
- `longrun_agent/agent/context.py`
- `longrun_agent/agent/runtime.py`
- `longrun_agent/cli/main.py`
- `longrun_agent/cli/commands.py`
- `longrun_agent/config.py`

## Skills Imported

The source directory:

```text
C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\skills
```

was copied into:

```text
C:\Users\asiqi\OneDrive\Desktop\Dbot\Dbot Agentic Flow\myagent\longrun-agent-mvp\skills
```

Copy result:

```text
CopiedFiles=486
SkillFiles=73
```

## Skill Commands Added

List bundled or home skills:

```powershell
longrun skills list --source bundled
longrun skills list --source home
longrun skills list --source all
```

Read one full `SKILL.md`:

```powershell
longrun skills view codex --source bundled
```

Import bundled skills into the user's LongRun home:

```powershell
longrun skills import-bundled
```

## Codex 5.4 Mini Auth Added

LongRun now supports importing existing Codex CLI auth from:

```text
~/.codex/auth.json
```

Command:

```powershell
longrun auth import-codex-cli
```

Behavior:

- reads `tokens.access_token` and `tokens.refresh_token`.
- rejects missing or expired access tokens.
- stores credentials in LongRun's `auth.json`.
- sets provider to `openai-codex`.
- sets model to `gpt-5.4-mini`.

## Codex Transport Added

`CodexResponsesTransport.complete()` now performs a no-tool Responses request
through the OpenAI SDK against:

```text
https://chatgpt.com/backend-api/codex
```

For the no-tool MVP path it:

- converts system messages into `instructions`.
- converts user/assistant messages into Responses input items.
- sends `store=False`.
- extracts `response.output_text` or message output text.

## Context Window

LongRun now recognizes:

```text
gpt-5.4-mini
```

Provider-aware context behavior:

- direct OpenAI API fallback: `400000`.
- `openai-codex` fallback: `272000`.

## Verification Evidence

Syntax:

```powershell
python -m compileall longrun_agent
```

Observed result:

```text
compileall completed without syntax errors
```

Bundled skills:

```powershell
uv run longrun skills list --source bundled
```

Observed:

```text
SKILLS_LIST_EXIT=0
73
```

Skill view:

```powershell
uv run longrun skills view codex --source bundled
```

Observed:

```text
SKILL_VIEW_EXIT=0
# codex
description: "Delegate coding to OpenAI Codex CLI (features, PRs)."
# Codex CLI
```

Import bundled skills into temporary LongRun home:

```powershell
uv run longrun skills import-bundled
```

Observed:

```text
"copied": 18
HomeSkillFiles=73
```

Import Codex CLI auth:

```powershell
uv run longrun auth import-codex-cli
uv run longrun auth status
uv run longrun model show
```

Observed:

```text
Provider: openai-codex
Model: gpt-5.4-mini
openai-codex: configured source=auth.json detail=expires_at=2026-06-25T05:13:27+00:00
Provider: openai-codex
Model: gpt-5.4-mini
```

Codex transport was verified with a fake OpenAI client so no quota/network was
spent:

```text
codex fake reply
True
gpt-5.4-mini
system rules
user
False
```

Meaning:

- fake response returned through `CodexResponsesTransport`.
- token was read from LongRun auth.
- model was `gpt-5.4-mini`.
- system prompt became Responses `instructions`.
- input item role was `user`.
- `store` was `False`.

## Next Step

Continue normal Stage 8 work:

- memory.
- session search.
- plugin loader.
- hook lifecycle.
- MCP scaffold.

