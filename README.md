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
- `VOICE_AGENT_INPUT_DEVICE`: optional sounddevice index or name when Windows picks the wrong microphone.
- `VOICE_AGENT_OPENWAKEWORD_MODELS`: semicolon-separated openWakeWord model names or model paths. The default is `hey_jarvis`.
- `VOICE_AGENT_OPENWAKEWORD_THRESHOLD` and `VOICE_AGENT_OPENWAKEWORD_FRAME_MS`: tune local wake sensitivity and streaming frame size.
- `VOICE_AGENT_WAKE_SILENCE_SECONDS`, `VOICE_AGENT_WAKE_CHUNK_SECONDS`, `VOICE_AGENT_COMMAND_SILENCE_SECONDS`, and `VOICE_AGENT_COMMAND_CHUNK_SECONDS`: tune the faster wake capture separately from the longer command capture.
- `VOICE_AGENT_SPEECH_THRESHOLD` and `VOICE_AGENT_LISTEN_BLOCK_MS`: tune speech detection sensitivity and how quickly silence is noticed.
- `VOICE_AGENT_SUBMITTED_ACK`: quick neutral acknowledgement after a command is accepted locally. Keep it neutral because the task may still fail or be unsupported.
- `VOICE_AGENT_LISTENING_ACK`: optional prompt after a wake-only utterance. The current demo value is `uh huh`; the voice agent waits for this short acknowledgement to finish before recording the command.
- `VOICE_AGENT_TTS_VOICE`: optional Windows SAPI voice name. On this Windows machine the installed choices are `Microsoft David Desktop`, `Microsoft Zira Desktop`, and `Microsoft Haruka Desktop`; the current demo value is `Microsoft Zira Desktop`.
- If the wake word is heard without a command, the voice agent immediately treats the next utterance as the command.

Example:

`Computer, open notepad and type in hello from the local voice agent`

This is still a scaffold. The current recommended demo path is the refined Whisper-poll loop because it supports both `Jarvis` and `Computer`. It gives a short wake acknowledgement, gives a quick neutral acknowledgement after command submission, stays quiet on successful task completion, and only speaks again for unsupported, failed, or approval-gated tasks. The next privacy step is local NVIDIA Speech NIM/Riva ASR and TTS when those services are available, plus either a custom openWakeWord model or another local detector for "Computer."

### Real Windows desktop tool mode

For the first real desktop-control slice, set `TOOL_MODE=windows` and run the tool server from an interactive Windows terminal. The tool server currently allowlists `notepad`, `calculator`/`calc`, `paint`/`mspaint`, and `discord` for `app_launch`, supports `keyboard_type` through clipboard paste, supports opening a fresh VS Code window and inserting generated code through `vscode_paste_code`, supports Discord message sending to the currently active conversation, supports `browser_open` through the default Windows browser, supports Canvas course opening through configured aliases or an optional Canvas API token, and has screenshot-first mouse clicking for YouTube video selection with a ratio-click fallback.

First manual test prompt:

`Open Notepad and type "Hello from NemotronOS."`

Browser test prompts:

`Open my web browser and navigate to Canvas.`

`To cnn.com.`

`To Canvas.`

Canvas course test prompt:

`Open Canvas and navigate to my intro to AI course.`

For deterministic Canvas course routing, set either `CANVAS_INTRO_TO_AI_URL=https://canvas.oregonstate.edu/courses/<course-id>` or a semicolon-separated alias map such as `CANVAS_COURSE_ALIASES=intro to ai=https://canvas.oregonstate.edu/courses/<course-id>`. Optional `CANVAS_API_TOKEN` lets the tool list active Canvas courses through `/api/v1/courses` and fuzzy-match the requested course name.

`Open YouTube and play a random video.`

`Play lofi hip hop on YouTube.`

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

Currently registered tool-server tools include `app_launch`, `keyboard_type`, `vscode_paste_code`, `discord_send_message`, `mouse_click`, `browser_open`, `canvas_open_course`, `youtube_open`, `youtube_click_video`, `fs_plan_changes`, `fs_apply_changes`, `screen_capture`, `shell_run`, and `notify_user`.

## Notes

- Stores are in memory for this MVP, but the layout is intentionally modular so we can replace them with SQLite or Postgres later.
- `MODEL_MODE=openai_compatible` is scaffolded for an OpenAI-compatible endpoint such as local NVIDIA NIM.
- `DEFAULT_DOWNLOADS_PATH` controls the Windows path the model layer uses for the Downloads demo. The default is `C:\Users\Raed\Downloads` for the current fake Windows sandbox, but it should stay env-driven for real Windows testing.
- `TOOL_MODE=mock_windows` keeps platform behavior behind interfaces so we avoid macOS-only dependencies while developing away from the Windows machine.
