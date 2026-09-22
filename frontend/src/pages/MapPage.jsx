import { useEffect, useMemo, useState } from "react";
import { MapContainer, TileLayer, Popup, CircleMarker } from "react-leaflet";
import { fetchSites } from "../api.js";
import { StatusBadge } from "../components/Shared.jsx";
import "leaflet/dist/leaflet.css";

const STATUS_ORDER = ["idle", "warning", "ok", "info", "no_data"];

export default function MapPage() {
  const [sites, setSites] = useState([]);
  const [statuses, setStatuses] = useState([]);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState(null);

  useEffect(() => {
    fetchSites()
      .then((d) => {
        setSites(d.sites || []);
        setStatuses(d.statuses || []);
      })
      .catch((e) => setError(e.message));
  }, []);

  const visible = useMemo(() => {
    if (!filter) return sites;
    return sites.filter((s) => s.last_status === filter);
  }, [sites, filter]);

  const center = [55.75, 37.62];

  const legend = statuses.length
    ? statuses
    : STATUS_ORDER.map((code) => ({
        code,
        label: code,
        color: "#888",
      }));

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Карта и список ЖК</h1>
          <p className="subtitle">
            Одни и те же объекты: маркеры на карте = строки списка. Комментарий — по
            бизнес-логике статусов.
          </p>
        </div>
      </header>

      {error && <p className="status-line error">{error}</p>}

      <section className="panel legend-bar">
        <h2>Легенда статусов</h2>
        <div className="status-legend">
          {legend.map((s) => (
            <button
              key={s.code}
              type="button"
              className={`legend-chip ${filter === s.code ? "active" : ""}`}
              onClick={() => setFilter((f) => (f === s.code ? null : s.code))}
              title={s.description || s.label}
            >
              <span className="dot" style={{ background: s.color }} />
              {s.label}
              <span className="mono muted">
                {sites.filter((x) => x.last_status === s.code).length}
              </span>
            </button>
          ))}
          {filter && (
            <button type="button" className="btn ghost sm" onClick={() => setFilter(null)}>
              Сбросить фильтр
            </button>
          )}
        </div>
      </section>

      <div className="map-frame panel">
        <MapContainer center={center} zoom={10} style={{ height: 420, width: "100%" }}>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {visible.map((s) => {
            const color = s.last_status_color || "#6C757D";
            return (
              <CircleMarker
                key={s.id}
                center={[s.lat, s.lng]}
                radius={12}
                pathOptions={{
                  color,
                  fillColor: color,
                  fillOpacity: 0.85,
                  weight: 2,
                }}
              >
                <Popup>
                  <strong>{s.name}</strong>
                  <br />
                  <StatusBadge status={s.last_status} />
                  <br />
                  <span style={{ fontSize: 12, color: "#444" }}>
                    {(s.comment || s.scenario || "").slice(0, 160)}
                    {(s.comment || "").length > 160 ? "…" : ""}
                  </span>
                  <br />
                  <a href={`#/site/${s.id}`}>Открыть карточку</a>
                </Popup>
              </CircleMarker>
            );
          })}
        </MapContainer>
      </div>

      <section className="panel">
        <h2>Список ЖК ({visible.length}) — те же объекты, что на карте</h2>
        <ul className="site-list rich">
          {visible.map((s) => (
            <li key={s.id}>
              {s.thumb_url ? (
                <a href={`#/site/${s.id}`} className="site-thumb">
                  <img src={s.thumb_url} alt={s.name} />
                </a>
              ) : (
                <div className="site-thumb empty">нет фото</div>
              )}
              <div className="site-body">
                <a href={`#/site/${s.id}`}>
                  <strong>{s.name}</strong>
                </a>
                <div className="muted">{s.address}</div>
                <p className="site-comment">{s.comment || s.scenario || "—"}</p>
              </div>
              <div className="site-meta">
                <StatusBadge status={s.last_status} />
                <span className="mono muted">{s.last_date || "—"}</span>
                <span className="mono muted">{s.photos_count || 0} фото</span>
              </div>
            </li>
          ))}
          {!visible.length && !error && (
            <li className="muted">Нет объектов для выбранного фильтра</li>
          )}
        </ul>
      </section>
    </div>
  );
}
