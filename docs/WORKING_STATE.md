# WORKING_STATE.md

Last updated: 2026-05-02

Purpose: current operational snapshot for any teammate or AI agent joining mid-hackathon. Keep this short, current, and action-oriented.

## Current System Status

- The repo has a working macOS development slice for a Windows-first PC agent demo.
- The main demo is: organize Downloads by file type, show the plan first, require approval, then apply changes.
- The stack is split into a FastAPI agent server, a FastAPI tool server, and a React dashboard.

## What Works Now

- `POST /tasks` creates a task and starts async processing in the agent server.
- The mock model can route the Downloads-organization prompt into `fs_plan_changes`.
- The tool server can build a dry-run file organization plan against the fake Windows Downloads folder.
- The policy engine marks `fs_apply_changes` as medium risk and the dashboard exposes approval.
- Approved plans can be applied and generate an undo log.
- The dashboard can submit tasks, poll health/tasks/events, show the plan preview, and send approval.

## What Is Stubbed Or Fake

- The fake Windows filesystem under `sandbox/fake_windows_home` is the active environment, not a real Windows box.
- The mock model does not behave like a general agent yet. It mainly supports the Downloads-organization path and otherwise falls back to `notify_user`.
- `screen_capture` is mock output in `TOOL_MODE=mock_windows`.
- `shell_run` is a safe stub in `TOOL_MODE=mock_windows`; it does not execute real shell commands there.
- The real Windows desktop backend is not implemented yet. `WindowsDesktopBackend.capture_screen()` raises `NotImplementedError`.
- The agent advertises more tool definitions than the tool server currently registers. Treat `apps/tool-server/nemotronos_tools/registry.py` as the runtime truth.

## Highest-Priority Next Tasks

1. Validate the full startup flow on a real Windows machine once the team switches over.
2. Decide which tools are actually in scope for the MVP and align tool definitions with registered runtime behavior.
3. Expand beyond the single Downloads demo path only if the main Windows demo is already stable.
4. Remove or clearly quarantine generated artifacts from active source review if they start causing confusion during the hackathon.

## Windows Handoff Notes

- Current path assumptions are Windows-style at the agent/tool boundary and local sandbox paths underneath.
- The real user path for the demo is modeled as `C:\Users\Raed\Downloads`.
- `TOOL_MODE=mock_windows` is the safe current dev path.
- Switching to real Windows behavior will require replacing or extending the scaffolded desktop/tool backends, not just changing docs or prompts.
- Check Python 3.11+ and Node/Vite startup on Windows before promising demo readiness.

## Known Mismatches And Risks

- `README.md` tells developers to copy `.env.example`, but `.env.example` is not present in the repo.
- State is in memory, so restarts wipe tasks, events, approval state, and stored plans.
- The repo includes committed `__pycache__`, `dist`, and `*.egg-info` artifacts. They should not be treated as the canonical implementation.
- The broader tool list in `apps/agent-server/nemotronos_agent/tool_defs.py` can make the system look more complete than the runtime actually is.

## Update Protocol

- Replace stale bullets instead of appending status history.
- Keep next actions ordered by what the next contributor should do first.
- Record blockers only when they immediately affect the next contributor.
