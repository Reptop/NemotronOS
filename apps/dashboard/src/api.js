const AGENT_SERVER_URL =
  import.meta.env.VITE_AGENT_SERVER_URL || "http://127.0.0.1:5051";

async function request(path, options = {}) {
  const response = await fetch(`${AGENT_SERVER_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    const message = await response.text();
    let detail = message;
    try {
      const payload = JSON.parse(message);
      detail = payload.detail || message;
    } catch {
      detail = message;
    }
    throw new Error(detail || `Request failed for ${path}`);
  }

  return response.json();
}

export function createTask(goal) {
  return request("/tasks", {
    method: "POST",
    body: JSON.stringify({ goal }),
  });
}

export function createVoiceTask({ audioBase64, mimeType, filename }) {
  return request("/voice/tasks", {
    method: "POST",
    body: JSON.stringify({
      audio_base64: audioBase64,
      mime_type: mimeType,
      filename,
    }),
  });
}

export function createVoiceTextTask({ transcript, source = "browser_speech" }) {
  return request("/voice/text-tasks", {
    method: "POST",
    body: JSON.stringify({
      transcript,
      source,
    }),
  });
}

export function detectWakeWord({ audioBase64, mimeType, filename }) {
  return request("/voice/wake-detect", {
    method: "POST",
    body: JSON.stringify({
      audio_base64: audioBase64,
      mime_type: mimeType,
      filename,
    }),
  });
}

export function fetchTasks() {
  return request("/tasks");
}

export function fetchTask(taskId) {
  return request(`/tasks/${taskId}`);
}

export function fetchEvents() {
  return request("/events");
}

export function fetchHealth() {
  return request("/health");
}

export function approveTask(taskId, approved) {
  return request(`/tasks/${taskId}/approve`, {
    method: "POST",
    body: JSON.stringify({ approved }),
  });
}

export function resetDemoDownloads() {
  return request("/demo/reset-downloads", {
    method: "POST",
  });
}
