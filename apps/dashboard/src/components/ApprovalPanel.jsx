export default function ApprovalPanel({ task, onApprove, isSubmitting }) {
  const pendingApproval = task?.pending_approval;

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>
          <span className="nf-icon" aria-hidden="true">󰛯</span>
          Approval gate
        </h2>
        <p>Risky actions pause here before the agent touches anything sensitive.</p>
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
              {isSubmitting ? (
                "Applying..."
              ) : (
                <>
                  <span className="button-icon nf-icon" aria-hidden="true">󰄬</span>
                  <span>Approve and apply</span>
                </>
              )}
            </button>
            <button
              className="secondary-button"
              disabled={isSubmitting}
              onClick={() => onApprove(task.id, false)}
            >
              <span className="button-icon nf-icon" aria-hidden="true">󰅖</span>
              <span>Decline</span>
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
