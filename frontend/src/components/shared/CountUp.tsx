"use client";

import { useEffect, useRef, useState } from "react";

/**
 * A number that counts up from zero the first time it appears.
 * Renders the final value on the server and for reduced-motion users.
 */
export function CountUp({
  value,
  format = (n) => String(Math.round(n)),
  duration = 700,
}: {
  value: number;
  format?: (n: number) => string;
  duration?: number;
}) {
  const [n, setN] = useState(value);
  const played = useRef(false);

  useEffect(() => {
    if (played.current || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setN(value);
      return;
    }
    played.current = true;
    const t0 = performance.now();
    let raf = 0;
    const step = (t: number) => {
      const p = Math.min(1, (t - t0) / duration);
      setN(value * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);

  return <span suppressHydrationWarning>{format(n)}</span>;
}
