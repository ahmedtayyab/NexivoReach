import { useEffect } from 'react';
import { CheckCircle2, Inbox, Mail, X, XCircle, Info } from 'lucide-react';

export type ToastKind = 'sent' | 'received' | 'ok' | 'error' | 'info';

export type AppToast = {
  id: string;
  kind: ToastKind;
  title: string;
  body?: string;
};

type Props = {
  toasts: AppToast[];
  onDismiss: (id: string) => void;
};

const ICONS: Record<ToastKind, typeof Mail> = {
  sent: Mail,
  received: Inbox,
  ok: CheckCircle2,
  error: XCircle,
  info: Info,
};

export default function ToastHost({ toasts, onDismiss }: Props) {
  return (
    <div className="toast-host" aria-live="polite" aria-relevant="additions">
      {toasts.map(t => (
        <ToastCard key={t.id} toast={t} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

function ToastCard({ toast, onDismiss }: { toast: AppToast; onDismiss: (id: string) => void }) {
  useEffect(() => {
    const ms = toast.kind === 'error' ? 7000 : 4500;
    const id = window.setTimeout(() => onDismiss(toast.id), ms);
    return () => window.clearTimeout(id);
  }, [toast.id, toast.kind, onDismiss]);

  const Icon = ICONS[toast.kind];
  return (
    <div className={`toast toast--${toast.kind}`} role="status">
      <span className="toast__icon" aria-hidden>
        <Icon className="w-4 h-4" strokeWidth={2} />
      </span>
      <div className="toast__copy">
        <p className="toast__title">{toast.title}</p>
        {toast.body ? <p className="toast__body">{toast.body}</p> : null}
      </div>
      <button
        type="button"
        className="toast__close"
        aria-label="Dismiss"
        onClick={() => onDismiss(toast.id)}
      >
        <X className="w-3.5 h-3.5" strokeWidth={2} />
      </button>
    </div>
  );
}
