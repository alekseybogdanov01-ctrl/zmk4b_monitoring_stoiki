async function parseError(res) {
  try {
    const data = await res.json();
    if (data?.detail) {
      return typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail);
    }
  } catch {
    /* ignore */
  }
  return `HTTP ${res.status}`;
}

export async function fetchHealth() {
  const res = await fetch("/api/health");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchClasses() {
  const res = await fetch("/api/classes");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchStages() {
  const res = await fetch("/api/stages");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function detectFrame(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/detect", { method: "POST", body: form });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchSites() {
  const res = await fetch("/api/sites", { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function lookupParcel(cadastral) {
  const params = new URLSearchParams({ cadastral });
  const res = await fetch(`/api/nspd/parcel?${params}`, { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function createSite(body) {
  const res = await fetch("/api/sites", {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function downloadSitesExcel() {
  const res = await fetch("/api/sites/export", { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "объекты.xlsx";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/** Сводка по всем объектам города для дашборда */
export async function fetchDashboard() {
  const res = await fetch("/api/dashboard", { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchSite(id) {
  const res = await fetch(`/api/sites/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchTimeline(siteId) {
  const res = await fetch(`/api/sites/${siteId}/timeline`, { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchPhoto(photoId) {
  const res = await fetch(`/api/photos/${photoId}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function uploadSitePhoto(siteId, file, capturedAt) {
  const form = new FormData();
  form.append("file", file);
  form.append("captured_at", capturedAt);
  const res = await fetch(`/api/sites/${siteId}/photos`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function uploadSitePlan(siteId, file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`/api/sites/${siteId}/plan`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

/** Готовый пакет из папки Демо: метаданные + URL файлов. */
export async function fetchDemoPack() {
  const res = await fetch("/api/demo/pack");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

async function fileFromUrl(url, name, fallbackType) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await parseError(res));
  const blob = await res.blob();
  return new File([blob], name, { type: blob.type || fallbackType });
}

/** Скачать файлы пакета и собрать File, как если бы их выбрали вручную. */
export async function loadDemoPackFiles() {
  const pack = await fetchDemoPack();
  const planFile = await fileFromUrl(
    pack.plan.url,
    pack.plan.name,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  );
  const photos = [];
  for (const photo of pack.photos) {
    photos.push(await fileFromUrl(photo.url, photo.name, "image/jpeg"));
  }
  return {
    siteName: pack.site_name,
    baseDate: pack.base_date,
    stepDays: pack.step_days,
    planFile,
    photos,
  };
}

/** Полный сценарий ТЗ: план + фото с датами → timeline + отклонения */
export async function runDemoAnalyze({
  planFile,
  photos,
  dates,
  siteName = "Демо-площадка",
}) {
  const form = new FormData();
  form.append("plan_file", planFile);
  photos.forEach((f) => form.append("photos", f));
  form.append("dates", JSON.stringify(dates));
  form.append("site_name", siteName);
  const res = await fetch("/api/demo/analyze", { method: "POST", body: form });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
