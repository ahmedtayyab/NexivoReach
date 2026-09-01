import { Search, Settings, Database, LayoutList } from 'lucide-react';

interface Props {
  activeTab: string;
  onTabChange: (tab: string) => void;
  pendingCount: number;
}

export default function Sidebar({ activeTab, onTabChange, pendingCount }: Props) {
  const primary = [
    { id: 'queue', label: 'Queue', icon: LayoutList },
    { id: 'discover', label: 'Discover', icon: Search },
    { id: 'catalog', label: 'Catalog', icon: Database },
  ];

  return (
    <aside className="w-52 bg-white border-r border-slate-200 flex flex-col h-screen sticky top-0 select-none shrink-0">
      {/* Wordmark */}
      <div className="px-4 h-12 flex items-center border-b border-slate-200">
        <span className="font-semibold text-slate-900 text-sm tracking-tight">NexivoReach</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 py-3 space-y-0.5">
        {primary.map(({ id, label, icon: Icon }) => {
          const active = activeTab === id;
          return (
            <button
              key={id}
              onClick={() => onTabChange(id)}
              className={`w-full flex items-center justify-between pl-2 pr-2 py-1.5 rounded text-sm transition-colors ${
                active
                  ? 'bg-slate-100 text-slate-900 font-medium'
                  : 'text-slate-500 hover:text-slate-900 hover:bg-slate-50'
              }`}
            >
              <div className="flex items-center space-x-2.5">
                <Icon className="w-4 h-4 shrink-0" strokeWidth={1.75} />
                <span>{label}</span>
              </div>
              {id === 'queue' && pendingCount > 0 && (
                <span className="text-xs text-slate-500 font-normal tabular-nums">{pendingCount}</span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Settings — bottom */}
      <div className="px-2 pb-3 border-t border-slate-200 pt-3">
        <button
          onClick={() => onTabChange('settings')}
          className={`w-full flex items-center space-x-2.5 pl-2 pr-2 py-1.5 rounded text-sm transition-colors ${
            activeTab === 'settings'
              ? 'bg-slate-100 text-slate-900 font-medium'
              : 'text-slate-500 hover:text-slate-900 hover:bg-slate-50'
          }`}
        >
          <Settings className="w-4 h-4 shrink-0" strokeWidth={1.75} />
          <span>Settings</span>
        </button>

        {/* Active workspace */}
        <div className="mt-3 pl-2 pr-2">
          <p className="text-xs text-slate-400 leading-tight">Active workspace</p>
          <p className="text-xs font-medium text-slate-700 mt-0.5 truncate">Apex Fitness Equipment</p>
        </div>
      </div>
    </aside>
  );
}
