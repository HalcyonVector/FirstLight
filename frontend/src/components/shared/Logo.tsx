/** The mark: a star trail climbing to a four-point star. Also drawn in app/icon.svg. */
export function LogoMark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" className="logomark">
      <path
        d="M2.5 20.5 L8.5 15 L12.5 17 L17 10.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity=".5"
      />
      <path d="M19 1.5 L20.4 5.1 L24 6.5 L20.4 7.9 L19 11.5 L17.6 7.9 L14 6.5 L17.6 5.1 Z" fill="var(--ember)" />
    </svg>
  );
}
