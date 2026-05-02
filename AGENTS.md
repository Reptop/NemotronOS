# AGENTS.md

## Read This First

Before changing behavior, read `README.md` and `docs/WORKING_STATE.md`. Treat this file as the stable repo guide and `docs/WORKING_STATE.md` as the current handoff snapshot.

## Mission

NemotronOS is a hackathon MVP for a local, private, voice-controlled PC agent. The team is building on macOS right now, but the MVP target is Windows in the next few hours, so the current code intentionally keeps the core flow platform-light while the real Windows/Desktop pieces are still being swapped in.

## Repo Map

- `apps/agent-server/nemotronos_agent/main.py`
  - FastAPI entrypoint for task creation, approvals, event listing, and health.
- `apps/agent-server/nemotronos_agent/coordinator.py`
  - Main task orchestration and approval flow.
- `apps/agent-server/nemotronos_agent/model_client.py`
  - Mock-first tool planning. In practice, the mock path mainly supports the Downloads organization demo.
- `apps/tool-server/nemotronos_tools/main.py`
  - FastAPI tool host.
- `apps/tool-server/nemotronos_tools/registry.py`
  - Actual tool registration. Use this, not just tool definitions, to understand what is callable.
- `apps/tool-server/nemotronos_tools/tools/filesystem.py`
  - The real MVP slice: dry-run file organization plan, apply flow, and undo log generation.
- `apps/dashboard/src/App.jsx`
  - Main dashboard entrypoint for task submission, approval, and event polling.
- `sandbox/fake_windows_home`
  - Fake Windows filesystem used during macOS development.

## Current Vertical Slice

The only fully-shaped demo flow today is:

1. A user submits a task from the dashboard or `POST /tasks`.
2. The agent server creates a task and starts background processing.
3. The model client chooses `fs_plan_changes` for the Downloads organization prompt.
4. The tool server maps `C:\Users\Raed\Downloads` into `sandbox/fake_windows_home/Users/Raed/Downloads`.
5. `fs_plan_changes` builds a dry-run move plan grouped by file type.
6. The policy engine classifies `fs_apply_changes` as medium risk and requires approval.
7. After approval, `fs_apply_changes` applies the moves and writes an undo log under `C:\.nemotronos\undo_logs`.

If you are changing behavior outside that path, verify it in code first. Do not assume the rest of the advertised surface is equally implemented.

## Rules For Agents

- Read `README.md` and `docs/WORKING_STATE.md` before making non-trivial changes.
- Verify repo facts from source code, not from stale docs or inferred architecture.
- Update `docs/WORKING_STATE.md` whenever behavior, blockers, priorities, or operating assumptions change.
- Keep docs high signal. Replace stale bullets instead of appending a running diary.
- Distinguish source from generated artifacts. `__pycache__`, `dist`, and `*.egg-info` are present in the repo and are not the source of truth.
- Prefer small, targeted edits over broad cleanup during the hackathon window unless cleanup unblocks the current MVP.

## Current Constraints

- State is in memory. Tasks, events, approvals, and stored plans do not survive restarts.
- The model layer is mock-first. The mock client reliably handles the Downloads organization path and falls back to a simple notification for unsupported goals.
- The filesystem demo uses a fake Windows root, not a real Windows machine yet.
- The tool surface is only partially real:
  - `fs_plan_changes` and `fs_apply_changes` are the most complete tools.
  - `screen_capture`, `shell_run`, and `notify_user` exist, but they are still mock/stub behavior in `TOOL_MODE=mock_windows`.
  - Several tool definitions advertised by the agent are not registered by the tool server yet.
- The real Windows desktop backend is scaffolded, but `WindowsDesktopBackend.capture_screen()` still raises `NotImplementedError`.

## Doc Maintenance

Keep this file stable and process-oriented. Put time-sensitive status, blockers, and next actions in `docs/WORKING_STATE.md`.
