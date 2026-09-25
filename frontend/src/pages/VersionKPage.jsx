import { useEffect, useMemo, useState } from "react";
import { fetchClasses, fetchSites, fetchStages } from "../api.js";
import { StatusBadge } from "../components/Shared.jsx";

const SOURCES = [
  {
    title: "Камеры на площадке",
    text:
      "Кадры со стационарных камер и таймлапс-съёмки. Поддерживаются JPG, PNG, WebP и BMP " +
      "до 25 МБ на файл. Каждому кадру присваивается дата съёмки — она и связывает факт с планом.",
  },
  {
    title: "Календарный план СМР",
    text:
      "CSV или Excel с колонками этап, дата начала и дата окончания. Названия этапов " +
      "принимаются и по-русски — «котлован», «сваи», «монолит», «монтаж», — и кодами.",
  },
  {
    title: "Справочник техники и методика",
    text:
      "Каталог из 12 классов машин и правила «этап → необходимая техника». Это нормативная " +
      "часть системы: она задаёт, что именно должно находиться на площадке в каждый период.",
  },
];

const PIPELINE = [
  {
    title: "Приём кадра",
    text: "Проверка формата и размера, декодирование изображения без потери исходника.",
  },
  {
    title: "Детекция техники",
    text:
      "Один прогон YOLO по кадру с заведомо низким входным порогом 0,05 — чтобы на " +
      "следующем шаге отсечь лишнее осознанно, а не потерять слабые объекты сразу.",
  },
  {
    title: "Фильтр по классам",
    text:
      "У каждого класса свой порог уверенности. Крупную характерную технику отсекаем " +
      "строже, мелкую и однотипную — мягче.",
  },
  {
    title: "Агрегация за сутки",
    text:
      "Детекции со всех кадров одной даты сводятся в количество машин по классам. " +
      "Единица сопоставления — день, а не отдельный снимок.",
  },
  {
    title: "Сопоставление с планом",
    text:
      "Для планового этапа проверяется наличие маркерной техники и полнота звена — " +
      "набора машин, без которых работа физически не идёт.",
  },
  {
    title: "Статус и отклонения",
    text:
      "Формируются отклонения со ссылками на конкретные снимки и зону, затем день " +
      "получает статус. Объекту присваивается худший статус среди дней со съёмкой.",
  },
];

const DEVIATIONS = [
  {
    code: "missing_required",
    title: "Нет необходимой техники",
    severity: "Критично",
    text:
      "По календарю этап идёт, но маркерной техники на кадрах нет. Это либо отставание, " +
      "либо неявка подрядной техники.",
  },
  {
    code: "incomplete_link",
    title: "Неполное звено",
    severity: "Предупреждение",
    text:
      "Маркерная техника есть, а звено разорвано: экскаватор без самосвалов, бетононасос " +
      "без миксера. Работа формально идёт, фактически — простой.",
  },
  {
    code: "unexpected_equipment",
    title: "Техника не под этап",
    severity: "Предупреждение",
    text:
      "На кадре техника другого этапа, чем в плане. Не нарушение само по себе, но сигнал " +
      "о смене стадии раньше или позже графика.",
  },
];

export default function VersionKPage() {
  const [classes, setClasses] = useState([]);
  const [thresholds, setThresholds] = useState({});
  const [stages, setStages] = useState([]);
  const [sites, setSites] = useState([]);
  const [statuses, setStatuses] = useState([]);
  const [sitesLoading, setSitesLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    Promise.all([fetchClasses(), fetchStages()])
      .then(([c, s]) => {
        if (!alive) return;
        setClasses(c.classes || []);
        setThresholds(c.confidence_by_class || {});
        setStages(s.stages || []);
      })
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    let alive = true;
    fetchSites()
      .then((d) => {
        if (!alive) return;
        setSites(d.sites || []);
        setStatuses(d.statuses || []);
      })
      .catch(() => {})
      .finally(() => alive && setSitesLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  const labelOf = useMemo(() => {
    const map = new Map(classes.map((c) => [c.code, c.label]));
    return (code) => map.get(code) || code;
  }, [classes]);

  const examples = useMemo(() => {
    return ["idle", "warning", "ok", "info"]
      .map((code) => sites.find((s) => s.last_status === code && s.thumb_url))
      .filter(Boolean);
  }, [sites]);

  return (
    <div className="page vk">
      {error && <p className="status-line error">{error}</p>}

      <section className="vk-hero">
        <img src="/versionk/hero-site.png" alt="Стройплощадка под наблюдением камер" />
        <div className="vk-hero-body">
          <span className="vk-kicker">О продукте</span>
          <h1>Контроль стройки по кадрам с камер</h1>
          <p>
            Система смотрит на площадку глазами камеры, распознаёт строительную технику и
            сверяет увиденное с календарным планом работ. На выходе — не набор рамок на
            фотографии, а ответ на вопрос заказчика: идут ли работы так, как обещано.
          </p>
          <div className="vk-metrics">
            <div>
              <strong>{classes.length || 12}</strong>
              <span>класса техники</span>
            </div>
            <div>
              <strong>{stages.length || 4}</strong>
              <span>этапа СМР</span>
            </div>
            <div>
              <strong>{DEVIATIONS.length}</strong>
              <span>типа отклонений</span>
            </div>
            <div>
              <strong>{statuses.length || 5}</strong>
              <span>статуса объекта</span>
            </div>
          </div>
        </div>
      </section>

      <section className="panel vk-split">
        <div>
          <h2>Откуда берутся данные</h2>
          <p className="vk-lead">
            Система соединяет три независимых потока. Ни один из них сам по себе не даёт
            вывода: снимки без плана — это просто фотографии техники, план без снимков —
            обещание без проверки.
          </p>
          <div className="vk-cards">
            {SOURCES.map((s) => (
              <article key={s.title} className="vk-card">
                <h3>{s.title}</h3>
                <p>{s.text}</p>
              </article>
            ))}
          </div>
        </div>
        <figure className="vk-figure">
          <img src="/versionk/data-sources.png" alt="Три источника данных сходятся в систему" />
          <figcaption>
            Кадры камер, календарный план и справочник методики сходятся в один поток
            обработки.
          </figcaption>
        </figure>
      </section>

      <section className="panel">
        <h2>Как обрабатываются</h2>
        <p className="vk-lead">
          Путь от байтов снимка до формулировки отклонения — шесть шагов. Разделение на
          «низкий порог детектора» и «строгий порог по классу» сделано намеренно: решение о
          том, что считать техникой, принимается там, где известен класс.
        </p>
        <div className="vk-split">
          <ol className="vk-steps">
            {PIPELINE.map((step, i) => (
              <li key={step.title}>
                <span className="vk-step-num">{i + 1}</span>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.text}</p>
                </div>
              </li>
            ))}
          </ol>
          <figure className="vk-figure">
            <img src="/versionk/detection.png" alt="Детекция техники на кадре с камеры" />
            <figcaption>
              Детектор возвращает рамку, класс и уверенность по каждой машине в кадре.
            </figcaption>
          </figure>
        </div>
      </section>

      <section className="panel">
        <h2>Отклонения, которые ищет система</h2>
        <div className="vk-cards three">
          {DEVIATIONS.map((d) => (
            <article key={d.code} className={`vk-card dev ${d.code}`}>
              <span className="vk-sev">{d.severity}</span>
              <h3>{d.title}</h3>
              <p>{d.text}</p>
              <code className="mono muted">{d.code}</code>
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <h2>Методика «этап → техника»</h2>
        <p className="vk-lead">
          Маркер — машина, по которой этап опознаётся однозначно. Звено — набор, без
          которого работа встаёт: внутри группы достаточно любой машины, но все группы
          должны быть закрыты одновременно.
        </p>
        <figure className="vk-figure wide">
          <img src="/versionk/stages.png" alt="Этапы строительства и техника" />
          <figcaption>
            Расчистка участка, откопка котлована, фундаменты, каркас со стенами
            и перекрытиями, благоустройство — у каждого этапа свой характерный парк техники.
          </figcaption>
        </figure>
        <div className="vk-cards">
          {stages.map((s) => (
            <article key={s.code} className="vk-card">
              <h3>{s.label}</h3>
              <p className="vk-row">
                <span className="muted">Маркеры:</span>{" "}
                {s.markers.map(labelOf).join(", ")}
              </p>
              <p className="vk-row">
                <span className="muted">Звено:</span>{" "}
                {s.link_groups?.length
                  ? s.link_groups.map((g) => g.map(labelOf).join(" или ")).join(" + ")
                  : "не требуется"}
              </p>
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <h2>Классы техники и пороги уверенности</h2>
        <p className="vk-lead">
          Порог у каждого класса свой. Характерную по силуэту технику можно отсекать
          строго, а однотипные грузовики и башенные краны, которые модель распознаёт
          сложнее, приходится пропускать мягче.
        </p>
        <div className="vk-classes">
          {classes.map((c) => (
            <div key={c.code} className="vk-class">
              <span className="dot" style={{ background: c.color }} />
              <span className="vk-class-name">{c.label}</span>
              <span className="mono muted">
                {thresholds[c.code] != null ? thresholds[c.code].toFixed(2) : "—"}
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <h2>Статусы объекта</h2>
        <p className="vk-lead">
          Статус дня выводится из найденных отклонений, а объект получает худший статус
          среди дней, за которые есть съёмка. Порядок приоритета — слева направо.
        </p>
        <div className="vk-statuses">
          {statuses.map((s) => (
            <article key={s.code} className="vk-status" style={{ borderLeftColor: s.color }}>
              <span className="dot" style={{ background: s.color }} />
              <h3>{s.label}</h3>
              <p>{s.description}</p>
            </article>
          ))}
          {!statuses.length && <p className="muted">Загрузка статусов…</p>}
        </div>
      </section>

      <section className="panel">
        <h2>Примеры на реальных кадрах</h2>
        <p className="vk-lead">
          Ниже — объекты демо-портфеля на настоящих снимках строительных площадок.
          Формулировку в каждой карточке система составляет сама, по типу найденного
          отклонения.
        </p>
        {sitesLoading ? (
          <p className="muted">Считаем таймлайны объектов…</p>
        ) : (
          <div className="vk-examples">
            {examples.map((s) => (
              <a key={s.id} className="vk-example" href={`#/site/${s.id}`}>
                <img src={s.thumb_url} alt={s.name} />
                <div className="vk-example-body">
                  <div className="vk-example-head">
                    <strong>{s.name}</strong>
                    <StatusBadge status={s.last_status} />
                  </div>
                  <p>{s.comment}</p>
                </div>
              </a>
            ))}
            {!examples.length && <p className="muted">Демо-объекты не загружены</p>}
          </div>
        )}
      </section>

    </div>
  );
}
