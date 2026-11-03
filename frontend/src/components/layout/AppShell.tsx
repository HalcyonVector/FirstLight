"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { CommandPalette } from "@/components/shared/CommandPalette";
import { LogoMark } from "@/components/shared/Logo";

// 24px line icons for the phone tab bar.
const ICONS: Record<string, React.ReactNode> = {
  home: <path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" />,
  week: <path d="M4 5h16v14H4zM4 9h16M8 3v4M16 3v4M8 13h3M8 16h6" />,
  trends: <path d="M3 17l6-6 4 4 8-8M15 7h6v6" />,
  repos: <path d="M5 4h14v16H5zM9 8h6M9 12h6M9 16h4" />,
  breakouts: <path d="M12 2l2.6 6.4L21 11l-6.4 2.6L12 20l-2.6-6.4L3 11l6.4-2.6z" />,
  you: <path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z" />,
};

// `also` lists other routes that live under the same tab.
const NAV = [
  { href: "/", label: "Dashboard", short: "Home", icon: "home" },
  { href: "/this-week", label: "This Week", short: "Week", icon: "week" },
  { href: "/trends", label: "Trends", short: "Trends", icon: "trends", also: ["/radar"] },
  { href: "/repositories", label: "Repos", short: "Repos", icon: "repos", also: ["/languages", "/repos/", "/compare"] },
  { href: "/breakouts", label: "Breakouts", short: "Calls", icon: "breakouts" },
  { href: "/for-you", label: "For You", short: "For you", icon: "you", also: ["/watchlist"] },
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
              <LogoMark size={24} />
              <span>
                GitHub Trending <em>Intelligence</em>
              </span>
            </Link>
            <div className="issue" suppressHydrationWarning>
              {dateLine}
            </div>
            <div className="mtools">
              <button className="mtheme" onClick={toggleTheme} aria-label="Toggle color theme">
                {theme === "dusk" ? "◐" : "◑"}
              </button>
              <button className="msearch" onClick={() => setCmdOpen(true)} aria-label="Open search">
                ⌕
              </button>
            </div>
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

      <nav className="bnav" aria-label="Sections">
        {NAV.map((n) => (
          <Link key={n.href} href={n.href} className={cn(isActive(n) && "on")} aria-label={n.label}>
            <svg
              viewBox="0 0 24 24"
              width="21"
              height="21"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              {ICONS[n.icon]}
            </svg>
            <span>{n.short}</span>
          </Link>
        ))}
      </nav>

      <CommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} />
    </>
  );
}
