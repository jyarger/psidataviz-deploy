// Brand icons for the tested public data sources. Recognizable marks in brand colors; small inline SVGs.
export function ProviderIcon({ id, size = 22 }: { id: string; size?: number }) {
  const box = { width: size, height: size, display: "block", borderRadius: 5 } as const;
  switch (id) {
    case "github":
      return (
        <svg viewBox="0 0 16 16" style={{ width: size, height: size, display: "block" }} aria-hidden>
          <path
            fill="#e6edf3"
            d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38
            0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01
            1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95
            0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 2-.27c.68 0
            1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0
            3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01
            8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"
          />
        </svg>
      );
    case "gdrive":
      return (
        <svg viewBox="0 0 1443 1250" style={{ width: size, height: size, display: "block" }} aria-hidden>
          <path fill="#3777e3" d="m240.5 1250 240.5-416.7h962L1202.5 1250z" />
          <path fill="#ffcf63" d="m962 833.3h481L962 0H481z" />
          <path fill="#11a861" d="m0 833.3 240.5 416.7 481-833.3L481 0z" />
        </svg>
      );
    case "codeberg":
      return (
        <svg viewBox="0 0 24 24" style={box} aria-hidden>
          <rect width="24" height="24" rx="5" fill="#2185d0" />
          <path fill="#fff" d="M12 4 4.6 18.2A8 8 0 0 0 6 19.4L12 8.6l6 10.8a8 8 0 0 0 1.4-1.2z" />
        </svg>
      );
    case "box":
      return (
        <svg viewBox="0 0 24 24" style={box} aria-hidden>
          <rect width="24" height="24" rx="5" fill="#0061d5" />
          <text x="12" y="16.5" textAnchor="middle" fontSize="11" fontWeight="700" fill="#fff"
            fontFamily="Arial, sans-serif">box</text>
        </svg>
      );
    case "chemotion":
      return (
        <svg viewBox="0 0 24 24" style={box} aria-hidden>
          <rect width="24" height="24" rx="5" fill="#13a89e" />
          <path fill="none" stroke="#fff" strokeWidth="1.6" strokeLinejoin="round"
            d="M12 5.4 17 8.3v5.8L12 17l-5-2.9V8.3z" />
          <circle cx="12" cy="11.2" r="1.7" fill="#fff" />
        </svg>
      );
    default:
      return (
        <span className="src-ic" style={{ width: size, height: size }}>
          {id.slice(0, 2).toUpperCase()}
        </span>
      );
  }
}
