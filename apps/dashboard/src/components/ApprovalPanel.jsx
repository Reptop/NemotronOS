export default function ApprovalPanel({ task, onApprove, isSubmitting }) {
  const pendingApproval = task?.pending_approval;

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Approval Gate</h2>
        <p>Medium and high risk actions stop here before the agent can continue.</p>
      </div>

      {!task ? (
        <div className="empty-state">
          <p>Select a task to inspect its approval state.</p>
        </div>
      ) : null}

      {task && !pendingApproval ? (
        <div className="empty-state">
          <p>No approval is required for the selected task right now.</p>
        </div>
      ) : null}

      {pendingApproval ? (
        <div className="approval-card">
          <span className={`badge badge-${pendingApproval.risk_level}`}>
            {pendingApproval.risk_level} risk
          </span>
          <h3>{pendingApproval.tool_name}</h3>
          <p>{pendingApproval.reason}</p>
          <pre>{JSON.stringify(pendingApproval.arguments, null, 2)}</pre>
          <div className="approval-actions">
            <button
              className="primary-button"
              disabled={isSubmitting}
              onClick={() => onApprove(task.id, true)}
            >
              {isSubmitting ? "Applying..." : "Approve and apply"}
            </button>
            <button
              className="secondary-button"
              disabled={isSubmitting}
              onClick={() => onApprove(task.id, false)}
            >
              Decline
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
