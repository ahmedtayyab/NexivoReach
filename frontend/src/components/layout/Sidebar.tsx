import { Search, Settings, Database, LayoutList, Activity, LogOut } from 'lucide-react';
import type { AuthUser } from '../../types';

interface Props {
  activeTab: string;
  onTabChange: (tab: string) => void;
  pendingCount: number;
  workspaceName?: string;
  user?: AuthUser | null;
  onLogout?: () => void;
}

export default function Sidebar({ activeTab, onTabChange, pendingCount, workspaceName, user, onLogout }: Props) {
  const primary = [
    { id: 'queue', label: 'Queue', icon: LayoutList },
    { id: 'discover', label: 'Discover', icon: Search },
    { id: 'catalog', label: 'Catalog', icon: Database },
  ];

  const secondary = [
    { id: 'activity', label: 'Activity', icon: Activity },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  return (
    <aside className="w-52 bg-white border-r border-slate-200 flex flex-col h-screen sticky top-0 select-none shrink-0">
      <div className="px-4 h-12 flex items-center border-b border-slate-200">
        <div className="flex items-center space-x-2">
          <div className="w-5 h-5 rounded bg-blue-600 flex items-center justify-center shrink-0">
            <span className="text-white font-bold text-[10px] leading-none">NR</span>
          </div>
          <span className="font-semibold text-slate-900 text-sm tracking-tight">NexivoReach</span>
        </div>
      </div>

      <nav className="flex-1 px-2 pt-3 pb-2 space-y-px">
        {primary.map(({ id, label, icon: Icon }) => {
          const active = activeTab === id;
          return (
            <button
              key={id}
              onClick={() => onTabChange(id)}
              className={`w-full flex items-center justify-between pl-2.5 pr-2 py-[7px] rounded-md text-[13px] transition-colors ${
                active
                  ? 'bg-slate-100 text-slate-900 font-medium'
                  : 'text-slate-500 hover:text-slate-900 hover:bg-slate-50'
              }`}
            >
              <div className="flex items-center space-x-2.5">
                <Icon
                  className={`w-[15px] h-[15px] shrink-0 ${active ? 'text-slate-700' : 'text-slate-400'}`}
                  strokeWidth={active ? 2 : 1.75}
                />
                <span>{label}</span>
              </div>
              {id === 'queue' && pendingCount > 0 && (
                <span className={`text-[11.5px] tabular-nums font-medium ${active ? 'text-slate-700' : 'text-slate-400'}`}>
                  {pendingCount}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      <div className="mx-2 border-t border-slate-100" />

      <div className="px-2 py-2 space-y-px">
        {secondary.map(({ id, label, icon: Icon }) => {
          const active = activeTab === id;
          return (
            <button
              key={id}
              onClick={() => onTabChange(id)}
              className={`w-full flex items-center space-x-2.5 pl-2.5 pr-2 py-[7px] rounded-md text-[13px] transition-colors ${
                active
                  ? 'bg-slate-100 text-slate-900 font-medium'
                  : 'text-slate-500 hover:text-slate-900 hover:bg-slate-50'
              }`}
            >
              <Icon
                className={`w-[15px] h-[15px] shrink-0 ${active ? 'text-slate-700' : 'text-slate-400'}`}
                strokeWidth={active ? 2 : 1.75}
              />
              <span>{label}</span>
            </button>
          );
        })}
      </div>

      <div className="px-3 py-3 border-t border-slate-100 space-y-2">
        {user && (
          <div className="flex items-center gap-2 min-w-0">
            {user.picture ? (
              <img src={user.picture} alt="" className="w-6 h-6 rounded-full shrink-0" />
            ) : (
              <div className="w-6 h-6 rounded-full bg-slate-200 shrink-0" />
            )}
            <div className="min-w-0 flex-1">
              <p className="text-[12px] font-medium text-slate-700 truncate">{user.name}</p>
              <p className="text-[11px] text-slate-400 truncate">{user.email}</p>
            </div>
          </div>
        )}
        <div className="flex items-center space-x-2">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="text-[11px] text-slate-400 leading-none mb-0.5">Workspace</p>
            <p className="text-[12.5px] font-medium text-slate-700 truncate leading-tight">
              {workspaceName || 'Set up workspace'}
            </p>
          </div>
        </div>
        {onLogout && (
          <button
            onClick={onLogout}
            className="w-full flex items-center gap-2 text-[12px] text-slate-500 hover:text-slate-800 pt-1"
          >
            <LogOut className="w-3.5 h-3.5" strokeWidth={1.75} />
            Sign out
          </button>
        )}
      </div>
    </aside>
  );
}
