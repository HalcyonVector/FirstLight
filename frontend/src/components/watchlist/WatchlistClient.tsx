"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueries } from "@tanstack/react-query";
import { getRepository } from "@/lib/api";
import { useWatchlist } from "@/hooks/useWatchlist";
import {
  addToWatchlist,
  getAlertThreshold,
  importWatchlist,
  readWatchlist,
  refreshWatchSnapshot,
  setAlertThreshold,
} from "@/lib/watchlist";
import { enablePush, disablePush, syncPush, isPushEnabled, pushSupported } from "@/lib/push";
import { formatDelta } from "@/lib/utils";

type PushState = "unknown" | "on" | "off" | "unsupported" | "server-disabled" | "denied";

export function WatchlistClient() {
  const { items, remove } = useWatchlist();
  const [threshold, setThreshold] = useState(80);
  const [push, setPush] = useState<PushState>("unknown");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const params = useSearchParams();
  const router = useRouter();

  const ids = items.map((w) => w.id);

  // A shared link (/watchlist?add=1,2,3) adds those repos, then tidies the URL.
  useEffect(() => {
    const add = (params.get("add") ?? "")
      .split(",")
      .map(Number)
      .filter((n) => Number.isInteger(n) && n > 0)
      .slice(0, 50);
    if (!add.length) return;
    Promise.allSettled(add.map((id) => getRepository(id))).then((res) => {
      let n = 0;
      res.forEach((r) => {
        if (r.status !== "fulfilled") return;
        const repo = r.value;
        if (readWatchlist().some((w) => w.id === repo.id)) return;
        addToWatchlist({
          id: repo.id,
          full_name: repo.full_name,
          name: repo.name,
          language: repo.language,
          momentum_score: repo.momentum_score,
          stars_gained_week: repo.stars_gained_week,
        });
        n++;
      });
      setMsg(`Added ${n} repositor${n === 1 ? "y" : "ies"} from the shared link.`);
      router.replace("/watchlist", { scroll: false });
    });
  }, [params, router]);

  function exportFile() {
    const blob = new Blob([JSON.stringify({ version: 1, items: readWatchlist() }, null, 2)], {
      type: "application/json",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "gti-watchlist.json";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function importFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    try {
      const n = importWatchlist(JSON.parse(await file.text()));
      setMsg(`Imported ${n} new repositor${n === 1 ? "y" : "ies"}.`);
    } catch {
      setMsg("That file isn't a watchlist export.");
    }
  }

  async function copyShareLink() {
    const url = `${window.location.origin}/watchlist?add=${ids.join(",")}`;
    try {
      await navigator.clipboard.writeText(url);
      setMsg("Share link copied. Opening it adds these repositories to any browser.");
    } catch {
      setMsg(url);
    }
  }

  useEffect(() => {
    setThreshold(getAlertThreshold());
    if (!pushSupported()) {
      setPush("unsupported");
      return;
    }
    isPushEnabled().then((on) => setPush(on ? "on" : "off"));
  }, []);

  // Live momentum for each watched repo
  const queries = useQueries({
    queries: items.map((w) => ({
      queryKey: ["repo", w.id],
      queryFn: () => getRepository(w.id),
      staleTime: 5 * 60_000,
      retry: false,
    })),
  });

  // Keep stored snapshots fresh for display/deltas
  useEffect(() => {
    queries.forEach((q, i) => {
      const live = q.data;
      const w = items[i];
      if (live && w) refreshWatchSnapshot(w.id, live.momentum_score, live.stars_gained_week);
    });
  }, [queries, items]);

  // If push is on, keep the backend in sync with the current watchlist + threshold
  useEffect(() => {
    if (push === "on") syncPush(ids, threshold).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [push, threshold, items.length]);

  async function turnOn() {
    setBusy(true);
    const res = await enablePush(ids, threshold);
    setBusy(false);
    if (res.ok) setPush("on");
    else if (res.reason === "server-disabled") setPush("server-disabled");
    else if (res.reason === "denied") setPush("denied");
    else if (res.reason === "unsupported") setPush("unsupported");
    else setPush("off");
  }

  async function turnOff() {
    setBusy(true);
    await disablePush().catch(() => {});
    setBusy(false);
    setPush("off");
  }

  function onThreshold(v: number) {
    setThreshold(v);
    setAlertThreshold(v);
  }

  return (
    <div className="fade-up">
      <div className="kicker">Your Watchlist · saved in this browser</div>
      <h1 className="big">
        Repositories you&apos;re <span className="ember">tracking.</span>
      </h1>
      <p className="standfirst">
        A private watchlist stored locally on your device — no account needed. Turn on background
        alerts to get a notification when a watched repo crosses your momentum threshold, even with
        the tab closed.
      </p>

      <div className="alertbar">
        <div className="alertctl">
          {push === "on" ? (
            <button className="watchbtn on" onClick={turnOff} disabled={busy}>
              ● Background alerts on — turn off
            </button>
          ) : push === "unsupported" ? (
            <span className="alertoff">Push not supported in this browser</span>
          ) : push === "server-disabled" ? (
            <span className="alertoff">Push not configured on the server (set VAPID keys)</span>
          ) : push === "denied" ? (
            <span className="alertoff">Notifications blocked — enable them in browser settings</span>
          ) : (
            <button className="watchbtn on" onClick={turnOn} disabled={busy}>
              {busy ? "Enabling…" : "Enable background alerts"}
            </button>
          )}
          <label className="thresh">
            Alert at momentum ≥ <b>{threshold}</b>
            <input
              type="range"
              min={40}
              max={100}
              step={5}
              value={threshold}
              onChange={(e) => onThreshold(Number(e.target.value))}
            />
          </label>
        </div>
        <div className="fm">
          {push === "on"
            ? "Alerts arrive via the 6-hour momentum job · even when closed"
            : `${items.length} watched`}
        </div>
      </div>

      <div className="wlactions">
        <button className="watchbtn" onClick={exportFile} disabled={!items.length}>
          Export
        </button>
        <button className="watchbtn" onClick={() => fileRef.current?.click()}>
          Import
        </button>
        <button className="watchbtn" onClick={copyShareLink} disabled={!items.length}>
          Copy share link
        </button>
        <input ref={fileRef} type="file" accept="application/json,.json" hidden onChange={importFile} />
        {msg && <span className="wlmsg">{msg}</span>}
      </div>

      {items.length === 0 ? (
        <div className="note" style={{ marginTop: 30 }}>
          You&apos;re not watching anything yet. Open any repository and press{" "}
          <b style={{ color: "var(--ember)" }}>☆ Watch</b>, or tap ☆ on a dashboard leaderboard row. Moving
          browsers? Use Import with a file you exported, or open a share link.
        </div>
      ) : (
        <div style={{ marginTop: 22 }}>
          {items.map((w, i) => {
            const live = queries[i]?.data;
            const current = live ? live.momentum_score : w.momentum_score;
            const delta = current - w.baseline_momentum;
            return (
              <div key={w.id} className="lentry">
                <div className="rk">{String(i + 1).padStart(2, "0")}</div>
                <div>
                  <Link href={`/repos/${w.id}`} className="nm" style={{ display: "block" }}>
                    {w.full_name}
                    {w.language && <span className="lang">{w.language}</span>}
                  </Link>
                  <div className="ds">
                    momentum {Math.round(current)} · since watched{" "}
                    <span className={delta >= 0 ? "up" : "dn"}>
                      {delta > 0 ? "▲ +" : delta < 0 ? "▼ " : "— "}
                      {Math.abs(delta).toFixed(0)}
                    </span>{" "}
                    · {formatDelta(w.stars_gained_week)} stars/wk
                  </div>
                </div>
                <div className="rt" style={{ display: "flex", gap: 14, alignItems: "center" }}>
                  <div>
                    <div className="gv">{Math.round(current)}</div>
                    <div className="gl">momentum</div>
                  </div>
                  <button
                    className="watchicon on"
                    title="Remove from watchlist"
                    onClick={() => remove(w.id)}
                  >
                    ★
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="foot">
        <div className="fb">{items.length} repositories watched</div>
        <div className="fm">Watchlist stored locally · alerts delivered free via Web Push</div>
      </div>
    </div>
  );
}
