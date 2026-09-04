import { Search, Settings, LayoutList, Database, Mail } from 'lucide-react';
import type { AppRoute } from '../../lib/navigation';

interface Props {
  activeTab: string;
  activeRoute: AppRoute;
  onTabChange: (tab: string) => void;
  pendingCount: number;
  draftCount?: number;
}

const items = [
  { id: 'queue', label: 'Leads', icon: LayoutList },
  { id: 'discover', label: 'Discover', icon: Search },
  { id: 'outreach', label: 'Outreach', icon: Mail },
  { id: 'catalog', label: 'Catalog', icon: Database },
  { id: 'settings', label: 'Settings', icon: Settings },
] as const;

export default function MobileNav({
  activeTab,
  activeRoute,
  onTabChange,
  pendingCount,
  draftCount = 0,
}: Props) {
  return (
    <nav
      className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-panel-elevated/95 backdrop-blur border-t border-border safe-bottom"
      aria-label="Primary"
    >
      <div className="grid grid-cols-5 h-14">
        {items.map(({ id, label, icon: Icon }) => {
          const isActive =
            id === 'catalog'
              ? activeRoute === 'catalog'
              : id === 'settings'
                ? activeRoute === 'company' || activeRoute === 'icp' || activeRoute === 'integrations'
                : activeTab === id;
          const badge =
            id === 'queue' ? pendingCount
            : id === 'outreach' ? draftCount
            : 0;
          return (
            <button
              key={id}
              type="button"
              onClick={() => onTabChange(id)}
              className={`flex flex-col items-center justify-center gap-0.5 text-[10px] ${
                isActive ? 'text-accent font-medium' : 'text-ink-muted'
              }`}
            >
              <span className="relative">
                <Icon className="w-5 h-5" strokeWidth={isActive ? 2 : 1.75} />
                {badge > 0 && (
                  <span className="absolute -top-1.5 -right-2 min-w-[14px] h-3.5 px-0.5 rounded-full bg-accent text-panel-elevated text-[9px] leading-3.5 text-center tabular-nums">
                    {badge > 9 ? '9+' : badge}
                  </span>
                )}
              </span>
              {label}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
