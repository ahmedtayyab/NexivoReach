import type { Prospect } from '../../types';
import { X, ArrowLeft, ExternalLink, CheckCircle, Edit3 } from 'lucide-react';
import { useState } from 'react';

interface Props {
  prospect: Prospect | null;
  onClose: () => void;
  onUpdateStatus: (id: string, status: NonNullable<Prospect['outreachDraft']>['status']) => void;
}

export default function ReviewDrawer({ prospect, onClose, onUpdateStatus }: Props) {
  const [editingDraft, setEditingDraft] = useState(false);
  const [draftBody, setDraftBody] = useState('');
  const [draftSubject, setDraftSubject] = useState('');

  if (!prospect) return null;

  const draft = prospect.outreachDraft;
  const alreadySent = draft?.status === 'Sent';
  const alreadyApproved = draft?.status === 'Approved';

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
      {/* Backdrop */}
      <div className="absolute inset-0 drawer-overlay" onClick={onClose} />

      {/* Drawer */}
      <div className="relative w-full max-w-xl bg-white border-l border-slate-200 h-full overflow-y-auto flex flex-col z-10">
        {/* Drawer top bar */}
        <div className="sticky top-0 bg-white border-b border-slate-200 px-5 py-3 flex items-center justify-between z-20">
          <button
            onClick={onClose}
            className="flex items-center space-x-1.5 text-sm text-slate-500 hover:text-slate-900 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" strokeWidth={1.75} />
            <span>Back to Queue</span>
          </button>

          <div className="flex items-center space-x-2">
            {!alreadySent && !alreadyApproved && draft && (
              <button
                onClick={() => onUpdateStatus(prospect.id, 'Approved')}
                className="px-3.5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-md transition-colors"
              >
                Approve &amp; Send
              </button>
            )}
            {alreadyApproved && !alreadySent && (
              <button
                onClick={() => onUpdateStatus(prospect.id, 'Sent')}
                className="px-3.5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-md transition-colors"
              >
                Dispatch Email
              </button>
            )}
            {alreadySent && (
              <span className="text-sm text-green-700 font-medium flex items-center space-x-1">
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

        {/* Prospect identity */}
        <div className="px-5 pt-5 pb-4 border-b border-slate-100">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-base font-semibold text-slate-900">{prospect.companyName}</h1>
              <p className="text-sm text-slate-500 mt-0.5">
                {prospect.location} · {prospect.industry}
              </p>
            </div>
            <div className="text-right shrink-0">
              <span className="text-base font-bold text-slate-900">{prospect.fitScore}%</span>
              <p className="text-xs text-slate-400 mt-0.5">Fit Score</p>
            </div>
          </div>
          {prospect.website && (
            <a
              href={prospect.website}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center space-x-1 text-xs text-blue-600 hover:text-blue-800 mt-2"
            >
              <span>{prospect.website}</span>
              <ExternalLink className="w-3 h-3" strokeWidth={1.75} />
            </a>
          )}
        </div>

        <div className="px-5 py-5 space-y-6 flex-1">
          {/* Why contact now */}
          <section>
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-2">
              Why Contact Now?
            </h2>
            <div className="h-px bg-slate-100 mb-3" />
            <p className="text-sm text-slate-700 leading-relaxed">
              {prospect.whyThisProspect}
            </p>

            {/* Evidence sources */}
            {prospect.buyingSignals.map((sig, i) => (
              <div key={i} className="mt-3 pl-3 border-l-2 border-blue-200">
                <p className="text-sm text-slate-600">{sig.whyItMatters}</p>
                {sig.sourceExcerpt && (
                  <p className="text-xs text-slate-400 mt-1 italic">"{sig.sourceExcerpt}"</p>
                )}
                {sig.sourceUrl && (
                  <a
                    href={sig.sourceUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center space-x-1 text-xs text-blue-600 hover:underline mt-1"
                  >
                    <span>Source</span>
                    <ExternalLink className="w-3 h-3" strokeWidth={1.5} />
                  </a>
                )}
              </div>
            ))}
          </section>

          {/* Product match */}
          <section>
            <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-2">
              Product Match
            </h2>
            <div className="h-px bg-slate-100 mb-3" />
            <div className="space-y-2">
              {prospect.productFit.map((item, i) => (
                <div key={i} className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-slate-800">{i + 1}. {item.productName}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{item.reasoning}</p>
                  </div>
                  <span className={`text-xs font-semibold shrink-0 mt-0.5 ${
                    item.fitLevel === 'High' ? 'text-green-700' : 'text-slate-500'
                  }`}>
                    {item.fitLevel}
                  </span>
                </div>
              ))}
            </div>
          </section>

          {/* Draft outreach */}
          {draft && (
            <section>
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
                  Draft Outreach
                </h2>
                {!alreadySent && (
                  <button
                    onClick={() => {
                      setDraftSubject(draft.subject);
                      setDraftBody(draft.body);
                      setEditingDraft(!editingDraft);
                    }}
                    className="flex items-center space-x-1 text-xs text-slate-500 hover:text-slate-800 transition-colors"
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
                    className="w-full border border-slate-200 rounded-md px-3 py-2 text-sm text-slate-800 focus:outline-none"
                    placeholder="Subject line..."
                  />
                  <textarea
                    value={draftBody}
                    onChange={e => setDraftBody(e.target.value)}
                    rows={8}
                    className="w-full border border-slate-200 rounded-md px-3 py-2 text-sm text-slate-800 focus:outline-none resize-none"
                  />
                  <div className="flex justify-end space-x-2">
                    <button
                      onClick={() => setEditingDraft(false)}
                      className="px-3 py-1.5 text-sm text-slate-600 hover:text-slate-900"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => setEditingDraft(false)}
                      className="px-3 py-1.5 bg-slate-900 hover:bg-slate-700 text-white text-sm rounded-md transition-colors"
                    >
                      Save
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-xs text-slate-400">
                    Subject: <span className="text-slate-700 font-medium">{draft.subject}</span>
                  </p>
                  <p className="text-sm text-slate-700 whitespace-pre-line leading-relaxed border-t border-slate-100 pt-3">
                    {draft.body}
                  </p>
                  {draft.personalizedReason && (
                    <p className="text-xs text-slate-400 border-t border-slate-100 pt-2">
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
