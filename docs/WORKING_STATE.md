# WORKING_STATE.md

Last updated: 2026-05-02

Purpose: current operational snapshot for any teammate or AI agent joining mid-hackathon. Keep this short, current, and action-oriented.

## Current System Status

- The repo has a working Windows mock development slice for a Windows-first PC agent demo.
- The main demo is: organize Downloads by file type, show the plan first, require approval, then apply changes.
- The stack is split into a FastAPI agent server, a FastAPI tool server, and a React dashboard.
- On 2026-05-02, the stack was validated on Windows with `TOOL_MODE=mock_windows` and `MODEL_MODE=mock`.
- On 2026-05-02, local NVIDIA NIM was validated from Windows at `http://127.0.0.1:8000/v1` with `nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1`.
- The current live desktop demo path is the Windows Notepad typing flow, and the Windows backend now has a first screenshot capture path for desktop-state inspection.

## What Works Now

- `POST /tasks` creates a task and starts async processing in the agent server.
- The mock model can route the Downloads-organization prompt into `fs_plan_changes`.
- The tool server can build a dry-run file organization plan against the fake Windows Downloads folder.
- The policy engine marks `fs_apply_changes` as medium risk and the dashboard exposes approval.
- Approved plans can be applied and generate an undo log.
- The dashboard can submit tasks, poll health/tasks/events, show the plan preview, and send approval.
- The agent model layer works with `MODEL_MODE=openai_compatible` against the local 4B NIM endpoint for the Downloads demo. The client forces `fs_plan_changes` for the known Downloads organizer prompt and normalizes the root path to `DEFAULT_DOWNLOADS_PATH`.
- The dashboard has a reset control wired through `POST /demo/reset-downloads` to restore the fake Downloads fixture for repeatable demos.
- In `TOOL_MODE=windows`, the desktop backend can launch allowlisted apps, create a fresh temp file for Notepad, focus the launched window when Windows allows it, and paste text through `keyboard_type`.
- In `TOOL_MODE=windows`, `screen_capture` uses Pillow/ImageGrab to save a PNG screenshot under the local temp `NemotronOS/screenshots` directory and returns the saved file path plus dimensions.
- The coordinator auto-follows known Notepad typing goals with `keyboard_type` after `app_launch`, and voice dictation text can override the model's shorter typed-text argument.
- The dashboard has a browser microphone path wired through `POST /voice/tasks`. The agent server transcribes with OpenAI's audio transcription API when `OPENAI_API_KEY` is configured, then submits the transcript as a normal task.
- The dashboard supports a browser-scoped voice hotkey: `Ctrl+Shift+Space` toggles recording while the dashboard tab is active.
- The dashboard supports browser-scoped wake words while enabled: utterances beginning with "Jarvis" or "Computer" are stripped of the wake word and submitted through `POST /voice/text-tasks`. Chrome/Edge use browser speech recognition; Firefox falls back to short MediaRecorder chunks sent to `POST /voice/wake-detect` for Whisper-based detection.
- `apps/voice-agent` is scaffolded as a separate local voice loop. The current recommended demo mode is back to `VOICE_AGENT_WAKE_MODE=whisper_poll` because it supports both preferred wake words, `Jarvis` and `Computer`, through `/voice/wake-detect`. The refined Whisper-poll path keeps separate wake and command timing profiles: wake capture at `VOICE_AGENT_WAKE_CHUNK_SECONDS=6`, `VOICE_AGENT_WAKE_SILENCE_SECONDS=1.1`, and `VOICE_AGENT_WAKE_MIN_RECORD_SECONDS=0.45`; command capture at `VOICE_AGENT_COMMAND_CHUNK_SECONDS=12`, `VOICE_AGENT_COMMAND_SILENCE_SECONDS=1.35`, and `VOICE_AGENT_COMMAND_MIN_RECORD_SECONDS=0.6`; plus `VOICE_AGENT_LISTEN_BLOCK_MS=50`. `VOICE_AGENT_WAKE_MODE=openwakeword` remains available as an optional local wake mode for the installed `hey_jarvis` model, but "Computer" still needs a custom wake model or a different local wake engine. `--mode manual` submits typed commands for fast pipeline testing. It speaks acknowledgements through Windows SAPI when `VOICE_AGENT_TTS_MODE=windows_sapi`. `VOICE_AGENT_INPUT_DEVICE` can pin a microphone by sounddevice index or name.
- The voice agent reuses one HTTP client for wake/text/audio requests, and the final command acknowledgement no longer blocks task submission.
- Voice acknowledgements are outcome-aware: unsupported fallback tasks that complete through `notify_user` say "I don't know how to do that yet" instead of the success acknowledgement, approval-gated tasks ask for approval, and failed/cancelled/blocked tasks report failure.
- Voice transcripts are stored on task memory. Explicit verbatim markers such as "word for word" preserve the post-marker text as a memory override. Voice dictation commands also store the text after generic type/write/enter/paste wording so a too-short model `keyboard_type` argument cannot truncate longer notes.
- Browser navigation is implemented as a real `browser_open` tool. It opens the default Windows browser to an http(s) URL, domain, search query, or known shortcut such as `canvas`, currently mapped to Oregon State Canvas.
- YouTube has a first site-specific interaction path. `youtube_open` can open YouTube home, exact YouTube video URLs/IDs, or a search for a spoken video title. For search/random-video requests, the coordinator now auto-follows with `youtube_click_video`, which first focuses a window titled like YouTube, captures the screen, finds likely visible YouTube thumbnail rectangles, clicks the selected thumbnail center, and falls back to foreground-window ratio clicks if screenshot detection fails.
- If the OpenAI transcription call fails, the dashboard can fall back to browser speech recognition through `POST /voice/text-tasks` when the browser exposes `SpeechRecognition`/`webkitSpeechRecognition`.

## What Is Stubbed Or Fake

- The fake Windows filesystem under `sandbox/fake_windows_home` is the active environment, not a real Windows box.
- Voice transcription currently uses OpenAI as temporary development scaffolding, not the final private/local STT architecture.
- The local voice agent's current recommended wake mode is the refined Whisper-poll loop because it supports `Computer` and `Jarvis`. Local openWakeWord for `hey_jarvis` is implemented but optional until a good "Computer" wake model is available. Command transcription still uses the temporary OpenAI transcription path until local NVIDIA Speech NIM/Riva ASR is available.
- The mock model does not behave like a general agent yet. It mainly supports the Downloads-organization path and otherwise falls back to `notify_user`.
- `screen_capture` is still mock output in `TOOL_MODE=mock_windows`.
- `shell_run` is a safe stub in `TOOL_MODE=mock_windows`; it does not execute real shell commands there.
- The real Windows desktop backend now includes `screen_capture` through Pillow/ImageGrab plus the earlier allowlisted `app_launch`, `browser_open`, `youtube_open`, `youtube_click_video`, `mouse_click`, and `keyboard_type` implementation. Notepad launch creates a unique empty temp document so the demo does not type into a restored/preexisting note. The text follow-up is model-mediated, with voice memory overriding the typed text when the transcript contains clear dictation content. Windows text entry uses clipboard paste rather than per-character `SendInput`.
- The agent advertises more tool definitions than the tool server currently registers. Treat `apps/tool-server/nemotronos_tools/registry.py` as the runtime truth.

## Highest-Priority Next Tasks

1. Align tool definitions with registered runtime behavior so the advertised surface matches what the tool server can actually execute, now that screenshot support has landed.
2. Verify `screen_capture` from a signed-in interactive Windows session and decide whether the next agent step should consume the saved file path directly or attach richer image metadata.
3. Improve YouTube card selection from local image heuristics to a controlled browser/DOM or model-vision path that can read titles and choose among actual visible video cards before clicking.
4. Add a second local wake model for "Computer" or choose a wake engine with an off-the-shelf "Computer" keyword so both preferred wake words are local.

## Windows Handoff Notes

- Current path assumptions are Windows-style at the agent/tool boundary and local sandbox paths underneath.
- The real user path for the demo is modeled by `DEFAULT_DOWNLOADS_PATH`, currently `C:\Users\Raed\Downloads`.
- `TOOL_MODE=mock_windows` is the safe current dev path.
- Switching to real Windows behavior will require replacing or extending the scaffolded desktop/tool backends, not just changing docs or prompts.
- Check Python 3.11+ and Node/Vite startup on Windows before promising demo readiness.
- In the Codex sandbox on Windows, the user-level `python` and `py` shims were not usable; the bundled Python runtime plus repo-local `.deps/python` worked after allowing pip network access.
- For local NIM on the RTX 4090, the 8B NIM and 4B TensorRT buildable BF16 profile were killed during startup. The working path was the 4B NIM `vllm-bf16-tp1-pp1` profile with reduced context (`NIM_MAX_MODEL_LEN=4096`).
- Real Windows desktop input should be tested from an interactive user-launched tool server. In the Codex hidden process context, Notepad can be launched but may not expose a focusable desktop window, so `SetForegroundWindow` can fail even when `SendInput` succeeds.
- On 2026-05-02, voice transcription briefly failed because an inherited Windows `OPENAI_API_KEY` took precedence over the repo `.env` key. `get_settings()` now loads the repo `.env` with override semantics for local dev; the backend transcriber was verified against `C:\Users\Raed\Downloads\file.mp3`.

## Known Mismatches And Risks

- State is in memory, so restarts wipe tasks, events, approval state, and stored plans.
- The repo includes committed `__pycache__`, `dist`, and `*.egg-info` artifacts. They should not be treated as the canonical implementation.
- The broader tool list in `apps/agent-server/nemotronos_agent/tool_defs.py` can make the system look more complete than the runtime actually is.
- Local NIM may return a tool call with non-demo-safe paths. The current OpenAI-compatible client intentionally normalizes the known Downloads demo arguments before tool execution.

## Update Protocol

- Replace stale bullets instead of appending status history.
- Keep next actions ordered by what the next contributor should do first.
- Record blockers only when they immediately affect the next contributor.
