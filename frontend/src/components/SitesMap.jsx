import { useEffect } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer, useMap } from "react-leaflet";
import { StatusBadge } from "./Shared.jsx";
import "leaflet/dist/leaflet.css";

const MOSCOW = [55.75, 37.62];

function InvalidateSize() {
  const map = useMap();
  useEffect(() => {
    const id = setTimeout(() => map.invalidateSize(), 60);
    return () => clearTimeout(id);
  }, [map]);
  return null;
}

/** Leaflet рисует в подписи свой префикс с флагом — оставляем только © Яндекс. */
function StripLeafletFlag() {
  const map = useMap();
  useEffect(() => {
    map.attributionControl?.setPrefix(false);
  }, [map]);
  return null;
}

/** Объекты портфеля на карте; маркер окрашен в цвет статуса. */
export default function SitesMap({ sites, height = "100%" }) {
  // scrollWheelZoom выключен: карта живёт внутри длинной страницы,
  // колесо должно прокручивать дашборд, а не зумить.
  return (
    <MapContainer
      center={MOSCOW}
      zoom={10}
      scrollWheelZoom={false}
      style={{ height, width: "100%" }}
    >
      <InvalidateSize />
      <StripLeafletFlag />
      <TileLayer
        attribution='&copy; <a href="https://yandex.ru/maps">Яндекс</a>'
        url="https://core-renderer-tiles.maps.yandex.net/tiles?l=map&x={x}&y={y}&z={z}&scale=1&lang=ru_RU&projection=web_mercator"
      />
      {sites
        .filter((s) => s.lat != null && s.lng != null)
        .map((s) => {
          const color = s.status_color || "#6C757D";
          const note =
            s.comment || s.top_deviation?.message || s.status_description || "";
          return (
            <CircleMarker
              key={s.id}
              center={[s.lat, s.lng]}
              radius={11}
              pathOptions={{ color, fillColor: color, fillOpacity: 0.85, weight: 2 }}
            >
              <Popup>
                {s.thumb_url && (
                  <img className="popup-thumb" src={s.thumb_url} alt={s.name} />
                )}
                <strong>{s.name}</strong>
                <StatusBadge status={s.status} />
                {s.cadastral_number && <span className="popup-note">{s.cadastral_number}</span>}
                <span className="popup-note">
                  {note.slice(0, 160)}
                  {note.length > 160 ? "…" : ""}
                </span>
                <a href={`#/site/${s.id}`}>Открыть карточку</a>
              </Popup>
            </CircleMarker>
          );
        })}
    </MapContainer>
  );
}
