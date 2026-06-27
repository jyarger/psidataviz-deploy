export type View = "QUICK" | "DATA" | "VIZ";

// The advanced tabs use Dirac bracket-ket wordmarks: Ψ|Data⟩ and Ψ|Viz⟩.
// (QUICK is the home page — reached via the logo, not a nav item.)
const ITEMS: { id: View; label: string; ket?: string }[] = [
  { id: "DATA", label: "Data", ket: "|Data⟩" },
  { id: "VIZ", label: "Viz", ket: "|Viz⟩" },
];

export function Header({ view, onNav }: { view: View; onNav: (v: View) => void }) {
  return (
    <header className="header">
      <div className="brand" onClick={() => onNav("QUICK")} role="button" tabIndex={0}
        title="Home">
        <span className="psi">Ψ</span>DataViz
        <small>Scientific Data Visualization</small>
      </div>
      <nav className="nav">
        {ITEMS.map((it) => (
          <button key={it.id} className={it.id === view ? "active" : ""} onClick={() => onNav(it.id)}>
            {it.ket ? (
              <>
                <span className="psi">Ψ</span>
                <span className="ket">{it.ket}</span>
              </>
            ) : (
              it.label
            )}
          </button>
        ))}
        <button className="nav-soon" disabled title="Sign in / register — coming soon">
          <span className="psi">Ψ</span>
          <span className="ket">|Login⟩</span>
        </button>
      </nav>
    </header>
  );
}
