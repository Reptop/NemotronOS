import { useEffect, useMemo, useState } from "react";

import { approveTask, createTask, fetchEvents, fetchHealth, fetchTasks } from "./api.js";
import ApprovalPanel from "./components/ApprovalPanel.jsx";
import EventTimeline from "./components/EventTimeline.jsx";
import StatusBar from "./components/StatusBar.jsx";
import TaskList from "./components/TaskList.jsx";

const DEFAULT_GOAL =
  "Organize my Downloads folder into folders by file type, but show me the plan first.";

export default function App() {
  const [goal, setGoal] = useState(DEFAULT_GOAL);
  const [tasks, setTasks] = useState([]);
  const [events, setEvents] = useState([]);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");
  const [selectedTaskId, setSelectedTaskId] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isApproving, setIsApproving] = useState(false);

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
