import { useEffect, useState } from "react";
import {
  fetchSite,
  fetchStages,
  fetchTimeline,
  uploadSitePhoto,
  uploadSitePlan,
} from "../api.js";
import { TimelineTable, StatusBadge } from "../components/Shared.jsx";
import FileField from "../components/FileField.jsx";

const STAGE_ORDER = ["clearing", "excavation", "foundations", "frame", "landscaping"];

const STAGE_FALLBACK = [
  { code: "clearing", label: "Расчистка участка" },
  { code: "excavation", label: "Откопка котлована" },
  { code: "foundations", label: "Устройство фундаментов" },
  { code: "frame", label: "Монтаж каркаса, стены и перекрытия" },
  { code: "landscaping", label: "Благоустройство" },
];

// Смещения от сегодня, как в шаблоне: этапы идут по очереди и немного пересекаются.
const PREFILL_SPANS = [
  [0, 19],
  [28, 47],
  [45, 63],
  [59, 83],
  [78, 103],
];

function todayIso() {
  const date = new Date();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function addDays(iso, days) {
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  date.setDate(date.getDate() + days);
  const nextMonth = String(date.getMonth() + 1).padStart(2, "0");
  const nextDay = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${nextMonth}-${nextDay}`;
}

function sortStages(list) {
  const rank = (code) => {
    const index = STAGE_ORDER.indexOf(code);
    return index === -1 ? STAGE_ORDER.length : index;
  };
  return [...list].sort((a, b) => rank(a.code) - rank(b.code));
}

function defaultRows(stages) {
  const start = todayIso();
  return stages.map((stage, index) => {
    const [from, to] = PREFILL_SPANS[index] || [index * 21, index * 21 + 20];
    return {
      stage_code: stage.code,
      date_from: addDays(start, from),
      date_to: addDays(start, to),
    };
  });
}

function rowsFromPlan(plan) {
  return (plan || []).map((row) => ({
    stage_code: row.stage_code,
    date_from: String(row.date_from || "").slice(0, 10),
    date_to: String(row.date_to || "").slice(0, 10),
  }));
}

function rowsToFile(rows) {
  const ready = rows.filter((row) => row.stage_code && row.date_from && row.date_to);
  if (!ready.length) return null;
  const lines = ["stage,date_from,date_to"];
  for (const row of ready) {
    lines.push(`${row.stage_code},${row.date_from},${row.date_to}`);
  }
  return new File([`${lines.join("\n")}\n`], "schedule.csv", { type: "text/csv" });
}

function stageTitle(stages, code) {
  return stages.find((stage) => stage.code === code)?.label || code;
}

export default function SitePage({ siteId }) {
  const [site, setSite] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [savedNote, setSavedNote] = useState("");
  const [capturedAt, setCapturedAt] = useState(todayIso());
  const [stages, setStages] = useState(STAGE_FALLBACK);
  const [scheduleMode, setScheduleMode] = useState("editor");
  const [draftRows, setDraftRows] = useState(() => defaultRows(STAGE_FALLBACK));

  const reload = async () => {
    const [nextSite, nextTimeline] = await Promise.all([
      fetchSite(siteId),
      fetchTimeline(siteId),
    ]);
    setSite(nextSite);
    setTimeline(nextTimeline.timeline || []);
    return nextSite;
  };

  useEffect(() => {
    let alive = true;
    setError(null);
    setSavedNote("");
    setScheduleMode("editor");
    Promise.all([fetchSite(siteId), fetchTimeline(siteId), fetchStages()])
      .then(([nextSite, nextTimeline, stageData]) => {
        if (!alive) return;
        const nextStages = sortStages(stageData.stages || []);
        const catalog = nextStages.length ? nextStages : STAGE_FALLBACK;
        setStages(catalog);
        setSite(nextSite);
        setTimeline(nextTimeline.timeline || []);
        setDraftRows(
          nextSite.plan?.length ? rowsFromPlan(nextSite.plan) : defaultRows(catalog),
        );
      })
      .catch((err) => alive && setError(err.message));
    return () => {
      alive = false;
    };
  }, [siteId]);

  const updateDraft = (index, patch) => {
    setSavedNote("");
    setDraftRows((rows) => rows.map((row, rowIndex) => (
      rowIndex === index ? { ...row, ...patch } : row
    )));
  };

  const saveDraft = async () => {
    const invalid = draftRows.find(
      (row) => row.date_from && row.date_to && row.date_from > row.date_to,
    );
    if (invalid) {
      setError("Дата окончания не может быть раньше даты начала");
      return;
    }
    const file = rowsToFile(draftRows);
    if (!file) {
      setError("Укажите даты хотя бы у одного этапа");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await uploadSitePlan(siteId, file);
      const nextSite = await reload();
      setDraftRows(
        nextSite.plan?.length ? rowsFromPlan(nextSite.plan) : defaultRows(stages),
      );
      setSavedNote("График сохранён");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const onPlanFile = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    setSavedNote("");
    try {
      await uploadSitePlan(siteId, file);
      const nextSite = await reload();
      setDraftRows(
        nextSite.plan?.length ? rowsFromPlan(nextSite.plan) : defaultRows(stages),
      );
      setSavedNote("График загружен из файла");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  };

  const onPhoto = async (event) => {
    const file = event.target.files?.[0];
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
      event.target.value = "";
    }
  };

  if (!site && !error) return <p className="muted">Загрузка…</p>;

  const statusCode = site?.project_status?.status || site?.seed_status;
  const hasSavedPlan = Boolean(site?.plan?.length);

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="crumb">
            <a href="#/dashboard">Дашборд</a> / объект
          </p>
          <h1>{site?.name || "Объект"}</h1>
          <p className="subtitle">
            {site?.address}
            {site?.cadastral_number ? ` · ${site.cadastral_number}` : ""}
          </p>
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
            {site.photos.map((photo) => (
              <a key={photo.id} href={`#/photo/${photo.id}`} className="photo-card">
                <img src={photo.file_url} alt={photo.filename} />
                <span className="mono">{photo.captured_at}</span>
              </a>
            ))}
          </div>
        </section>
      )}

      <section className="panel">
        <h2>График строительства</h2>
        <p className="hint">
          Этап, дата начала и дата окончания. Соберите периоды в форме или загрузите
          заполненный шаблон Excel.
          {hasSavedPlan
            ? " В форме сейчас сохранённый график."
            : " Даты в форме уже стоят от сегодняшнего дня."}
        </p>
        <div className="plan-modes" role="group" aria-label="Способ заполнения графика">
          <button
            type="button"
            aria-pressed={scheduleMode === "editor"}
            onClick={() => setScheduleMode("editor")}
          >
            В форме
          </button>
          <button
            type="button"
            aria-pressed={scheduleMode === "file"}
            onClick={() => setScheduleMode("file")}
          >
            Шаблон Excel
          </button>
        </div>

        {scheduleMode === "editor" && (
          <>
            <div className="plan-editor">
              {draftRows.map((row, index) => (
                <div className="plan-row" key={`${row.stage_code}-${index}`}>
                  <select
                    value={row.stage_code}
                    disabled={busy}
                    aria-label="Этап"
                    onChange={(event) => updateDraft(index, { stage_code: event.target.value })}
                  >
                    {stages.map((stage) => (
                      <option key={stage.code} value={stage.code}>
                        {stage.label}
                      </option>
                    ))}
                  </select>
                  <input
                    type="date"
                    value={row.date_from}
                    disabled={busy}
                    aria-label="Начало"
                    onChange={(event) => updateDraft(index, { date_from: event.target.value })}
                  />
                  <input
                    type="date"
                    value={row.date_to}
                    disabled={busy}
                    aria-label="Окончание"
                    onChange={(event) => updateDraft(index, { date_to: event.target.value })}
                  />
                  <button
                    type="button"
                    className="btn ghost sm"
                    disabled={busy || draftRows.length < 2}
                    onClick={() => {
                      setSavedNote("");
                      setDraftRows((rows) => rows.filter((_, rowIndex) => rowIndex !== index));
                    }}
                  >
                    Убрать
                  </button>
                </div>
              ))}
              <button
                type="button"
                className="btn ghost sm"
                disabled={busy}
                onClick={() => {
                  setSavedNote("");
                  setDraftRows((rows) => [
                    ...rows,
                    {
                      stage_code: stages[0]?.code || "clearing",
                      date_from: todayIso(),
                      date_to: addDays(todayIso(), 20),
                    },
                  ]);
                }}
              >
                Добавить период
              </button>
            </div>
            <div className="schedule-actions">
              <button type="button" className="btn sm" disabled={busy} onClick={saveDraft}>
                {busy ? "Сохраняем…" : "Сохранить график"}
              </button>
              {savedNote && <span className="muted">{savedNote}</span>}
            </div>
          </>
        )}

        {scheduleMode === "file" && (
          <>
            <div className="plan-file-actions">
              <a className="btn ghost sm" href="/api/plan/template">
                Скачать шаблон Excel
              </a>
              <span className="muted">Колонки: stage, date_from, date_to</span>
            </div>
            <FileField
              accept=".csv,.xlsx,.xls,text/csv"
              buttonText="Загрузить заполненный шаблон"
              placeholder="Перетащите Excel или CSV сюда"
              disabled={busy}
              onChange={onPlanFile}
            />
            {savedNote && <p className="muted">{savedNote}</p>}
            {hasSavedPlan && (
              <ul className="plan-list">
                {site.plan.map((row, index) => (
                  <li key={`${row.stage_code}-${index}`}>
                    <strong>{stageTitle(stages, row.stage_code)}</strong>
                    {" "}
                    {String(row.date_from).slice(0, 10)} — {String(row.date_to).slice(0, 10)}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </section>

      <section className="panel">
        <h2>Добавить снимок</h2>
        <label className="field">
          <span>Дата съёмки</span>
          <input
            type="date"
            value={capturedAt}
            onChange={(event) => setCapturedAt(event.target.value)}
          />
        </label>
        <FileField
          accept="image/jpeg,image/png,image/webp,image/bmp"
          disabled={busy}
          onChange={onPhoto}
          buttonText="Выбрать снимок"
          placeholder="JPG, PNG или WebP"
        />
      </section>

      <section className="panel">
        <h2>Таймлайн</h2>
        <TimelineTable timeline={timeline} />
      </section>
    </div>
  );
}
