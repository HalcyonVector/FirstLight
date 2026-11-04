"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getForUser } from "@/lib/api";
import { formatDelta } from "@/lib/utils";
import { WatchButton } from "@/components/shared/WatchButton";

const KEY = "gti:gh-user:v1";

/** Rising repos matched to the topics and languages of a GitHub user's public stars. */
export function StarsRadar() {
  const [login, setLogin] = useState("");
  const [draft, setDraft] = useState("");

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(KEY) ?? "";
      setLogin(saved);
      setDraft(saved);
    } catch {
      /* storage blocked */
    }
  }, []);

  const { data, error, isFetching } = useQuery({
    queryKey: ["for-user", login.toLowerCase()],
    queryFn: () => getForUser(login),
    enabled: login.length > 0,
    staleTime: 60 * 60_000,
    retry: false,
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const next = draft.trim().replace(/^@/, "");
    setLogin(next);
    try {
      if (next) window.localStorage.setItem(KEY, next);
      else window.localStorage.removeItem(KEY);
    } catch {
      /* storage blocked */
    }
  }

  return (
    <>
      <div className="rulehead">
        From your GitHub stars <span className="meta">public stars only · results kept for a few hours, no account</span>
      </div>
      <form className="askbox ghbox" onSubmit={submit}>
        <span className="ico" aria-hidden>
          @
        </span>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Your GitHub username"
          aria-label="GitHub username"
          autoComplete="off"
          spellCheck={false}
          maxLength={39}
        />
        <button type="submit" disabled={!draft.trim() && !login}>
          {isFetching ? "…" : "Match"}
        </button>
      </form>

      {error && <div className="note">{(error as Error).message}</div>}

      {data && (
        <>
          <p className="radarlead">
            Read {data.starred} starred repos
            {data.topics.length > 0 && (
              <>
                : you lean towards <b>{data.topics.slice(0, 4).join(", ")}</b>
              </>
            )}
            {data.languages.length > 0 && <> in {data.languages.join(", ")}</>}. Rising repos you haven&apos;t
            starred yet:
          </p>
          {data.repos.length ? (
            data.repos.map((r) => (
              <Link key={r.id} className="lentry" href={`/repos/${r.id}`}>
                <div className="rk">◎</div>
                <div>
                  <div className="nm">
                    {r.full_name}
                    {r.language && <span className="lang">{r.language}</span>}
                  </div>
                  <div className="ds">
                    {r.like ? `Like ${r.like}, which you starred` : `Shares ${r.shared_topics.join(", ") || r.language}`}
                    {r.like && r.shared_topics.length > 0 && ` · ${r.shared_topics.join(", ")}`}
                  </div>
                </div>
                <div className="rt rtwatch">
                  <div>
                    <div className="gv">{formatDelta(r.stars_gained_week)}</div>
                    <div className="gl">this week</div>
                  </div>
                  <WatchButton
                    variant="icon"
                    repo={{
                      id: r.id,
                      full_name: r.full_name,
                      name: r.name,
                      language: r.language,
                      momentum_score: r.momentum_score,
                      stars_gained_week: r.stars_gained_week,
                    }}
                  />
                </div>
              </Link>
            ))
          ) : (
            <div className="note">
              Nothing tracked matches those stars yet. Starred repos with topics give the best matches.
            </div>
          )}
        </>
      )}
    </>
  );
}
