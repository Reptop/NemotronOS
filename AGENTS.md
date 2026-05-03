# AGENTS.md

## Read This First

Before changing behavior, read `README.md` and `docs/WORKING_STATE.md`. Treat this file as the stable repo guide and `docs/WORKING_STATE.md` as the current handoff snapshot.

## Mission

NemotronOS is a hackathon MVP for a local, private, voice-controlled PC agent. Day-to-day editing may still happen away from the target machine, but the live MVP surface is now centered on Windows demos while some desktop capabilities are still being swapped in.

## Repo Map

- `apps/agent-server/nemotronos_agent/main.py`
  - FastAPI entrypoint for task creation, approvals, event listing, and health.
- `apps/agent-server/nemotronos_agent/coordinator.py`
  - Main task orchestration and approval flow.
- `apps/agent-server/nemotronos_agent/model_client.py`
  - Mock-first and OpenAI-compatible tool planning. The current forced demo routing is Downloads organization, Notepad typing, and browser open.
- `apps/tool-server/nemotronos_tools/main.py`
  - FastAPI tool host.
- `apps/tool-server/nemotronos_tools/registry.py`
  - Actual tool registration. Use this, not just tool definitions, to understand what is callable.
- `apps/tool-server/nemotronos_tools/tools/filesystem.py`
  - The real MVP slice: dry-run file organization plan, apply flow, and undo log generation.
- `apps/tool-server/nemotronos_tools/tools/desktop_windows.py`
  - Real Windows desktop backend for allowlisted app launch, browser open, and clipboard-based text entry. `capture_screen()` is still unimplemented here.
- `apps/dashboard/src/App.jsx`
  - Main dashboard entrypoint for task submission, approval, event polling, browser microphone capture, and browser-scoped wake words.
- `apps/voice-agent/nemotronos_voice_agent/main.py`
  - Local Windows-oriented voice loop for wake-word listening, command submission, and spoken acknowledgement.
- `sandbox/fake_windows_home`
  - Fake Windows filesystem used during macOS development.

## Current Vertical Slice

There are two concrete demo paths in the repo today:

1. A user submits a task from the dashboard or `POST /tasks`.
2. The agent server creates a task and starts background processing.
3. For the Downloads organizer prompt, the model client chooses `fs_plan_changes`.
4. The tool server maps `C:\Users\Raed\Downloads` into `sandbox/fake_windows_home/Users/Raed/Downloads`.
5. `fs_plan_changes` builds a dry-run move plan grouped by file type.
6. The policy engine classifies `fs_apply_changes` as medium risk and requires approval.
7. After approval, `fs_apply_changes` applies the moves and writes an undo log under `C:\.nemotronos\undo_logs`.

Separately, under `TOOL_MODE=windows`, the current live desktop demo path is:

1. A user submits a Notepad typing or browser navigation task.
2. The agent model routes known Notepad goals through `app_launch` and known browser goals through `browser_open`.
3. For Notepad typing goals, the coordinator follows the launch with `keyboard_type`, using stored voice dictation text when present.

The Downloads flow is still the only approval-driven end-to-end slice. If you are changing behavior outside these scoped paths, verify it in code first. Do not assume the rest of the advertised surface is equally implemented.

## Rules For Agents

- Read `README.md` and `docs/WORKING_STATE.md` before making non-trivial changes.
- Verify repo facts from source code, not from stale docs or inferred architecture.
- Update `docs/WORKING_STATE.md` whenever behavior, blockers, priorities, or operating assumptions change.
- Keep docs high signal. Replace stale bullets instead of appending a running diary.
- Distinguish source from generated artifacts. `__pycache__`, `dist`, and `*.egg-info` are present in the repo and are not the source of truth.
- Prefer small, targeted edits over broad cleanup during the hackathon window unless cleanup unblocks the current MVP.

## Current Constraints

- State is in memory. Tasks, events, approvals, and stored plans do not survive restarts.
- The model layer is still demo-routed. The most reliable paths are Downloads organization, Notepad typing, and browser open; unsupported goals still fall back to a simple notification in mock mode.
- The filesystem demo uses a fake Windows root, not a real Windows machine yet.
- The tool surface is only partially real:
  - `fs_plan_changes` and `fs_apply_changes` are the most complete tools.
  - `app_launch`, `keyboard_type`, and `browser_open` have real Windows implementations in `TOOL_MODE=windows`.
  - `screen_capture`, `shell_run`, and `notify_user` exist, but they are still mock/stub behavior in `TOOL_MODE=mock_windows`.
  - Several tool definitions advertised by the agent are not registered by the tool server yet.
- The real Windows desktop backend is partially implemented, but `WindowsDesktopBackend.capture_screen()` still raises `NotImplementedError`.

## Doc Maintenance

Keep this file stable and process-oriented. Put time-sensitive status, blockers, and next actions in `docs/WORKING_STATE.md`.
