import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchPhoto } from "../api.js";
import { DetectionOverlay, StatusBadge } from "./Shared.jsx";

const CYCLE_MS = 7000;

/**
 * Обход камер портфеля: крупный кадр с распознанной техникой и лента
 * превью. Листается сам, на наведении останавливается.
 */
export default function CameraWall({ sites }) {
  const cams = useMemo(() => sites.filter((s) => s.last_photo_id), [sites]);
  const [index, setIndex] = useState(0);
  const [frame, setFrame] = useState(null);
  const [paused, setPaused] = useState(false);
  const [progress, setProgress] = useState(0);
  const cache = useRef(new Map());

  const safeIndex = cams.length ? Math.min(index, cams.length - 1) : 0;
  const current = cams[safeIndex] || null;

  const select = useCallback((next) => {
    setIndex(next);
    setProgress(0);
  }, []);

  // Детекции для выбранного кадра; повторно уже загруженные не запрашиваем.
  useEffect(() => {
    if (!current?.last_photo_id) return undefined;
    const id = current.last_photo_id;
    const cached = cache.current.get(id);
    if (cached) {
      setFrame(cached);
      return undefined;
    }

    let alive = true;
    setFrame(null);
    fetchPhoto(id)
      .then((data) => {
        cache.current.set(id, data);
        if (alive) setFrame(data);
      })
      .catch(() => alive && setFrame(null));
    return () => {
      alive = false;
    };
  }, [current?.last_photo_id]);

  // Автолисты и полоса прогресса идут от одного таймера.
  useEffect(() => {
    if (paused || cams.length < 2) return undefined;
    const started = performance.now();
    let raf;
    const tick = (now) => {
      const p = (now - started) / CYCLE_MS;
      if (p >= 1) {
        setIndex((i) => (i + 1) % cams.length);
        setProgress(0);
        return;
      }
      setProgress(p);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [paused, cams.length, index]);

  if (!cams.length) {
    return (
      <section className="panel db-cams">
        <h2>Кадры с камер</h2>
        <p className="muted">
          Ни по одному объекту ещё не поступило снимков — показывать нечего.
        </p>
      </section>
    );
  }

  const photo = frame?.photo;
  const detections = photo?.detections || [];
  const verdict = current.top_deviation?.message || current.status_description;
  const equipment = [
    ...new Set(detections.map((d) => d.label || d.class).filter(Boolean)),
  ];
  const planned = current.planned_stages?.map((p) => p.label).filter(Boolean).join(", ");

  return (
    <section
      className="panel flush db-cams"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <div className="db-cams-head">
        <span className="db-live">
          <span className="db-live-dot" />
          Кадры с камер
        </span>
        <span className="db-cams-counter mono">
          {safeIndex + 1} / {cams.length}
        </span>
      </div>

      <div className="db-cam-stage">
        <div className="db-cam-frame">
          <div className="db-cam-photo">
            <img
              key={current.last_photo_id}
              className="db-cam-img"
              src={current.thumb_url}
              alt={`Кадр с камеры: ${current.name}`}
            />

            {photo?.width ? (
              <div className="db-cam-overlay" key={`ov-${photo.id}`}>
                <DetectionOverlay
                  animated
                  fit="contain"
                  result={{
                    width: photo.width,
                    height: photo.height,
                    detections,
                  }}
                />
              </div>
            ) : null}

            <span className="db-cam-scan" key={`scan-${current.last_photo_id}`} />
          </div>
        </div>

        <div className="db-cam-caption">
          <div className="db-cam-caption-top">
            <StatusBadge status={current.status} />
            <span className="mono muted">{current.last_date || "—"}</span>
          </div>
          <h3>{current.name}</h3>
          <p className="db-cam-addr">{current.address || "адрес не указан"}</p>
          <dl className="db-cam-facts">
            <div>
              <dt>План</dt>
              <dd>{planned || "—"}</dd>
            </div>
            <div>
              <dt>Факт</dt>
              <dd>{current.fact_stage_label || "не распознан"}</dd>
            </div>
            <div>
              <dt>Техника</dt>
              <dd>{equipment.length ? equipment.join(", ") : "не распознана"}</dd>
            </div>
            <div>
              <dt>Кадров</dt>
              <dd className="mono">{current.photos_count || 0}</dd>
            </div>
          </dl>
          {verdict ? <p className="db-cam-verdict">{verdict}</p> : null}
          <a className="btn sm" href={`#/site/${current.id}`}>
            Открыть объект
          </a>
        </div>
      </div>

      <div className="db-cam-strip">
        {cams.map((s, i) => (
          <button
            key={s.id}
            type="button"
            className={`db-cam-thumb ${s.status} ${i === safeIndex ? "active" : ""}`}
            onClick={() => select(i)}
            title={`${s.name} — ${s.status_label}`}
          >
            <img src={s.thumb_url} alt={s.name} />
            <span className="db-cam-thumb-name">{s.name}</span>
            {i === safeIndex && (
              <span
                className="db-cam-thumb-progress"
                style={{ transform: `scaleX(${paused ? 1 : progress})` }}
              />
            )}
          </button>
        ))}
      </div>
    </section>
  );
}
