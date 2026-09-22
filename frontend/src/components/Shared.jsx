export function DetectionOverlay({ result }) {
  if (!result?.detections?.length) return null;
  const { width, height, detections } = result;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet">
      {detections.map((d, i) => {
        const [x1, y1, x2, y2] = d.bbox;
        const w = Math.max(0, x2 - x1);
        const h = Math.max(0, y2 - y1);
        const label = `${d.label || d.class} ${((d.confidence || 0) * 100).toFixed(0)}%`;
        const ty = Math.max(14, y1 - 4);
        const color = d.color || "#3d9cf0";
        return (
          <g key={`${d.class || d.class_code}-${i}`}>
            <rect
              x={x1}
              y={y1}
              width={w}
              height={h}
              fill="none"
              stroke={color}
              strokeWidth={Math.max(2, Math.min(width, height) * 0.003)}
            />
            <text className="box-label" x={x1 + 4} y={ty} fill={color}>
              {label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function StatusBadge({ status }) {
  const map = {
    idle: { text: "Простой", cls: "idle" },
    warning: { text: "Возможное нарушение", cls: "warn" },
    ok: { text: "В норме", cls: "ok" },
    info: { text: "Информация", cls: "info" },
    no_data: { text: "Нет данных", cls: "muted" },
    // legacy plan_status
    on_track: { text: "По плану", cls: "ok" },
    lag: { text: "Отставание", cls: "warn" },
    other_stage: { text: "Другой этап", cls: "info" },
    no_plan: { text: "Нет плана", cls: "muted" },
  };
  const m = map[status] || { text: status || "—", cls: "muted" };
  return <span className={`badge ${m.cls}`}>{m.text}</span>;
}

export function DeviationList({ deviations }) {
  if (!deviations?.length) {
    return <p className="muted">Отклонений не выявлено</p>;
  }
  return (
    <ul className="dev-list">
      {deviations.map((d, i) => (
        <li key={i} className={`dev-item ${d.severity || ""}`}>
          <div className="dev-head">
            <strong>{typeLabel(d.type)}</strong>
            {d.date && <span className="mono">{d.date}</span>}
            {d.zone && <span className="zone">зона: {d.zone}</span>}
          </div>
          <p>{d.message}</p>
          {d.photo_ids?.length > 0 && (
            <div className="dev-photos">
              {d.photo_ids.map((id) => (
                <a key={id} href={`#/photo/${id}`}>
                  снимок {id.slice(0, 8)}
                </a>
              ))}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

function typeLabel(t) {
  const m = {
    missing_required: "Нет необходимой техники",
    incomplete_link: "Неполное звено",
    unexpected_equipment: "Техника не под этап",
  };
  return m[t] || t;
}

export function TimelineTable({ timeline, onSelectDay, onOpenPhoto }) {
  if (!timeline?.length) return <p className="muted">Нет снимков с датами для анализа</p>;
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Дата снимка</th>
            <th>План на дату</th>
            <th>Факт (этап)</th>
            <th>Статус</th>
            <th>Откл.</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {timeline.map((day) => {
            const photoId = day.photo_ids?.[0];
            return (
              <tr key={day.date}>
                <td className="mono">{day.date}</td>
                <td>
                  {day.planned_stages?.length
                    ? day.planned_stages.map((s) => s.stage_label).join(", ")
                    : "—"}
                </td>
                <td>{day.primary_stage_label || "—"}</td>
                <td>
                  <StatusBadge status={day.project_status || day.plan_status} />
                </td>
                <td>{day.deviations?.length || 0}</td>
                <td>
                  <button
                    type="button"
                    className="btn ghost sm"
                    title={
                      photoId
                        ? "Открыть снимок: детекции ML и вывод алгоритма на эту дату"
                        : "Показать разбор по дате"
                    }
                    onClick={() => {
                      if (photoId && onOpenPhoto) {
                        onOpenPhoto(photoId, day);
                      } else if (photoId) {
                        window.location.hash = `#/photo/${photoId}`;
                      } else {
                        onSelectDay?.(day);
                      }
                    }}
                  >
                    Открыть снимок
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
