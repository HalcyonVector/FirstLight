"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { search as searchApi } from "@/lib/api";
import { getRecentRepos } from "@/lib/recent";
import { formatDelta } from "@/lib/utils";

interface Props {
  open: boolean;
  onClose: () => void;
}

const NAV_CMDS = [
  { label: "Dashboard", href: "/" },
  { label: "This Week", href: "/this-week" },
  { label: "Trends", href: "/trends" },
  { label: "Radar", href: "/radar" },
  { label: "Repositories", href: "/repositories" },
  { label: "Languages", href: "/languages" },
  { label: "Compare", href: "/compare" },
  { label: "Watchlist", href: "/watchlist" },
  { label: "Search", href: "/search" },
];

interface CmdItem {
  key: string;
  label: string;
  sub: string;
  run: () => void;
}

export function CommandPalette({ open, onClose }: Props) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);

  const { data } = useQuery({
    queryKey: ["cmdk-search", q],
    queryFn: () => searchApi(q, 6),
    enabled: open && q.trim().length >= 2,
    staleTime: 30_000,
  });

  useEffect(() => {
    if (open) {
      setQ("");
      setSel(0);
    }
  }, [open]);

  useEffect(() => setSel(0), [q]);

  const items: CmdItem[] = useMemo(() => {
    const ql = q.trim().toLowerCase();
    const nav = NAV_CMDS.filter((n) => !ql || n.label.toLowerCase().includes(ql)).map((n) => ({
      key: `nav:${n.href}`,
      label: n.label,
      sub: "Go to page",
      run: () => {
        onClose();
        router.push(n.href);
      },
    }));
    const theme: CmdItem[] =
      !ql || "theme dusk paper".includes(ql)
        ? [
            {
              key: "act:theme",
              label: "Toggle theme",
              sub: "Dusk / Paper",
              run: () => {
                window.dispatchEvent(new Event("gti-toggle-theme"));
                onClose();
              },
            },
          ]
        : [];

    if (ql.length >= 2) {
      const repos = (data?.repos ?? []).map((r) => ({
        key: `repo:${r.id}`,
        label: r.full_name,
        sub: `${formatDelta(r.stars_gained_week)} stars/wk`,
        run: () => {
          onClose();
          router.push(`/repos/${r.id}`);
        },
      }));
      return [...repos, ...nav, ...theme];
    }

    const recent = getRecentRepos().map((r) => ({
      key: `recent:${r.id}`,
      label: r.full_name,
      sub: "Recent",
      run: () => {
        onClose();
        router.push(`/repos/${r.id}`);
      },
    }));
    return [...recent, ...nav, ...theme];
  }, [q, data, onClose, router]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowDown") {
        e.preventDefault();
        setSel((s) => Math.min(s + 1, items.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSel((s) => Math.max(s - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        items[sel]?.run();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, items, sel, onClose]);

  if (!open) return null;

  return (
    <div className="cmdk" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="cmdbox" role="dialog" aria-modal="true">
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search repositories, or jump to a page…"
          aria-label="Command palette search"
        />
        <div className="cres">
          {items.length ? (
            items.map((it, i) => (
              <div
                key={it.key}
                className="cr"
                aria-selected={i === sel}
                onMouseEnter={() => setSel(i)}
                onClick={it.run}
              >
                <span className="cn">{it.label}</span>
                <span className="cg">{it.sub}</span>
              </div>
            ))
          ) : (
            <div className="cr">
              <span className="cn" style={{ color: "var(--dim)" }}>
                No matches
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
