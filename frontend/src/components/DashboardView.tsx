import type { Prospect, Product, AgentRunLog } from '../types';
import { 
  Package, 
  Users, 
  Send, 
  TrendingUp, 
  Sparkles, 
  ChevronRight
} from 'lucide-react';

interface Props {
  prospects: Prospect[];
  products: Product[];
  agentLogs: AgentRunLog[];
  onSelectProspect: (id: string) => void;
  onNavigate: (tab: string) => void;
}

export default function DashboardView({ prospects, products, agentLogs, onSelectProspect, onNavigate }: Props) {
  const pipelineStages = [
    { id: 'New', label: 'New Discovered', color: 'bg-slate-700 text-slate-200' },
    { id: 'Researched', label: 'Researched', color: 'bg-blue-900/60 text-blue-300 border border-blue-700/40' },
    { id: 'Qualified', label: 'Qualified', color: 'bg-emerald-900/60 text-emerald-300 border border-emerald-700/40' },
    { id: 'Contacted', label: 'Contacted', color: 'bg-amber-900/60 text-amber-300 border border-amber-700/40' },
    { id: 'Replied', label: 'Replied', color: 'bg-purple-900/60 text-purple-300 border border-purple-700/40' },
    { id: 'Meeting', label: 'Meeting Scheduled', color: 'bg-indigo-900/60 text-indigo-300 border border-indigo-700/40' },
  ];

  const getStageCount = (stageId: string) => prospects.filter(p => p.stage === stageId).length;

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="bg-gradient-to-r from-blue-950/80 via-slate-900 to-indigo-950/80 border border-blue-900/40 rounded-xl p-6 relative overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-blue-500/5 rounded-full blur-3xl -mr-20 -mt-20 pointer-events-none" />
        <div className="relative z-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2 text-blue-400 text-xs font-semibold uppercase tracking-wider mb-1">
              <Sparkles className="w-4 h-4" />
              <span>Sales Prospecting Command Center</span>
            </div>
            <h1 className="text-2xl font-bold text-white tracking-tight">Apex Fitness Prospecting Hub</h1>
            <p className="text-sm text-slate-300 mt-1 max-w-2xl">
              NexivoReach agent is monitoring GCC commercial fitness expansions, evaluating catalog fit, and preparing personalized outreach with human approval.
            </p>
          </div>

          <div className="flex items-center space-x-3">
            <button 
              onClick={() => onNavigate('discovery')}
              className="px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs rounded-lg shadow-lg shadow-blue-600/30 flex items-center space-x-2 transition-all"
            >
              <Sparkles className="w-4 h-4" />
              <span>Run Prospecting Agent</span>
            </button>
          </div>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[#121929] border border-slate-800/80 rounded-xl p-4 flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 font-medium">Catalog Products</p>
            <p className="text-2xl font-bold text-white mt-1">{products.length}</p>
            <p className="text-[11px] text-emerald-400 mt-0.5">Ready for buyer matching</p>
          </div>
          <div className="w-10 h-10 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
            <Package className="w-5 h-5 text-indigo-400" />
          </div>
        </div>

        <div className="bg-[#121929] border border-slate-800/80 rounded-xl p-4 flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 font-medium">Total Prospects</p>
            <p className="text-2xl font-bold text-white mt-1">{prospects.length}</p>
            <p className="text-[11px] text-blue-400 mt-0.5">High-fit commercial buyers</p>
          </div>
          <div className="w-10 h-10 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
            <Users className="w-5 h-5 text-blue-400" />
          </div>
        </div>

        <div className="bg-[#121929] border border-slate-800/80 rounded-xl p-4 flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 font-medium">Pending Approvals</p>
            <p className="text-2xl font-bold text-white mt-1">
              {prospects.filter(p => p.outreachDraft && p.outreachDraft.status === 'Draft').length}
            </p>
            <p className="text-[11px] text-amber-400 mt-0.5">Outreach drafts awaiting review</p>
          </div>
          <div className="w-10 h-10 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
            <Send className="w-5 h-5 text-amber-400" />
          </div>
        </div>

        <div className="bg-[#121929] border border-slate-800/80 rounded-xl p-4 flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 font-medium">Avg Prospect Fit Score</p>
            <p className="text-2xl font-bold text-emerald-400 mt-1">91%</p>
            <p className="text-[11px] text-emerald-400 mt-0.5">Transparent evidence-backed</p>
          </div>
          <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
            <TrendingUp className="w-5 h-5 text-emerald-400" />
          </div>
        </div>
      </div>

      {/* Prospect Pipeline Bar */}
      <div className="bg-[#121929] border border-slate-800/80 rounded-xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-slate-200 flex items-center space-x-2">
            <span>Sales Prospect Pipeline</span>
            <span className="text-xs text-slate-400 font-normal">(New → Qualified → Contacted → Replied)</span>
          </h2>
          <button 
            onClick={() => onNavigate('prospects')}
            className="text-xs text-blue-400 hover:text-blue-300 flex items-center space-x-1"
          >
            <span>View All Prospects</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          {pipelineStages.map((stage) => {
            const count = getStageCount(stage.id);
            return (
              <div key={stage.id} className="bg-[#0b101c] border border-slate-800/70 rounded-lg p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[11px] font-medium text-slate-400 truncate">{stage.label}</span>
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${stage.color}`}>{count}</span>
                </div>
                <div className="w-full bg-slate-800 rounded-full h-1.5 mt-2">
                  <div 
                    className="bg-blue-500 h-1.5 rounded-full transition-all" 
                    style={{ width: `${prospects.length > 0 ? (count / prospects.length) * 100 : 0}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Grid: Priority Prospects & Agent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Priority Prospects List */}
        <div className="lg:col-span-2 bg-[#121929] border border-slate-800/80 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-200">High-Priority Prospect Match List</h2>
            <span className="text-xs text-slate-400">Ranked by Transparent Fit Score</span>
          </div>

          <div className="space-y-3">
            {prospects.map((prospect) => (
              <div 
                key={prospect.id}
                onClick={() => onSelectProspect(prospect.id)}
                className="bg-[#0b101c] hover:bg-slate-800/60 border border-slate-800 hover:border-slate-700 rounded-lg p-4 transition-all cursor-pointer flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"
              >
                <div className="space-y-1 max-w-md">
                  <div className="flex items-center space-x-2">
                    <span className="font-semibold text-white text-sm">{prospect.companyName}</span>
                    <span className="text-xs text-slate-400">• {prospect.location}</span>
                  </div>
                  <p className="text-xs text-slate-300 line-clamp-2">{prospect.whyThisProspect}</p>
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {prospect.buyingSignals.slice(0, 2).map((sig, idx) => (
                      <span key={idx} className="text-[10px] bg-emerald-950/60 text-emerald-400 border border-emerald-800/50 px-2 py-0.5 rounded font-medium">
                        ⚡ {sig.signal}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="flex items-center space-x-4 self-end sm:self-center">
                  <div className="text-right">
                    <div className="text-lg font-bold text-emerald-400">{prospect.fitScore}% Match</div>
                    <span className="text-[10px] text-slate-400">Transparent Fit</span>
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-500" />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Recent Agent Activity */}
        <div className="bg-[#121929] border border-slate-800/80 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-200">Recent Agent Activity</h2>
            <button 
              onClick={() => onNavigate('activity')}
              className="text-xs text-blue-400 hover:text-blue-300"
            >
              Full Log
            </button>
          </div>

          <div className="space-y-3">
            {agentLogs.flatMap(log => log.decisions).map((dec, idx) => (
              <div key={idx} className="bg-[#0b101c] border border-slate-800/60 rounded-lg p-3 text-xs space-y-1">
                <div className="flex items-center justify-between text-slate-400">
                  <span className="font-mono text-[10px] text-blue-400">Step {dec.step}</span>
                  {dec.toolCalled && (
                    <span className="bg-slate-800 text-slate-300 px-1.5 py-0.5 rounded text-[10px]">
                      Tool: {dec.toolCalled}
                    </span>
                  )}
                </div>
                <p className="text-slate-200 font-medium">{dec.decision}</p>
                {dec.toolResultSnippet && (
                  <p className="text-[11px] text-slate-400 bg-slate-900/80 p-1.5 rounded font-mono border border-slate-800">
                    {dec.toolResultSnippet}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
