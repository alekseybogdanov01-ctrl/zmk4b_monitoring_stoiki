import { useEffect, useMemo, useState } from "react";
import { fetchSites, fetchStages, loadDemoPackFiles, runDemoAnalyze } from "../api.js";
import { DeviationList, TimelineTable, StatusBadge } from "../components/Shared.jsx";
import FileField from "../components/FileField.jsx";

const STAGE_ORDER = ["clearing", "excavation", "foundations", "frame", "landscaping"];

const STAGE_FALLBACK = [
  { code: "clearing", label: "Расчистка участка" },
  { code: "excavation", label: "Откопка котлована" },
  { code: "foundations", label: "Устройство фундаментов" },
  { code: "frame", label: "Монтаж каркаса, стены и перекрытия" },
  { code: "landscaping", label: "Благоустройство" },
];

function addDays(iso, n) {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

function sortStages(list) {
  const rank = (code) => {
    const i = STAGE_ORDER.indexOf(code);
    return i === -1 ? STAGE_ORDER.length : i;
  };
  return [...list].sort((a, b) => rank(a.code) - rank(b.code));
}

function blankRows(stages) {
  return stages.map((stage) => ({
    stage_code: stage.code,
    date_from: "",
    date_to: "",
  }));
}

function rowsToFile(rows, filename) {
  const ready = rows.filter((row) => row.stage_code && row.date_from && row.date_to);
  if (!ready.length) return null;
  const lines = ["stage,date_from,date_to"];
  for (const row of ready) {
    lines.push(`${row.stage_code},${row.date_from},${row.date_to}`);
  }
  return new File([`${lines.join("\n")}\n`], filename, { type: "text/csv" });
}

function stageTitle(stages, code) {
  return stages.find((stage) => stage.code === code)?.label || code;
}

export default function DemoPage() {
  const [planFile, setPlanFile] = useState(null);
  const [planMode, setPlanMode] = useState("existing");
  const [sites, setSites] = useState([]);
  const [stages, setStages] = useState(STAGE_FALLBACK);
  const [existingId, setExistingId] = useState("");
  const [draftRows, setDraftRows] = useState(() => blankRows(STAGE_FALLBACK));
  const [photoFiles, setPhotoFiles] = useState([]);
  const [previews, setPreviews] = useState([]);
  const [baseDate, setBaseDate] = useState("2025-01-10");
  const [stepDays, setStepDays] = useState(10);
  const [siteName, setSiteName] = useState("Демо-площадка (ТЗ)");
  const [fromPack, setFromPack] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loadingPack, setLoadingPack] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [selectedDay, setSelectedDay] = useState(null);

  const dates = useMemo(() => {
    return photoFiles.map((_, i) => addDays(baseDate, i * Number(stepDays || 1)));
  }, [photoFiles, baseDate, stepDays]);

  useEffect(() => {
    fetchSites()
      .then((data) => setSites((data.sites || []).filter((site) => site.plan?.length)))
      .catch(() => setSites([]));
    fetchStages()
      .then((data) => {
        const next = sortStages(data.stages || []);
        if (!next.length) return;
        setStages(next);
        setDraftRows(blankRows(next));
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (planMode === "existing") {
      const site = sites.find((item) => item.id === existingId);
      setPlanFile(site ? rowsToFile(site.plan, "plan.csv") : null);
    } else if (planMode === "editor") {
      setPlanFile(rowsToFile(draftRows, "plan.csv"));
    }
  }, [planMode, existingId, sites, draftRows]);

  useEffect(() => {
    const urls = photoFiles.map((f) => URL.createObjectURL(f));
    setPreviews(urls);
    return () => urls.forEach((u) => URL.revokeObjectURL(u));
  }, [photoFiles]);

  const setPhotos = (list) => {
    const next = Array.from(list || []);
    next.sort((a, b) => a.name.localeCompare(b.name, "ru"));
    setPhotoFiles(next);
    setFromPack(false);
    setResult(null);
  };

  const onPlan = (e) => {
    setPlanFile(e.target.files?.[0] || null);
    setFromPack(false);
    setResult(null);
  };

  const onPhotos = (e) => setPhotos(e.target.files);

  const updateDraft = (index, patch) => {
    setDraftRows((rows) => rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
    setFromPack(false);
    setResult(null);
  };

  const onLoadPack = async () => {
    setError(null);
    setLoadingPack(true);
    try {
      const pack = await loadDemoPackFiles();
      setPlanFile(pack.planFile);
      setPhotoFiles(pack.photos);
      setBaseDate(pack.baseDate);
      setStepDays(pack.stepDays);
      setSiteName(pack.siteName);
      setFromPack(true);
      setPlanMode("file");
      setResult(null);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoadingPack(false);
    }
  };

  const onRun = async () => {
    setError(null);
    if (!planFile) {
      setError("Сначала загрузите календарный план");
      return;
    }
    if (!photoFiles.length) {
      setError("Загрузите хотя бы один снимок с камеры");
      return;
    }
    setBusy(true);
    try {
      const data = await runDemoAnalyze({
        planFile,
        photos: photoFiles,
        dates,
        siteName,
      });
      setResult(data);
      setSelectedDay(
        data.timeline?.find((d) => d.deviations?.length) || data.timeline?.[0] || null,
      );
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  };

  const ready = Boolean(planFile && photoFiles.length);
  const blocked = busy || loadingPack;

  return (
    <div className="page demo">
      <header className="page-head">
        <div>
          <h1>Разбор площадки</h1>
          <p className="subtitle">
            Нужны две вещи: календарный план работ и кадры с камер. Система найдёт технику
            на снимках и сверит её с планом.
          </p>
        </div>
        <button
          type="button"
          className="btn ghost"
          disabled={blocked}
          onClick={onLoadPack}
        >
          {loadingPack ? "Загрузка пакета…" : "Загрузить демо-данные"}
        </button>
      </header>

      {fromPack && (
        <p className="demo-pack-note">
          Подставлен пакет из папки <code>Демо_конкурс</code>: план и 5 кадров таймлапса.
          Даты уже проставлены — можно сразу запускать анализ.
        </p>
      )}

      <section className="demo-steps">
        <article className={`demo-step plan-step ${planFile ? "done" : ""}`}>
          <span className="demo-step-num">1</span>
          <div className="demo-step-body">
            <h2>Календарный план</h2>
            <p className="hint">
              Этап, даты начала и окончания. Можно взять план готового объекта,
              собрать периоды в форме или загрузить заполненный шаблон Excel.
            </p>
            <div className="plan-modes" role="group" aria-label="Способ заполнения плана">
              <button
                type="button"
                aria-pressed={planMode === "existing"}
                onClick={() => {
                  setPlanMode("existing");
                  setFromPack(false);
                }}
              >
                Из существующих
              </button>
              <button
                type="button"
                aria-pressed={planMode === "editor"}
                onClick={() => {
                  setPlanMode("editor");
                  setFromPack(false);
                }}
              >
                Новый план
              </button>
              <button
                type="button"
                aria-pressed={planMode === "file"}
                onClick={() => {
                  setPlanMode("file");
                  setPlanFile(null);
                  setFromPack(false);
                }}
              >
                Шаблон Excel
              </button>
            </div>

            {planMode === "existing" && (
              <>
                <label className="field">
                  <span>Объект с уже загруженным планом</span>
                  <select
                    value={existingId}
                    disabled={blocked}
                    onChange={(e) => {
                      setExistingId(e.target.value);
                      setFromPack(false);
                    }}
                  >
                    <option value="">Выберите объект</option>
                    {sites.map((site) => (
                      <option key={site.id} value={site.id}>
                        {site.name}
                        {site.address ? ` — ${site.address}` : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <PlanPreview
                  rows={sites.find((site) => site.id === existingId)?.plan || []}
                  stages={stages}
                />
              </>
            )}

            {planMode === "editor" && (
              <div className="plan-editor">
                {draftRows.map((row, index) => (
                  <div className="plan-row" key={`${row.stage_code}-${index}`}>
                    <select
                      value={row.stage_code}
                      disabled={blocked}
                      aria-label="Этап"
                      onChange={(e) => updateDraft(index, { stage_code: e.target.value })}
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
                      disabled={blocked}
                      aria-label="Начало"
                      onChange={(e) => updateDraft(index, { date_from: e.target.value })}
                    />
                    <input
                      type="date"
                      value={row.date_to}
                      disabled={blocked}
                      aria-label="Окончание"
                      onChange={(e) => updateDraft(index, { date_to: e.target.value })}
                    />
                    <button
                      type="button"
                      className="btn ghost sm"
                      disabled={blocked || draftRows.length < 2}
                      onClick={() =>
                        setDraftRows((rows) => rows.filter((_, rowIndex) => rowIndex !== index))
                      }
                    >
                      Убрать
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  className="btn ghost sm"
                  disabled={blocked}
                  onClick={() =>
                    setDraftRows((rows) => [
                      ...rows,
                      { stage_code: stages[0]?.code || "clearing", date_from: "", date_to: "" },
                    ])
                  }
                >
                  Добавить период
                </button>
              </div>
            )}

            {planMode === "file" && (
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
                  value={planFile?.name}
                  placeholder="Перетащите Excel или CSV сюда"
                  disabled={blocked}
                  onChange={onPlan}
                />
              </>
            )}
          </div>
        </article>

        <article className={`demo-step plan-step ${photoFiles.length ? "done" : ""}`}>
          <span className="demo-step-num">2</span>
          <div className="demo-step-body">
            <h2>Снимки с камер</h2>
            <p className="hint">
              Несколько JPG или PNG. Порядок файлов = порядок съёмки: система сама
              разнесёт кадры по датам.
            </p>
            <FileField
              accept="image/jpeg,image/png,image/webp,image/bmp"
              multiple
              buttonText="Выбрать кадры"
              value={
                photoFiles.length
                  ? `${photoFiles.length} кадр(ов)`
                  : ""
              }
              placeholder="Перетащите снимки сюда"
              disabled={blocked}
              onChange={onPhotos}
            />
          </div>
        </article>
      </section>

      {photoFiles.length > 0 && (
        <section className="panel">
          <h2>Как система назначит даты</h2>
          <p className="hint">
            Первый файл — базовая дата, каждый следующий сдвигается на шаг. Имена
            сортируются по алфавиту, поэтому в демо-пакете кадры названы 01_, 02_, 03_…
          </p>
          <div className="demo-date-grid">
            {photoFiles.map((f, i) => (
              <figure key={f.name + i} className="demo-shot">
                {previews[i] ? (
                  <img src={previews[i]} alt={f.name} />
                ) : (
                  <div className="demo-shot-ph" />
                )}
                <figcaption>
                  <span className="mono">{dates[i]}</span>
                  <span>{f.name}</span>
                </figcaption>
              </figure>
            ))}
          </div>
          <div className="demo-settings">
            <label className="field">
              <span>Дата первого кадра</span>
              <input
                type="date"
                value={baseDate}
                disabled={blocked}
                onChange={(e) => setBaseDate(e.target.value)}
              />
            </label>
            <label className="field">
              <span>Шаг между кадрами, дни</span>
              <input
                type="number"
                min={1}
                value={stepDays}
                disabled={blocked}
                onChange={(e) => setStepDays(e.target.value)}
              />
            </label>
            <label className="field">
              <span>Название объекта</span>
              <input
                type="text"
                value={siteName}
                disabled={blocked}
                onChange={(e) => setSiteName(e.target.value)}
              />
            </label>
          </div>
        </section>
      )}

      <div className="actions">
        <button type="button" className="btn" disabled={blocked || !ready} onClick={onRun}>
          {busy ? "Анализ…" : "Запустить анализ"}
        </button>
        {!ready && !error && (
          <span className="muted">
            {!planFile && !photoFiles.length
              ? "Загрузите план и снимки — или нажмите «Загрузить демо-данные»"
              : !planFile
                ? "Осталось загрузить календарный план"
                : "Осталось загрузить снимки"}
          </span>
        )}
        {error && <span className="status-line error">{error}</span>}
      </div>

      {result && (
        <>
          <section className="panel">
            <div className="panel-head">
              <h2>Результат анализа</h2>
              <a className="btn ghost sm" href={`#/site/${result.site.id}`}>
                Открыть объект
              </a>
            </div>
            <p>
              Объект: <strong>{result.site.name}</strong> · фото: {result.photos.length} ·
              отклонений: {result.deviations.length}
            </p>
            {result.performance && (
              <p className="muted">
                Детекция: {result.performance.detect_avg_ms} мс на кадр в среднем, максимум{" "}
                {result.performance.detect_max_ms} мс. Сопоставление с планом:{" "}
                {result.performance.matching_ms} мс. Весь разбор:{" "}
                {(result.performance.total_ms / 1000).toFixed(1)} с.
              </p>
            )}
            {result.errors?.length > 0 && (
              <p className="status-line error">{result.errors.join("; ")}</p>
            )}
          </section>

          <section className="panel">
            <h2>Предупреждения (отклонения)</h2>
            <DeviationList deviations={result.deviations} />
          </section>

          <section className="panel">
            <h2>Таймлайн план / факт</h2>
            <TimelineTable timeline={result.timeline} onSelectDay={setSelectedDay} />
          </section>

          {selectedDay && (
            <section className="panel day-detail">
              <div className="panel-head">
                <h2>День {selectedDay.date}</h2>
                <StatusBadge status={selectedDay.project_status || selectedDay.plan_status} />
              </div>
              <dl className="kv">
                <div>
                  <dt>План</dt>
                  <dd>
                    {selectedDay.planned_stages?.length
                      ? selectedDay.planned_stages
                          .map((s) => s.stage_label)
                          .join("; ")
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>Факт (этап)</dt>
                  <dd>{selectedDay.primary_stage_label || "техника не распознана / нет маркера"}</dd>
                </div>
                <div>
                  <dt>Техника на снимках</dt>
                  <dd className="mono">
                    {Object.entries(selectedDay.counts || {})
                      .map(([k, v]) => `${k}:${v}`)
                      .join(" ") || "—"}
                  </dd>
                </div>
              </dl>
              <DeviationList
                deviations={(selectedDay.deviations || []).map((d) => ({
                  ...d,
                  date: selectedDay.date,
                }))}
              />
              {selectedDay.photo_ids?.length > 0 && (
                <div className="photo-links">
                  <h3>Подтверждающие снимки</h3>
                  {selectedDay.photo_ids.map((id) => (
                    <a key={id} className="btn ghost sm" href={`#/photo/${id}`}>
                      Открыть снимок {id.slice(0, 8)}…
                    </a>
                  ))}
                </div>
              )}
            </section>
          )}

          <section className="panel">
            <h2>Методика «этап → техника»</h2>
            <div className="method-grid">
              {(result.methodology || []).map((s) => (
                <div key={s.code} className="method-card">
                  <h3>{s.label}</h3>
                  <p>
                    <span className="muted">Маркеры:</span> {s.markers.join(", ")}
                  </p>
                  {s.link_groups?.length > 0 && (
                    <p>
                      <span className="muted">Звено:</span>{" "}
                      {s.link_groups.map((g) => g.join("/")).join(" + ")}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function PlanPreview({ rows, stages }) {
  if (!rows.length) return null;
  return (
    <ul className="plan-preview">
      {rows.map((row, index) => (
        <li key={`${row.stage_code}-${row.date_from}-${index}`}>
          <strong>{stageTitle(stages, row.stage_code)}</strong>
          {" · "}
          <span className="mono">
            {row.date_from} — {row.date_to}
          </span>
        </li>
      ))}
    </ul>
  );
}
