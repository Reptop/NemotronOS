function StatusPill({ icon, label, value, tone = "neutral" }) {
  return (
    <div className={`status-pill tone-${tone}`}>
      <span className="status-pill-icon nf-icon" aria-hidden="true">
        {icon}
      </span>
      <span className="status-pill-copy">
        <span className="status-pill-label">{label}</span>
        <strong>{value}</strong>
      </span>
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
    <section className="status-bar" aria-label="System status">
      <StatusPill
        icon="󰚩"
        label="Agent"
        value={health?.status || "offline"}
        tone={health?.status === "ok" ? "good" : "bad"}
      />
      <StatusPill
        icon="󰍛"
        label="Model"
        value={health?.model_mode || "unknown"}
        tone="neutral"
      />
      <StatusPill
        icon="󰒓"
        label="Tool Mode"
        value={health?.tool_server?.tool_mode || "unknown"}
        tone="neutral"
      />
      <StatusPill
        icon="󰄬"
        label="Active Tasks"
        value={String(activeCount)}
        tone={activeCount > 0 ? "good" : "neutral"}
      />
      <StatusPill
        icon="󰛯"
        label="Approvals"
        value={String(waitingCount)}
        tone={waitingCount > 0 ? "warn" : "neutral"}
      />
    </section>
  );
}
