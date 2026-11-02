import { describe, it, expect } from "vitest";
import { milestoneMarkers, releaseMarkers } from "./markers";

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
