# NemotronOS

NemotronOS is a hackathon MVP for a local, private, voice-controlled PC agent inspired by Jarvis. This repo is set up so we can build and demo the platform-independent core on macOS now, then move the same project to a Windows RTX 4090 machine later and swap in NVIDIA NIM plus real Windows desktop tooling.

## Current MVP

- `apps/agent-server`: FastAPI runtime for tasks, events, policy checks, approvals, and tool dispatch.
- `apps/tool-server`: FastAPI tool host with a mock Windows sandbox, safe path mapping, stored filesystem plans, apply flow, undo logs, and a few stub tools.
- `apps/dashboard`: React + Vite dashboard for submitting tasks, watching task state, reviewing plans, approving medium-risk actions, and inspecting the event timeline.
- `apps/voice-agent`: local voice loop for wake word detection, command submission, and spoken acknowledgement.
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

### One-command launcher

If your `.env` is already in place, you can bootstrap and start the local stack from one terminal:

```bash
python3 scripts/run_local_stack.py
```

The launcher creates `.venv` if needed, installs the editable Python apps, runs `npm install` for the dashboard when `apps/dashboard/node_modules` is missing, then starts the tool server, agent server, and dashboard together. Stop it with `Ctrl+C`.

The script respects `.env` plus any shell overrides, so you can switch model providers inline, for example:

```bash
MODEL_MODE=openai_compatible MODEL_PROVIDER=ollama python3 scripts/run_local_stack.py
```

If you want the agent server and dashboard in WSL but the real Windows desktop tool server in an interactive PowerShell window, use two scripts:

```bash
python3 scripts/run_windows_tool_server.py
python3 scripts/run_wsl_agent_dashboard.py
```

The Windows launcher opens the tool server in a separate PowerShell window. The WSL launcher starts the agent server and dashboard in the current terminal. The Windows launcher assumes the tool-server environment lives at `.venv-win\Scripts\python.exe` under the same repo on the Windows side. Override that with `WINDOWS_TOOL_PYTHON` if needed.

### Manual startup

### 1. Create a virtual environment and install Python apps

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e apps/tool-server -e apps/agent-server -e apps/voice-agent
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

### Model providers

The agent server keeps the existing OpenAI-compatible/NIM path and now also supports a local Ollama path. Keep `MODEL_MODE=openai_compatible` when you want real model planning, then select the provider with `MODEL_PROVIDER`.

NIM example:

```bash
MODEL_MODE=openai_compatible
MODEL_PROVIDER=nim
MODEL_BASE_URL=http://127.0.0.1:8000/v1
MODEL_NAME=nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1
MODEL_API_KEY=local-dev-key
```

Ollama example:

```bash
MODEL_MODE=openai_compatible
MODEL_PROVIDER=ollama
MODEL_BASE_URL=http://localhost:11434
MODEL_NAME=nemotron-3-nano:4b
MODEL_API_KEY=ollama
```

For the Ollama path, pull the model once and make sure the local Ollama server is running:

```bash
ollama pull nemotron-3-nano:4b
ollama serve
```

NemotronOS calls Ollama through its OpenAI-compatible `v1/chat/completions` endpoint behind that base URL.

### Voice commands

The dashboard can record a short browser microphone clip and send it to the agent server through `POST /voice/tasks`. The agent server transcribes the audio with OpenAI's `/v1/audio/transcriptions` endpoint, then creates a normal NemotronOS task from the transcript.

Set these values in `.env` to enable the temporary development speech-to-text path:

```bash
OPENAI_API_KEY=<your-openai-api-key>
OPENAI_BASE_URL=https://api.openai.com/v1
TRANSCRIPTION_MODEL=whisper-1
```

The browser never receives the OpenAI API key. This is temporary scaffolding; the long-term privacy goal is still local speech-to-text.

### Local voice agent

`apps/voice-agent` is the first Windows-oriented voice loop outside the browser. It listens for wake words, submits commands to the agent server, and speaks a short acknowledgement through Windows SAPI.

Run the MVP loop:

```bash
nemotronos-voice-agent
```

Useful modes:

- `VOICE_AGENT_WAKE_MODE=whisper_poll`: recommended current demo mode. It waits for speech, records until a short silence, and asks the agent server to detect `Jarvis` or `Computer` through `POST /voice/wake-detect`.
- `VOICE_AGENT_WAKE_MODE=openwakeword`: optional local wake mode. It listens locally with openWakeWord, then only sends the post-wake command audio for transcription. The current installed local model is `hey_jarvis`, so use Whisper-poll mode if you want `Computer`.
- `nemotronos-voice-agent --mode manual`: no microphone; type commands into the console for quick testing.
- `nemotronos-voice-agent --test-tts "Testing the NemotronOS voice."`: speak once through the configured TTS backend and exit. This is the quickest way to diagnose OpenAI TTS without starting the wake loop.
- `VOICE_AGENT_INPUT_DEVICE`: optional sounddevice index or name when Windows picks the wrong microphone.
- `VOICE_AGENT_OPENWAKEWORD_MODELS`: semicolon-separated openWakeWord model names or model paths. The default is `hey_jarvis`.
- `VOICE_AGENT_OPENWAKEWORD_THRESHOLD` and `VOICE_AGENT_OPENWAKEWORD_FRAME_MS`: tune local wake sensitivity and streaming frame size.
- `VOICE_AGENT_WAKE_SILENCE_SECONDS`, `VOICE_AGENT_WAKE_CHUNK_SECONDS`, `VOICE_AGENT_COMMAND_SILENCE_SECONDS`, and `VOICE_AGENT_COMMAND_CHUNK_SECONDS`: tune the faster wake capture separately from the longer command capture.
- `VOICE_AGENT_SPEECH_THRESHOLD` and `VOICE_AGENT_LISTEN_BLOCK_MS`: tune speech detection sensitivity and how quickly silence is noticed.
- `VOICE_AGENT_SUBMITTED_ACK`: quick neutral acknowledgement after a command is accepted locally. Keep it neutral because the task may still fail or be unsupported.
- `VOICE_AGENT_ACCESSIBILITY_ACK`: quick acknowledgement for screen-reading or "what did you do" commands. The current demo value is `Let me take a look.`
- `VOICE_AGENT_LISTENING_ACK`: optional prompt after a wake-only utterance. The current demo value is `uh huh`; the voice agent waits for this short acknowledgement to finish before recording the command.
- `VOICE_AGENT_OUTCOME_WAIT_SECONDS`: short foreground wait after command submission before the agent returns to listening.
- `VOICE_AGENT_FINAL_OUTCOME_WAIT_SECONDS`: longer background wait for delayed spoken results such as accessibility narration.
- `VOICE_AGENT_TTS_MODE`: `windows_sapi` for the built-in offline Windows voices, or `openai` for the more natural temporary dev voice path.
- `VOICE_AGENT_TTS_VOICE`: for `windows_sapi`, use an installed SAPI voice such as `Microsoft Zira Desktop`; for `openai`, use a TTS voice such as `marin`, `cedar`, `coral`, `sage`, or `nova`.
- `VOICE_AGENT_TTS_MODEL`: default `gpt-4o-mini-tts` for the OpenAI TTS mode.
- `VOICE_AGENT_TTS_RESPONSE_FORMAT`: default `mp3`; this is the most reliable Windows playback path for the current demo.
- `VOICE_AGENT_TTS_INSTRUCTIONS`: optional style prompt for OpenAI TTS, for example `Speak like a calm, warm PC accessibility assistant.`
- `VOICE_AGENT_TTS_SPEED`: optional speech speed; default `1.0`.
- If the wake word is heard without a command, the voice agent immediately treats the next utterance as the command.

Example:

`Computer, open notepad and type in hello from the local voice agent`

This is still a scaffold. The current recommended demo path is the refined Whisper-poll loop because it supports both `Jarvis` and `Computer`. It gives a short wake acknowledgement, gives a quick neutral acknowledgement after command submission, uses a more specific "Let me take a look" acknowledgement for accessibility narration, and speaks again for unsupported, failed, approval-gated, spoken-result, or safely narrated completed actions. Speech output is serialized so the quick acknowledgement and final narration do not overlap. If a task is still running after the short foreground wait, the voice agent keeps a background watcher alive so delayed accessibility responses such as "explain the active window" are still spoken when the task completes. The next privacy step is local NVIDIA Speech NIM/Riva ASR and TTS when those services are available, plus either a custom openWakeWord model or another local detector for "Computer."

For a more human-sounding demo voice, keep the existing temporary OpenAI dev key in `.env` and set:

```bash
VOICE_AGENT_TTS_MODE=openai
VOICE_AGENT_TTS_MODEL=gpt-4o-mini-tts
VOICE_AGENT_TTS_VOICE=marin
VOICE_AGENT_TTS_RESPONSE_FORMAT=mp3
VOICE_AGENT_TTS_INSTRUCTIONS=Speak like a calm, warm PC accessibility assistant. Use natural pacing and clear pronunciation.
```

This is not the final private voice architecture; it is temporary demo scaffolding like the current Whisper transcription path. The app should disclose that the voice is AI-generated when used with real users.

### Real Windows desktop tool mode

For the first real desktop-control slice, set `TOOL_MODE=windows` and run the tool server from an interactive Windows terminal. The tool server currently allowlists `notepad`, `calculator`/`calc`, `paint`/`mspaint`, and `discord` for `app_launch`, supports `keyboard_type` through clipboard paste, supports opening a fresh VS Code window and inserting generated code through `vscode_paste_code`, supports Discord message sending to the currently active conversation, supports Gmail draft creation through `email_create_draft`, supports `browser_open` through the default Windows browser, supports accessibility screen narration through `accessibility_describe_screen`, supports Canvas course opening and Canvas assignment lookup through configured aliases or an optional Canvas API token, supports local todo note creation through `sticky_note_create`, and has screenshot-first mouse clicking for YouTube video selection with a ratio-click fallback.

First manual test prompt:

`Open Notepad and type "Hello from NemotronOS."`

Browser test prompts:

`Open my web browser and navigate to Canvas.`

`To cnn.com.`

`To Canvas.`

Accessibility narration test prompts:

`Computer, what am I looking at?`

`Computer, explain this screen.`

`Computer, read the active window.`

`Computer, explain the active window.`

`Computer, describe my active window.`

`Computer, what did you just do?`

`Computer, what did the AI just do?`

These commands route through the normal model-first tool planner, then gather structured desktop context with `accessibility_describe_screen`, ask the model to produce a spoken-friendly explanation, and return that explanation through `notify_user` so the voice agent can read it aloud. A conservative fallback still catches common screen/window phrasing if the planner is unavailable. The first Windows version reports foreground-window, visible-window, focused-element, and screenshot metadata; deeper Windows UI Automation element trees are the next accessibility step.

If the local model returns an empty, clipped, or markdown-fragment accessibility narration, the coordinator falls back to a plain spoken summary built from the structured window context so the voice response stays useful during demos. The fallback avoids internal implementation caveats and speaks in user-facing terms.

Successful user-visible actions now also store a short safe narration under `voice_response_text`, so the local voice agent can confirm what actually happened after completion without echoing private dictated content. Examples include opening websites, opening Canvas courses, sending a Discord message to the active conversation, typing into Notepad, clicking a YouTube video result, inserting generated code into VS Code, creating a Gmail draft, creating a Canvas TODO note, and applying an approved file plan.

Canvas course test prompt:

`Open Canvas and navigate to my intro to AI course.`

For deterministic Canvas course routing, set either `CANVAS_INTRO_TO_AI_URL=https://canvas.oregonstate.edu/courses/<course-id>` or a semicolon-separated alias map such as `CANVAS_COURSE_ALIASES=intro to ai=https://canvas.oregonstate.edu/courses/<course-id>`. Optional `CANVAS_API_TOKEN` lets the tool list active Canvas courses through `/api/v1/courses` and fuzzy-match the requested course name.

Canvas assignment todo test prompt:

`Open Canvas, find assignments due within the next week, and create a TODO sticky note with links and due dates.`

This workflow uses the Canvas API through `CANVAS_API_TOKEN` to list upcoming assignments, opens Canvas in the default browser, then creates a local Sticky Notes note sorted by earliest due date. If Sticky Notes is unavailable or cannot be focused, the Windows backend falls back to a fresh Notepad note.

Gmail draft test prompt:

`Computer, compose an email to alex@example.com with subject Hackathon update saying I finished the demo slice.`

NemotronOS creates a Gmail draft through the Gmail API and then opens Gmail Drafts in the default browser so the user can inspect it. It does not send email. Set these values in `.env`:

```bash
GMAIL_CLIENT_SECRETS_PATH=C:/Users/Raed/Downloads/client_secret_...apps.googleusercontent.com.json
GMAIL_TOKEN_PATH=.secrets/gmail_token.json
```

The first draft request opens a Google OAuth consent page and stores the resulting local token at `GMAIL_TOKEN_PATH`. `.secrets/` is gitignored. The OAuth scope is draft/compose only: `https://www.googleapis.com/auth/gmail.compose`.

Use a full email address for the recipient. A domain like `example.com` is treated as invalid; use something shaped like `alex@example.com`.

`Open YouTube and play a random video.`

`Play lofi hip hop on YouTube.`

Generic browser-agent prompts:

`Open cnn.com and tell me the top headline.`

`Open GitHub, search for NemotronOS, and open the repository.`

`Open Google, search for RTX 2070 Super VRAM, and open the first result.`

`Open Gmail and click Compose.`

For the new managed browser tools, read-only actions such as session start, navigate, and snapshot run immediately. Browser mutations such as DOM click, type, select, and key press now require approval before execution.

Discord test prompt:

`Open Discord and send a message saying hello from NemotronOS.`

This sends to the currently active Discord conversation. It does not select servers or channels, so put Discord on the target chat first.

Code generation test prompt:

`Code me a Python script that prints the Fibonacci sequence.`

This asks the model to generate a single-file code snippet, opens a fresh VS Code window, and inserts the generated code without saving or running it. The tool server uses `VSCODE_COMMAND`, defaulting to `code`, so install the VS Code shell command or set `VSCODE_COMMAND` to the VS Code CLI path if Windows cannot find it.

If the tool server is launched from a hidden or non-interactive service context, Windows may create a process without a focusable desktop window. Run it from the signed-in desktop session for real UI interaction tests.

## API endpoints

### Agent server

- `POST /tasks`
- `POST /voice/tasks`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `POST /tasks/{task_id}/approve`
- `GET /events`
- `GET /health`
- `POST /demo/reset-downloads`

### Tool server

- `POST /tool`
- `GET /health`
- `POST /demo/reset-downloads`

Currently registered tool-server tools include `app_launch`, `keyboard_type`, `accessibility_describe_screen`, `sticky_note_create`, `vscode_paste_code`, `discord_send_message`, `email_create_draft`, `mouse_click`, `browser_open`, `browser_session_ensure`, `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_select_option`, `browser_press`, `canvas_open_course`, `canvas_list_assignments_due_soon`, `youtube_open`, `youtube_click_video`, `fs_plan_changes`, `fs_apply_changes`, `screen_capture`, `shell_run`, and `notify_user`.

## Notes

- Stores are in memory for this MVP, but the layout is intentionally modular so we can replace them with SQLite or Postgres later.
- `MODEL_MODE=openai_compatible` is scaffolded for OpenAI-compatible endpoints including local NVIDIA NIM and local Ollama.
- `DEFAULT_DOWNLOADS_PATH` controls the Windows path the model layer uses for the Downloads demo. The default is `C:\Users\Raed\Downloads` for the current fake Windows sandbox, but it should stay env-driven for real Windows testing.
- `TOOL_MODE=mock_windows` keeps platform behavior behind interfaces so we avoid macOS-only dependencies while developing away from the Windows machine.
