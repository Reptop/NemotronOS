# WORKING_STATE.md

Last updated: 2026-05-03

Purpose: current operational snapshot for any teammate or AI agent joining mid-hackathon. Keep this short, current, and action-oriented.

## Current System Status

- The repo has a working Windows mock development slice for a Windows-first PC agent demo.
- The main demo is: organize Downloads by file type, show the plan first, require approval, then apply changes.
- The stack is split into a FastAPI agent server, a FastAPI tool server, and a React dashboard.
- On 2026-05-02, the stack was validated on Windows with `TOOL_MODE=mock_windows` and `MODEL_MODE=mock`.
- On 2026-05-02, local NVIDIA NIM was validated from Windows at `http://127.0.0.1:8000/v1` with `nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1`.
- The agent server now supports `MODEL_PROVIDER=nim|ollama` while keeping the same `MODEL_MODE=openai_compatible` path, so teammates can keep the NIM setup while lighter local Ollama tests target `nemotron-3-nano:4b`.
- The current live desktop demo path is the Windows Notepad typing flow, and the Windows backend now has a first screenshot capture path for desktop-state inspection.

## What Works Now

- `POST /tasks` creates a task and starts async processing in the agent server.
- The mock model can route the Downloads-organization prompt into `fs_plan_changes`.
- The tool server can build a dry-run file organization plan against the fake Windows Downloads folder.
- The policy engine marks `fs_apply_changes` as medium risk and the dashboard exposes approval.
- Approved plans can be applied and generate an undo log.
- The dashboard can submit tasks, poll health/tasks/events, show the plan preview, and send approval.
- The agent model layer works with `MODEL_MODE=openai_compatible` against the local 4B NIM endpoint for the Downloads demo. The client forces `fs_plan_changes` for the known Downloads organizer prompt and normalizes the root path to `DEFAULT_DOWNLOADS_PATH`.
- `MODEL_PROVIDER=ollama` now defaults the same OpenAI-compatible client to `http://localhost:11434` with model `nemotron-3-nano:4b`, while `MODEL_PROVIDER=nim` preserves the prior NIM-oriented defaults and overrides.
- The dashboard has a reset control wired through `POST /demo/reset-downloads` to restore the fake Downloads fixture for repeatable demos.
- `scripts/run_local_stack.py` can bootstrap the local Python/dashboard dependencies and start the tool server, agent server, and dashboard from one terminal, skipping only `.env` creation.
- `scripts/run_windows_tool_server.py` can launch the tool server in a separate interactive Windows PowerShell window, and `scripts/run_wsl_agent_dashboard.py` can run the agent server plus dashboard in WSL, matching the current mixed-environment desktop demo setup.
- In `TOOL_MODE=windows`, the desktop backend can launch allowlisted apps, create a fresh temp file for Notepad, focus the launched window when Windows allows it, and paste text through `keyboard_type`.
- In `TOOL_MODE=windows`, `screen_capture` uses Pillow/ImageGrab to save a PNG screenshot under the local temp `NemotronOS/screenshots` directory and returns the saved file path plus dimensions.
- The coordinator auto-follows known Notepad typing goals with `keyboard_type` after `app_launch`. It now prefers locally extracted quoted/trailing text from the user goal, then falls back to stored voice dictation text, and only asks the model for a second planning step when the literal text is still unclear.
- The dashboard has a browser microphone path wired through `POST /voice/tasks`. The agent server transcribes with OpenAI's audio transcription API when `OPENAI_API_KEY` is configured, then submits the transcript as a normal task.
- The dashboard supports a browser-scoped voice hotkey: `Ctrl+Shift+Space` toggles recording while the dashboard tab is active.
- The dashboard supports browser-scoped wake words while enabled: utterances beginning with "Jarvis" or "Computer" are stripped of the wake word and submitted through `POST /voice/text-tasks`. Chrome/Edge use browser speech recognition; Firefox falls back to short MediaRecorder chunks sent to `POST /voice/wake-detect` for Whisper-based detection.
- `apps/voice-agent` is scaffolded as a separate local voice loop. The current recommended demo mode is `VOICE_AGENT_WAKE_MODE=whisper_poll` because it supports both preferred wake words, `Jarvis` and `Computer`, through `/voice/wake-detect`. The refined Whisper-poll path keeps separate wake and command timing profiles: wake capture at `VOICE_AGENT_WAKE_CHUNK_SECONDS=5`, `VOICE_AGENT_WAKE_SILENCE_SECONDS=0.9`, and `VOICE_AGENT_WAKE_MIN_RECORD_SECONDS=0.35`; command capture at `VOICE_AGENT_COMMAND_CHUNK_SECONDS=12`, `VOICE_AGENT_COMMAND_SILENCE_SECONDS=1.15`, and `VOICE_AGENT_COMMAND_MIN_RECORD_SECONDS=0.6`; plus `VOICE_AGENT_LISTEN_BLOCK_MS=50`. `VOICE_AGENT_WAKE_MODE=openwakeword` remains available as an optional local wake mode for the installed `hey_jarvis` model, but "Computer" still needs a custom wake model or a different local wake engine. `--mode manual` submits typed commands for fast pipeline testing. It speaks acknowledgements through Windows SAPI when `VOICE_AGENT_TTS_MODE=windows_sapi`; `VOICE_AGENT_TTS_VOICE` currently selects `Microsoft Zira Desktop`. `VOICE_AGENT_INPUT_DEVICE` is currently pinned back to sounddevice index `3`, the earlier Microsoft LifeCam/MME input, with `VOICE_AGENT_SAMPLE_RATE=16000` and `VOICE_AGENT_SPEECH_THRESHOLD=350`.
- The voice agent reuses one HTTP client for wake/text/audio requests, gives a quick neutral `VOICE_AGENT_SUBMITTED_ACK` after command submission, and no longer blocks on a success acknowledgement.
- Voice acknowledgements are outcome-aware: wake-only utterances say the short `VOICE_AGENT_LISTENING_ACK` value, currently "uh huh", before recording the follow-up command; successful tasks stay quiet after the neutral command-submitted acknowledgement, unsupported fallback tasks that complete through `notify_user` say "I don't know how to do that yet", approval-gated tasks ask for approval, and failed/cancelled/blocked tasks report failure.
- Voice transcripts are stored on task memory. Explicit verbatim markers such as "word for word" preserve the post-marker text as a memory override. Voice dictation commands also store the text after generic type/write/enter/paste wording so a too-short model `keyboard_type` argument cannot truncate longer notes.
- In `MODEL_MODE=openai_compatible`, first-action routing is now model-first for normal desktop, browser, YouTube, Canvas, and Discord voice commands. The old regex extractors remain as fallback when the local model request fails or returns no usable tool call, but they are no longer the primary path. The system prompt asks Nemotron to interpret short/noisy voice transcripts against the registered tool list and emit exactly one tool call.
- Browser navigation is implemented as a real `browser_open` tool. It opens the default Windows browser to an http(s) URL, domain, search query, or known shortcut such as `canvas`, currently mapped to Oregon State Canvas. Canvas course navigation has a first `canvas_open_course` tool: it resolves configured course aliases such as `CANVAS_INTRO_TO_AI_URL`, can optionally use `CANVAS_API_TOKEN` with Canvas `/api/v1/courses` to fuzzy-match active courses, and otherwise falls back to opening the Canvas courses page.
- YouTube has a first site-specific interaction path. `youtube_open` can open YouTube home, exact YouTube video URLs/IDs, or a search for a spoken video title. Voice-noisy fragments that only preserve `<query> on YouTube`, such as `Zajef77 on YouTube`, are treated as YouTube searches and now request YouTube's video-results filter before clicking so direct channel-name searches do not land on the channel card. For search/random-video requests, the coordinator auto-follows with `youtube_click_video`, which first focuses a window titled like YouTube, captures the screen, finds likely visible YouTube thumbnail rectangles, and clicks the first playable video result below any channel/header card. It falls back to foreground-window ratio clicks if screenshot detection fails.
- Discord has a first low-navigation messaging path. Discord voice routing is intentionally forgiving for the hackathon: if a transcript contains Discord-like words such as `discord`, `chord`, or `cord`, or has a generic `send a message saying ...` shape, the agent treats it as a Discord message command. `discord_send_message` focuses or opens Discord, presses Escape once to clear common overlays/search focus, pastes the requested text into whatever Discord conversation is currently active, and presses Enter. It intentionally does not select servers, channels, or recipients.
- If the OpenAI transcription call fails, the dashboard can fall back to browser speech recognition through `POST /voice/text-tasks` when the browser exposes `SpeechRecognition`/`webkitSpeechRecognition`.

## What Is Stubbed Or Fake

- The fake Windows filesystem under `sandbox/fake_windows_home` is the active environment, not a real Windows box.
- Voice transcription currently uses OpenAI as temporary development scaffolding, not the final private/local STT architecture.
- The local voice agent's current recommended wake mode is the refined Whisper-poll loop because it supports `Computer` and `Jarvis`. Local openWakeWord for `hey_jarvis` is implemented but optional until a good "Computer" wake model is available. Command transcription still uses the temporary OpenAI transcription path until local NVIDIA Speech NIM/Riva ASR is available.
- The mock model does not behave like a general agent yet. It mainly supports the Downloads-organization path and otherwise falls back to `notify_user`.
- `screen_capture` is still mock output in `TOOL_MODE=mock_windows`.
- `shell_run` is a safe stub in `TOOL_MODE=mock_windows`; it does not execute real shell commands there.
- The real Windows desktop backend now includes `screen_capture` through Pillow/ImageGrab plus the earlier allowlisted `app_launch`, `browser_open`, `canvas_open_course`, `youtube_open`, `youtube_click_video`, `discord_send_message`, `mouse_click`, and `keyboard_type` implementation. Notepad launch creates a unique empty temp document so the demo does not type into a restored/preexisting note. Discord launch uses the `discord:` URI through Explorer. The text follow-up is model-mediated, with voice memory overriding the typed text when the transcript contains clear dictation content. Windows text entry uses clipboard paste rather than per-character `SendInput`.
- The agent tool definitions have been trimmed to registered runtime tools. Treat `apps/tool-server/nemotronos_tools/registry.py` as the runtime truth if adding new tools.

## Highest-Priority Next Tasks

1. Live-test model-first routing on the Windows NIM path with the current voice/browser commands and tune the system prompt only where needed.
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
- Model-first routing can still be brittle with the local 4B model. Keep fallback parsers conservative and prefer prompt/tool-schema improvements over adding new command-specific regexes.
- Local NIM may return a tool call with non-demo-safe paths. The current OpenAI-compatible client intentionally normalizes the known Downloads demo arguments before tool execution.
- Ollama provider support is wired through Ollama's OpenAI-compatible endpoint, but this repo snapshot has only code-level and unit-test validation for that path so far, not a recorded Windows live run yet.
- Earlier tool-call failures could lose useful detail when the underlying exception had an empty string form; the agent now records a fallback exception type string and includes tool-server response bodies on HTTP failures.

## Update Protocol

- Replace stale bullets instead of appending status history.
- Keep next actions ordered by what the next contributor should do first.
- Record blockers only when they immediately affect the next contributor.
