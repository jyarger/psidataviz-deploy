import type { Diagnostics as DiagnosticsData } from "../api";

// Surfaces what didn't parse and where it would help most to add a reader — the iterate-on-coverage
// loop the project is built around.
export function Diagnostics({ d }: { d: DiagnosticsData }) {
  if (!d) return null;
  const allReadable = d.n_unsupported === 0;
  const known = d.unread_formats.filter((f) => f.note);
  return (
    <div className="card diag">
      <div className="toolbar" style={{ marginBottom: 8 }}>
        <span className="section-title" style={{ margin: 0 }}>Parsing coverage</span>
        <span className={"coverage" + (allReadable ? " ok" : "")}>{d.coverage}% readable</span>
      </div>
      <div className="coverage-bar">
        <div className="coverage-fill" style={{ width: `${d.coverage}%` }} />
      </div>
      {allReadable ? (
        <p className="muted" style={{ marginTop: 10 }}>
          All {d.n_supported} datasets here are readable. 🎉
        </p>
      ) : (
        <>
          <p className="muted" style={{ marginTop: 10 }}>
            <b>{d.n_supported}</b> readable · <b>{d.n_unsupported}</b> not yet. These formats are present
            but unread — the highest-count ones are where a new reader helps most:
          </p>
          <div className="chips">
            {d.unread_formats.map((f) => (
              <span
                className={"chip unread" + (f.note ? " known" : "")}
                key={f.ext}
                title={f.note || `${f.count} dataset${f.count === 1 ? "" : "s"} use ${f.ext || "(no extension)"}`}
              >
                {f.ext || "(none)"}
                <span className="count">{f.count}</span>
              </span>
            ))}
          </div>

          {known.length > 0 && (
            <div className="known-formats">
              <div className="section-title" style={{ margin: "14px 0 6px" }}>Recognized formats</div>
              <ul>
                {known.map((f) => (
                  <li key={f.ext}>
                    <code>{f.ext}</code> — {f.note}
                    {f.hint && <span className="diag-hint"> {f.hint}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {d.unread_items && d.unread_items.length > 0 && (
            <details className="unread-detail">
              <summary>Which datasets, and why ({d.unread_items.length})</summary>
              <ul className="unread-list">
                {d.unread_items.map((it, i) => (
                  <li key={i}>
                    <span className="fmt">{it.name}</span>
                    <span className="muted">
                      {" · "}
                      {it.technique} · {it.formats.join("/")}
                    </span>
                    <div className="diag-hint">
                      {it.reason}
                      {it.hint ? ` — ${it.hint}` : ""}
                    </div>
                  </li>
                ))}
              </ul>
            </details>
          )}

          <p className="muted diag-hint">
            Spot a format we should read? Open a{" "}
            <a
              className="link"
              href="https://github.com/jyarger/PsiDataViz/issues/new?labels=parsing,reader&template=data_format_request.md"
              target="_blank"
              rel="noreferrer"
            >
              data-format request
            </a>{" "}
            with a sample file.
          </p>
        </>
      )}
    </div>
  );
}
