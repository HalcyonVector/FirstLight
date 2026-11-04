import { describe, it, expect } from "vitest";
import { milestoneMarkers, releaseMarkers, spikeCauseLine, spikeMarkers } from "./markers";

const days = ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"].map((date) => ({ date }));

const rel = (tag: string, published_at: string, prerelease = false) => ({
  tag,
  name: tag,
  published_at,
  url: null,
  prerelease,
  snippet: null,
});

describe("releaseMarkers", () => {
  it("places a release on its publish day", () => {
    const m = releaseMarkers(days, [rel("v2", "2026-10-03T15:00:00Z")]);
    expect(m).toEqual([{ index: 2, label: "Released v2", kind: "release" }]);
  });
  it("skips prereleases and releases before the range", () => {
    expect(releaseMarkers(days, [rel("v0", "2026-09-01T00:00:00Z"), rel("rc", "2026-10-02T00:00:00Z", true)])).toEqual([]);
  });
});

describe("milestoneMarkers", () => {
  it("marks the day a round number is crossed", () => {
    const m = milestoneMarkers([{ stars_total: 900 }, { stars_total: 980 }, { stars_total: 1040 }]);
    expect(m).toEqual([{ index: 2, label: "Crossed 1.0k ★", kind: "milestone" }]);
  });
  it("ignores the jump from an empty first snapshot", () => {
    expect(milestoneMarkers([{ stars_total: 0 }, { stars_total: 5000 }])).toEqual([]);
  });
});

describe("spikeMarkers", () => {
  type Cause = import("./types").SpikeCause;
  const hn: Cause = { kind: "hn", title: "Show HN", url: null, at: null, points: 412 };
  const spike = (date: string, causes: Cause[] = [hn]) => ({ date, gain: 2500, baseline: 70, causes });

  it("labels a spike with its cause", () => {
    expect(spikeMarkers(days, [spike("2026-10-02")])).toEqual([
      { index: 1, label: "+2.5k ★ · Hacker News · 412 points", kind: "spike" },
    ]);
  });
  it("falls back to a release, then to the jump itself", () => {
    const rel: Cause = { kind: "release", title: "v2.0", url: null, at: null };
    expect(spikeCauseLine(spike("2026-10-02", [rel]))).toBe("Released v2.0");
    expect(spikeCauseLine(spike("2026-10-02", []))).toBe("+2.5k stars in a day");
  });
  it("skips spikes outside the chart's range", () => {
    expect(spikeMarkers(days, [spike("2026-09-01")])).toEqual([]);
  });
});
