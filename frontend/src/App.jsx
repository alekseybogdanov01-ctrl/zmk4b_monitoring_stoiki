import { useEffect, useState } from "react";
import DemoPage from "./pages/DemoPage.jsx";
import SitePage from "./pages/SitePage.jsx";
import PhotoPage from "./pages/PhotoPage.jsx";
import DetectPage from "./pages/DetectPage.jsx";
import VersionKPage from "./pages/VersionKPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";

const THEME_KEY = "bw-theme";

function readTheme() {
  const current = document.documentElement.dataset.theme;
  return current === "light" ? "light" : "dark";
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const color = document.querySelector('meta[name="theme-color"]');
  if (color) color.setAttribute("content", theme === "light" ? "#f3f6fb" : "#0b0f16");
  const scheme = document.querySelector('meta[name="color-scheme"]');
  if (scheme) scheme.setAttribute("content", theme);
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* приватный режим */
  }
}

function parseHash() {
  const raw = (window.location.hash || "#/demo").replace(/^#/, "") || "/demo";
  const parts = raw.split("/").filter(Boolean);
  const page = parts[0] || "demo";
  return { page, id: parts[1] || null };
}

export default function App() {
  const [route, setRoute] = useState(parseHash);
  const [theme, setTheme] = useState(readTheme);

  const chooseTheme = (next) => {
    setTheme(next);
    applyTheme(next);
  };

  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  let body;
  // Карта переехала на дашборд, но старые ссылки #/map ещё живут в закладках.
  if (route.page === "dashboard" || route.page === "map") body = <DashboardPage />;
  else if (route.page === "detect") body = <DetectPage />;
  else if (route.page === "version-k") body = <VersionKPage />;
  else if (route.page === "site" && route.id) body = <SitePage siteId={route.id} />;
  else if (route.page === "photo" && route.id) body = <PhotoPage photoId={route.id} />;
  else body = <DemoPage />;

  return (
    <>
      <header className="appbar">
        <nav className="topnav">
          <a className="brand" href="#/demo">
            <img className="brand-mark" src="/radar.png" alt="" />
            Строй<span>Радар</span>
          </a>
          <div className="nav-links">
            <a
              href="#/dashboard"
              className={
                route.page === "dashboard" || route.page === "map" ? "active" : ""
              }
            >
              Дашборд
            </a>
            <a href="#/demo" className={route.page === "demo" ? "active" : ""}>
              Демо
            </a>
            <a href="#/detect" className={route.page === "detect" ? "active" : ""}>
              Тест модели
            </a>
            <a href="#/version-k" className={route.page === "version-k" ? "active" : ""}>
              О продукте
            </a>
          </div>
          <div className="theme-switch" role="group" aria-label="Тема оформления">
            <button
              type="button"
              aria-pressed={theme === "dark"}
              onClick={() => chooseTheme("dark")}
            >
              Тёмная
            </button>
            <button
              type="button"
              aria-pressed={theme === "light"}
              onClick={() => chooseTheme("light")}
            >
              Светлая
            </button>
          </div>
        </nav>
      </header>
      <main className="app">{body}</main>
    </>
  );
}
