import { useState } from 'react';
import type { Prospect } from '../../types';
import { 
  X, 
  Globe, 
  MapPin, 
  Zap, 
  ExternalLink, 
  Send, 
  CheckCircle2, 
  ShieldCheck, 
  Package, 
  Edit3
} from 'lucide-react';

interface Props {
  prospect: Prospect | null;
  onClose: () => void;
  onUpdateStatus: (prospectId: string, status: NonNullable<Prospect['outreachDraft']>['status']) => void;
}

export default function ProspectDrawer({ prospect, onClose, onUpdateStatus }: Props) {
  if (!prospect) return null;

  const [isEditingDraft, setIsEditingDraft] = useState(false);
  const [editedBody, setEditedBody] = useState(prospect.outreachDraft?.body || '');
  const [editedSubject, setEditedSubject] = useState(prospect.outreachDraft?.subject || '');

  const draft = prospect.outreachDraft;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div 
        className="fixed inset-0 drawer-backdrop transition-opacity" 
        onClick={onClose}
      />

      {/* Drawer Panel */}
      <div className="relative w-full max-w-2xl bg-[#0f172a] border-l border-slate-800 h-full overflow-y-auto shadow-2xl flex flex-col z-10 font-sans text-slate-100">
        {/* Drawer Header */}
        <div className="p-6 border-b border-slate-800 flex items-start justify-between bg-[#090d16]/60 sticky top-0 backdrop-blur z-20">
          <div className="space-y-1">
            <div className="flex items-center space-x-3">
              <h2 className="text-lg font-bold text-white">{prospect.companyName}</h2>
              <a
                href={prospect.website}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-blue-400 hover:text-blue-300 flex items-center space-x-1"
              >
                <Globe className="w-3.5 h-3.5" />
                <span>Website</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
            <div className="flex items-center space-x-3 text-xs text-slate-400">
              <span className="flex items-center space-x-1">
                <MapPin className="w-3.5 h-3.5 text-slate-500" />
                <span>{prospect.location}</span>
              </span>
              <span>•</span>
              <span>{prospect.industry}</span>
              <span>•</span>
              <span>{prospect.companySize}</span>
            </div>
          </div>

          <div className="flex items-center space-x-4">
            <div className="text-right">
              <span className={`text-xl font-extrabold block ${
                prospect.fitScore >= 90 ? 'text-emerald-400' : 'text-blue-400'
              }`}>
                {prospect.fitScore}% Fit
              </span>
              <span className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Match Score</span>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Drawer Content */}
        <div className="p-6 space-y-6 flex-1">
          {/* Executive Summary */}
          <div className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Why this prospect?
            </h3>
            <div className="bg-[#1e293b]/70 border border-slate-800 rounded-lg p-4 text-xs text-slate-200 leading-relaxed">
              {prospect.whyThisProspect}
            </div>
          </div>

          {/* Evidence & Detected Buying Signals */}
          <div className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center space-x-2">
              <Zap className="w-4 h-4 text-emerald-400" />
              <span>Verified Evidence & Buying Signals</span>
            </h3>

            <div className="space-y-3">
              {prospect.buyingSignals.map((sig, idx) => (
                <div key={idx} className="bg-[#1e293b]/50 border border-slate-800 rounded-lg p-4 space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-emerald-400">⚡ {sig.signal}</span>
                    {sig.sourceUrl && (
                      <a
                        href={sig.sourceUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[11px] text-blue-400 hover:text-blue-300 flex items-center space-x-1 font-mono"
                      >
                        <span>Source Link</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>
                  <p className="text-slate-300">{sig.whyItMatters}</p>
                  {sig.sourceExcerpt && (
                    <div className="bg-[#090d16] p-2.5 rounded border border-slate-800 text-[11px] text-slate-400 italic font-serif">
                      "{sig.sourceExcerpt}"
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Product Catalog Fit Matrix */}
          <div className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center space-x-2">
              <Package className="w-4 h-4 text-indigo-400" />
              <span>Catalog Product Fit Matrix</span>
            </h3>

            <div className="space-y-2">
              {prospect.productFit.map((item, idx) => (
                <div key={idx} className="bg-[#1e293b]/50 border border-slate-800 rounded-lg p-3 flex items-start justify-between gap-3 text-xs">
                  <div>
                    <span className="font-semibold text-white">{item.productName}</span>
                    <p className="text-[11px] text-slate-400 mt-0.5">{item.reasoning}</p>
                  </div>
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded whitespace-nowrap ${
                    item.fitLevel === 'High' 
                      ? 'bg-emerald-950/80 text-emerald-400 border border-emerald-800/60' 
                      : 'bg-blue-950/80 text-blue-400 border border-blue-800/60'
                  }`}>
                    {item.fitLevel} Match
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Outreach Draft & Action */}
          {draft && (
            <div className="space-y-3 pt-2 border-t border-slate-800">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center space-x-2">
                  <Send className="w-4 h-4 text-amber-400" />
                  <span>Personalized Outreach Draft</span>
                </h3>

                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded ${
                  draft.status === 'Approved'
                    ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                    : draft.status === 'Sent'
                    ? 'bg-blue-950 text-blue-400 border border-blue-800'
                    : 'bg-amber-950 text-amber-300 border border-amber-800'
                }`}>
                  {draft.status === 'Draft' ? 'Requires Approval' : draft.status}
                </span>
              </div>

              <div className="bg-[#090d16] border border-slate-800 rounded-lg p-4 space-y-3 text-xs">
                {isEditingDraft ? (
                  <div className="space-y-2">
                    <input
                      type="text"
                      value={editedSubject}
                      onChange={(e) => setEditedSubject(e.target.value)}
                      className="w-full bg-[#121929] border border-slate-700 rounded p-2 text-slate-200 text-xs"
                    />
                    <textarea
                      value={editedBody}
                      onChange={(e) => setEditedBody(e.target.value)}
                      rows={6}
                      className="w-full bg-[#121929] border border-slate-700 rounded p-2 text-slate-200 text-xs"
                    />
                    <div className="flex justify-end space-x-2">
                      <button
                        onClick={() => setIsEditingDraft(false)}
                        className="px-3 py-1 bg-slate-800 text-slate-300 rounded text-xs"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={() => setIsEditingDraft(false)}
                        className="px-3 py-1 bg-blue-600 text-white rounded text-xs font-medium"
                      >
                        Save Draft Changes
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="text-slate-400 font-mono text-[11px]">
                      <strong>Subject:</strong> {draft.subject}
                    </div>
                    <div className="text-slate-200 whitespace-pre-line leading-relaxed border-t border-slate-800 pt-2.5 font-sans">
                      {draft.body}
                    </div>
                  </>
                )}
              </div>

              <p className="text-[11px] text-slate-400 italic">
                <strong>Personalization note: </strong>{draft.personalizedReason}
              </p>

              {/* Action Toolbar */}
              <div className="flex items-center justify-between pt-2">
                <button
                  onClick={() => setIsEditingDraft(!isEditingDraft)}
                  className="text-xs text-slate-400 hover:text-slate-200 flex items-center space-x-1"
                >
                  <Edit3 className="w-3.5 h-3.5" />
                  <span>Edit Draft</span>
                </button>

                <div className="flex items-center space-x-2">
                  {draft.status === 'Draft' && (
                    <button
                      onClick={() => onUpdateStatus(prospect.id, 'Approved')}
                      className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-md flex items-center space-x-1.5 transition-all shadow-sm"
                    >
                      <ShieldCheck className="w-4 h-4" />
                      <span>Approve Outreach Draft</span>
                    </button>
                  )}

                  {draft.status === 'Approved' && (
                    <button
                      onClick={() => onUpdateStatus(prospect.id, 'Sent')}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold rounded-md flex items-center space-x-1.5 transition-all shadow-sm"
                    >
                      <Send className="w-4 h-4" />
                      <span>Dispatch Outreach Email</span>
                    </button>
                  )}

                  {draft.status === 'Sent' && (
                    <span className="text-xs text-emerald-400 font-medium flex items-center space-x-1">
                      <CheckCircle2 className="w-4 h-4" />
                      <span>Dispatched (Tracking Replies)</span>
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
