import { useEffect, useMemo, useRef, useState } from "react";
import { CircleMarker, MapContainer, TileLayer, useMap, useMapEvents } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { createSite, lookupParcel } from "../api.js";

const MOSCOW = [55.75, 37.62];
const CAD_RE = /^\d+:\d+:\d+:\d+$/;

function compact(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^0-9a-zа-яё]/gi, "");
}

function StripLeafletFlag() {
  const map = useMap();
  useEffect(() => {
    map.attributionControl?.setPrefix(false);
    const id = setTimeout(() => map.invalidateSize(), 60);
    return () => clearTimeout(id);
  }, [map]);
  return null;
}

function FlyTo({ target }) {
  const map = useMap();
  useEffect(() => {
    if (!target) return;
    map.setView(target, 16);
  }, [target, map]);
  return null;
}

function PinPicker({ point, onPick }) {
  useMapEvents({
    click(event) {
      onPick([event.latlng.lat, event.latlng.lng]);
    },
  });
  if (!point) return null;
  return (
    <CircleMarker
      center={point}
      radius={11}
      pathOptions={{ color: "#4d92f8", fillColor: "#4d92f8", fillOpacity: 0.9, weight: 2 }}
    />
  );
}

export default function AddSiteDialog({ open, sites, onClose, onCreated }) {
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [cadastral, setCadastral] = useState("");
  const [point, setPoint] = useState(null);
  const [focus, setFocus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [looking, setLooking] = useState(false);
  const [lookupError, setLookupError] = useState("");
  const [fromNspd, setFromNspd] = useState(false);
  const [attempted, setAttempted] = useState("");
  const [error, setError] = useState("");
  const [created, setCreated] = useState(null);
  const busyRef = useRef(false);
  busyRef.current = busy || looking;

  useEffect(() => {
    if (!open) return undefined;
    setName("");
    setAddress("");
    setCadastral("");
    setPoint(null);
    setFocus(null);
    setBusy(false);
    setLooking(false);
    setLookupError("");
    setFromNspd(false);
    setAttempted("");
    setError("");
    setCreated(null);
    const onKey = (event) => {
      if (event.key === "Escape" && !busyRef.current) onClose();
    };
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [open, onClose]);

  const duplicate = useMemo(() => {
    const key = compact(cadastral);
    if (!key) return null;
    return (sites || []).find((site) => compact(site.cadastral_number) === key) || null;
  }, [cadastral, sites]);

  const cadValue = cadastral.trim().replace(/\s+/g, "");
  const cadReady = CAD_RE.test(cadValue);
  const findRef = useRef(null);

  useEffect(() => {
    if (!open || !cadReady || attempted === cadValue) return undefined;
    const timer = setTimeout(() => {
      findRef.current?.(cadValue);
    }, 500);
    return () => clearTimeout(timer);
  }, [open, cadReady, cadValue, attempted]);

  if (!open) return null;

  const findParcel = async (value) => {
    const cad = String(value || "").trim().replace(/\s+/g, "");
    if (!CAD_RE.test(cad)) {
      setLookupError("Кадастровый номер укажите в виде 77:09:0004012:1145");
      return;
    }
    setAttempted(cad);
    setLooking(true);
    setLookupError("");
    try {
      const parcel = await lookupParcel(cad);
      setCadastral(parcel.cadastral_number || cad);
      setAddress(parcel.address || "");
      if (parcel.lat != null && parcel.lng != null) {
        const next = [parcel.lat, parcel.lng];
        setPoint(next);
        setFocus(next);
      }
      setFromNspd(true);
    } catch (err) {
      setFromNspd(false);
      setLookupError(
        err.message || "НСПД не ответила. Адрес и точку можно указать вручную.",
      );
    } finally {
      setLooking(false);
    }
  };
  findRef.current = findParcel;

  const submit = async (event) => {
    event.preventDefault();
    const cad = cadastral.trim().replace(/\s+/g, "");
    if (!CAD_RE.test(cad)) {
      setError("Укажите кадастровый номер земельного участка");
      return;
    }
    if (!point) {
      setError("Дождитесь точки из НСПД или укажите её на карте");
      return;
    }
    if (duplicate) {
      setError(`Этот участок уже есть у «${duplicate.name}»`);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const site = await createSite({
        name: name.trim(),
        address: address.trim() || null,
        cadastral_number: cad,
        lat: point[0],
        lng: point[1],
      });
      setCreated(site);
      await onCreated(site);
    } catch (err) {
      setError(err.message || "Не удалось добавить объект");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="site-dialog-backdrop" onClick={() => !busy && onClose()}>
      <div
        className="site-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-site-title"
        onClick={(event) => event.stopPropagation()}
      >
        {created ? (
          <>
            <h2 id="add-site-title">Объект добавлен</h2>
            <p>
              «{created.name}» уже на карте и в списке. Кадров ещё нет, поэтому статус —
              «Нет данных». План и снимки загружаются в карточке.
            </p>
            <div className="site-dialog-actions">
              <a className="btn" href={`#/site/${created.id}`} onClick={onClose}>
                Открыть карточку
              </a>
              <button type="button" className="btn ghost" onClick={onClose}>
                Остаться на дашборде
              </button>
            </div>
          </>
        ) : (
          <form onSubmit={submit}>
            <h2 id="add-site-title">Новый объект наблюдения</h2>
            <p className="hint">
              Сначала кадастровый номер: НСПД подставит адрес и точку на карте. Название можно
              не заполнять — тогда объект назовётся по присвоенному номеру. План и кадры
              загружаются потом, в карточке.
            </p>
            <label className="field">
              <span>Кадастровый номер участка</span>
              <span className="cad-lookup">
                <input
                  type="text"
                  autoFocus
                  required
                  value={cadastral}
                  placeholder="77:09:0004012:1145"
                  onChange={(event) => {
                    setCadastral(event.target.value);
                    setFromNspd(false);
                  }}
                />
                <button
                  type="button"
                  className="btn ghost"
                  disabled={looking || !cadReady}
                  onClick={() => findParcel(cadValue)}
                >
                  {looking ? "Ищем…" : "Найти в НСПД"}
                </button>
              </span>
            </label>
            {lookupError && <p className="status-line error">{lookupError}</p>}
            {fromNspd && (
              <p className="muted cad-note">Адрес и точка взяты из НСПД. Их можно поправить.</p>
            )}
            {duplicate && (
              <p className="status-line error">
                Участок уже в списке: «{duplicate.name}». Откройте его, а не создавайте второй.
              </p>
            )}
            <label className="field">
              <span>Название</span>
              <input
                type="text"
                value={name}
                placeholder="Если пусто — Объект № …"
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label className="field">
              <span>Адрес</span>
              <input
                type="text"
                value={address}
                placeholder="Подставится из НСПД или введите вручную"
                onChange={(event) => setAddress(event.target.value)}
              />
            </label>
            <div className="field">
              <span>Точка на карте</span>
              <div className="site-pin-map">
                <MapContainer
                  center={point || MOSCOW}
                  zoom={point ? 16 : 10}
                  scrollWheelZoom={false}
                  style={{ height: "100%", width: "100%" }}
                >
                  <StripLeafletFlag />
                  <FlyTo target={focus} />
                  <TileLayer
                    attribution='&copy; <a href="https://yandex.ru/maps">Яндекс</a>'
                    url="https://core-renderer-tiles.maps.yandex.net/tiles?l=map&x={x}&y={y}&z={z}&scale=1&lang=ru_RU&projection=web_mercator"
                  />
                  <PinPicker point={point} onPick={setPoint} />
                </MapContainer>
              </div>
              <span className="muted">
                {looking
                  ? "Запрашиваем координаты в НСПД…"
                  : point
                    ? `${point[0].toFixed(5)}, ${point[1].toFixed(5)} — нажмите на карту, чтобы перенести`
                    : "Точка появится из НСПД. Если сервис не ответит, отметьте её вручную."}
              </span>
            </div>
            {error && <p className="status-line error">{error}</p>}
            <div className="site-dialog-actions">
              <button
                type="submit"
                className="btn"
                disabled={busy || looking || !cadReady || !point || duplicate}
              >
                {busy ? "Добавляем…" : "Добавить объект"}
              </button>
              <button type="button" className="btn ghost" disabled={busy} onClick={onClose}>
                Отмена
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
