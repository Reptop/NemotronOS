export default function EventTimeline({ events }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Event Timeline</h2>
        <p>Every major state change and tool call is captured for the demo.</p>
      </div>

      {!events.length ? (
        <div className="empty-state">
          <p>No events yet.</p>
        </div>
      ) : (
        <ul className="event-list">
          {events.map((event) => (
            <li key={event.id} className="event-row">
              <div className="event-row-top">
                <strong>{event.type}</strong>
                <span>{new Date(event.created_at).toLocaleTimeString()}</span>
              </div>
              <p>{event.task_id || "global"}</p>
              <pre>{JSON.stringify(event.details, null, 2)}</pre>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
