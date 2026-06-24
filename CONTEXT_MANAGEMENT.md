# LongRun Context Management

LongRun follows MyAgent's cache-first rule: the system prompt is built once per session and reused byte-for-byte across normal turns.

## Turn Flow

1. Load active session.
2. Build turn context.
3. Reuse cached system prompt if present.
4. If no prompt snapshot exists, build one from base rules, project instructions, tool map, memory, and environment hints.
5. Estimate tokens before the model call.
6. Compress only when needed.
7. Preserve system prompt, recent tail, latest user request, latest assistant response, and valid tool call/result pairs.

Skills are inserted as user-turn context. They do not mutate the cached system prompt mid-session.

