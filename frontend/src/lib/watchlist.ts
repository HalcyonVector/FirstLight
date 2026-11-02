// ─── Client-side watchlist, persisted in localStorage (no account, no backend) ──

export interface WatchItem {
  id: number;
  full_name: string;
  name: string;
  language: string | null;
  momentum_score: number;
  stars_gained_week: number;
  baseline_momentum: number; // momentum when first watched — used for delta + alerts
  watched_at: string;
}

const KEY = "gti:watchlist:v1";
const EVENT = "gti-watchlist-change";

function isBrowser() {
  return typeof window !== "undefined";
}

export function readWatchlist(): WatchItem[] {
  if (!isBrowser()) return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as WatchItem[]) : [];
  } catch {
    return [];
  }
}

function writeWatchlist(list: WatchItem[]) {
  if (!isBrowser()) return;
  window.localStorage.setItem(KEY, JSON.stringify(list));
  window.dispatchEvent(new Event(EVENT));
}

export function isWatched(id: number): boolean {
  return readWatchlist().some((w) => w.id === id);
}

export function addToWatchlist(item: Omit<WatchItem, "baseline_momentum" | "watched_at">) {
  const list = readWatchlist();
  if (list.some((w) => w.id === item.id)) return;
  list.push({
    ...item,
    baseline_momentum: item.momentum_score,
    watched_at: new Date().toISOString(),
  });
  writeWatchlist(list);
}

export function removeFromWatchlist(id: number) {
  writeWatchlist(readWatchlist().filter((w) => w.id !== id));
}

export function toggleWatch(item: Omit<WatchItem, "baseline_momentum" | "watched_at">): boolean {
  if (isWatched(item.id)) {
    removeFromWatchlist(item.id);
    return false;
  }
  addToWatchlist(item);
  return true;
}

/**
 * Merge items from an exported file into the watchlist (existing entries win).
 * Returns how many were added; throws on anything that isn't a watchlist export.
 */
export function importWatchlist(raw: unknown): number {
  const incoming = Array.isArray(raw) ? raw : (raw as { items?: unknown })?.items;
  if (!Array.isArray(incoming)) throw new Error("Not a watchlist file");
  const list = readWatchlist();
  let added = 0;
  for (const it of incoming as Partial<WatchItem>[]) {
    if (typeof it?.id !== "number" || typeof it.full_name !== "string") continue;
    if (list.some((w) => w.id === it.id)) continue;
    list.push({
      id: it.id,
      full_name: it.full_name,
      name: it.name ?? it.full_name.split("/").pop() ?? it.full_name,
      language: it.language ?? null,
      momentum_score: Number(it.momentum_score ?? 0),
      stars_gained_week: Number(it.stars_gained_week ?? 0),
      baseline_momentum: Number(it.baseline_momentum ?? it.momentum_score ?? 0),
      watched_at: it.watched_at ?? new Date().toISOString(),
    });
    added++;
  }
  writeWatchlist(list);
  return added;
}

/** Update the stored momentum snapshot for a watched repo (keeps deltas fresh). */
export function refreshWatchSnapshot(id: number, momentum: number, gainedWeek: number) {
  const list = readWatchlist();
  const item = list.find((w) => w.id === id);
  if (!item) return;
  item.momentum_score = momentum;
  item.stars_gained_week = gainedWeek;
  writeWatchlist(list);
}

/** Subscribe to any change (in this tab or another). Returns an unsubscribe fn. */
export function subscribeWatchlist(cb: () => void): () => void {
  if (!isBrowser()) return () => {};
  const handler = () => cb();
  window.addEventListener(EVENT, handler);
  window.addEventListener("storage", handler);
  return () => {
    window.removeEventListener(EVENT, handler);
    window.removeEventListener("storage", handler);
  };
}

// ─── Alert preferences ──────────────────────────────────────────────────────

const ALERT_KEY = "gti:alert-threshold:v1";

export function getAlertThreshold(): number {
  if (!isBrowser()) return 80;
  const raw = window.localStorage.getItem(ALERT_KEY);
  const n = raw ? Number(raw) : NaN;
  return Number.isFinite(n) ? n : 80;
}

export function setAlertThreshold(n: number) {
  if (!isBrowser()) return;
  window.localStorage.setItem(ALERT_KEY, String(n));
}
