import { useState } from "react";

const CONTACT = "jyarger@proton.me";

// A simple feedback form. With no backend store yet, "Send" composes an email to the maintainer
// (a backend /api/feedback can replace the mailto later without changing this UI).
export function FeedbackForm({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");

  function send() {
    const body = `From: ${name || "(anonymous)"}${email ? ` <${email}>` : ""}\n\n${message}`;
    window.location.href =
      `mailto:${CONTACT}?subject=${encodeURIComponent("PsiDataViz feedback")}` +
      `&body=${encodeURIComponent(body)}`;
    onClose();
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>
            <span className="psi">Ψ</span> Feedback
          </h2>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <p className="muted">
          Spotted a bug, a format we should read, or have an idea? Tell us — it goes to the maintainer.
        </p>
        <div className="fb-form">
          <input type="text" placeholder="Your name (optional)" value={name}
            onChange={(e) => setName(e.target.value)} />
          <input type="text" placeholder="Your email (optional)" value={email}
            onChange={(e) => setEmail(e.target.value)} />
          <textarea placeholder="Your message…" rows={5} value={message}
            onChange={(e) => setMessage(e.target.value)} />
          <button className="btn" disabled={!message.trim()} onClick={send}>
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
