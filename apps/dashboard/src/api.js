const AGENT_SERVER_URL =
  import.meta.env.VITE_AGENT_SERVER_URL || "http://localhost:5051";

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
    throw new Error(message || `Request failed for ${path}`);
  }

  return response.json();
}

export function createTask(goal) {
  return request("/tasks", {
    method: "POST",
    body: JSON.stringify({ goal }),
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
