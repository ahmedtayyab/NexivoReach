import type { Prospect, Product, AgentRunLog } from '../types';
import { 
  Sparkles, 
  ArrowRight,
  CheckCircle2,
  MapPin
} from 'lucide-react';

interface Props {
  prospects: Prospect[];
  products?: Product[];
  agentLogs: AgentRunLog[];
  onSelectProspect: (id: string) => void;
  onNavigate: (tab: string) => void;
  onUpdateStatus: (prospectId: string, status: NonNullable<Prospect['outreachDraft']>['status']) => void;
}

export default function DashboardView({
  prospects,
  agentLogs,
  onSelectProspect,
  onNavigate,
  onUpdateStatus
}: Props) {
  const pendingApprovals = prospects.filter(p => p.outreachDraft && p.outreachDraft.status === 'Draft');
  const recentDiscoveries = prospects.slice(0, 5);
  const lastRunTime = agentLogs[0]?.timestamp || 'Today';

  return (
    <div className="space-y-6 font-sans text-slate-100">
      {/* Top Banner / Header Bar */}
      <div className="bg-[#1e293b] border border-slate-800 rounded-lg p-5 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-bold text-white tracking-tight">Sales Command Center</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Apex Fitness Prospecting Hub • Last discovery run: <span className="text-slate-300 font-mono">{lastRunTime}</span>
          </p>
        </div>

        <button
          onClick={() => onNavigate('discovery')}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs rounded-md flex items-center space-x-2 transition-all shadow-sm"
        >
          <Sparkles className="w-4 h-4" />
          <span>Run Discovery Search</span>
        </button>
      </div>

      {/* 4 Compact Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[#1e293b] border border-slate-800 rounded-lg p-4">
          <span className="text-xs text-slate-400 block font-medium">Total Prospects</span>
          <div className="flex items-baseline space-x-2 mt-1">
            <span className="text-2xl font-bold text-white">{prospects.length}</span>
            <span className="text-[11px] text-slate-400">Qualified leads</span>
          </div>
        </div>

        <div className="bg-[#1e293b] border border-slate-800 rounded-lg p-4">
          <span className="text-xs text-slate-400 block font-medium">Pending Approvals</span>
          <div className="flex items-baseline space-x-2 mt-1">
            <span className="text-2xl font-bold text-amber-400">{pendingApprovals.length}</span>
            <span className="text-[11px] text-amber-300/80">Drafts awaiting review</span>
          </div>
        </div>

        <div className="bg-[#1e293b] border border-slate-800 rounded-lg p-4">
          <span className="text-xs text-slate-400 block font-medium">Outreach Dispatched</span>
          <div className="flex items-baseline space-x-2 mt-1">
            <span className="text-2xl font-bold text-blue-400">
              {prospects.filter(p => p.outreachDraft?.status === 'Sent').length}
            </span>
            <span className="text-[11px] text-slate-400">Sent this week</span>
          </div>
        </div>

        <div className="bg-[#1e293b] border border-slate-800 rounded-lg p-4">
          <span className="text-xs text-slate-400 block font-medium">Avg Fit Score</span>
          <div className="flex items-baseline space-x-2 mt-1">
            <span className="text-2xl font-bold text-emerald-400">91%</span>
            <span className="text-[11px] text-emerald-400">Evidence backed</span>
          </div>
        </div>
      </div>

      {/* Priority Section: Pending Approvals Queue */}
      <div className="bg-[#1e293b] border border-slate-800 rounded-lg p-5 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div>
            <h2 className="text-sm font-semibold text-white">Priority Approvals Required ({pendingApprovals.length})</h2>
            <p className="text-xs text-slate-400">Review AI-personalized outreach drafts before sending</p>
          </div>
          {pendingApprovals.length > 0 && (
            <button
              onClick={() => onNavigate('outreach')}
              className="text-xs text-blue-400 hover:text-blue-300 font-medium flex items-center space-x-1"
            >
              <span>View All Outreach Queue</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {pendingApprovals.length === 0 ? (
          <div className="text-center py-6 text-xs text-slate-400 space-y-1">
            <CheckCircle2 className="w-6 h-6 text-emerald-500 mx-auto" />
            <p className="font-semibold text-slate-300">All outreach drafts approved!</p>
            <p>No pending messages awaiting human review.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-slate-400 text-[11px] font-semibold">
                  <th className="py-2.5 px-3">Company</th>
                  <th className="py-2.5 px-3">Location</th>
                  <th className="py-2.5 px-3">Fit Score</th>
                  <th className="py-2.5 px-3">Top Buying Signal</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {pendingApprovals.slice(0, 5).map((prospect) => (
                  <tr key={prospect.id} className="hover:bg-slate-800/40 transition-all">
                    <td className="py-3 px-3">
                      <button
                        onClick={() => onSelectProspect(prospect.id)}
                        className="font-semibold text-white hover:text-blue-400 text-left"
                      >
                        {prospect.companyName}
                      </button>
                      <span className="text-[11px] text-slate-400 block">{prospect.industry}</span>
                    </td>
                    <td className="py-3 px-3 text-slate-300">{prospect.location}</td>
                    <td className="py-3 px-3 font-bold text-emerald-400">{prospect.fitScore}%</td>
                    <td className="py-3 px-3 text-slate-300">
                      ⚡ {prospect.buyingSignals[0]?.signal || 'Facility Expansion'}
                    </td>
                    <td className="py-3 px-3 text-right space-x-2">
                      <button
                        onClick={() => onSelectProspect(prospect.id)}
                        className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px] rounded font-medium"
                      >
                        Review
                      </button>
                      <button
                        onClick={() => onUpdateStatus(prospect.id, 'Approved')}
                        className="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] rounded font-semibold transition-all"
                      >
                        Approve
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Recent Discoveries Section */}
      <div className="bg-[#1e293b] border border-slate-800 rounded-lg p-5 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <h2 className="text-sm font-semibold text-white">Recent Qualified Discoveries</h2>
          <button
            onClick={() => onNavigate('prospects')}
            className="text-xs text-blue-400 hover:text-blue-300 font-medium flex items-center space-x-1"
          >
            <span>View All Prospects</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {recentDiscoveries.map((prospect) => (
            <div
              key={prospect.id}
              onClick={() => onSelectProspect(prospect.id)}
              className="bg-[#090d16] border border-slate-800 hover:border-slate-700 rounded-lg p-4 space-y-2 cursor-pointer transition-all"
            >
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-white text-xs">{prospect.companyName}</h3>
                  <span className="text-[11px] text-slate-400 flex items-center space-x-1 mt-0.5">
                    <MapPin className="w-3 h-3 text-slate-500" />
                    <span>{prospect.location}</span>
                  </span>
                </div>
                <span className="text-xs font-bold text-emerald-400">{prospect.fitScore}%</span>
              </div>
              <p className="text-[11px] text-slate-300 line-clamp-2">{prospect.whyThisProspect}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
