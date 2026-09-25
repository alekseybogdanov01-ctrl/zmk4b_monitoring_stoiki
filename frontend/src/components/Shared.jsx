import { useMemo, useState } from "react";

/** Раскладка подписей: внутри кадра и без наложений друг на друга. */
function layoutLabels(detections, width, height, fontSize) {
  const padX = fontSize * 0.35;
  const boxHeight = fontSize * 1.45;
  const placed = [];

  return detections.map((d) => {
    const [x1, y1] = d.bbox || [0, 0, 0, 0];
    const text = `${d.label || d.class || d.class_code} ${Math.round(
      (d.confidence || 0) * 100,
    )}%`;
    const boxWidth = Math.min(width, text.length * fontSize * 0.62 + padX * 2);

    const x = Math.min(Math.max(0, x1), Math.max(0, width - boxWidth));
    const above = y1 - boxHeight;
    let y = above >= 0 ? above : Math.min(Math.max(0, y1), height - boxHeight);

    const overlaps = (candidate) =>
      placed.some(
        (p) =>
          x + boxWidth > p.x &&
          p.x + p.width > x &&
          candidate + boxHeight > p.y &&
          p.y + boxHeight > candidate,
      );

    let guard = 0;
    while (overlaps(y) && guard < 40 && y + boxHeight * 2 <= height) {
      y += boxHeight + fontSize * 0.15;
      guard += 1;
    }

    const slot = { x, y, width: boxWidth, height: boxHeight, text, color: d.color };
    placed.push(slot);
    return slot;
  });
}

/** `fit="cover"` — как object-fit: cover у кадра на дашборде. */
export function DetectionOverlay({ result, animated = false, fit = "contain" }) {
  const { width, height, detections } = result || {};
  if (!width || !height || !detections?.length) return null;

  const fontSize = Math.max(11, Math.min(width, height) * 0.026);
  const strokeWidth = Math.max(2, Math.min(width, height) * 0.003);
  const labels = layoutLabels(detections, width, height, fontSize);
  const slice = fit === "cover" ? "slice" : "meet";

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio={`xMidYMid ${slice}`}
    >
      {detections.map((d, i) => {
        const [x1, y1, x2, y2] = d.bbox || [0, 0, 0, 0];
        return (
          <rect
            key={`box-${i}`}
            className={animated ? "det-anim" : undefined}
            style={animated ? { "--i": i } : undefined}
            x={x1}
            y={y1}
            width={Math.max(0, x2 - x1)}
            height={Math.max(0, y2 - y1)}
            fill="none"
            stroke={d.color || "#3d9cf0"}
            strokeWidth={strokeWidth}
          />
        );
      })}
      {labels.map((slot, i) => (
        <g
          key={`label-${i}`}
          className={animated ? "det-anim" : undefined}
          style={animated ? { "--i": i } : undefined}
        >
          <rect
            x={slot.x}
            y={slot.y}
            width={slot.width}
            height={slot.height}
            rx={fontSize * 0.25}
            fill={slot.color || "#3d9cf0"}
            fillOpacity={0.92}
          />
          <text
            className="box-label"
            style={{ fontSize }}
            x={slot.x + fontSize * 0.35}
            y={slot.y + slot.height * 0.72}
          >
            {slot.text}
          </text>
        </g>
      ))}
    </svg>
  );
}

export function StatusBadge({ status }) {
  const map = {
    idle: { text: "Простой", cls: "idle" },
    warning: { text: "Возможное нарушение", cls: "warn" },
    ok: { text: "В норме", cls: "ok" },
    info: { text: "Опережение графика", cls: "info" },
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

const TIMELINE_STATUSES = [
  ["idle", "Простой"],
  ["warning", "Возможное нарушение"],
  ["info", "Опережение графика"],
  ["ok", "В норме"],
  ["no_data", "Нет данных"],
];

export function TimelineTable({ timeline, onSelectDay }) {
  const [status, setStatus] = useState("all");
  const present = useMemo(() => {
    const codes = new Set((timeline || []).map((d) => d.project_status || d.plan_status));
    return TIMELINE_STATUSES.filter(([code]) => codes.has(code));
  }, [timeline]);
  const rows =
    status === "all"
      ? timeline || []
      : (timeline || []).filter((d) => (d.project_status || d.plan_status) === status);

  if (!timeline?.length) return <p className="muted">Таймлайн пуст</p>;

  return (
    <>
      <div className="tl-filter" role="group" aria-label="Фильтр таймлайна по статусу">
        <button
          type="button"
          className={`legend-chip ${status === "all" ? "active" : ""}`}
          aria-pressed={status === "all"}
          onClick={() => setStatus("all")}
        >
          Все
          <span className="mono muted">{timeline.length}</span>
        </button>
        {present.map(([code, label]) => {
          const count = timeline.filter(
            (d) => (d.project_status || d.plan_status) === code,
          ).length;
          return (
            <button
              key={code}
              type="button"
              className={`legend-chip ${status === code ? "active" : ""}`}
              aria-pressed={status === code}
              onClick={() => setStatus((prev) => (prev === code ? "all" : code))}
            >
              {label}
              <span className="mono muted">{count}</span>
            </button>
          );
        })}
      </div>
      {rows.length ? (
        <div className="table-wrap scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Дата</th>
                <th>План</th>
                <th>Факт (этап)</th>
                <th>Статус</th>
                <th>Откл.</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((day) => (
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
                      onClick={() => onSelectDay?.(day)}
                    >
                      Открыть
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">Нет дней с выбранным статусом</p>
      )}
    </>
  );
}
