import { Settings, LayoutList, Activity, Mail, LifeBuoy } from 'lucide-react';
import type { AppRoute } from '../../lib/navigation';

interface Props {
  activeTab: string;
  activeRoute: AppRoute;
  onTabChange: (tab: string) => void;
  pendingCount: number;
  draftCount?: number;
}

const items = [
  { id: 'settings', label: 'Workspace', icon: Settings },
  { id: 'queue', label: 'Leads', icon: LayoutList },
  { id: 'outreach', label: 'Outreach', icon: Mail },
  { id: 'support', label: 'Support', icon: LifeBuoy },
  { id: 'activity', label: 'Activity', icon: Activity },
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
      className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-panel-elevated border-t border-border safe-bottom"
      aria-label="Primary"
    >
      <div className="grid grid-cols-5 h-14">
        {items.map(({ id, label, icon: Icon }) => {
          const isActive =
            id === 'settings'
              ? activeRoute === 'company' || activeRoute === 'catalog' || activeRoute === 'icp' || activeRoute === 'integrations'
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
                isActive ? 'text-accent font-semibold' : 'text-ink-muted'
              }`}
            >
              <span className="relative">
                <Icon className="w-5 h-5" strokeWidth={isActive ? 2 : 1.75} />
                {badge > 0 && (
                  <span className="absolute -top-1.5 -right-2 min-w-[14px] h-3.5 px-0.5 bg-accent text-panel-elevated text-[9px] leading-3.5 text-center tabular-nums">
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
