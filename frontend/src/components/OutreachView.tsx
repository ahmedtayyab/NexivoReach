import { useState } from 'react';
import type { Prospect } from '../types';
import { 
  Send, 
  ShieldCheck, 
  CheckCircle2, 
  ExternalLink
} from 'lucide-react';

interface Props {
  prospects: Prospect[];
  onUpdateStatus: (prospectId: string, status: NonNullable<Prospect['outreachDraft']>['status']) => void;
  onSelectProspect: (id: string) => void;
}

export default function OutreachView({ prospects, onUpdateStatus, onSelectProspect }: Props) {
  const [filterStatus, setFilterStatus] = useState<string>('Draft');

  const prospectsWithOutreach = prospects.filter(p => p.outreachDraft !== undefined);
  const filteredProspects = prospectsWithOutreach.filter(p => {
    if (filterStatus === 'All') return true;
    return p.outreachDraft && p.outreachDraft.status === filterStatus;
  });

  return (
    <div className="space-y-6 font-sans text-slate-100">
      {/* Header */}
      <div className="bg-[#1e293b] border border-slate-800 rounded-lg p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-bold text-white tracking-tight">Outreach Approval Queue</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Review personalized outreach drafts generated from verified prospect news and buying signals.
          </p>
        </div>
      </div>

      {/* Filter Tabs Toolbar */}
      <div className="flex items-center justify-between bg-[#1e293b] border border-slate-800 rounded-lg p-3">
        <div className="flex space-x-2">
          {[
            { id: 'Draft', label: 'Pending Approval' },
            { id: 'Approved', label: 'Approved' },
            { id: 'Sent', label: 'Sent' },
            { id: 'All', label: 'All Messages' },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setFilterStatus(tab.id)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                filterStatus === tab.id 
                  ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30' 
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <span className="text-xs text-slate-400 font-mono">
          Showing {filteredProspects.length} Messages
        </span>
      </div>

      {/* Queue Items List */}
      <div className="space-y-4">
        {filteredProspects.map(prospect => {
          const draft = prospect.outreachDraft!;
          return (
            <div 
              key={prospect.id} 
              className="bg-[#1e293b] border border-slate-800 hover:border-slate-700 rounded-lg p-5 space-y-4 transition-all"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
                <div>
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={() => onSelectProspect(prospect.id)}
                      className="font-bold text-white hover:text-blue-400 text-sm"
                    >
                      {prospect.companyName}
                    </button>
                    <span className="text-xs text-emerald-400 font-bold">• {prospect.fitScore}% Fit Match</span>
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5">{prospect.location} — {prospect.industry}</p>
                </div>

                <span className={`text-[10px] font-semibold px-2.5 py-1 rounded ${
                  draft.status === 'Approved' 
                    ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' 
                    : draft.status === 'Sent'
                    ? 'bg-blue-950 text-blue-400 border border-blue-800'
                    : 'bg-amber-950 text-amber-300 border border-amber-800'
                }`}>
                  {draft.status === 'Draft' ? 'Requires Approval' : draft.status}
                </span>
              </div>

              {/* Message Preview */}
              <div className="bg-[#090d16] border border-slate-800 rounded-lg p-4 space-y-2 text-xs">
                <div className="text-slate-300 font-semibold">
                  <span className="text-slate-500 font-mono text-[11px]">Subject: </span>
                  <span>{draft.subject}</span>
                </div>
                <p className="text-slate-300 whitespace-pre-line leading-relaxed border-t border-slate-800 pt-2 font-sans">
                  {draft.body}
                </p>
              </div>

              {/* Personalization Note */}
              <p className="text-[11px] text-slate-400 italic">
                <strong>Personalization note: </strong>{draft.personalizedReason}
              </p>

              {/* Actions */}
              <div className="flex items-center justify-between pt-1">
                <button
                  onClick={() => onSelectProspect(prospect.id)}
                  className="text-xs text-blue-400 hover:text-blue-300 flex items-center space-x-1"
                >
                  <span>Inspect Prospect Evidence & Signals</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </button>

                <div className="flex items-center space-x-2">
                  {draft.status === 'Draft' && (
                    <button
                      onClick={() => onUpdateStatus(prospect.id, 'Approved')}
                      className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs rounded-md flex items-center space-x-1.5 shadow-sm transition-all"
                    >
                      <ShieldCheck className="w-4 h-4" />
                      <span>Approve Outreach Draft</span>
                    </button>
                  )}

                  {draft.status === 'Approved' && (
                    <button
                      onClick={() => onUpdateStatus(prospect.id, 'Sent')}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs rounded-md flex items-center space-x-1.5 shadow-sm transition-all"
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
          );
        })}
      </div>
    </div>
  );
}
