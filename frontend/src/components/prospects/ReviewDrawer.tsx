import type { Prospect } from '../../types';
import { X, ArrowLeft, ExternalLink, CheckCircle, Edit3 } from 'lucide-react';
import { useState } from 'react';

interface Props {
  prospect: Prospect | null;
  onClose: () => void;
  onUpdateStatus: (id: string, status: NonNullable<Prospect['outreachDraft']>['status']) => void;
  onSaveDraft: (id: string, subject: string, body: string) => void;
}

export default function ReviewDrawer({ prospect, onClose, onUpdateStatus, onSaveDraft }: Props) {
  const [editingDraft, setEditingDraft] = useState(false);
  const [draftBody, setDraftBody] = useState('');
  const [draftSubject, setDraftSubject] = useState('');

  if (!prospect) return null;

  const draft = prospect.outreachDraft;
  const alreadySent = draft?.status === 'Sent';
  const alreadyApproved = draft?.status === 'Approved';
  const breakdown = prospect.fitBreakdown;
  const scoreClass =
    prospect.fitScore >= 90 ? 'score-high'
    : prospect.fitScore >= 80 ? 'score-mid'
    : 'score-low';

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
      <div className="absolute inset-0 drawer-overlay" onClick={onClose} />

      <div className="relative w-full max-w-xl bg-panel-elevated border-l border-border h-full overflow-y-auto flex flex-col z-10">
        <div className="sticky top-0 bg-panel-elevated border-b border-border px-5 py-3 flex items-center justify-between z-20">
          <button
            onClick={onClose}
            className="flex items-center space-x-1.5 text-[13px] text-ink-secondary hover:text-ink transition-colors"
          >
            <ArrowLeft className="w-4 h-4" strokeWidth={1.75} />
            <span>Back to Queue</span>
          </button>

          <div className="flex items-center space-x-2">
            {!alreadySent && !alreadyApproved && draft && (
              <button
                onClick={() => onUpdateStatus(prospect.id, 'Approved')}
                className="px-3.5 py-1.5 bg-accent hover:bg-accent-hover text-white text-[13px] font-medium rounded-md transition-colors"
              >
                Approve &amp; Send
              </button>
            )}
            {alreadyApproved && !alreadySent && (
              <button
                onClick={() => onUpdateStatus(prospect.id, 'Sent')}
                className="px-3.5 py-1.5 bg-accent hover:bg-accent-hover text-white text-[13px] font-medium rounded-md transition-colors"
              >
                Dispatch Email
              </button>
            )}
            {alreadySent && (
              <span className="text-[13px] text-green-700 font-medium flex items-center space-x-1">
                <CheckCircle className="w-4 h-4" strokeWidth={1.75} />
                <span>Sent</span>
              </span>
            )}
            <button
              onClick={onClose}
              className="p-1 text-slate-400 hover:text-slate-700 transition-colors"
              aria-label="Close"
            >
              <X className="w-4 h-4" strokeWidth={1.75} />
            </button>
          </div>
        </div>

        <div className="px-5 pt-5 pb-4 border-b border-slate-100">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-[15px] font-semibold text-ink">{prospect.companyName}</h1>
              <p className="text-[13px] text-slate-500 mt-0.5">
                {prospect.location} · {prospect.industry}
              </p>
            </div>
            <div className="text-right shrink-0">
              <span className={`text-base font-bold tabular-nums ${scoreClass}`}>{prospect.fitScore}</span>
              <p className="text-[11px] text-slate-400 mt-0.5">Fit (not intent)</p>
            </div>
          </div>
          {prospect.website && (
            <a
              href={prospect.website}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center space-x-1 text-[12px] text-blue-600 hover:text-blue-800 mt-2"
            >
              <span>{prospect.website}</span>
              <ExternalLink className="w-3 h-3" strokeWidth={1.75} />
            </a>
          )}
        </div>

        <div className="px-5 py-5 space-y-6 flex-1">
          <section>
            <h2 className="section-label mb-2">Qualification</h2>
            <div className="h-px bg-slate-100 mb-3" />
            <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-[13px]">
              <LevelRow label="ICP fit" value={prospect.icpFit || breakdown?.icpFit} />
              <LevelRow label="Offer fit" value={prospect.offerFit || breakdown?.offerFit} />
              <LevelRow label="Motion fit" value={prospect.motionFit || breakdown?.motionFit} />
              <LevelRow label="Intent" value={prospect.intent || breakdown?.intent || 'none'} />
            </div>
            {prospect.priority && (
              <p className="text-[12px] text-slate-500 mt-2">Priority: {prospect.priority}</p>
            )}
          </section>

          <section>
            <h2 className="section-label mb-2">Why this prospect?</h2>
            <div className="h-px bg-slate-100 mb-3" />
            <p className="text-[13.5px] text-slate-700 leading-relaxed">
              {prospect.whyThisProspect}
            </p>
            {(prospect.evidence || prospect.fitBreakdown?.evidence || [])
              .filter(e => e.claim !== 'intent')
              .slice(0, 4)
              .map((e, i) => (
                <p key={i} className="source-quote mt-2">{e.quote || e.statement}</p>
              ))}
          </section>

          <section>
            <h2 className="section-label mb-2">Why now?</h2>
            <div className="h-px bg-slate-100 mb-3" />
            <p className="text-[13.5px] text-slate-700 leading-relaxed">
              {prospect.whyNow || breakdown?.whyNow || 'No timing evidence.'}
            </p>
            {(prospect.buyingSignals || []).map((sig, i) => (
              <div key={i} className="mt-3">
                <p className="text-[13px] font-medium text-ink-secondary">{sig.signal}</p>
                <p className="source-quote mt-1">{sig.sourceExcerpt || sig.whyItMatters}</p>
                {sig.sourceUrl && (
                  <a
                    href={sig.sourceUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center space-x-1 text-[12px] text-blue-600 hover:underline mt-1"
                  >
                    <span>Source</span>
                    <ExternalLink className="w-3 h-3" strokeWidth={1.5} />
                  </a>
                )}
              </div>
            ))}
          </section>

          <section>
            <h2 className="section-label mb-2">Product Match</h2>
            <div className="h-px bg-slate-100 mb-3" />
            <div className="space-y-2">
              {(prospect.productFit || []).map((item, i) => (
                <div key={i} className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[13.5px] font-medium text-ink-secondary">{i + 1}. {item.productName}</p>
                    <p className="text-[12px] text-slate-500 mt-0.5">{item.reasoning}</p>
                  </div>
                  <span className={`text-[12px] font-semibold shrink-0 mt-0.5 ${
                    item.fitLevel === 'High' ? 'text-green-700' : 'text-slate-500'
                  }`}>
                    {item.fitLevel}
                  </span>
                </div>
              ))}
            </div>
            {prospect.recommendedApproach && (
              <p className="text-[12px] text-slate-500 mt-3 border-t border-slate-100 pt-3">
                Approach: {prospect.recommendedApproach}
              </p>
            )}
          </section>

          {draft && (
            <section>
              <div className="flex items-center justify-between mb-2">
                <h2 className="section-label">Draft Outreach</h2>
                {!alreadySent && (
                  <button
                    onClick={() => {
                      setDraftSubject(draft.subject);
                      setDraftBody(draft.body);
                      setEditingDraft(!editingDraft);
                    }}
                    className="flex items-center space-x-1 text-[12px] text-slate-500 hover:text-ink-secondary transition-colors"
                  >
                    <Edit3 className="w-3.5 h-3.5" strokeWidth={1.75} />
                    <span>Edit Draft</span>
                  </button>
                )}
              </div>
              <div className="h-px bg-slate-100 mb-3" />

              {editingDraft ? (
                <div className="space-y-2">
                  <input
                    value={draftSubject}
                    onChange={e => setDraftSubject(e.target.value)}
                    className="w-full border border-border rounded-md px-3 py-2 text-[13px] text-ink-secondary"
                    placeholder="Subject line..."
                  />
                  <textarea
                    value={draftBody}
                    onChange={e => setDraftBody(e.target.value)}
                    rows={8}
                    className="w-full border border-border rounded-md px-3 py-2 text-[13px] text-ink-secondary resize-none"
                  />
                  <div className="flex justify-end space-x-2">
                    <button
                      onClick={() => setEditingDraft(false)}
                      className="px-3 py-1.5 text-[13px] text-ink-secondary hover:text-ink"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => {
                        onSaveDraft(prospect.id, draftSubject, draftBody);
                        setEditingDraft(false);
                      }}
                      className="px-3 py-1.5 bg-slate-900 hover:bg-slate-700 text-white text-[13px] rounded-md transition-colors"
                    >
                      Save
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-[12px] text-slate-400">
                    Subject: <span className="text-slate-700 font-medium">{draft.subject}</span>
                  </p>
                  <p className="text-[13.5px] text-slate-700 whitespace-pre-line leading-relaxed border-t border-slate-100 pt-3">
                    {draft.body}
                  </p>
                  {draft.personalizedReason && (
                    <p className="text-[12px] text-slate-400 border-t border-slate-100 pt-2">
                      Personalized using: {draft.personalizedReason}
                    </p>
                  )}
                </div>
              )}
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

function LevelRow({ label, value }: { label: string; value?: string }) {
  const display = (value || 'unknown').toLowerCase();
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-500">{label}</span>
      <span className="text-ink-secondary font-medium capitalize">{display}</span>
    </div>
  );
}
