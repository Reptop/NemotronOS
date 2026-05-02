# NemotronOS

NemotronOS is a hackathon MVP for a local, private, voice-controlled PC agent inspired by Jarvis. This repo is set up so we can build and demo the platform-independent core on macOS now, then move the same project to a Windows RTX 4090 machine later and swap in NVIDIA NIM plus real Windows desktop tooling.

## Current MVP

- `apps/agent-server`: FastAPI runtime for tasks, events, policy checks, approvals, and tool dispatch.
- `apps/tool-server`: FastAPI tool host with a mock Windows sandbox, safe path mapping, stored filesystem plans, apply flow, undo logs, and a few stub tools.
- `apps/dashboard`: React + Vite dashboard for submitting tasks, watching task state, reviewing plans, approving medium-risk actions, and inspecting the event timeline.
- `sandbox/fake_windows_home`: fake Windows filesystem rooted at `C:\`.

## Demo flow

The first vertical slice is built around this prompt:

`Organize my Downloads folder into folders by file type, but show me the plan first.`

Expected flow:

1. Submit the task in the dashboard or through `POST /tasks`.
2. The agent creates a task, asks the mock model for the next action, and calls `fs_plan_changes`.
3. The tool server scans `C:\Users\Raed\Downloads` inside the sandbox.
4. The policy engine marks `fs_apply_changes` as medium risk.
5. The dashboard shows the move plan and an approval button.
6. Approving the task triggers `fs_apply_changes`, creates an undo log, and completes the task.

## Sandbox mapping

- Windows path: `C:\Users\Raed\Downloads`
- Local sandbox path: `sandbox/fake_windows_home/Users/Raed/Downloads`

Only absolute `C:\...` or `C:/...` paths are accepted. Path traversal and sandbox escapes are rejected.

## Run locally

### 1. Create a virtual environment and install Python apps

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e apps/tool-server -e apps/agent-server
```

### 2. Copy the environment file

```bash
cp .env.example .env
```

### 3. Start the tool server

```bash
uvicorn nemotronos_tools.main:app --app-dir apps/tool-server --reload --port 5050 --env-file .env
```

### 4. Start the agent server

```bash
uvicorn nemotronos_agent.main:app --app-dir apps/agent-server --reload --port 5051 --env-file .env
```

### 5. Start the dashboard

```bash
cd apps/dashboard
npm install
npm run dev
```

The dashboard defaults to `http://localhost:5173` and polls the agent server at `http://localhost:5051`.

## API endpoints

### Agent server

- `POST /tasks`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `POST /tasks/{task_id}/approve`
- `GET /events`
- `GET /health`

### Tool server

- `POST /tool`
- `GET /health`

## Notes

- Stores are in memory for this MVP, but the layout is intentionally modular so we can replace them with SQLite or Postgres later.
- `MODEL_MODE=openai_compatible` is scaffolded for an OpenAI-compatible endpoint such as local NVIDIA NIM.
- `TOOL_MODE=mock_windows` keeps platform behavior behind interfaces so we avoid macOS-only dependencies while developing away from the Windows machine.
