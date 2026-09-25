import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { detectFrame, fetchClasses, fetchHealth } from "../api.js";
import { DetectionOverlay } from "../components/Shared.jsx";

const DEFAULT_CLASSES = [
  { id: 0, code: "excavator", label: "Экскаватор", color: "#E85D04" },
  { id: 1, code: "bulldozer", label: "Бульдозер", color: "#F48C06" },
  { id: 2, code: "loader", label: "Погрузчик", color: "#FAA307" },
  { id: 3, code: "dump_truck", label: "Самосвал", color: "#DC2F02" },
  { id: 4, code: "concrete_mixer", label: "Бетономешалка", color: "#9D4EDD" },
  { id: 5, code: "concrete_pump", label: "Бетононасос", color: "#7B2CBF" },
  { id: 6, code: "tower_crane", label: "Башенный кран", color: "#0077B6" },
  { id: 7, code: "autocrane", label: "Автокран", color: "#00B4D8" },
  { id: 8, code: "pile_driver", label: "Сваебой", color: "#2D6A4F" },
  { id: 9, code: "roller", label: "Каток", color: "#BC6C25" },
  { id: 10, code: "crane_manipulator", label: "Кран-манипулятор", color: "#48CAE4" },
  { id: 11, code: "truck", label: "Грузовик", color: "#6C757D" },
];

export default function DetectPage() {
  const inputRef = useRef(null);
  const [classes, setClasses] = useState(DEFAULT_CLASSES);
  const [health, setHealth] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [drag, setDrag] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [h, c] = await Promise.all([fetchHealth(), fetchClasses()]);
        if (!alive) return;
        setHealth(h);
        if (c?.classes?.length) setClasses(c.classes);
      } catch (e) {
        if (!alive) return;
        setHealth({ status: "error", model_ready: false, model: String(e.message) });
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const runDetect = useCallback(async (file) => {
    if (!file) return;
    setError(null);
    setBusy(true);
    setResult(null);
    const url = URL.createObjectURL(file);
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return url;
    });
    try {
      const data = await detectFrame(file);
      setResult(data);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const onFile = (e) => {
    const file = e.target.files?.[0];
    if (file) runDetect(file);
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDrag(false);
    const file = e.dataTransfer.files?.[0];
    if (file) runDetect(file);
  };

  const counts = result?.counts || {};
  const total = useMemo(
    () => Object.values(counts).reduce((a, b) => a + b, 0),
    [counts]
  );

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Тест модели</h1>
          <p className="subtitle">
            Загрузите один кадр — ML-модель отметит технику (без плана и отклонений), если у
            вас нет кадров со стройки, возьмите изображение{" "}
            <a
              href="https://yandex.ru/images/search?from=tabbar&lr=16&text=%D1%81%D1%82%D1%80%D0%BE%D0%B8%D1%82%D0%B5%D0%BB%D1%8C%D0%BD%D0%B0%D1%8F%20%D0%BF%D0%BB%D0%BE%D1%89%D0%B0%D0%B4%D0%BA%D0%B0%20%D0%B2%D0%B8%D0%B4%20%D1%81%20%D0%BA%D0%B0%D0%BC%D0%B5%D1%80%D1%8B"
              target="_blank"
              rel="noreferrer"
            >
              отсюда
            </a>
            .
          </p>
        </div>
      </header>

      <div className="layout">
        <section className="panel flush">
          <div className="panel-head">
            <h2>Кадр</h2>
            <div className="toolbar">
              <button
                type="button"
                className="btn ghost"
                disabled={busy}
                onClick={() => inputRef.current?.click()}
              >
                Выбрать файл
              </button>
              <input
                ref={inputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/bmp"
                onChange={onFile}
                hidden
              />
            </div>
          </div>

          {!previewUrl ? (
            <div
              className={`dropzone empty ${drag ? "drag" : ""}`}
              onDragOver={(e) => {
                e.preventDefault();
                setDrag(true);
              }}
              onDragLeave={() => setDrag(false)}
              onDrop={onDrop}
              onClick={() => inputRef.current?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
              }}
            >
              <strong>Перетащите кадр сюда</strong>
              <span>JPG, PNG, WebP — один снимок с камеры стройплощадки</span>
              <button type="button" className="btn" disabled={busy}>
                Загрузить кадр
              </button>
            </div>
          ) : (
            <div className="dropzone">
              {busy && (
                <div className="overlay-busy">
                  <span className="spinner" />
                  Детекция…
                </div>
              )}
              <div className="viewer">
                <img src={previewUrl} alt="Кадр с камеры" />
                {result && (
                  <DetectionOverlay
                    result={{
                      width: result.width,
                      height: result.height,
                      detections: result.detections,
                    }}
                  />
                )}
              </div>
            </div>
          )}

          <div className="panel-head">
            {error ? (
              <span className="status-line error">{error}</span>
            ) : result ? (
              <span className="status-line">
                найдено: {total} · {result.width}×{result.height}
                {result.inference_ms != null && ` · ${result.inference_ms} мс`}
              </span>
            ) : (
              <span className="status-line">ожидание кадра</span>
            )}
            {previewUrl && (
              <button
                type="button"
                className="btn ghost"
                disabled={busy}
                onClick={() => {
                  setPreviewUrl((prev) => {
                    if (prev) URL.revokeObjectURL(prev);
                    return null;
                  });
                  setResult(null);
                  setError(null);
                  if (inputRef.current) inputRef.current.value = "";
                }}
              >
                Сбросить
              </button>
            )}
          </div>
        </section>

        <aside className="side">
          <div className="panel legend">
            <h3>Классы</h3>
            {classes.map((c) => (
              <div className="legend-item" key={c.code}>
                <span className="swatch" style={{ background: c.color }} />
                <span>{c.label}</span>
                <span className={`legend-count ${counts[c.code] ? "active" : ""}`}>
                  {counts[c.code] || 0}
                </span>
              </div>
            ))}
          </div>

          <div className="panel meta">
            <dl>
              <div>
                <dt>Модель</dt>
                <dd>{result?.model || health?.model || "—"}</dd>
              </div>
              <div>
                <dt>Детекций</dt>
                <dd>{result ? total : "—"}</dd>
              </div>
              <div>
                <dt>Время детекции</dt>
                <dd>{result?.inference_ms != null ? `${result.inference_ms} мс` : "—"}</dd>
              </div>
            </dl>
          </div>
        </aside>
      </div>
    </div>
  );
}
