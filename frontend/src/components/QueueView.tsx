import type { Prospect, AgentRunLog } from '../types';

interface Props {
  prospects: Prospect[];
  agentLogs: AgentRunLog[];
  onReviewProspect: (id: string) => void;
}

export default function QueueView({ prospects, agentLogs, onReviewProspect }: Props) {
  const pending = prospects.filter(
    p => !p.outreachDraft || p.outreachDraft.status === 'Draft'
  );
  const reviewed = prospects.filter(
    p => p.outreachDraft && p.outreachDraft.status !== 'Draft'
  );

  const lastRun = agentLogs[0];
  const lastRunLabel = lastRun
    ? formatRelative(lastRun.timestamp)
    : 'never';

  return (
    <div className="max-w-2xl">
      {/* Page heading */}
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-slate-900">Review Queue</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          {pending.length} prospect{pending.length !== 1 ? 's' : ''} awaiting your approval
          {lastRun && <span className="ml-1">· Last scan {lastRunLabel}</span>}
        </p>
      </div>

      {/* Active queue */}
      {pending.length === 0 ? (
        <div className="border border-slate-200 rounded-md px-4 py-8 text-center">
          <p className="text-sm font-medium text-slate-700">Queue is empty</p>
          <p className="text-sm text-slate-400 mt-1">Run a discovery scan to find new prospects.</p>
        </div>
      ) : (
        <div className="border border-slate-200 rounded-md divide-y divide-slate-100">
          {pending.map(prospect => (
            <QueueRow
              key={prospect.id}
              prospect={prospect}
              isNew
              onReview={() => onReviewProspect(prospect.id)}
            />
          ))}
        </div>
      )}

      {/* Recently reviewed */}
      {reviewed.length > 0 && (
        <div className="mt-8">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-widest mb-3">
            Recently Reviewed
          </p>
          <div className="divide-y divide-slate-100">
            {reviewed.map(prospect => (
              <QueueRow
                key={prospect.id}
                prospect={prospect}
                isNew={false}
                onReview={() => onReviewProspect(prospect.id)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function QueueRow({
  prospect,
  isNew,
  onReview,
}: {
  prospect: Prospect;
  isNew: boolean;
  onReview: () => void;
}) {
  const topSignal = prospect.buyingSignals[0]?.signal;
  const status = prospect.outreachDraft?.status;

  const statusLabel =
    status === 'Approved' ? 'Approved'
    : status === 'Sent' ? 'Sent'
    : status === 'Replied' ? 'Replied'
    : null;

  return (
    <div
      className="queue-row px-4 py-3.5 flex items-center justify-between gap-4 cursor-pointer"
      onClick={onReview}
    >
      <div className="flex items-start gap-3 min-w-0">
        {/* Status dot */}
        <div className="mt-1.5 shrink-0">
          <div
            className={`w-2 h-2 rounded-full ${isNew ? 'bg-blue-600' : 'bg-slate-300'}`}
            title={isNew ? 'Needs review' : 'Reviewed'}
          />
        </div>

        {/* Company name + signal */}
        <div className="min-w-0">
          <p className={`text-sm truncate ${isNew ? 'font-medium text-slate-900' : 'text-slate-500'}`}>
            {prospect.companyName}
          </p>
          <p className="text-xs text-slate-400 mt-0.5 truncate">
            {prospect.location}
            {topSignal && <span className="ml-2 text-slate-500">· {topSignal}</span>}
          </p>
        </div>
      </div>

      {/* Score + CTA */}
      <div className="flex items-center gap-5 shrink-0">
        <span className={`text-sm tabular-nums ${isNew ? 'font-semibold text-slate-900' : 'font-normal text-slate-400'}`}>
          {prospect.fitScore}%
        </span>

        {statusLabel ? (
          <span className="text-xs text-slate-400 w-16 text-right">{statusLabel}</span>
        ) : (
          <button
            onClick={e => { e.stopPropagation(); onReview(); }}
            className="text-sm text-blue-600 hover:text-blue-800 font-medium whitespace-nowrap transition-colors"
          >
            Review →
          </button>
        )}
      </div>
    </div>
  );
}

/** Simple relative time without date-fns to avoid dep issues */
function formatRelative(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp.replace(' ', 'T')).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
