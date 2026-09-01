import { useState } from 'react';
import type { Prospect } from '../types';
import { 
  Send, 
  ShieldCheck, 
  CheckCircle2, 
  Sparkles, 
  ExternalLink
} from 'lucide-react';

interface Props {
  prospects: Prospect[];
  onUpdateStatus: (prospectId: string, status: NonNullable<Prospect['outreachDraft']>['status']) => void;
  onSelectProspect: (id: string) => void;
}

export default function OutreachView({ prospects, onUpdateStatus, onSelectProspect }: Props) {
  const [filterStatus, setFilterStatus] = useState<string>('All');

  const prospectsWithOutreach = prospects.filter(p => p.outreachDraft !== undefined);
  const filteredProspects = prospectsWithOutreach.filter(p => {
    if (filterStatus === 'All') return true;
    return p.outreachDraft && p.outreachDraft.status === filterStatus;
  });

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-2">
        <div className="flex items-center space-x-2 text-amber-400 text-xs font-semibold uppercase tracking-wider">
          <Send className="w-4 h-4" />
          <span>Step 6: Personalized Outreach & Human Approval Center</span>
        </div>
        <h1 className="text-xl font-bold text-white">Review & Approve Agent Outreach Drafts</h1>
        <p className="text-xs text-slate-300">
          NexivoReach generates personalized outreach messages tied directly to company research and buying signals. Messages require explicit human approval before sending.
        </p>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center justify-between bg-[#121929] border border-slate-800 rounded-xl p-4">
        <div className="flex space-x-2">
          {['All', 'Draft', 'Approved', 'Sent', 'Replied'].map(status => (
            <button
              key={status}
              onClick={() => setFilterStatus(status)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                filterStatus === status 
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30' 
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {status === 'Draft' ? 'Pending Approval' : status}
            </button>
          ))}
        </div>

        <span className="text-xs text-slate-400 font-mono">
          Showing {filteredProspects.length} Messages
        </span>
      </div>

      {/* Draft List */}
      <div className="space-y-4">
        {filteredProspects.map(prospect => {
          const draft = prospect.outreachDraft!;
          return (
            <div 
              key={prospect.id} 
              className="bg-[#121929] border border-slate-800 hover:border-slate-700 rounded-xl p-5 space-y-4 transition-all"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
                <div>
                  <div className="flex items-center space-x-2">
                    <h3 className="font-bold text-white text-sm">{prospect.companyName}</h3>
                    <span className="text-xs text-emerald-400 font-bold">• {prospect.fitScore}% Fit</span>
                  </div>
                  <p className="text-xs text-slate-400">{prospect.location} — {prospect.industry}</p>
                </div>

                <div className="flex items-center space-x-2">
                  <span className={`text-[10px] font-bold px-2.5 py-1 rounded-full ${
                    draft.status === 'Approved' 
                      ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' 
                      : draft.status === 'Sent'
                      ? 'bg-blue-950 text-blue-400 border border-blue-800'
                      : 'bg-amber-950 text-amber-300 border border-amber-800'
                  }`}>
                    {draft.status === 'Draft' ? '⚠️ Human Approval Required' : draft.status}
                  </span>
                </div>
              </div>

              {/* Subject & Body */}
              <div className="bg-[#0b101c] border border-slate-800 rounded-lg p-4 space-y-3 text-xs">
                <div className="text-slate-300 font-semibold flex items-center space-x-2">
                  <span className="text-slate-500 font-mono">Subject:</span>
                  <span>{draft.subject}</span>
                </div>
                <div className="text-slate-200 whitespace-pre-line leading-relaxed border-t border-slate-800/80 pt-2.5 font-sans">
                  {draft.body}
                </div>
              </div>

              {/* Personalization Reason */}
              <div className="bg-amber-950/20 border border-amber-900/30 rounded-lg p-3 text-xs text-amber-200 flex items-start space-x-2">
                <Sparkles className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                <div>
                  <strong className="font-semibold block text-amber-300">Why this message was personalized:</strong>
                  <span>{draft.personalizedReason}</span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center justify-between pt-1">
                <button
                  onClick={() => onSelectProspect(prospect.id)}
                  className="text-xs text-blue-400 hover:text-blue-300 flex items-center space-x-1"
                >
                  <span>Inspect Prospect Evidence</span>
                  <ExternalLink className="w-3 h-3" />
                </button>

                <div className="flex items-center space-x-2">
                  {draft.status === 'Draft' && (
                    <button
                      onClick={() => onUpdateStatus(prospect.id, 'Approved')}
                      className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs rounded-lg flex items-center space-x-1.5 shadow-md shadow-emerald-600/20"
                    >
                      <ShieldCheck className="w-4 h-4" />
                      <span>Approve Outreach Draft</span>
                    </button>
                  )}

                  {draft.status === 'Approved' && (
                    <button
                      onClick={() => onUpdateStatus(prospect.id, 'Sent')}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs rounded-lg flex items-center space-x-1.5 shadow-md shadow-blue-600/20"
                    >
                      <Send className="w-4 h-4" />
                      <span>Dispatch Outreach Email</span>
                    </button>
                  )}

                  {draft.status === 'Sent' && (
                    <span className="text-xs text-emerald-400 font-medium flex items-center space-x-1">
                      <CheckCircle2 className="w-4 h-4" />
                      <span>Dispatched (Tracking Follow-ups)</span>
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
