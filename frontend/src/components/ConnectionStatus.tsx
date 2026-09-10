import { useEffect, useState } from 'react';
import { apiFetch } from '../lib/api';

type Props = {
  gmailConnected?: boolean;
  gmailEmail?: string;
  onOpenConnect: () => void;
};

type SheetsSnap = {
  connected?: boolean;
  userOauthConnected?: boolean;
  oauth?: { connected?: boolean; email?: string };
};

/**
 * Persistent integration status — recognition over recall.
 * Lives in chrome so Connect isn't only at the bottom of Workspace.
 */
export default function ConnectionStatus({
  gmailConnected = false,
  gmailEmail,
  onOpenConnect,
}: Props) {
  const [sheets, setSheets] = useState<SheetsSnap | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await apiFetch('/api/sheets/status');
        if (!r.ok || cancelled) return;
        setSheets(await r.json());
      } catch {
        // ignore — chrome status is best-effort
      }
    })();
    const onFocus = () => {
      void apiFetch('/api/sheets/status')
        .then(r => (r.ok ? r.json() : null))
        .then(data => {
          if (!cancelled && data) setSheets(data);
        })
        .catch(() => {});
    };
    window.addEventListener('focus', onFocus);
    return () => {
      cancelled = true;
      window.removeEventListener('focus', onFocus);
    };
  }, []);

  const sheetsLinked = Boolean(sheets?.connected);
  const sheetsOauth = Boolean(sheets?.userOauthConnected ?? sheets?.oauth?.connected);

  return (
    <div className="conn-status" aria-label="Connected accounts">
      <button type="button" className="conn-status__row" onClick={onOpenConnect} title={gmailEmail || 'Gmail'}>
        <span className={`conn-dot ${gmailConnected ? 'is-on' : 'is-off'}`} aria-hidden />
        <span className="conn-status__label">Gmail</span>
        <span className="conn-status__state">{gmailConnected ? 'On' : 'Off'}</span>
      </button>
      <button type="button" className="conn-status__row" onClick={onOpenConnect} title={sheets?.oauth?.email || 'Sheets'}>
        <span className={`conn-dot ${sheetsLinked ? 'is-on' : sheetsOauth ? 'is-ready' : 'is-off'}`} aria-hidden />
        <span className="conn-status__label">Sheets</span>
        <span className="conn-status__state">
          {sheetsLinked ? 'Linked' : sheetsOauth ? 'Ready' : 'Off'}
        </span>
      </button>
    </div>
  );
}
