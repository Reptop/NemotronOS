import { useEffect, useMemo, useRef, useState } from "react";

import {
  approveTask,
  createTask,
  createVoiceTextTask,
  createVoiceTask,
  detectWakeWord,
  fetchEvents,
  fetchHealth,
  fetchTasks,
  resetDemoDownloads,
} from "./api.js";
import ApprovalPanel from "./components/ApprovalPanel.jsx";
import EventTimeline from "./components/EventTimeline.jsx";
import StatusBar from "./components/StatusBar.jsx";
import TaskList from "./components/TaskList.jsx";

const DEFAULT_GOAL =
  "Organize my Downloads folder into folders by file type, but show me the plan first.";
const WAKE_WORDS = ["jarvis", "computer"];
const WAKE_AUDIO_CHUNK_MS = 4500;

export default function App() {
  const [goal, setGoal] = useState(DEFAULT_GOAL);
  const [tasks, setTasks] = useState([]);
  const [events, setEvents] = useState([]);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");
  const [selectedTaskId, setSelectedTaskId] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isApproving, setIsApproving] = useState(false);
  const [isResettingDemo, setIsResettingDemo] = useState(false);
  const [isRecordingVoice, setIsRecordingVoice] = useState(false);
  const [isSubmittingVoice, setIsSubmittingVoice] = useState(false);
  const [isWakeListening, setIsWakeListening] = useState(false);
  const [lastTranscript, setLastTranscript] = useState("");
  const mediaRecorderRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const recordedChunksRef = useRef([]);
  const speechRecognitionRef = useRef(null);
  const wakeRecognitionRef = useRef(null);
  const wakeAudioStreamRef = useRef(null);
  const wakeAudioRecorderRef = useRef(null);
  const wakeAudioChunksRef = useRef([]);
  const wakeAudioDetectInFlightRef = useRef(false);
  const wakeListeningRef = useRef(false);
  const wakeRestartTimerRef = useRef(null);
  const lastWakeCommandRef = useRef({ command: "", at: 0 });
  const browserTranscriptRef = useRef("");

  async function refresh() {
    try {
      const [healthData, tasksData, eventsData] = await Promise.all([
        fetchHealth(),
        fetchTasks(),
        fetchEvents(),
      ]);
      setHealth(healthData);
      setTasks(tasksData);
      setEvents(eventsData.slice(0, 20));
      setError("");

      if (!selectedTaskId && tasksData.length > 0) {
        setSelectedTaskId(tasksData[0].id);
      }
    } catch (refreshError) {
      setError(refreshError.message);
    }
  }

  useEffect(() => {
    refresh();
    const intervalId = window.setInterval(refresh, 2000);
    return () => window.clearInterval(intervalId);
  }, []);

  useEffect(() => {
    function handleVoiceHotkey(event) {
      if (!isVoiceHotkey(event) || event.repeat || isSubmittingVoice) {
        return;
      }

      event.preventDefault();
      if (isRecordingVoice) {
        handleStopVoice();
      } else {
        void handleStartVoice();
      }
    }

    window.addEventListener("keydown", handleVoiceHotkey);
    return () => window.removeEventListener("keydown", handleVoiceHotkey);
  }, [isRecordingVoice, isSubmittingVoice]);

  useEffect(() => {
    return () => {
      wakeListeningRef.current = false;
      clearWakeRestartTimer();
      stopWakeWordRecognition();
      stopWakeAudioDetection();
    };
  }, []);

  const selectedTask = useMemo(
    () => tasks.find((task) => task.id === selectedTaskId) || tasks[0] || null,
    [selectedTaskId, tasks],
  );

  async function handleSubmit(event) {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      const createdTask = await createTask(goal);
      setSelectedTaskId(createdTask.id);
      setGoal(DEFAULT_GOAL);
      await refresh();
    } catch (submitError) {
      setError(submitError.message);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleApprove(taskId, approved) {
    setIsApproving(true);
    try {
      await approveTask(taskId, approved);
      await refresh();
    } catch (approvalError) {
      setError(approvalError.message);
    } finally {
      setIsApproving(false);
    }
  }

  async function handleResetDemo() {
    setIsResettingDemo(true);
    try {
      await resetDemoDownloads();
      await refresh();
    } catch (resetError) {
      setError(resetError.message);
    } finally {
      setIsResettingDemo(false);
    }
  }

  async function handleStartVoice() {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError("Voice recording is not supported in this browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "";
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recordedChunksRef.current = [];
      browserTranscriptRef.current = "";
      mediaStreamRef.current = stream;
      mediaRecorderRef.current = recorder;
      pauseWakeWordRecognition();
      startBrowserSpeechRecognition();

      recorder.addEventListener("dataavailable", (event) => {
        if (event.data.size > 0) {
          recordedChunksRef.current.push(event.data);
        }
      });

      recorder.addEventListener("stop", async () => {
        const audioBlob = new Blob(recordedChunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        recordedChunksRef.current = [];

        try {
          setIsSubmittingVoice(true);
          const audioBase64 = await blobToBase64(audioBlob);
          let response;
          try {
            response = await createVoiceTask({
              audioBase64,
              mimeType: audioBlob.type || "audio/webm",
              filename: "voice-command.webm",
            });
          } catch (transcriptionError) {
            const fallbackTranscript = browserTranscriptRef.current.trim();
            if (!fallbackTranscript) {
              throw transcriptionError;
            }
            response = await createVoiceTextTask({
              transcript: fallbackTranscript,
              source: "browser_speech_fallback",
            });
          }
          setLastTranscript(response.transcription.text);
          setSelectedTaskId(response.task.id);
          await refresh();
        } catch (voiceError) {
          setError(voiceError.message);
        } finally {
          setIsSubmittingVoice(false);
          cleanupVoiceStream();
        }
      });

      recorder.start();
      setIsRecordingVoice(true);
      setError("");
    } catch (voiceError) {
      setError(voiceError.message);
      cleanupVoiceStream();
    }
  }

  function handleStopVoice() {
    if (mediaRecorderRef.current?.state === "recording") {
      stopBrowserSpeechRecognition();
      mediaRecorderRef.current.stop();
      setIsRecordingVoice(false);
    }
  }

  function cleanupVoiceStream() {
    stopBrowserSpeechRecognition();
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    mediaRecorderRef.current = null;
    setIsRecordingVoice(false);
    resumeWakeWordRecognition();
  }

  function startBrowserSpeechRecognition() {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = "en-US";
      recognition.addEventListener("result", (event) => {
        let transcript = "";
        for (let index = 0; index < event.results.length; index += 1) {
          transcript += event.results[index][0].transcript;
        }
        browserTranscriptRef.current = transcript.trim();
      });
      recognition.addEventListener("error", () => {
        speechRecognitionRef.current = null;
      });
      speechRecognitionRef.current = recognition;
      recognition.start();
    } catch {
      speechRecognitionRef.current = null;
    }
  }

  function stopBrowserSpeechRecognition() {
    if (!speechRecognitionRef.current) {
      return;
    }

    try {
      speechRecognitionRef.current.stop();
    } catch {
      speechRecognitionRef.current.abort?.();
    } finally {
      speechRecognitionRef.current = null;
    }
  }

  function handleToggleWakeWords() {
    if (isWakeListening) {
      stopWakeWords();
    } else {
      startWakeWords();
    }
  }

  function startWakeWords() {
    const SpeechRecognition = getSpeechRecognition();
    const canRecordWakeAudio = navigator.mediaDevices?.getUserMedia && window.MediaRecorder;
    if (!SpeechRecognition && !canRecordWakeAudio) {
      setError("Wake words are not supported in this browser.");
      return;
    }

    wakeListeningRef.current = true;
    setIsWakeListening(true);
    setError("");
    if (SpeechRecognition) {
      startWakeWordRecognition();
    } else {
      void startWakeAudioDetection();
    }
  }

  function stopWakeWords() {
    wakeListeningRef.current = false;
    setIsWakeListening(false);
    clearWakeRestartTimer();
    stopWakeWordRecognition();
    stopWakeAudioDetection();
  }

  function startWakeWordRecognition() {
    if (!wakeListeningRef.current || wakeRecognitionRef.current || isRecordingVoice) {
      return;
    }

    const SpeechRecognition = getSpeechRecognition();
    if (!SpeechRecognition) {
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = false;
      recognition.lang = "en-US";
      recognition.addEventListener("result", (event) => {
        for (let index = event.resultIndex; index < event.results.length; index += 1) {
          if (!event.results[index].isFinal) {
            continue;
          }
          const transcript = event.results[index][0].transcript.trim();
          const command = extractWakeCommand(transcript);
          if (command) {
            void submitWakeCommand(command);
          }
        }
      });
      recognition.addEventListener("error", () => {
        wakeRecognitionRef.current = null;
        if (wakeListeningRef.current && !isRecordingVoice) {
          clearWakeRestartTimer();
          wakeRestartTimerRef.current = window.setTimeout(() => {
            void startWakeAudioDetection();
          }, 350);
        }
      });
      recognition.addEventListener("end", () => {
        wakeRecognitionRef.current = null;
        if (wakeListeningRef.current && !isRecordingVoice) {
          clearWakeRestartTimer();
          wakeRestartTimerRef.current = window.setTimeout(
            startWakeWordRecognition,
            350,
          );
        }
      });
      wakeRecognitionRef.current = recognition;
      recognition.start();
    } catch {
      wakeRecognitionRef.current = null;
    }
  }

  async function submitWakeCommand(command) {
    const now = Date.now();
    if (
      lastWakeCommandRef.current.command === command &&
      now - lastWakeCommandRef.current.at < 4000
    ) {
      return;
    }
    lastWakeCommandRef.current = { command, at: now };

    try {
      setIsSubmittingVoice(true);
      const response = await createVoiceTextTask({
        transcript: command,
        source: "browser_wake_word",
      });
      setLastTranscript(response.transcription.text);
      setSelectedTaskId(response.task.id);
      await refresh();
    } catch (wakeError) {
      setError(wakeError.message);
    } finally {
      setIsSubmittingVoice(false);
    }
  }

  function pauseWakeWordRecognition() {
    clearWakeRestartTimer();
    stopWakeWordRecognition();
    stopWakeAudioDetection();
  }

  function resumeWakeWordRecognition() {
    if (!wakeListeningRef.current) {
      return;
    }

    if (getSpeechRecognition()) {
      startWakeWordRecognition();
    } else {
      void startWakeAudioDetection();
    }
  }

  function stopWakeWordRecognition() {
    if (!wakeRecognitionRef.current) {
      return;
    }

    try {
      wakeRecognitionRef.current.stop();
    } catch {
      wakeRecognitionRef.current.abort?.();
    } finally {
      wakeRecognitionRef.current = null;
    }
  }

  function clearWakeRestartTimer() {
    if (wakeRestartTimerRef.current) {
      window.clearTimeout(wakeRestartTimerRef.current);
      wakeRestartTimerRef.current = null;
    }
  }

  async function startWakeAudioDetection() {
    if (
      !wakeListeningRef.current ||
      wakeAudioStreamRef.current ||
      isRecordingVoice ||
      !navigator.mediaDevices?.getUserMedia ||
      !window.MediaRecorder
    ) {
      return;
    }

    try {
      wakeAudioStreamRef.current = await navigator.mediaDevices.getUserMedia({
        audio: true,
      });
      startWakeAudioChunk();
    } catch (wakeError) {
      wakeListeningRef.current = false;
      setIsWakeListening(false);
      setError(wakeError.message);
    }
  }

  function startWakeAudioChunk() {
    if (
      !wakeListeningRef.current ||
      !wakeAudioStreamRef.current ||
      wakeAudioRecorderRef.current ||
      wakeAudioDetectInFlightRef.current ||
      isRecordingVoice
    ) {
      return;
    }

    const mimeType = MediaRecorder.isTypeSupported("audio/webm")
      ? "audio/webm"
      : "";
    const recorder = new MediaRecorder(
      wakeAudioStreamRef.current,
      mimeType ? { mimeType } : undefined,
    );
    wakeAudioChunksRef.current = [];
    wakeAudioRecorderRef.current = recorder;

    recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) {
        wakeAudioChunksRef.current.push(event.data);
      }
    });

    recorder.addEventListener("stop", async () => {
      const chunks = wakeAudioChunksRef.current;
      wakeAudioChunksRef.current = [];
      wakeAudioRecorderRef.current = null;
      if (!wakeListeningRef.current || !chunks.length || isRecordingVoice) {
        return;
      }

      wakeAudioDetectInFlightRef.current = true;
      try {
        const audioBlob = new Blob(chunks, {
          type: recorder.mimeType || "audio/webm",
        });
        const result = await detectWakeWord({
          audioBase64: await blobToBase64(audioBlob),
          mimeType: audioBlob.type || "audio/webm",
          filename: "wake-word.webm",
        });
        if (result.detected && result.command) {
          await submitWakeCommand(result.command);
        }
      } catch (wakeError) {
        setError(wakeError.message);
      } finally {
        wakeAudioDetectInFlightRef.current = false;
        if (wakeListeningRef.current && !isRecordingVoice) {
          wakeRestartTimerRef.current = window.setTimeout(startWakeAudioChunk, 250);
        }
      }
    });

    recorder.start();
    wakeRestartTimerRef.current = window.setTimeout(() => {
      if (recorder.state === "recording") {
        recorder.stop();
      }
    }, WAKE_AUDIO_CHUNK_MS);
  }

  function stopWakeAudioDetection() {
    if (wakeAudioRecorderRef.current?.state === "recording") {
      wakeAudioRecorderRef.current.stop();
    }
    wakeAudioRecorderRef.current = null;
    wakeAudioChunksRef.current = [];
    wakeAudioStreamRef.current?.getTracks().forEach((track) => track.stop());
    wakeAudioStreamRef.current = null;
    wakeAudioDetectInFlightRef.current = false;
  }

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">NemotronOS</p>
          <h1>Private PC agent control room</h1>
          <p className="hero-copy">
            Develop the Windows-first agent core on macOS today, then swap in
            NIM and real desktop tools later.
          </p>
        </div>

        <form className="task-form" onSubmit={handleSubmit}>
          <label htmlFor="goal">New task</label>
          <textarea
            id="goal"
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            rows={4}
          />
          <button className="primary-button" disabled={isSubmitting} type="submit">
            {isSubmitting ? "Submitting..." : "Submit task"}
          </button>
          <button
            className="secondary-button"
            disabled={isResettingDemo}
            onClick={handleResetDemo}
            type="button"
          >
            {isResettingDemo ? "Resetting..." : "Reset demo files"}
          </button>
          <div className="voice-actions">
            <button
              aria-keyshortcuts="Control+Shift+Space"
              className={isRecordingVoice ? "danger-button" : "secondary-button"}
              disabled={isSubmittingVoice}
              onClick={isRecordingVoice ? handleStopVoice : handleStartVoice}
              type="button"
            >
              {isRecordingVoice ? "Stop voice" : "Record voice command"}
            </button>
            <button
              className={isWakeListening ? "primary-button" : "secondary-button"}
              disabled={isRecordingVoice || isSubmittingVoice}
              onClick={handleToggleWakeWords}
              type="button"
            >
              {isWakeListening ? "Wake words active" : "Enable wake words"}
            </button>
            {isSubmittingVoice ? <span>Transcribing...</span> : null}
            {lastTranscript ? <p>Last transcript: {lastTranscript}</p> : null}
          </div>
        </form>
      </header>

      <StatusBar health={health} tasks={tasks} />

      {error ? <section className="error-banner">{error}</section> : null}

      <section className="dashboard-grid">
        <TaskList
          tasks={tasks}
          selectedTaskId={selectedTask?.id}
          onSelectTask={setSelectedTaskId}
        />
        <ApprovalPanel
          task={selectedTask}
          onApprove={handleApprove}
          isSubmitting={isApproving}
        />
      </section>

      <EventTimeline events={events} />
    </main>
  );
}

function getSpeechRecognition() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function extractWakeCommand(transcript) {
  const normalizedTranscript = transcript.trim();
  const loweredTranscript = normalizedTranscript.toLowerCase();

  for (const wakeWord of WAKE_WORDS) {
    const index = loweredTranscript.indexOf(wakeWord);
    if (index < 0) {
      continue;
    }

    const before = loweredTranscript[index - 1] || " ";
    const after = loweredTranscript[index + wakeWord.length] || " ";
    if (/\w/.test(before) || /\w/.test(after)) {
      continue;
    }

    const command = normalizedTranscript
      .slice(index + wakeWord.length)
      .replace(/^[\s,.:;-]+/, "")
      .trim();
    if (command) {
      return command;
    }
  }

  return "";
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

function isVoiceHotkey(event) {
  return (
    event.ctrlKey &&
    event.shiftKey &&
    !event.altKey &&
    !event.metaKey &&
    (event.code === "Space" || event.key === " ")
  );
}
