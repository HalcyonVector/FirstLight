"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { CommandPalette } from "@/components/shared/CommandPalette";

// `also` lists other routes that live under the same tab.
const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/this-week", label: "This Week" },
  { href: "/trends", label: "Trends", also: ["/radar"] },
  { href: "/repositories", label: "Repos", also: ["/languages", "/repos/"] },
  { href: "/compare", label: "Compare" },
  { href: "/watchlist", label: "Watchlist" },
];

type Theme = "dusk" | "paper";

function currentTheme(): Theme {
  return document.documentElement.getAttribute("data-theme") === "paper" ? "paper" : "dusk";
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [cmdOpen, setCmdOpen] = useState(false);
  const [theme, setTheme] = useState<Theme>("dusk");
  const [shortcut, setShortcut] = useState("Ctrl K");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCmdOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // The pre-paint script in layout.tsx has already set data-theme; mirror it here.
  useEffect(() => {
    setTheme(currentTheme());
    if (/Mac|iPhone|iPad/.test(navigator.platform)) setShortcut("⌘K");
  }, []);

  function applyTheme(next: Theme) {
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    try {
      window.localStorage.setItem("gti:theme", next);
    } catch {
      /* ignore */
    }
  }
  function toggleTheme() {
    applyTheme(currentTheme() === "dusk" ? "paper" : "dusk");
  }

  // The command palette requests a theme toggle via a window event
  useEffect(() => {
    window.addEventListener("gti-toggle-theme", toggleTheme);
    return () => window.removeEventListener("gti-toggle-theme", toggleTheme);
  }, []);

  const dateLine = new Date()
    .toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric", year: "numeric" })
    .toUpperCase();

  const isActive = (n: (typeof NAV)[number]) =>
    n.href === "/"
      ? pathname === "/"
      : [n.href, ...(n.also ?? [])].some((h) => pathname.startsWith(h));

  return (
    <>
      <header className="mast">
        <div className="wrap">
          <div className="masthead">
            <Link href="/" className="brand">
              GitHub Trending <em>Intelligence</em>
            </Link>
            <div className="issue" suppressHydrationWarning>
              {dateLine}
            </div>
            <button className="msearch" onClick={() => setCmdOpen(true)} aria-label="Open search">
              ⌕
            </button>
          </div>
          <nav className="tabs">
            {NAV.map((n) => (
              <Link key={n.href} href={n.href} className={cn(isActive(n) && "on")}>
                {n.label}
              </Link>
            ))}
            <div className="spring">
              <button className="themebtn" onClick={toggleTheme} aria-label="Toggle color theme">
                {theme === "dusk" ? "◐ Dusk" : "◑ Paper"}
              </button>
              <button
                className="kbd"
                onClick={() => setCmdOpen(true)}
                aria-label="Open search"
              >
                Search <span suppressHydrationWarning>{shortcut}</span>
              </button>
            </div>
          </nav>
        </div>
      </header>

      <main className="wrap" style={{ paddingBottom: 90, position: "relative", zIndex: 2 }}>
        {children}
      </main>

      <CommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} />
    </>
  );
}
