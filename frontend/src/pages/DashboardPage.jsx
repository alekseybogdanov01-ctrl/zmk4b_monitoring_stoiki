import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { downloadSitesExcel, fetchDashboard } from "../api.js";
import { StatusBadge } from "../components/Shared.jsx";
import AddSiteDialog from "../components/AddSiteDialog.jsx";
import CameraWall from "../components/CameraWall.jsx";
import SitesMap from "../components/SitesMap.jsx";
import { useCountUp, useRevealed } from "../motion.js";

const DEVIATION_HINT = {
  missing_required: "по плану этап идёт, техники нет",
  incomplete_link: "техника есть, звено разорвано",
  unexpected_equipment: "на площадке техника другого этапа",
};

function countOf(byStatus, code) {
  return byStatus.find((s) => s.code === code)?.count ?? 0;
}

/** Карточка показателя: число набирается от нуля, клик фильтрует портфель. */
function KpiCard({ value, label, accent, delay = 0, active = false, title, onClick }) {
  const shown = useCountUp(value);
  return (
    <button
      type="button"
      className={`db-kpi-card ${accent} db-rise ${active ? "active" : ""}`}
      style={{ "--d": delay }}
      title={title}
      aria-pressed={active}
      onClick={onClick}
    >
      <strong>{shown}</strong>
      <span>{label}</span>
    </button>
  );
}

/** Кольцо покрытия съёмкой: дуга дорисовывается при появлении. */
function CoverageGauge({ value, total, active = false, onClick }) {
  const revealed = useRevealed(140);
  const share = total ? value / total : 0;
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const percent = useCountUp(Math.round(share * 100));

  return (
    <button
      type="button"
      className={`db-gauge ${active ? "active" : ""}`}
      title="Показать объекты, по которым пришли кадры"
      aria-pressed={active}
      onClick={onClick}
    >
      <svg viewBox="0 0 128 128" aria-hidden="true">
        <circle className="db-gauge-track" cx="64" cy="64" r={radius} />
        <circle
          className="db-gauge-value"
          cx="64"
          cy="64"
          r={radius}
          style={{
            strokeDasharray: circumference,
            strokeDashoffset: revealed ? circumference * (1 - share) : circumference,
          }}
        />
      </svg>
      <span className="db-gauge-body">
        <strong>{percent}%</strong>
        <span>
          {value} из {total} объектов
          <br />
          прислали кадры
        </span>
      </span>
    </button>
  );
}

function siteMatches(site, filter) {
  if (!filter) return true;
  if (filter === "attention") return site.status === "idle" || site.status === "warning";
  if (filter === "covered") return (site.photos_count || 0) > 0;
  if (filter === "deviations") return (site.deviations_count || 0) > 0;
  return site.status === filter;
}

function compact(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[\s:.\-—]/g, "");
}

function siteMatchesQuery(site, query) {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const qCompact = compact(q);
  return [site.name, site.address, site.cadastral_number].some((value) => {
    const text = String(value || "").toLowerCase();
    if (text.includes(q)) return true;
    return qCompact.length >= 3 && compact(text).includes(qCompact);
  });
}

const FILTER_CAPTION = {
  attention: "требуют внимания",
  covered: "прислали кадры",
  deviations: "с отклонениями",
};

const DEVIATION_COLOR = {
  missing_required: "#ef5666",
  incomplete_link: "#efab51",
  unexpected_equipment: "#8ed44a",
};

function polar(cx, cy, radius, angle) {
  const rad = ((angle - 90) * Math.PI) / 180;
  return [cx + radius * Math.cos(rad), cy + radius * Math.sin(rad)];
}

function withShares(items) {
  const total = items.reduce((sum, item) => sum + item.value, 0) || 1;
  let cursor = 0;
  let used = 0;
  return items.map((item, index) => {
    const sweep = (item.value / total) * 360;
    const start = cursor;
    const end = cursor + sweep;
    cursor = end;
    const pct =
      index === items.length - 1
        ? Math.max(0, 100 - used)
        : Math.round((item.value / total) * 100);
    used += pct;
    return { ...item, start, end, pct };
  });
}

function slicePath(start, end) {
  const [x1, y1] = polar(100, 100, 78, start);
  const [x2, y2] = polar(100, 100, 78, end);
  const large = end - start > 180 ? 1 : 0;
  return `M 100 100 L ${x1} ${y1} A 78 78 0 ${large} 1 ${x2} ${y2} Z`;
}

function PieChart({ slices, onPick, isDimmed }) {
  const drawn = withShares(slices.filter((item) => item.value > 0));
  if (!drawn.length) return <p className="muted">Нет данных для диаграммы</p>;
  const anyDimmed = drawn.some((slice) => isDimmed?.(slice.code));

  return (
    <div className="db-pie">
      <svg viewBox="0 0 200 200" role="img" aria-label="Круговая диаграмма">
        {drawn.map((slice) => {
          const full = slice.end - slice.start >= 359.99;
          const [lx, ly] = polar(100, 100, 48, slice.start + (slice.end - slice.start) / 2);
          return (
            <g
              key={slice.code}
              opacity={isDimmed?.(slice.code) ? 0.35 : 1}
              onClick={onPick ? () => onPick(slice.code) : undefined}
              style={{ cursor: onPick ? "pointer" : "default" }}
            >
              {full ? (
                <circle cx="100" cy="100" r="78" fill={slice.color} />
              ) : (
                <path d={slicePath(slice.start, slice.end)} fill={slice.color} />
              )}
              {slice.pct >= 8 && (
                <text
                  className="db-pie-label"
                  x={lx}
                  y={ly}
                  textAnchor="middle"
                  dominantBaseline="middle"
                >
                  {slice.pct}%
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <ul className="db-pie-legend">
        {drawn.map((slice) => {
          const body = (
            <>
              <span className="dot" style={{ background: slice.color }} />
              <span>
                <span className="db-pie-name">{slice.label}</span>
                {slice.hint ? <span className="db-pie-hint">{slice.hint}</span> : null}
              </span>
              <b className="db-pie-pct">
                {slice.pct}% <span className="muted">{slice.value}</span>
              </b>
            </>
          );
          return (
            <li key={slice.code}>
              {onPick ? (
                <button
                  type="button"
                  className={anyDimmed && !isDimmed(slice.code) ? "active" : ""}
                  onClick={() => onPick(slice.code)}
                >
                  {body}
                </button>
              ) : (
                <div className="db-pie-row">{body}</div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState(null);
  const [query, setQuery] = useState("");
  const [listQuery, setListQuery] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [freshId, setFreshId] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");
  const mapRef = useRef(null);
  const closeAdd = useCallback(() => setAddOpen(false), []);

  useEffect(() => {
    let alive = true;
    fetchDashboard()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (addOpen || !freshId) return;
    document.getElementById(`site-${freshId}`)?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
  }, [addOpen, freshId, data]);

  const revealed = useRevealed();

  const maxStage = useMemo(() => {
    if (!data?.by_stage?.length) return 1;
    return Math.max(...data.by_stage.map((s) => s.planned), 1);
  }, [data]);

  if (error) return <p className="status-line error">{error}</p>;

  if (!data) {
    return (
      <div className="page db">
        <header className="page-head">
          <div>
            <h1>Контроль строительства</h1>
            <p className="subtitle">Собираем сводку по объектам…</p>
          </div>
        </header>
        <div className="db-skeleton" />
      </div>
    );
  }

  const t = data.totals;
  const idle = countOf(data.by_status, "idle");
  const warning = countOf(data.by_status, "warning");
  const visibleStatuses = data.by_status.filter((s) => s.count > 0);
  const queryText = query.trim();
  const listQueryText = listQuery.trim();
  const wall = data.sites.filter((s) => siteMatches(s, filter) && siteMatchesQuery(s, query));
  const registry = data.sites
    .filter((s) => s.address !== "Демо" && s.id !== "demo" && s.name !== "ДЕМО")
    .filter((s) => siteMatches(s, filter) && siteMatchesQuery(s, listQuery))
    .slice()
    .sort((a, b) => (a.object_no || 0) - (b.object_no || 0));
  const activeStatus = data.by_status.find((s) => s.code === filter);

  const scrollToMap = () => {
    mapRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const toggleFilter = (code) => {
    setFilter((prev) => (prev === code ? null : code));
    scrollToMap();
  };

  const showAll = () => {
    setFilter(null);
    scrollToMap();
  };

  const statusOn = (code) =>
    filter === code || (filter === "attention" && (code === "idle" || code === "warning"));

  const filterCaption = activeStatus
    ? `показаны только «${activeStatus.label}» — ${wall.length} из ${t.sites}`
    : filter
      ? `показаны объекты, которые ${FILTER_CAPTION[filter]} — ${wall.length} из ${t.sites}`
      : queryText
        ? `по запросу «${queryText}» — ${wall.length} из ${t.sites}`
        : null;

  return (
    <div className="page db">
      <header className="page-head">
        <div>
          <h1>Контроль строительства</h1>
        </div>
      </header>

      <section className="db-kpi">
        <article
          className={`db-hero ${t.attention ? "alert" : "calm"} ${filter === "attention" ? "is-active" : ""}`}
        >
          <div className="db-hero-main">
            <button
              type="button"
              className="db-hero-hit"
              title="Показать объекты, где факт расходится с планом"
              aria-pressed={filter === "attention"}
              onClick={() => toggleFilter("attention")}
            >
              <span className="db-hero-label">Требуют внимания</span>
              <HeroNumber value={t.attention} />
              <span className="db-hero-claim">
                {t.attention
                  ? `На ${t.attention} из ${t.sites} объектов факт с камер расходится с календарным планом`
                  : "Расхождений факта с планом не выявлено"}
              </span>
            </button>
            <div className="db-hero-split">
              <button
                type="button"
                className={`db-chip idle ${statusOn("idle") ? "active" : ""}`}
                onClick={() => toggleFilter("idle")}
              >
                Простой <b>{idle}</b>
              </button>
              <button
                type="button"
                className={`db-chip warn ${statusOn("warning") ? "active" : ""}`}
                onClick={() => toggleFilter("warning")}
              >
                Возможное нарушение <b>{warning}</b>
              </button>
            </div>
          </div>
          <CoverageGauge
            value={t.with_data}
            total={t.sites}
            active={filter === "covered"}
            onClick={() => toggleFilter("covered")}
          />
        </article>

        <div className="db-kpi-side">
          <KpiCard
            value={t.deviations}
            label="отклонений зафиксировано"
            accent="accent-danger"
            delay={0}
            active={filter === "deviations"}
            title="Показать объекты с отклонениями"
            onClick={() => toggleFilter("deviations")}
          />
          <KpiCard
            value={t.sites}
            label="объектов под наблюдением"
            accent="accent-info"
            delay={1}
            title="Показать все объекты"
            onClick={showAll}
          />
          <KpiCard
            value={t.without_data}
            label="объекта без съёмки"
            accent="accent-muted"
            delay={2}
            active={filter === "no_data"}
            title="Показать объекты без съёмки"
            onClick={() => toggleFilter("no_data")}
          />
          <KpiCard
            value={t.ok}
            label="объекта в норме"
            accent="accent-ok"
            delay={3}
            active={filter === "ok"}
            title="Показать объекты в норме"
            onClick={() => toggleFilter("ok")}
          />
        </div>
      </section>

      <section className="panel db-map" ref={mapRef}>
        <div className="db-section-head">
          <h2>Карта и список ЖК</h2>
          {filterCaption && <span className="muted">{filterCaption}</span>}
          <div className="db-head-actions">
            {(filter || queryText) && (
              <button
                type="button"
                className="btn ghost sm"
                onClick={() => {
                  setFilter(null);
                  setQuery("");
                }}
              >
                Сбросить
              </button>
            )}
            <button type="button" className="btn sm" onClick={() => setAddOpen(true)}>
              Добавить объект
            </button>
          </div>
        </div>
        <label className="db-search">
          <span>Поиск стройки</span>
          <input
            type="search"
            value={query}
            placeholder="Название, адрес или кадастровый номер"
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <div className="status-legend">
          {data.by_status.map((s) => (
            <button
              key={s.code}
              type="button"
              className={`legend-chip ${statusOn(s.code) ? "active" : ""}`}
              onClick={() => toggleFilter(s.code)}
              disabled={!s.count}
              title={s.description || s.label}
            >
              <span className="dot" style={{ background: s.color }} />
              {s.label}
              <span className="mono muted">{s.count}</span>
            </button>
          ))}
        </div>
        <div className="db-map-split">
          <div className="map-frame">
            <SitesMap sites={wall} height="100%" />
          </div>
          <ul className="db-map-list">
            {wall.map((s) => (
              <li key={s.id}>
                {s.thumb_url ? (
                  <a href={`#/site/${s.id}`} className="db-map-thumb">
                    <img src={s.thumb_url} alt="" />
                  </a>
                ) : (
                  <div className="db-map-thumb empty">нет фото</div>
                )}
                <div className="db-map-item-body">
                  <a href={`#/site/${s.id}`}>
                    <strong>{s.name}</strong>
                  </a>
                  <div className="muted">{s.address}</div>
                  {s.cadastral_number && (
                    <div className="mono muted">{s.cadastral_number}</div>
                  )}
                  <p className="db-map-item-note">
                    {s.comment || s.top_deviation?.message || s.status_description || "—"}
                  </p>
                </div>
                <div className="db-map-item-meta">
                  <StatusBadge status={s.status} />
                  <span className="mono muted">{s.last_date || "—"}</span>
                  <span className="mono muted">{s.photos_count || 0} фото</span>
                </div>
              </li>
            ))}
            {!wall.length && (
              <li className="muted">
                {queryText ? "Стройка не найдена" : "Нет объектов для выбранного фильтра"}
              </li>
            )}
          </ul>
        </div>
      </section>

      <CameraWall sites={wall} />

      <div className="db-split">
        <section className="panel">
          <div className="db-section-head">
            <h2>Структура по статусам строительства</h2>
            <span className="muted">нажмите сектор, чтобы отфильтровать объекты</span>
          </div>
          <PieChart
            slices={visibleStatuses.map((s) => ({
              code: s.code,
              label: s.label,
              value: s.count,
              color: s.color,
            }))}
            onPick={toggleFilter}
            isDimmed={(code) =>
              Boolean(
                filter &&
                  filter !== "covered" &&
                  filter !== "deviations" &&
                  !statusOn(code),
              )
            }
          />
        </section>

        <section className="panel">
          <div className="db-section-head">
            <h2>Причины нарушений</h2>
            <span className="muted">доля каждого типа среди всех отклонений</span>
          </div>
          <PieChart
            slices={(data.by_deviation || []).map((d) => ({
              code: d.type,
              label: d.label,
              value: d.count,
              color: DEVIATION_COLOR[d.type] || "#6c7a8c",
              hint: DEVIATION_HINT[d.type] || "",
            }))}
          />
        </section>
      </div>

      <section className="panel">
        <div className="db-section-head">
          <h2>Этапы работ</h2>
          <span className="muted">
            сколько объектов должно быть на этапе по плану и на скольких это подтверждено
            съёмкой
          </span>
        </div>
        <ul className="db-stages">
          {data.by_stage.map((s) => (
            <li key={s.code}>
              <span className="db-stage-name">{s.label}</span>
              <div className="db-stage-track">
                <div
                  className="db-stage-planned"
                  style={{ width: revealed ? `${(s.planned / maxStage) * 100}%` : "0%" }}
                />
                <div
                  className="db-stage-confirmed"
                  style={{
                    width: revealed ? `${(s.confirmed / maxStage) * 100}%` : "0%",
                  }}
                />
              </div>
              <span className="db-stage-num mono">
                {s.confirmed} / {s.planned}
              </span>
            </li>
          ))}
        </ul>
        <p className="db-stage-key">
          <span className="db-key planned" /> по плану
          <span className="db-key confirmed" /> подтверждено камерой
        </p>
      </section>

      <section className="panel" id="all-sites">
        <div className="db-section-head">
          <h2>Все объекты ({registry.length})</h2>
          <div className="db-head-actions">
            {filter && (
              <button type="button" className="btn ghost sm" onClick={() => setFilter(null)}>
                Показать все
              </button>
            )}
            <button type="button" className="btn sm" onClick={() => setAddOpen(true)}>
              Добавить объект
            </button>
            <button
              type="button"
              className="btn ghost sm"
              disabled={exporting}
              onClick={async () => {
                setExporting(true);
                setExportError("");
                try {
                  await downloadSitesExcel();
                } catch (err) {
                  setExportError(err.message || "Не удалось выгрузить файл");
                } finally {
                  setExporting(false);
                }
              }}
            >
              {exporting ? "Готовим файл…" : "Выгрузить в Excel"}
            </button>
          </div>
        </div>
        <label className="db-search">
          <span>Поиск стройки</span>
          <input
            type="search"
            value={listQuery}
            placeholder="Название, адрес или кадастровый номер"
            onChange={(event) => setListQuery(event.target.value)}
          />
        </label>
        {listQueryText && (
          <p className="muted db-list-note">
            по запросу «{listQueryText}» — {registry.length} из {t.sites}
          </p>
        )}
        {exportError && <p className="status-line error">{exportError}</p>}
        <div className="db-table-wrap">
          <table className="db-table">
            <thead>
              <tr>
                <th>№</th>
                <th>Название</th>
                <th>Адрес</th>
                <th>Кадастровый номер</th>
                <th>Статус</th>
                <th>План</th>
                <th>Факт</th>
                <th>Съёмка</th>
              </tr>
            </thead>
            <tbody>
              {registry.map((s) => (
                <tr
                  key={s.id}
                  id={`site-${s.id}`}
                  className={s.id === freshId ? "is-new" : ""}
                  onClick={() => {
                    window.location.hash = `#/site/${s.id}`;
                  }}
                >
                  <td className="mono">{s.object_no || "—"}</td>
                  <td className="db-table-name">{s.name}</td>
                  <td>{s.address || "—"}</td>
                  <td className="mono">{s.cadastral_number || "—"}</td>
                  <td>
                    <StatusBadge status={s.status} />
                  </td>
                  <td>
                    {s.planned_stages?.length
                      ? s.planned_stages.map((p) => p.label).join(", ")
                      : "—"}
                  </td>
                  <td>{s.fact_stage_label || "—"}</td>
                  <td className="mono">{s.last_date || "нет"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!registry.length && (
            <p className="muted">
              {listQueryText ? "Стройка не найдена" : "Объектов с таким статусом нет"}
            </p>
          )}
        </div>
      </section>
      <AddSiteDialog
        open={addOpen}
        sites={data.sites}
        onClose={closeAdd}
        onCreated={async (site) => {
          setFreshId(site.id);
          setFilter(null);
          setQuery("");
          setListQuery("");
          const next = await fetchDashboard();
          setData(next);
          return next;
        }}
      />
    </div>
  );
}

/** Крупное число героя вынесено отдельно ради собственного счётчика. */
function HeroNumber({ value }) {
  const shown = useCountUp(value, 1100);
  return <strong className="db-hero-num">{shown}</strong>;
}
