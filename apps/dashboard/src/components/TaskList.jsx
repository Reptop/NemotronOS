function RiskBadge({ level }) {
  if (!level) {
    return <span className="badge badge-neutral">No risk</span>;
  }

  return <span className={`badge badge-${level}`}>{level}</span>;
}

function ChangePreview({ change }) {
  if (change.operation === "mkdir") {
    return (
      <li className="change-row">
        <span className="change-op">mkdir</span>
        <code>{change.path}</code>
      </li>
    );
  }

  return (
    <li className="change-row">
      <span className="change-op">move</span>
      <code>{change.source}</code>
      <span className="change-arrow">→</span>
      <code>{change.destination}</code>
    </li>
  );
}

export default function TaskList({ tasks, selectedTaskId, onSelectTask }) {
  if (!tasks.length) {
    return (
      <section className="panel">
        <div className="empty-state">
          <h2>Task queue</h2>
          <p>Submit the Downloads organizer prompt to kick off the first demo.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>
          <span className="nf-icon" aria-hidden="true">󰄬</span>
          Task queue
        </h2>
        <p>Planning, approval, and completion stay visible as the agent works.</p>
      </div>
      <div className="task-list">
        {tasks.map((task) => (
          <article
            key={task.id}
            className={`task-card ${task.id === selectedTaskId ? "selected" : ""}`}
            onClick={() => onSelectTask(task.id)}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                onSelectTask(task.id);
              }
            }}
          >
            <div className="task-card-top">
              <div>
                <p className="task-goal">{task.goal}</p>
                <small>{task.id}</small>
              </div>
              <div className="task-meta">
                <span className={`badge badge-state badge-${task.state}`}>
                  {task.state}
                </span>
                <RiskBadge level={task.risk_level} />
              </div>
            </div>

            {task.plan_preview?.length ? (
              <div className="task-plan">
                <p className="task-plan-title">Plan preview</p>
                <ul className="changes-list">
                  {task.plan_preview.slice(0, 5).map((change, index) => (
                    <ChangePreview key={`${task.id}-${index}`} change={change} />
                  ))}
                </ul>
              </div>
            ) : null}

            {task.result?.undo_log_path ? (
              <p className="task-result">Undo log: {task.result.undo_log_path}</p>
            ) : null}

            {task.error ? <p className="task-error">{task.error}</p> : null}
          </article>
        ))}
      </div>
    </section>
  );
}
