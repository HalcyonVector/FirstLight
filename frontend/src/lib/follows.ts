// ─── Followed categories and languages for the For You feed (localStorage) ────

export interface Follows {
  categories: string[]; // category slugs
  languages: string[];
}

const KEY = "gti:follows:v1";
const EVENT = "gti-follows-change";
const EMPTY: Follows = { categories: [], languages: [] };

export function readFollows(): Follows {
  if (typeof window === "undefined") return EMPTY;
  try {
    const raw = JSON.parse(window.localStorage.getItem(KEY) ?? "null") as Partial<Follows> | null;
    return {
      categories: Array.isArray(raw?.categories) ? raw!.categories.filter((c) => typeof c === "string") : [],
      languages: Array.isArray(raw?.languages) ? raw!.languages.filter((l) => typeof l === "string") : [],
    };
  } catch {
    return EMPTY;
  }
}

function write(f: Follows) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(f));
  } catch {
    /* storage blocked: follows just won't persist */
  }
  window.dispatchEvent(new Event(EVENT));
}

export function toggleFollow(kind: keyof Follows, value: string): boolean {
  const f = readFollows();
  const on = f[kind].includes(value);
  write({ ...f, [kind]: on ? f[kind].filter((v) => v !== value) : [...f[kind], value] });
  return !on;
}

export function subscribeFollows(cb: () => void): () => void {
  const onStorage = (e: StorageEvent) => e.key === KEY && cb();
  window.addEventListener(EVENT, cb);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(EVENT, cb);
    window.removeEventListener("storage", onStorage);
  };
}
