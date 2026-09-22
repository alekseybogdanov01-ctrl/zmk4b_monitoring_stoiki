import { useEffect, useState } from "react";
import {
  fetchSite,
  fetchTimeline,
  uploadSitePhoto,
  uploadSitePlan,
} from "../api.js";
import { DeviationList, TimelineTable, StatusBadge } from "../components/Shared.jsx";

export default function SitePage({ siteId }) {
  const [site, setSite] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [selectedDay, setSelectedDay] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [capturedAt, setCapturedAt] = useState(new Date().toISOString().slice(0, 10));

  const reload = async () => {
    const [s, t] = await Promise.all([fetchSite(siteId), fetchTimeline(siteId)]);
    setSite(s);
    setTimeline(t.timeline || []);
  };

  useEffect(() => {
    setError(null);
    reload().catch((e) => setError(e.message));
  }, [siteId]);

  const onPlan = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await uploadSitePlan(siteId, file);
      await reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const onPhoto = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await uploadSitePhoto(siteId, file, capturedAt);
      await reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  };

  if (!site && !error) return <p className="muted">Загрузка…</p>;

  const statusCode = site?.project_status?.status || site?.seed_status;

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="crumb">
            <a href="#/map">Карта / список</a> / объект
          </p>
          <h1>{site?.name || "Объект"}</h1>
          <p className="subtitle">{site?.address}</p>
        </div>
        <StatusBadge status={statusCode} />
      </header>

      {error && <p className="status-line error">{error}</p>}

      {site?.comment && (
        <section className="panel comment-panel">
          <h2>Комментарий (бизнес-логика)</h2>
          <p className="site-comment">{site.comment}</p>
        </section>
      )}

      {(site?.photos || []).length > 0 && (
        <section className="panel">
          <h2>Тестовые / загруженные снимки</h2>
          <div className="photo-grid">
            {site.photos.map((p) => (
              <a key={p.id} href={`#/photo/${p.id}`} className="photo-card">
                <img src={p.file_url} alt={p.filename} />
                <span className="mono">{p.captured_at}</span>
              </a>
            ))}
          </div>
        </section>
      )}

      <section className="panel upload-grid">
        <div>
          <h2>Календарный план</h2>
          <input type="file" accept=".csv,.xlsx,.xls" disabled={busy} onChange={onPlan} />
          <ul className="plan-list">
            {(site?.plan || []).map((p, i) => (
              <li key={i}>
                <strong>{p.stage_code}</strong> {p.date_from} → {p.date_to}
                {p.zone ? ` · ${p.zone}` : ""}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h2>Добавить снимок</h2>
          <label className="field">
            <span>Дата съёмки</span>
            <input
              type="date"
              value={capturedAt}
              onChange={(e) => setCapturedAt(e.target.value)}
            />
          </label>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp,image/bmp"
            disabled={busy}
            onChange={onPhoto}
          />
        </div>
      </section>

      <section className="panel">
        <h2>Таймлайн</h2>
        <TimelineTable
          timeline={timeline}
          onSelectDay={(d) => setSelectedDay(d)}
          onOpenPhoto={(id) => {
            window.location.hash = `#/photo/${id}`;
          }}
        />
      </section>

      {selectedDay && (
        <section className="panel">
          <div className="panel-head">
            <h2>День {selectedDay.date}</h2>
            <StatusBadge status={selectedDay.project_status || selectedDay.plan_status} />
          </div>
          <DeviationList
            deviations={(selectedDay.deviations || []).map((d) => ({
              ...d,
              date: selectedDay.date,
            }))}
          />
          <div className="photo-links">
            {(selectedDay.photo_ids || []).map((id) => (
              <a key={id} className="btn ghost sm" href={`#/photo/${id}`}>
                Снимок {id.slice(0, 8)}
              </a>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
