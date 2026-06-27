import { useState } from "react";
import { ProviderIcon } from "./ProviderIcon";

type Provider = {
  id: string;
  label: string;
  icon: string;
  ready: boolean;
  status?: string; // overrides the badge text when not ready
  note?: string; // tooltip, e.g. why a host isn't supported
  example?: string;
  steps?: { title: string; items: string[] };
};

const PROVIDERS: Provider[] = [
  {
    id: "drive",
    label: "Google Drive",
    icon: "GD",
    ready: true,
    example: "https://drive.google.com/drive/folders/16VQhcRbCHkzhH2cq8T5DwyhTUBj2BrO4",
    steps: {
      title: "Share a Google Drive folder",
      items: [
        "Right-click your folder, choose Share",
        'Under "General access", set it to "Anyone with the link"',
        "Copy the link, paste it in the box above, then Scan",
      ],
    },
  },
  {
    id: "github",
    label: "GitHub",
    icon: "GH",
    ready: true,
    example: "https://github.com/yargerlab/Data",
    steps: {
      title: "Share a GitHub repository",
      items: [
        "Make the repository public",
        "Copy its URL (or just owner/repo)",
        "Paste it in the box above, then Scan",
      ],
    },
  },
  {
    id: "codeberg",
    label: "Codeberg",
    icon: "CB",
    ready: true,
    example: "https://codeberg.org/jyarger/PsiData",
    steps: {
      title: "Share a Codeberg repository",
      items: [
        "Make the repository public",
        "Copy its URL (e.g. codeberg.org/you/repo)",
        "Paste it in the box above, then Scan",
      ],
    },
  },
  {
    id: "box",
    label: "Box",
    icon: "BX",
    ready: true,
    example: "https://app.box.com/s/yigbg0fd5xj5n1hkxf8rcsemrkz7qgsx",
    steps: {
      title: "Share a Box folder",
      items: [
        'Open the folder, click Share, set access to "Anyone with the link"',
        "Copy the shared link (app.box.com/s/…)",
        "Paste it in the box above, then Scan",
      ],
    },
  },
];

export function ConnectGuide({ onTryExample }: { onTryExample?: (url: string) => void }) {
  const [active, setActive] = useState("drive");
  const provider = PROVIDERS.find((p) => p.id === active) ?? PROVIDERS[0];

  return (
    <div className="connect">
      <div className="connect-head">
        <span className="section-title" style={{ margin: 0 }}>Connect a public data source</span>
        <span className="muted">No account, no API key, no install — just a public share link.</span>
      </div>

      <div className="provider-grid">
        {PROVIDERS.map((p) => (
          <button
            key={p.id}
            className={"provider" + (p.id === active ? " active" : "") + (p.ready ? "" : " soon")}
            onClick={() => p.ready && setActive(p.id)}
            disabled={!p.ready}
            title={p.note}
          >
            <span className="provider-ic">
              <ProviderIcon id={p.id === "drive" ? "gdrive" : p.id} size={24} />
            </span>
            <span className="provider-name">{p.label}</span>
            <span className={"provider-status" + (p.ready ? " ok" : "")}>
              {p.ready ? "Ready" : (p.status ?? "Soon")}
            </span>
          </button>
        ))}
      </div>

      {provider.steps && (
        <div className="steps">
          <div className="steps-title">{provider.steps.title}</div>
          {provider.steps.items.map((item, i) => (
            <div className="step" key={i}>
              <span className="step-num">{i + 1}</span>
              <span>{item}</span>
            </div>
          ))}
          {provider.example && onTryExample && (
            <button className="btn ghost sm" onClick={() => onTryExample(provider.example!)}>
              Scan an example
            </button>
          )}
        </div>
      )}
    </div>
  );
}
