import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../lib/api';
import type { ToastKind } from './ToastHost';

type PendingMessage = {
  id: string;
  messageId: string;
  title: string;
  body: string;
  severity: string;
  requiresAck?: boolean;
  status: string;
};

type Props = {
  userId?: string | null;
  onToast?: (kind: ToastKind, title: string, body?: string) => void;
  onOpenSupport?: () => void;
  onRefreshNotifications?: () => void;
};

export default function AdminMessagePopup({
  userId,
  onToast,
  onOpenSupport,
  onRefreshNotifications,
}: Props) {
  const [pending, setPending] = useState<PendingMessage | null>(null);
  const [reply, setReply] = useState('');
  const [showReply, setShowReply] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!userId) {
      setPending(null);
      return;
    }
    try {
      const resp = await apiFetch('/api/messages/pending-popup');
      if (!resp.ok) return;
      const data = await resp.json();
      setPending(data.message || null);
      setShowReply(false);
      setReply('');
    } catch {
      // ignore — non-blocking
    }
  }, [userId]);

  useEffect(() => {
    void load();
    if (!userId) return;
    const t = window.setInterval(() => void load(), 60_000);
    return () => window.clearInterval(t);
  }, [load, userId]);

  const act = async (action: 'acknowledge' | 'dismiss' | 'reply') => {
    if (!pending) return;
    if (action === 'reply' && reply.trim().length < 2) {
      onToast?.('error', 'Write a short reply first');
      return;
    }
    setBusy(true);
    try {
      const resp = await apiFetch(`/api/messages/${pending.id}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, replyBody: reply }),
      });
      if (!resp.ok) {
        const text = await resp.text();
        let detail = text;
        try {
          const j = JSON.parse(text);
          if (typeof j.detail === 'string') detail = j.detail;
        } catch {
          /* plain */
        }
        throw new Error(detail || 'Could not update message');
      }
      const data = await resp.json();
      setPending(null);
      setShowReply(false);
      setReply('');
      onRefreshNotifications?.();
      if (action === 'reply') {
        onToast?.('sent', 'Reply sent', 'Opened as a Support ticket');
        onOpenSupport?.();
      } else if (action === 'acknowledge') {
        onToast?.('ok', 'Acknowledged', 'Saved in Notifications');
      } else {
        onToast?.('info', 'Dismissed', 'Saved in Notifications');
      }
      // If another popup is queued, show next
      void load();
      return data;
    } catch (e) {
      onToast?.('error', 'Message action failed', e instanceof Error ? e.message : '');
    } finally {
      setBusy(false);
    }
  };

  if (!pending) return null;

  const sev = (pending.severity || 'info').toLowerCase();
  const canDismiss = !pending.requiresAck;

  return (
    <div className="admin-msg-overlay" role="dialog" aria-modal="true" aria-labelledby="admin-msg-title">
      <div className={`admin-msg-dialog admin-msg-dialog--${sev}`}>
        <p className="admin-msg-dialog__eyebrow">Message from NexivoReach</p>
        <h2 id="admin-msg-title" className="admin-msg-dialog__title">
          {pending.title}
        </h2>
        <p className="admin-msg-dialog__body">{pending.body}</p>

        {showReply && (
          <textarea
            className="admin-msg-dialog__reply"
            rows={4}
            value={reply}
            onChange={e => setReply(e.target.value)}
            placeholder="Your reply (creates a Support ticket)…"
            disabled={busy}
          />
        )}

        <div className="admin-msg-dialog__actions">
          {!showReply ? (
            <>
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={() => void act('acknowledge')}
              >
                Acknowledge
              </button>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={busy}
                onClick={() => setShowReply(true)}
              >
                Reply
              </button>
              {canDismiss && (
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={busy}
                  onClick={() => void act('dismiss')}
                >
                  Dismiss
                </button>
              )}
            </>
          ) : (
            <>
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={() => void act('reply')}
              >
                Send reply
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                disabled={busy}
                onClick={() => {
                  setShowReply(false);
                  setReply('');
                }}
              >
                Cancel
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
