import type { Prospect } from '../types';
import { 
  Globe, 
  MapPin, 
  Zap, 
  ExternalLink, 
  Send, 
  Clock, 
  Sparkles, 
  ShieldCheck,
  Package,
  Users
} from 'lucide-react';

interface Props {
  prospects: Prospect[];
  selectedProspectId: string;
  onSelectProspect: (id: string) => void;
  onUpdateStatus: (prospectId: string, status: NonNullable<Prospect['outreachDraft']>['status']) => void;
  onNavigateToDiscovery: () => void;
}

export default function ProspectsView({ 
  prospects, 
  selectedProspectId, 
  onSelectProspect, 
  onUpdateStatus,
  onNavigateToDiscovery
}: Props) {
  const selectedProspect = prospects.find(p => p.id === selectedProspectId) || prospects[0];

  if (!selectedProspect) {
    return (
      <div className="text-center py-12 space-y-4 bg-slate-900 border border-slate-800 rounded-xl">
        <Users className="w-10 h-10 text-slate-500 mx-auto" />
        <h2 className="text-lg font-bold text-white">No prospects yet</h2>
        <p className="text-xs text-slate-400 max-w-sm mx-auto">
          Tell NexivoReach who you're trying to reach and we'll help you discover and qualify your first prospects.
        </p>
        <button
          onClick={onNavigateToDiscovery}
          className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs rounded-lg shadow-lg shadow-blue-600/30"
        >
          Find Prospects Now
        </button>
      </div>
    );
  }

  const { fitBreakdown } = selectedProspect;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      {/* Left Column: Prospect Selector List */}
      <div className="lg:col-span-4 bg-[#121929] border border-slate-800 rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <h2 className="text-xs font-semibold text-slate-200">Discovered Prospects ({prospects.length})</h2>
          <button 
            onClick={onNavigateToDiscovery} 
            className="text-[11px] text-blue-400 hover:text-blue-300 font-medium"
          >
            + Run Discovery
          </button>
        </div>

        <div className="space-y-2">
          {prospects.map(p => {
            const isSelected = p.id === selectedProspect.id;
            return (
              <div
                key={p.id}
                onClick={() => onSelectProspect(p.id)}
                className={`p-3 rounded-lg border text-xs cursor-pointer transition-all ${
                  isSelected 
                    ? 'bg-blue-950/60 border-blue-500/50 shadow-md shadow-blue-500/10' 
                    : 'bg-[#0b101c] border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-white truncate">{p.companyName}</span>
                  <span className={`text-[11px] font-bold ${
                    p.fitScore >= 90 ? 'text-emerald-400' : 'text-blue-400'
                  }`}>
                    {p.fitScore}%
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 mt-1 flex items-center space-x-1">
                  <MapPin className="w-3 h-3 text-slate-500" />
                  <span className="truncate">{p.location}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Right Column: Detailed Research View */}
      <div className="lg:col-span-8 space-y-6">
        {/* Header Hero Banner */}
        <div className="bg-[#121929] border border-slate-800 rounded-xl p-6 relative overflow-hidden space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
            <div className="space-y-1">
              <div className="flex items-center space-x-2">
                <h1 className="text-xl font-bold text-white">{selectedProspect.companyName}</h1>
                <a 
                  href={selectedProspect.website} 
                  target="_blank" 
                  rel="noreferrer"
                  className="text-xs text-blue-400 hover:text-blue-300 flex items-center space-x-1"
                >
                  <Globe className="w-3.5 h-3.5" />
                  <span>Website</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>
              <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
                <span className="flex items-center space-x-1">
                  <MapPin className="w-3.5 h-3.5 text-slate-500" />
                  <span>{selectedProspect.location}</span>
                </span>
                <span>•</span>
                <span>{selectedProspect.industry}</span>
                <span>•</span>
                <span>{selectedProspect.companySize}</span>
              </div>
            </div>

            {/* Match Badge */}
            <div className="bg-emerald-950/80 border border-emerald-500/30 rounded-xl px-5 py-3 text-center shadow-lg shadow-emerald-950/40">
              <span className="text-2xl font-extrabold text-emerald-400">{selectedProspect.fitScore}% Match</span>
              <span className="block text-[10px] uppercase font-semibold tracking-wider text-emerald-300 mt-0.5">
                Qualified Prospect
              </span>
            </div>
          </div>

          {/* AI Explanation */}
          <div className="space-y-1">
            <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center space-x-1.5">
              <Sparkles className="w-3.5 h-3.5 text-blue-400" />
              <span>Why this prospect?</span>
            </h3>
            <p className="text-xs text-slate-200 bg-[#0b101c] p-3 rounded-lg border border-slate-800/80 leading-relaxed">
              {selectedProspect.whyThisProspect}
            </p>
          </div>
        </div>

        {/* Transparent Score Breakdown Table */}
        <div className="bg-[#121929] border border-slate-800 rounded-xl p-5 space-y-3">
          <h3 className="text-xs font-semibold text-slate-200 flex items-center justify-between border-b border-slate-800 pb-2">
            <span>Transparent 100-Point Fit Score Breakdown</span>
            <span className="text-[10px] text-slate-400 font-mono">Configurable Formula</span>
          </h3>

          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs text-center font-mono">
            <div className="bg-[#0b101c] p-2.5 rounded border border-slate-800">
              <span className="block text-slate-400 text-[10px]">Industry Fit</span>
              <span className="text-emerald-400 font-bold text-sm">{fitBreakdown.industryFit}/25</span>
            </div>
            <div className="bg-[#0b101c] p-2.5 rounded border border-slate-800">
              <span className="block text-slate-400 text-[10px]">Location Match</span>
              <span className="text-emerald-400 font-bold text-sm">{fitBreakdown.locationFit}/20</span>
            </div>
            <div className="bg-[#0b101c] p-2.5 rounded border border-slate-800">
              <span className="block text-slate-400 text-[10px]">Product Overlap</span>
              <span className="text-emerald-400 font-bold text-sm">{fitBreakdown.productMatch}/20</span>
            </div>
            <div className="bg-[#0b101c] p-2.5 rounded border border-slate-800">
              <span className="block text-slate-400 text-[10px]">Buying Signals</span>
              <span className="text-emerald-400 font-bold text-sm">{fitBreakdown.buyingSignals}/20</span>
            </div>
            <div className="bg-[#0b101c] p-2.5 rounded border border-slate-800 col-span-2 sm:col-span-1">
              <span className="block text-slate-400 text-[10px]">Company Scale</span>
              <span className="text-emerald-400 font-bold text-sm">{fitBreakdown.companyFit}/15</span>
            </div>
          </div>
        </div>

        {/* Buying Signals detected */}
        <div className="bg-[#121929] border border-slate-800 rounded-xl p-5 space-y-3">
          <h3 className="text-xs font-semibold text-slate-200 flex items-center space-x-2 border-b border-slate-800 pb-2">
            <Zap className="w-4 h-4 text-emerald-400" />
            <span>Detected Buying Signals & Evidence Sources</span>
          </h3>

          <div className="space-y-3">
            {selectedProspect.buyingSignals.map((sig, idx) => (
              <div key={idx} className="bg-[#0b101c] border border-slate-800 rounded-lg p-3.5 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-emerald-400">⚡ {sig.signal}</span>
                  {sig.sourceUrl && (
                    <a 
                      href={sig.sourceUrl} 
                      target="_blank" 
                      rel="noreferrer" 
                      className="text-[10px] text-blue-400 hover:text-blue-300 flex items-center space-x-1 font-mono"
                    >
                      <span>Source Link</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  )}
                </div>
                <p className="text-slate-300">{sig.whyItMatters}</p>
                {sig.sourceExcerpt && (
                  <p className="text-[11px] text-slate-400 bg-slate-900/90 p-2 rounded border border-slate-800/80 italic font-serif">
                    "{sig.sourceExcerpt}"
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Product Fit Matrix */}
        <div className="bg-[#121929] border border-slate-800 rounded-xl p-5 space-y-3">
          <h3 className="text-xs font-semibold text-slate-200 flex items-center space-x-2 border-b border-slate-800 pb-2">
            <Package className="w-4 h-4 text-indigo-400" />
            <span>Catalog Product Fit Matrix</span>
          </h3>

          <div className="space-y-2">
            {selectedProspect.productFit.map((item, idx) => (
              <div key={idx} className="bg-[#0b101c] border border-slate-800 rounded-lg p-3 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 text-xs">
                <div>
                  <span className="font-semibold text-white">{item.productName}</span>
                  <p className="text-[11px] text-slate-400 mt-0.5">{item.reasoning}</p>
                </div>

                <span className={`text-[10px] font-bold px-2 py-0.5 rounded whitespace-nowrap ${
                  item.fitLevel === 'High' 
                    ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' 
                    : 'bg-blue-950 text-blue-400 border border-blue-800'
                }`}>
                  {item.fitLevel} Fit Match
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Recommended Approach & Outreach Draft */}
        {selectedProspect.outreachDraft && (
          <div className="bg-[#121929] border border-indigo-900/50 rounded-xl p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center space-x-2">
                <Send className="w-4 h-4 text-indigo-400" />
                <h3 className="text-xs font-semibold text-slate-200">Recommended Approach & Outreach</h3>
              </div>
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                selectedProspect.outreachDraft.status === 'Approved' 
                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' 
                  : selectedProspect.outreachDraft.status === 'Sent'
                  ? 'bg-blue-950 text-blue-400 border border-blue-800'
                  : 'bg-amber-950 text-amber-400 border border-amber-800'
              }`}>
                {selectedProspect.outreachDraft.status === 'Draft' ? 'Requires Human Approval' : selectedProspect.outreachDraft.status}
              </span>
            </div>

            <div className="bg-[#0b101c] p-3 rounded-lg border border-slate-800 text-xs text-slate-300">
              <strong className="text-indigo-400 font-semibold">Recommended Strategy: </strong>
              {selectedProspect.recommendedApproach}
            </div>

            <div className="bg-[#070a12] border border-slate-800 rounded-lg p-4 space-y-2 text-xs">
              <div className="text-slate-400 font-mono text-[11px]">
                <strong>Subject:</strong> {selectedProspect.outreachDraft.subject}
              </div>
              <div className="text-slate-200 whitespace-pre-line leading-relaxed font-sans pt-2 border-t border-slate-800/80">
                {selectedProspect.outreachDraft.body}
              </div>
            </div>

            <p className="text-[11px] text-slate-400 italic">
              <strong>Personalization Evidence: </strong>{selectedProspect.outreachDraft.personalizedReason}
            </p>

            {selectedProspect.outreachDraft.status === 'Draft' && (
              <div className="flex justify-end space-x-2 pt-2">
                <button
                  onClick={() => onUpdateStatus(selectedProspect.id, 'Approved')}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold rounded-lg flex items-center space-x-1.5 shadow-md shadow-emerald-600/20"
                >
                  <ShieldCheck className="w-4 h-4" />
                  <span>Approve Email Draft</span>
                </button>
              </div>
            )}
          </div>
        )}

        {/* Agent Activity Timeline */}
        <div className="bg-[#121929] border border-slate-800 rounded-xl p-5 space-y-3">
          <h3 className="text-xs font-semibold text-slate-200 flex items-center space-x-2 border-b border-slate-800 pb-2">
            <Clock className="w-4 h-4 text-blue-400" />
            <span>Agent Activity Timeline</span>
          </h3>

          <div className="space-y-2 text-xs">
            {selectedProspect.agentTimeline.map((item, idx) => (
              <div key={idx} className="flex items-center space-x-3 text-slate-300">
                <span className="font-mono text-[10px] text-slate-500 w-12">{item.time}</span>
                <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
                <span>{item.action}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
