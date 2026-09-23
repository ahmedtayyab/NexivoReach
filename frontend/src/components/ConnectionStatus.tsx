import { useEffect, useState } from 'react';
import { apiFetch } from '../lib/api';

type Props = {
  gmailConnected?: boolean;
  gmailEmail?: string;
  gmailNeedsReconnect?: boolean;
  onOpenConnect: () => void;
};

type SheetsSnap = {
  connected?: boolean;
  userOauthConnected?: boolean;
  oauth?: { connected?: boolean; email?: string };
};

/**
 * Persistent integration status — recognition over recall.
 * Gmail Ready ≠ Sheets Linked (send needs Gmail specifically).
 */
export default function ConnectionStatus({
  gmailConnected = false,
  gmailEmail,
  gmailNeedsReconnect = false,
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

  let gmailState = 'Not connected';
  let gmailDot = 'is-off';
  if (gmailConnected) {
    gmailState = 'Send ready';
    gmailDot = 'is-on';
  } else if (gmailNeedsReconnect || gmailEmail) {
    gmailState = 'Reconnect';
    gmailDot = 'is-ready';
  }

  return (
    <div className="conn-status" aria-label="Connected accounts">
      <button
        type="button"
        className="conn-status__row"
        onClick={onOpenConnect}
        title={gmailEmail || 'Gmail — required to send outreach'}
      >
        <span className={`conn-dot ${gmailDot}`} aria-hidden />
        <span className="conn-status__label">Gmail</span>
        <span className="conn-status__state">{gmailState}</span>
      </button>
      <button
        type="button"
        className="conn-status__row"
        onClick={onOpenConnect}
        title={sheets?.oauth?.email || 'Sheets — spreadsheet backup (not used for sending)'}
      >
        <span className={`conn-dot ${sheetsLinked ? 'is-on' : sheetsOauth ? 'is-ready' : 'is-off'}`} aria-hidden />
        <span className="conn-status__label">Sheets</span>
        <span className="conn-status__state">
          {sheetsLinked ? 'Linked' : sheetsOauth ? 'Ready' : 'Not connected'}
        </span>
      </button>
    </div>
  );
}
