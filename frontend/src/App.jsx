import { useEffect, useState } from "react";
import { fetchHealth } from "./api.js";
import DemoPage from "./pages/DemoPage.jsx";
import MapPage from "./pages/MapPage.jsx";
import SitePage from "./pages/SitePage.jsx";
import PhotoPage from "./pages/PhotoPage.jsx";
import DetectPage from "./pages/DetectPage.jsx";

function parseHash() {
  const raw = (window.location.hash || "#/demo").replace(/^#/, "") || "/demo";
  const parts = raw.split("/").filter(Boolean);
  const page = parts[0] || "demo";
  return { page, id: parts[1] || null };
}

export default function App() {
  const [route, setRoute] = useState(parseHash);
  const [health, setHealth] = useState(null);

  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch((e) => setHealth({ status: "error", model_ready: false, model: e.message }));
  }, []);

  const healthClass = health?.model_ready ? "ok" : health ? "bad" : "";

  let body;
  if (route.page === "map") body = <MapPage />;
  else if (route.page === "detect") body = <DetectPage />;
  else if (route.page === "site" && route.id) body = <SitePage siteId={route.id} />;
  else if (route.page === "photo" && route.id) body = <PhotoPage photoId={route.id} />;
  else body = <DemoPage />;

  return (
    <div className="app">
      <nav className="topnav">
        <a className="brand" href="#/demo">
          Build <span>Watch</span>
        </a>
        <div className="nav-links">
          <a href="#/demo" className={route.page === "demo" ? "active" : ""}>
            Демо
          </a>
          <a href="#/map" className={route.page === "map" ? "active" : ""}>
            Карта
          </a>
          <a href="#/detect" className={route.page === "detect" ? "active" : ""}>
            Тест модели
          </a>
        </div>
        <div className={`health ${healthClass}`}>
          {health?.model_ready
            ? `model ready · ${health.classes} cls`
            : health
              ? `model: ${health.status}`
              : "connecting…"}
        </div>
      </nav>
      {body}
    </div>
  );
}
