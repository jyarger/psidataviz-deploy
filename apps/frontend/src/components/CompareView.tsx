import type { CompareResult } from "../api";

export function CompareView({ result }: { result: CompareResult }) {
  if (!result.comparable) {
    return (
      <p className="muted">
        Only one parseable format ({result.formats.join(", ") || "—"}) — nothing to compare.
      </p>
    );
  }
  return (
    <div>
      <p className="section-title">
        Format comparison <span className="muted">— {result.summary}</span>
      </p>
      {Object.entries(result.comparisons ?? {}).map(([ext, c]) => (
        <div key={ext} className="cmp">
          <div className="cmp-head">
            <span className="fmt">
              {result.primary} vs {ext}
            </span>
            <span className={c.identical ? "badge ok" : "badge diff"}>
              {c.error ? "error" : c.identical ? "identical data" : c.summary}
            </span>
          </div>
          {c.error ? (
            <p className="error">{c.error}</p>
          ) : (
            c.differences &&
            c.differences.length > 0 && (
              <ul className="difflist">
                {c.differences.map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
              </ul>
            )
          )}
        </div>
      ))}
    </div>
  );
}
