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
  const res = await fetch("/api/sites");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchSite(id) {
  const res = await fetch(`/api/sites/${id}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchTimeline(siteId) {
  const res = await fetch(`/api/sites/${siteId}/timeline`);
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
