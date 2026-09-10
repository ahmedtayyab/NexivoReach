import { Plus, LogOut, ChevronDown, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { AuthUser, BusinessInfo } from '../../types';
import type { AppRoute } from '../../lib/navigation';
import { Settings, LayoutList, Activity, Mail } from 'lucide-react';
import BrandLockup from '../brand/BrandLockup';
import ConnectionStatus from '../ConnectionStatus';

interface Props {
  activeTab: string;
  activeRoute: AppRoute;
  onTabChange: (tab: string) => void;
  pendingCount: number;
  draftCount?: number;
  companies: BusinessInfo[];
  activeCompanyId?: string | null;
  onSwitchCompany: (id: string) => void;
  onAddCompany: () => void;
  user?: AuthUser | null;
  onLogout?: () => void;
  mobileOpen?: boolean;
  onMobileClose?: () => void;
}

export default function Sidebar({
  activeTab,
  activeRoute,
  onTabChange,
  pendingCount,
  draftCount = 0,
  companies,
  activeCompanyId,
  onSwitchCompany,
  onAddCompany,
  user,
  onLogout,
  mobileOpen = false,
  onMobileClose,
}: Props) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const active = companies.find(c => c.id === activeCompanyId) || companies[0];
  const label = active?.name?.trim() || 'Untitled company';

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  useEffect(() => {
    if (!mobileOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onMobileClose?.();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [mobileOpen, onMobileClose]);

  // Workspace first — the main input surface for the agent
  const primary = [
    { id: 'settings', label: 'Workspace', icon: Settings, emphasize: true },
    { id: 'queue', label: 'Leads', icon: LayoutList, emphasize: false },
    { id: 'outreach', label: 'Outreach', icon: Mail, emphasize: false },
  ];

  const secondary = [
    { id: 'activity', label: 'Activity', icon: Activity },
  ];

  const go = (id: string) => {
    onTabChange(id);
    onMobileClose?.();
  };

  const settingsActive =
    activeRoute === 'company' ||
    activeRoute === 'catalog' ||
    activeRoute === 'icp' ||
    activeRoute === 'integrations';

  return (
    <>
      {mobileOpen && (
        <div
          className="md:hidden fixed inset-0 z-40 bg-ink/35"
          onClick={onMobileClose}
          aria-hidden
        />
      )}

      <aside
        className={[
          'w-56 max-w-[85vw] bg-surface border-r border-border flex flex-col h-dvh select-none shrink-0',
          'fixed inset-y-0 left-0 z-50 transition-transform duration-200 ease-out',
          'md:sticky md:top-0 md:z-auto md:translate-x-0 md:h-screen',
          mobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
        ].join(' ')}
      >
        <div className="px-4 h-12 flex items-center justify-between border-b border-border">
          <BrandLockup size="sm" />
          <button
            type="button"
            className="md:hidden p-1.5 -mr-1 text-ink-muted hover:text-ink"
            onClick={onMobileClose}
            aria-label="Close menu"
          >
            <X className="w-4 h-4" strokeWidth={1.75} />
          </button>
        </div>

        <div className="px-2 pt-3 pb-1" ref={menuRef}>
          <button
            type="button"
            onClick={() => setOpen(v => !v)}
            className="w-full flex items-center justify-between gap-1 px-2.5 py-2 border border-border bg-panel hover:border-ink-muted transition-colors"
          >
            <div className="min-w-0 text-left">
              <p className="text-[10px] uppercase tracking-[0.12em] text-ink-muted leading-none mb-1">Company</p>
              <p className="text-[13px] font-medium text-ink truncate leading-tight">{label}</p>
            </div>
            <ChevronDown className={`w-3.5 h-3.5 text-ink-muted shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
          </button>
          {open && (
            <div className="mt-1 border border-border bg-panel-elevated overflow-hidden z-30 relative">
              <div className="max-h-48 overflow-auto py-1">
                {companies.map(c => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => {
                      if (c.id) onSwitchCompany(c.id);
                      setOpen(false);
                      onMobileClose?.();
                    }}
                    className={`w-full text-left px-3 py-2 text-[12.5px] truncate ${
                      c.id === activeCompanyId
                        ? 'bg-muted text-ink font-medium'
                        : 'text-ink-secondary hover:bg-canvas'
                    }`}
                  >
                    {c.name?.trim() || 'Untitled company'}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  onAddCompany();
                  onMobileClose?.();
                }}
                className="w-full flex items-center gap-1.5 px-3 py-2 text-[12px] text-accent border-t border-border hover:bg-canvas"
              >
                <Plus className="w-3.5 h-3.5" strokeWidth={2} />
                Add company
              </button>
            </div>
          )}
        </div>

        <nav className="flex-1 px-2 pt-3 pb-2 space-y-1 overflow-y-auto">
          {primary.map(({ id, label: itemLabel, icon: Icon, emphasize }) => {
            const isActive = id === 'settings' ? settingsActive : activeTab === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => go(id)}
                className={[
                  'nav-item-primary w-full flex items-center justify-between pl-2.5 pr-2 py-2 text-[13px] transition-colors',
                  emphasize ? 'is-workspace' : '',
                  isActive && !emphasize
                    ? 'bg-muted text-ink font-medium'
                    : !emphasize
                      ? 'text-ink-muted hover:text-ink hover:bg-panel/70'
                      : isActive
                        ? ''
                        : 'opacity-95',
                ].join(' ')}
              >
                <div className="flex items-center gap-2.5">
                  <Icon
                    className={`w-[15px] h-[15px] shrink-0 ${isActive || emphasize ? 'text-accent' : 'text-ink-muted'}`}
                    strokeWidth={isActive || emphasize ? 2 : 1.75}
                  />
                  <span>{itemLabel}</span>
                </div>
                {id === 'queue' && pendingCount > 0 && (
                  <span className="text-[11.5px] tabular-nums font-medium text-ink-secondary">{pendingCount}</span>
                )}
                {id === 'outreach' && draftCount > 0 && (
                  <span className="text-[11.5px] tabular-nums font-medium text-ink-secondary">{draftCount}</span>
                )}
              </button>
            );
          })}
        </nav>

        <div className="px-2 pb-2">
          <ConnectionStatus
            gmailConnected={Boolean(user?.gmail?.connected)}
            gmailEmail={user?.gmail?.email}
            onOpenConnect={() => go('integrations')}
          />
        </div>

        <div className="mx-2 border-t border-border-subtle" />

        <div className="px-2 py-2 space-y-px">
          {secondary.map(({ id, label: itemLabel, icon: Icon }) => {
            const isActive = activeTab === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => go(id)}
                className={`w-full flex items-center gap-2.5 pl-2.5 pr-2 py-[7px] text-[13px] transition-colors ${
                  isActive
                    ? 'bg-muted text-ink font-medium'
                    : 'text-ink-muted hover:text-ink hover:bg-panel/60'
                }`}
              >
                <Icon
                  className={`w-[15px] h-[15px] shrink-0 ${isActive ? 'text-ink-secondary' : 'text-ink-muted'}`}
                  strokeWidth={isActive ? 2 : 1.75}
                />
                <span>{itemLabel}</span>
              </button>
            );
          })}
        </div>

        <div className="px-3 py-3 border-t border-border-subtle space-y-2">
          {user && (
            <div className="flex items-center gap-2 min-w-0">
              {user.picture ? (
                <img src={user.picture} alt="" className="w-6 h-6 shrink-0 object-cover" />
              ) : (
                <div className="w-6 h-6 bg-border shrink-0" />
              )}
              <div className="min-w-0 flex-1">
                <p className="text-[12px] font-medium text-ink-secondary truncate">{user.name}</p>
                <p className="text-[11px] text-ink-muted truncate">{user.email}</p>
              </div>
            </div>
          )}
          {onLogout && (
            <button
              type="button"
              onClick={onLogout}
              className="w-full flex items-center gap-2 text-[12px] text-ink-muted hover:text-ink pt-1"
            >
              <LogOut className="w-3.5 h-3.5" strokeWidth={1.75} />
              Sign out
            </button>
          )}
        </div>
      </aside>
    </>
  );
}
