import BrandLockup from './brand/BrandLockup';
import ThemeToggle from './ThemeToggle';
import { brandAssets } from '../lib/brandAssets';

type Props = {
  /** When true, show a compact back control suitable inside the signed-in shell. */
  embedded?: boolean;
  onBack?: () => void;
};

/**
 * In-app privacy view (hash /privacy). Public Google URL remains /privacy.html.
 */
export default function PrivacyPolicyView({ embedded = false, onBack }: Props) {
  return (
    <div className={`legal-page ${embedded ? 'legal-page--embedded' : ''}`}>
      {!embedded && (
        <>
          <div className="login-theme-slot">
            <ThemeToggle compact />
          </div>
          <img
            src={brandAssets.loginAtmosphere}
            alt=""
            className="absolute inset-0 w-full h-full object-cover nr-kenburns opacity-40"
            decoding="async"
          />
          <div className="login-veil" aria-hidden />
          <div
            className="absolute -right-16 top-1/4 w-72 h-72 rounded-full opacity-40 pointer-events-none"
            style={{
              background:
                'radial-gradient(circle, color-mix(in srgb, var(--cta) 28%, transparent), transparent 70%)',
            }}
            aria-hidden
          />
        </>
      )}

      <div className="legal-page__inner nr-enter">
        {!embedded && (
          <div className="legal-page__brand">
            <a href="/" className="inline-flex">
              <BrandLockup size="md" />
            </a>
          </div>
        )}

        <article className="legal-sheet nr-enter nr-enter-delay-1">
          <p className="legal-sheet__eyebrow">Legal</p>
          <h1 className="legal-sheet__title">Privacy Policy</h1>
          <p className="legal-sheet__meta">Last updated: 15 September 2026 · NexivoReach</p>
          <p className="legal-sheet__lede">
            NexivoReach helps B2B sellers find buyer accounts and send outreach from their own Gmail.
            This policy explains what we collect, why, and how you control it.
          </p>

          <section>
            <h2>Who we are</h2>
            <p>
              NexivoReach is operated as a private / invite-only product deployment. “We” means the
              operators of the deployment you were invited to use.
            </p>
          </section>

          <section>
            <h2>What we collect</h2>
            <ul>
              <li>
                <strong>Account data</strong> — Google account email, name, and profile photo when you
                sign in with Google.
              </li>
              <li>
                <strong>Workspace data</strong> — company profiles, catalogs, ICP settings, leads,
                outreach drafts, activity logs, and support tickets you create.
              </li>
              <li>
                <strong>Connected Google services</strong> — if you connect Gmail and/or Google Sheets,
                we store OAuth tokens so we can send mail you approve and sync spreadsheets you
                authorize.
              </li>
              <li>
                <strong>Usage metrics</strong> — daily counts of hunts, extracts, prepares, and sends
                for rate limits and ops.
              </li>
              <li>
                <strong>Support content</strong> — ticket text, appeals, and any images you attach.
              </li>
            </ul>
          </section>

          <section>
            <h2>How we use data</h2>
            <ul>
              <li>To run discovery, scoring, drafting, sending, and Sheets sync that you request.</li>
              <li>To enforce invite-only access, usage caps, suspensions, and team seats.</li>
              <li>To operate admin tools for invited operators of this deployment.</li>
              <li>To improve reliability without selling your customer lists.</li>
            </ul>
          </section>

          <section>
            <h2>Google user data</h2>
            <p>
              Google sign-in uses basic profile scopes. Gmail and Sheets are connected only when you
              choose Workspace → Connect. We use Gmail only to send and read outreach threads you
              initiate, and Sheets only for workbooks you authorize. We do not use Google data for
              advertising.
            </p>
            <p>
              Disconnect Gmail or Sheets anytime in Workspace → Connect to clear stored tokens for
              that service.
            </p>
          </section>

          <section>
            <h2>AI and third parties</h2>
            <p>
              Research and drafting may send relevant product, ICP, or lead context to AI providers
              configured for this deployment (for example Groq or Gemini). Web search providers may
              receive search queries. If billing is enabled, the payment processor receives checkout
              details — we store plan status, not full card numbers.
            </p>
          </section>

          <section>
            <h2>Retention and deletion</h2>
            <p>
              Data is kept while your account is active. Request deletion via in-app Support (or the
              suspension appeal form if access is paused). Operators may delete accounts or clear
              leads on request.
            </p>
          </section>

          <section>
            <h2>Security</h2>
            <p>
              Access uses Google sign-in and session cookies. Gmail/Sheets tokens live on your user
              record for this deployment. Use Google 2FA when possible.
            </p>
          </section>

          <section>
            <h2>Children</h2>
            <p>NexivoReach is a B2B tool and is not directed at children under 16.</p>
          </section>

          <section>
            <h2>Contact</h2>
            <p>
              Questions or deletion requests: use in-app Support, or email the operator who invited
              you.
            </p>
          </section>

          <p className="legal-sheet__callout">
            Public URL for Google OAuth: <code>/privacy.html</code>
          </p>

          <div className="legal-sheet__nav">
            {onBack ? (
              <button type="button" className="linkish" onClick={onBack}>
                ← Back
              </button>
            ) : (
              <a href="/">← Back to app</a>
            )}
            <a href="/#support">Support</a>
            <a href="/privacy.html">Open public page</a>
          </div>
        </article>
      </div>
    </div>
  );
}
