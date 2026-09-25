import { useEffect, useState } from "react";
import { fetchPhoto } from "../api.js";
import { DetectionOverlay, DeviationList, StatusBadge } from "../components/Shared.jsx";

export default function PhotoPage({ photoId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setError(null);
    fetchPhoto(photoId)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [photoId]);

  if (error) return <p className="status-line error">{error}</p>;
  if (!data) return <p className="muted">Загрузка…</p>;

  const { photo, day_report: day, site } = data;
  const overlay = {
    width: photo.width,
    height: photo.height,
    detections: photo.detections || [],
  };

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="crumb">
            {site && <a href={`#/site/${site.id}`}>{site.name}</a>}
            {site && " / "}
            снимок
          </p>
          <h1>{photo.filename}</h1>
          <p className="subtitle mono">дата съёмки: {photo.captured_at}</p>
        </div>
        <StatusBadge status={day?.project_status || day?.plan_status} />
      </header>

      <div className="layout">
        <section className="panel">
          <div className="viewer">
            <img src={`/api/photos/${photo.id}/file`} alt={photo.filename} />
            <DetectionOverlay result={overlay} />
          </div>
        </section>

        <aside className="side">
          <div className="panel">
            <h3>Вывод ML</h3>
            <ul className="det-list">
              {(photo.detections || []).map((d, i) => (
                <li key={i}>
                  <span className="swatch" style={{ background: d.color }} />
                  {d.label} {(d.confidence * 100).toFixed(0)}%
                </li>
              ))}
              {!photo.detections?.length && <li className="muted">Нет детекций</li>}
            </ul>
          </div>

          <div className="panel">
            <h3>Алгоритм на дату</h3>
            <p>
              <span className="muted">План:</span>{" "}
              {day?.planned_stages?.map((s) => s.stage_label).join(", ") || "—"}
            </p>
            <p>
              <span className="muted">Факт:</span> {day?.primary_stage_label || "—"}
            </p>
            <DeviationList deviations={day?.deviations || []} />
          </div>
        </aside>
      </div>
    </div>
  );
}
