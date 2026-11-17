// Site-wide footer: what FirstLight is, where its data comes from, and the
// methods it leans on. Every outbound link opens in a new tab.

const REPO = "https://github.com/HalcyonVector/FirstLight";

const DATA = [
  {
    name: "GitHub REST API",
    href: "https://docs.github.com/en/rest",
    what: "Repositories, daily stars and forks, releases and weekly star history.",
  },
  {
    name: "Hacker News (Algolia API)",
    href: "https://hn.algolia.com/api",
    what: "Stories and points that line up with a star spike.",
  },
  {
    name: "Lobsters",
    href: "https://lobste.rs/about",
    what: "Stories linking to a repo, read from its public domain feeds.",
  },
  {
    name: "Bluesky AppView API",
    href: "https://docs.bsky.app/docs/api/app-bsky-feed-search-posts",
    what: "Posts sharing a repo inside a spike's date window.",
  },
  {
    name: "Groq",
    href: "https://console.groq.com/docs/overview",
    what: "Open-weight language models that write the summaries and answers.",
  },
];

const REFS = [
  {
    name: "Brier score",
    href: "https://en.wikipedia.org/wiki/Brier_score",
    what: "How the breakout odds are scored against a base rate (Brier, 1950).",
  },
  {
    name: "Probability calibration",
    href: "https://scikit-learn.org/stable/modules/calibration.html",
    what: "Reliability bins used to check the odds mean what they say.",
  },
  {
    name: "Regularised logistic regression",
    href: "https://scikit-learn.org/stable/modules/linear_model.html#logistic-regression",
    what: "The L2 logistic model behind each breakout probability.",
  },
];

function Ext({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}

export function SiteFooter() {
  return (
    <footer className="sitefoot">
      <div className="wrap">
        <div className="footgrid">
          <section>
            <h4>About</h4>
            <p>
              FirstLight watches GitHub for repositories gaining stars faster than usual, explains each spike
              from releases and public discussion, and puts odds on which ones keep growing.
            </p>
            <p className="fnote">
              Odds are a statistical estimate, not advice. Summaries are written by a language model and can be
              wrong, so check the linked sources.
            </p>
            <p>
              <Ext href={REPO}>Source code on GitHub</Ext>
            </p>
          </section>
          <section>
            <h4>Data</h4>
            <ul>
              {DATA.map((d) => (
                <li key={d.href}>
                  <Ext href={d.href}>{d.name}</Ext>
                  <span>{d.what}</span>
                </li>
              ))}
            </ul>
          </section>
          <section>
            <h4>References</h4>
            <ul>
              {REFS.map((r) => (
                <li key={r.href}>
                  <Ext href={r.href}>{r.name}</Ext>
                  <span>{r.what}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>
        <div className="footbar">
          <span>
            Built by <strong>Sagnik</strong>
          </span>
          <Ext href="https://github.com/HalcyonVector">GitHub @HalcyonVector</Ext>
          <Ext href={REPO}>Repository</Ext>
          <Ext href={`${REPO}/blob/main/LICENSE`}>MIT License</Ext>
        </div>
      </div>
    </footer>
  );
}
