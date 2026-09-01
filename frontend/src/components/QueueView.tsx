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
  const lastRunLabel = lastRun ? formatRelative(lastRun.timestamp) : null;

  return (
    <div className="max-w-2xl">

      {/* Page heading */}
      <div className="mb-7">
        <h1 className="text-[15px] font-semibold text-slate-900 tracking-tight">Review Queue</h1>
        <p className="text-[13px] text-slate-500 mt-0.5">
          <span className="font-medium text-slate-800">{pending.length}</span>{' '}
          prospect{pending.length !== 1 ? 's' : ''} awaiting approval
          {lastRunLabel && (
            <span className="text-slate-400"> · Last scan {lastRunLabel}</span>
          )}
        </p>
      </div>

      {/* Active queue */}
      {pending.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-lg px-5 py-10 text-center">
          <p className="text-[13.5px] font-medium text-slate-600">Queue is clear</p>
          <p className="text-[13px] text-slate-400 mt-1">
            Switch to <strong className="font-medium text-slate-500">Discover</strong> to find new prospects.
          </p>
        </div>
      ) : (
        <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
          {/* Column header */}
          <div className="grid grid-cols-[1fr_160px_64px_88px] items-center px-4 py-2 border-b border-slate-100 bg-slate-50">
            <span className="section-label">Company</span>
            <span className="section-label">Top Signal</span>
            <span className="section-label text-right">Fit</span>
            <span className="section-label text-right">Action</span>
          </div>
          <div className="divide-y divide-slate-100">
            {pending.map(prospect => (
              <QueueRow
                key={prospect.id}
                prospect={prospect}
                isNew
                onReview={() => onReviewProspect(prospect.id)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Reviewed section */}
      {reviewed.length > 0 && (
        <div className="mt-8">
          <p className="section-label mb-3">Reviewed</p>
          <div className="bg-white border border-slate-200 rounded-lg overflow-hidden divide-y divide-slate-100">
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
  const topSignal = prospect.buyingSignals?.[0]?.signal ?? '—';
  const status = prospect.outreachDraft?.status;
  const statusLabel =
    status === 'Approved' ? 'Approved'
    : status === 'Sent' ? 'Sent'
    : status === 'Replied' ? 'Replied'
    : null;

  const scoreClass =
    prospect.fitScore >= 90 ? 'score-high'
    : prospect.fitScore >= 80 ? 'score-mid'
    : 'score-low';

  return (
    <div
      className="queue-row grid grid-cols-[1fr_160px_64px_88px] items-center px-4 py-3 gap-2"
      onClick={onReview}
    >
      {/* Company col */}
      <div className="flex items-center gap-2.5 min-w-0">
        <div
          className={`w-1.5 h-1.5 rounded-full shrink-0 ${isNew ? 'bg-blue-600' : 'bg-slate-200'}`}
        />
        <div className="min-w-0">
          <p className={`text-[13.5px] truncate ${isNew ? 'font-medium text-slate-900' : 'text-slate-400'}`}>
            {prospect.companyName}
          </p>
          <p className="text-[12px] text-slate-400 truncate mt-px">{prospect.location}</p>
        </div>
      </div>

      {/* Top signal col */}
      <p className="text-[12.5px] text-slate-500 truncate">{topSignal}</p>

      {/* Score col */}
      <p className={`text-[13px] font-semibold text-right tabular-nums ${isNew ? scoreClass : 'text-slate-300'}`}>
        {prospect.fitScore}%
      </p>

      {/* Action col */}
      <div className="text-right">
        {statusLabel ? (
          <span className="text-[12px] text-slate-400">{statusLabel}</span>
        ) : (
          <button
            onClick={e => { e.stopPropagation(); onReview(); }}
            className="text-[13px] text-blue-600 hover:text-blue-800 font-medium transition-colors"
          >
            Review →
          </button>
        )}
      </div>
    </div>
  );
}

function formatRelative(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp.replace(' ', 'T')).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
