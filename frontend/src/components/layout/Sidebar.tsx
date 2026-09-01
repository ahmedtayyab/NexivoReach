import React from 'react';
import { 
  LayoutDashboard, 
  Users, 
  Send, 
  Building2, 
  Package, 
  Target, 
  Activity, 
  ChevronDown,
  ChevronRight
} from 'lucide-react';

interface Props {
  activeTab: string;
  onTabChange: (tab: string) => void;
  productsCount: number;
  prospectsCount: number;
  pendingApprovalsCount: number;
}

export default function Sidebar({
  activeTab,
  onTabChange,
  productsCount,
  prospectsCount,
  pendingApprovalsCount
}: Props) {
  const [setupOpen, setSetupOpen] = React.useState(true);

  const mainNav = [
    { id: 'dashboard', label: 'Command Center', icon: LayoutDashboard },
    { id: 'prospects', label: 'Prospects', icon: Users, badge: prospectsCount },
    { id: 'outreach', label: 'Outreach Queue', icon: Send, badge: pendingApprovalsCount, highlight: pendingApprovalsCount > 0 },
  ];

  const setupNav = [
    { id: 'onboarding', label: 'Company Profile', icon: Building2 },
    { id: 'catalog', label: 'Product Catalog', icon: Package, badge: productsCount },
    { id: 'icp', label: 'ICP & Signals', icon: Target },
    { id: 'activity', label: 'System Audit Log', icon: Activity },
  ];

  return (
    <aside className="w-64 bg-[#090d16] border-r border-slate-800 flex flex-col h-screen sticky top-0 flex-shrink-0 select-none">
      {/* Brand Header */}
      <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
        <div className="flex items-center space-x-2.5">
          <div className="w-7 h-7 rounded bg-blue-600 flex items-center justify-center font-bold text-white text-xs">
            NR
          </div>
          <div>
            <span className="font-bold text-white text-sm tracking-tight block">NexivoReach</span>
            <span className="text-[10px] text-slate-400 font-medium">B2B Prospecting Engine</span>
          </div>
        </div>
      </div>

      {/* Navigation Sections */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
        {/* Sales Workspace */}
        <div className="space-y-1">
          <span className="px-3 text-[10px] font-semibold uppercase tracking-wider text-slate-500 block mb-2">
            Sales Workspace
          </span>
          {mainNav.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onTabChange(item.id)}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-md text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-blue-600/15 text-blue-400 border border-blue-500/20'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                }`}
              >
                <div className="flex items-center space-x-2.5">
                  <Icon className={`w-4 h-4 ${isActive ? 'text-blue-400' : 'text-slate-400'}`} />
                  <span>{item.label}</span>
                </div>
                {item.badge !== undefined && item.badge > 0 && (
                  <span className={`px-1.5 py-0.2 text-[10px] font-bold rounded ${
                    item.highlight 
                      ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                      : isActive 
                      ? 'bg-blue-500/20 text-blue-300' 
                      : 'bg-slate-800 text-slate-400'
                  }`}>
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Configuration / Setup */}
        <div className="space-y-1">
          <button
            onClick={() => setSetupOpen(!setupOpen)}
            className="w-full flex items-center justify-between px-3 text-[10px] font-semibold uppercase tracking-wider text-slate-500 hover:text-slate-300 mb-1"
          >
            <span>Configuration & Setup</span>
            {setupOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          </button>

          {setupOpen && (
            <div className="space-y-0.5 pt-1">
              {setupNav.map((item) => {
                const Icon = item.icon;
                const isActive = activeTab === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => onTabChange(item.id)}
                    className={`w-full flex items-center justify-between px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                      isActive
                        ? 'bg-blue-600/15 text-blue-400 border border-blue-500/20'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                    }`}
                  >
                    <div className="flex items-center space-x-2.5">
                      <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-blue-400' : 'text-slate-400'}`} />
                      <span>{item.label}</span>
                    </div>
                    {item.badge !== undefined && (
                      <span className="text-[10px] text-slate-500">{item.badge}</span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Active Workspace / Business Context Footer */}
      <div className="p-3 border-t border-slate-800 bg-[#070a12] space-y-2">
        <div className="flex items-center space-x-2 text-xs text-slate-300">
          <div className="w-2 h-2 rounded-full bg-emerald-500" />
          <div className="truncate">
            <span className="text-[10px] text-slate-500 block">Active Business</span>
            <span className="font-semibold text-slate-200 text-xs">Apex Fitness Equipment</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
