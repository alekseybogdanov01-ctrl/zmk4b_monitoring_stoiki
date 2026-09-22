import { useMemo, useState } from "react";
import { runDemoAnalyze } from "../api.js";
import { DeviationList, TimelineTable } from "../components/Shared.jsx";

function addDays(iso, n) {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

export default function DemoPage() {
  const [planFile, setPlanFile] = useState(null);
  const [photoFiles, setPhotoFiles] = useState([]);
  const [baseDate, setBaseDate] = useState("2025-01-10");
  const [stepDays, setStepDays] = useState(10);
  const [siteName, setSiteName] = useState("Демо-площадка (ТЗ)");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const dates = useMemo(() => {
    return photoFiles.map((_, i) => addDays(baseDate, i * Number(stepDays || 1)));
  }, [photoFiles, baseDate, stepDays]);

  const onPhotos = (e) => {
    const list = Array.from(e.target.files || []);
    list.sort((a, b) => a.name.localeCompare(b.name, "ru"));
    setPhotoFiles(list);
    setResult(null);
  };

  const onRun = async () => {
    setError(null);
    if (!planFile) {
      setError("Загрузите календарный план (CSV/Excel)");
      return;
    }
    if (!photoFiles.length) {
      setError("Загрузите снимки с камер");
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
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Демо</h1>
          <p className="subtitle">
            Загрузите календарный план и снимки — система обнаружит технику, сопоставит с
            этапами СМР и покажет отклонения (по ТЗ ДГП Москвы).
          </p>
        </div>
      </header>

      <section className="panel upload-grid">
        <div>
          <h2>1. Календарный план</h2>
          <p className="hint">
            CSV/Excel: колонки stage / date_from / date_to / zone. Готовый файл:{" "}
            <code>Демо/demo_schedule_timelapse.xlsx</code> (лист{" "}
            <code>plan</code>). Для таймлапса: база <code>2025-01-10</code>, шаг{" "}
            <code>10</code> дней.
          </p>
          <input
            type="file"
            accept=".csv,.xlsx,.xls,text/csv"
            onChange={(e) => setPlanFile(e.target.files?.[0] || null)}
          />
          {planFile && <p className="file-name">{planFile.name}</p>}
        </div>

        <div>
          <h2>2. Снимки с камер</h2>
          <p className="hint">Несколько файлов. Даты назначаются по порядку (таймлапс).</p>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp,image/bmp"
            multiple
            onChange={onPhotos}
          />
          {photoFiles.length > 0 && (
            <p className="file-name">{photoFiles.length} файл(ов)</p>
          )}
        </div>

        <div>
          <h2>3. Даты снимков</h2>
          <label className="field">
            <span>Базовая дата первого кадра</span>
            <input
              type="date"
              value={baseDate}
              onChange={(e) => setBaseDate(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Шаг между кадрами (дни)</span>
            <input
              type="number"
              min={1}
              value={stepDays}
              onChange={(e) => setStepDays(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Название объекта</span>
            <input
              type="text"
              value={siteName}
              onChange={(e) => setSiteName(e.target.value)}
            />
          </label>
        </div>
      </section>

      {photoFiles.length > 0 && (
        <section className="panel">
          <h3>Назначенные даты</h3>
          <ul className="date-assign">
            {photoFiles.map((f, i) => (
              <li key={f.name + i}>
                <span className="mono">{dates[i]}</span>
                <span>{f.name}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="actions">
        <button type="button" className="btn" disabled={busy} onClick={onRun}>
          {busy ? "Анализ…" : "Запустить анализ"}
        </button>
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
            {result.errors?.length > 0 && (
              <p className="status-line error">{result.errors.join("; ")}</p>
            )}
          </section>

          <section className="panel">
            <h2>Предупреждения (отклонения)</h2>
            <DeviationList deviations={result.deviations} />
          </section>

          <section className="panel">
            <h2>Разбор по снимкам</h2>
            <p className="hint">
              Строка = дата кадра. «Открыть снимок» — детекции ML и вывод алгоритма на эту
              дату.
            </p>
            <TimelineTable timeline={result.timeline} />
          </section>

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
