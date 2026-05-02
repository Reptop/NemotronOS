function StatusPill({ label, value, tone = "neutral" }) {
  return (
    <div className={`status-pill tone-${tone}`}>
      <span className="status-pill-label">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default function StatusBar({ health, tasks }) {
  const waitingCount = tasks.filter(
    (task) => task.state === "waiting_for_approval",
  ).length;
  const activeCount = tasks.filter(
    (task) => !["completed", "failed", "cancelled"].includes(task.state),
  ).length;

  return (
    <section className="panel status-bar">
      <StatusPill
        label="Agent"
        value={health?.status || "offline"}
        tone={health?.status === "ok" ? "good" : "bad"}
      />
      <StatusPill
        label="Model"
        value={health?.model_mode || "unknown"}
        tone="neutral"
      />
      <StatusPill
        label="Tool Mode"
        value={health?.tool_server?.tool_mode || "unknown"}
        tone="neutral"
      />
      <StatusPill
        label="Active Tasks"
        value={String(activeCount)}
        tone={activeCount > 0 ? "good" : "neutral"}
      />
      <StatusPill
        label="Approvals"
        value={String(waitingCount)}
        tone={waitingCount > 0 ? "warn" : "neutral"}
      />
    </section>
  );
}
