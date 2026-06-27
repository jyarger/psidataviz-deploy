import { useEffect, useRef, useState } from "react";
import Plotly from "plotly.js-dist-min";
import { audioSrc, type DatasetData } from "../api";

// "PsiDataSound" — visualize an acoustic .wav as its time-domain waveform or its FFT spectrum, and play
// it in the browser. The dataset carries both views as signals (0 = waveform, 1 = FFT).
export function WaveformPlayer({ dataset }: { dataset: DatasetData }) {
  const ref = useRef<HTMLDivElement>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const [view, setView] = useState(0); // 0 = waveform, 1 = FFT
  const [playing, setPlaying] = useState(false);
  const sig = dataset.signals[view] ?? dataset.signals[0];
  const src = audioSrc(dataset);
  const title = (dataset.metadata.sample_name as string) || dataset.filename;

  useEffect(() => {
    if (!ref.current || !sig) return;
    const axisTitle = (a: { label: string; unit: string | null }) =>
      a.unit ? `${a.label} (${a.unit})` : a.label;
    const trace = {
      x: sig.points.map((p) => p[0]),
      y: sig.points.map((p) => p[1]),
      type: "scattergl",
      mode: "lines",
      line: { color: view === 0 ? "#4aa3ff" : "#51cf66", width: 1 },
    };
    const layout = {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#c9d1d9", size: 12 },
      margin: { l: 60, r: 16, t: 12, b: 44 },
      xaxis: { title: { text: axisTitle(sig.x), font: { size: 15 } }, gridcolor: "#21262d", zeroline: false },
      yaxis: { title: { text: axisTitle(sig.y), font: { size: 15 } }, gridcolor: "#21262d", zeroline: false },
      showlegend: false,
    };
    Plotly.react(ref.current, [trace] as never, layout as never, { responsive: true, displaylogo: false });
  }, [sig, view]);

  function togglePlay() {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) void a.play();
    else a.pause();
  }

  return (
    <div className="wave-card">
      <div className="wave-head">
        <span className="wave-brand" title="PsiDataSound">
          <span className="psi">Ψ</span>DataSound
        </span>
        <span className="wave-title">{title}</span>
        {dataset.audio && (
          <span className="mol-meta">
            {" "}
            · {dataset.audio.sample_rate / 1000} kHz · {dataset.audio.duration.toFixed(1)} s
          </span>
        )}
        <div className="wave-controls">
          <div className="seg">
            <button className={view === 0 ? "active" : ""} onClick={() => setView(0)}>
              Waveform
            </button>
            <button className={view === 1 ? "active" : ""} onClick={() => setView(1)}>
              Spectrum (FFT)
            </button>
          </div>
          {src && (
            <button className="play-btn" onClick={togglePlay} title="Play / pause">
              <span className="psi">Ψ</span> {playing ? "❚❚ Pause" : "▶ Play"}
            </button>
          )}
        </div>
      </div>
      <div ref={ref} className="wave-canvas" />
      {src && (
        <audio
          ref={audioRef}
          src={src}
          preload="none"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
        />
      )}
    </div>
  );
}
