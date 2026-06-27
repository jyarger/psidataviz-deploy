import { useState } from "react";
import { Resources } from "./Resources";
import { FeedbackForm } from "./FeedbackForm";
import { ProviderIcon } from "./ProviderIcon";

const REPO = "https://github.com/jyarger/PsiDataViz";

export function Footer() {
  const [showResources, setShowResources] = useState(false);
  const [showFeedback, setShowFeedback] = useState(false);
  return (
    <>
      <footer className="footer">
        <div>
          <h4>Resources</h4>
          <ul>
            <li>
              <a className="link" onClick={() => setShowResources(true)}>Documentation</a>
            </li>
            <li>
              <span className="muted">Tutorials <em>(coming soon)</em></span>
            </li>
            <li>
              <span className="muted">Gallery <em>(coming soon)</em></span>
            </li>
          </ul>
        </div>
        <div>
          <h4>Project</h4>
          <ul>
            <li>
              <a className="footer-gh" href={REPO} target="_blank" rel="noreferrer">
                <ProviderIcon id="github" size={16} /> GitHub
              </a>
            </li>
            <li>
              <a className="link" onClick={() => setShowFeedback(true)}>Feedback</a>
            </li>
          </ul>
        </div>
      </footer>
      {showResources && <Resources onClose={() => setShowResources(false)} />}
      {showFeedback && <FeedbackForm onClose={() => setShowFeedback(false)} />}
    </>
  );
}
