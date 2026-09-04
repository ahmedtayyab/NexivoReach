import { useState, useEffect, useCallback } from 'react';
import type { BusinessInfo, Product, IdealCustomerProfile, Prospect, AgentRunLog, AuthUser } from './types';
import {
  emptyBusinessInfo,
  emptyProducts,
  emptyICP,
  emptyProspects,
  emptyAgentLogs,
} from './data/defaults';
import { apiFetch, setActiveBusinessId } from './lib/api';
import { parseIcpResponse, parseProfileResponse } from './lib/workspace';
import {
  type AppRoute,
  type SettingsSection,
  isSettingsRoute,
  normalizeRoute,
  resolveRouteFromLocation,
  routeFromSidebarTab,
  sidebarTabForRoute,
} from './lib/navigation';

import Sidebar from './components/layout/Sidebar';
import MobileNav from './components/layout/MobileNav';
import QueueView from './components/QueueView';
import DiscoverView from './components/DiscoverView';
import SettingsView from './components/SettingsView';
import OutreachInboxView from './components/OutreachInboxView';
import ReviewDrawer from './components/prospects/ReviewDrawer';
import ActivityView from './components/ActivityView';
import LoginView from './components/LoginView';
import BrandLockup from './components/brand/BrandLockup';
import { Menu } from 'lucide-react';

export default function App() {
  const [authLoading, setAuthLoading] = useState(true);
  const [authConfigured, setAuthConfigured] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);

  const [activeRoute, setActiveRoute] = useState<AppRoute>('queue');
  const [companies, setCompanies] = useState<BusinessInfo[]>([]);
  const [activeCompanyId, setActiveCompanyIdState] = useState<string | null>(null);
  const [businessInfo, setBusinessInfo] = useState<BusinessInfo>(emptyBusinessInfo);
  const [products, setProducts] = useState<Product[]>(emptyProducts);
  const [icp, setIcp] = useState<IdealCustomerProfile>(emptyICP);
  const [prospects, setProspects] = useState<Prospect[]>(emptyProspects);
  const [agentLogs, setAgentLogs] = useState<AgentRunLog[]>(emptyAgentLogs);
  const [selectedProspectId, setSelectedProspectId] = useState<string | null>(null);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const selectedProspect = prospects.find(p => p.id === selectedProspectId) ?? null;

  const pendingCount = prospects.filter(
    p => !p.outreachDraft || p.outreachDraft.status === 'Draft'
  ).length;

  const draftCount = prospects.filter(
    p => p.outreachDraft && (p.outreachDraft.status === 'Draft' || p.outreachDraft.status === 'Approved')
  ).length;

  const navigate = (route: AppRoute, replace = false) => {
    const next = normalizeRoute(route);
    setActiveRoute(next);
    const url = `#${next}`;
    if (replace) {
      window.history.replaceState({ route: next }, '', url);
    } else {
      window.history.pushState({ route: next }, '', url);
    }
  };

  const loadCompanies = useCallback(async () => {
    const resp = await apiFetch('/api/companies/');
    if (!resp.ok) return null;
    const data = await resp.json();
    const list = Array.isArray(data.companies) ? (data.companies as BusinessInfo[]) : [];
    setCompanies(list);
    const active = (data.activeBusinessId as string) || list[0]?.id || null;
    if (active) {
      setActiveBusinessId(active);
      setActiveCompanyIdState(active);
    }
    return active;
  }, []);

  const loadCompanyData = useCallback(async () => {
    const [prospectsResp, logsResp, profileResp, productsResp, icpResp] = await Promise.all([
      apiFetch('/api/prospects/'),
      apiFetch('/api/discovery/runs'),
      apiFetch('/api/onboarding/profile'),
      apiFetch('/api/products/'),
      apiFetch('/api/icp/'),
    ]);

    if (prospectsResp.ok) {
      const list = await prospectsResp.json();
      if (Array.isArray(list)) setProspects(list as Prospect[]);
    } else {
      setProspects(emptyProspects);
    }
    if (logsResp.ok) {
      const logs = await logsResp.json();
      if (Array.isArray(logs)) setAgentLogs(logs as AgentRunLog[]);
    } else {
      setAgentLogs(emptyAgentLogs);
    }
    if (profileResp.ok) {
      setBusinessInfo(parseProfileResponse(await profileResp.json()));
    } else {
      setBusinessInfo(emptyBusinessInfo);
    }
    if (productsResp.ok) {
      const catalog = await productsResp.json();
      if (Array.isArray(catalog)) setProducts(catalog as Product[]);
    } else {
      setProducts(emptyProducts);
    }
    if (icpResp.ok) {
      setIcp(parseIcpResponse(await icpResp.json()));
    } else {
      setIcp(emptyICP);
    }
  }, []);

  const bootstrap = useCallback(async () => {
    await loadCompanies();
    await loadCompanyData();
  }, [loadCompanies, loadCompanyData]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('auth') === 'error') {
      setAuthError('Sign-in failed. Check your Google OAuth settings and try again.');
      window.history.replaceState({}, '', window.location.pathname + window.location.hash);
    }

    (async () => {
      try {
        const resp = await apiFetch('/api/auth/me');
        if (!resp.ok) throw new Error('Auth check failed');
        const data = await resp.json();
        setAuthConfigured(Boolean(data.configured));
        setUser(data.user ?? null);
        if (!data.configured || data.user) {
          await bootstrap();
        }
        if (data.user) {
          const initialRoute = resolveRouteFromLocation();
          setActiveRoute(initialRoute);
          window.history.replaceState({ route: initialRoute }, '', `#${initialRoute}`);
        }
        // Refresh Gmail status after OAuth return
        if (params.get('gmail') === 'connected') {
          const st = await apiFetch('/api/auth/gmail/status');
          if (st.ok) {
            const gmail = await st.json();
            setUser(prev => (prev ? { ...prev, gmail } : prev));
          }
        }
      } catch {
        setAuthConfigured(false);
        setUser(null);
      } finally {
        setAuthLoading(false);
      }
    })();
  }, [bootstrap]);

  useEffect(() => {
    const syncRoute = () => {
      if (window.location.pathname.startsWith('/api/')) {
        const route = resolveRouteFromLocation();
        window.location.replace(`/#${route}`);
        return;
      }
      setActiveRoute(resolveRouteFromLocation());
    };
    window.addEventListener('popstate', syncRoute);
    window.addEventListener('hashchange', syncRoute);
    return () => {
      window.removeEventListener('popstate', syncRoute);
      window.removeEventListener('hashchange', syncRoute);
    };
  }, []);

  useEffect(() => {
    if (authLoading || !user) return;
    const valid =
      activeRoute === 'queue' ||
      activeRoute === 'discover' ||
      activeRoute === 'outreach' ||
      activeRoute === 'activity' ||
      isSettingsRoute(activeRoute);
    if (!valid) {
      navigate('queue', true);
    }
  }, [activeRoute, authLoading, user]);

  const handleSidebarChange = (tab: string) => {
    navigate(routeFromSidebarTab(tab));
    setMobileNavOpen(false);
  };

  const handleSettingsSectionChange = (section: SettingsSection) => {
    navigate(section);
  };

  const handleSwitchCompany = async (id: string) => {
    setActiveBusinessId(id);
    setActiveCompanyIdState(id);
    setSelectedProspectId(null);
    await apiFetch(`/api/companies/${id}/activate`, { method: 'POST' });
    await loadCompanyData();
    await loadCompanies();
  };

  const handleAddCompany = async () => {
    const resp = await apiFetch('/api/companies/', {
      method: 'POST',
      body: JSON.stringify({ name: 'New company' }),
    });
    if (!resp.ok) return;
    const data = await resp.json();
    const id = data.activeBusinessId || data.company?.id;
    if (id) {
      setActiveBusinessId(id);
      setActiveCompanyIdState(id);
    }
    await loadCompanies();
    await loadCompanyData();
    navigate('company');
  };

  const persistProspect = async (prospect: Prospect) => {
    try {
      await apiFetch('/api/prospects/save', {
        method: 'POST',
        body: JSON.stringify(prospect),
      });
    } catch (e) {
      console.warn('Failed to persist prospect', e);
    }
  };

  const handleUpdateStatus = (
    prospectId: string,
    status: NonNullable<Prospect['outreachDraft']>['status']
  ) => {
    setProspects(prev =>
      prev.map(p => {
        if (p.id !== prospectId || !p.outreachDraft) return p;
        const stage =
          status === 'Approved' ? 'To contact'
          : status === 'Sent' ? 'Contacted'
          : status === 'Replied' ? 'Replied'
          : p.stage;
        const updated = {
          ...p,
          stage: stage as Prospect['stage'],
          outreachDraft: { ...p.outreachDraft, status },
        };
        void persistProspect(updated);
        return updated;
      })
    );
  };

  const handleSaveDraft = (prospectId: string, subject: string, body: string, toEmail?: string) => {
    setProspects(prev =>
      prev.map(p => {
        if (p.id !== prospectId || !p.outreachDraft) return p;
        const updated = {
          ...p,
          email: toEmail !== undefined && toEmail.trim() ? toEmail.trim() : p.email,
          outreachDraft: {
            ...p.outreachDraft,
            subject,
            body,
            ...(toEmail !== undefined ? { toEmail: toEmail.trim() } : {}),
          },
        };
        void persistProspect(updated);
        return updated;
      })
    );
  };

  const handleSendViaEmail = async (prospectId: string, overrides?: { subject?: string; body?: string; toEmail?: string }) => {
    const current = prospects.find(p => p.id === prospectId);
    const draft = current?.outreachDraft;
    try {
      const resp = await apiFetch(`/api/prospects/${prospectId}/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subject: overrides?.subject ?? draft?.subject,
          body: overrides?.body ?? draft?.body,
          toEmail: overrides?.toEmail ?? draft?.toEmail ?? current?.email ?? '',
        }),
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(text || 'Send failed');
      }
      const data = await resp.json();
      if (data.via === 'mailto' && data.mailto) {
        const params = new URLSearchParams();
        if (data.mailto.subject) params.set('subject', data.mailto.subject);
        if (data.mailto.body) params.set('body', data.mailto.body);
        const to = data.mailto.to || '';
        const href = to
          ? `mailto:${encodeURIComponent(to)}?${params.toString()}`
          : `mailto:?${params.toString()}`;
        window.open(href, '_blank');
      }
      if (data.prospect) {
        setProspects(prev => prev.map(p => (p.id === prospectId ? (data.prospect as Prospect) : p)));
      }
    } catch (err) {
      console.error(err);
      window.alert(err instanceof Error ? err.message : 'Send failed');
    }
  };

  const handleUpdateContactAgain = (prospectId: string, contactAgain: boolean) => {
    setProspects(prev =>
      prev.map(p => {
        if (p.id !== prospectId) return p;
        const stage = !contactAgain && (p.stage === 'To contact' || p.stage === 'Re-contact')
          ? 'Avoid'
          : contactAgain && p.stage === 'Avoid'
            ? 'Re-contact'
            : p.stage;
        const updated = { ...p, contactAgain, stage: stage as Prospect['stage'] };
        void persistProspect(updated);
        return updated;
      })
    );
  };

  const handlePrepareOutreach = async (prospectId?: string) => {
    try {
      if (prospectId) {
        const resp = await apiFetch(`/api/prospects/${prospectId}/prepare-outreach?force=true`, {
          method: 'POST',
        });
        if (!resp.ok) throw new Error(await resp.text());
        const row = (await resp.json()) as Prospect;
        setProspects(prev => prev.map(p => (p.id === row.id ? row : p)));
        return;
      }
      const resp = await apiFetch('/api/prospects/prepare-outreach-batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      const updated = (data.prospects || []) as Prospect[];
      if (updated.length) {
        const map = new Map(updated.map(p => [p.id, p]));
        setProspects(prev => prev.map(p => map.get(p.id) || p));
      }
      window.alert(`Prepared ${data.prepared || 0} outreach draft(s).`);
    } catch (err) {
      console.error(err);
      window.alert(err instanceof Error ? err.message : 'Prepare outreach failed');
    }
  };

  const handlePrepareFollowUp = async (prospectId: string) => {
    try {
      const resp = await apiFetch(`/api/prospects/${prospectId}/prepare-follow-up`, { method: 'POST' });
      if (!resp.ok) throw new Error(await resp.text());
      const row = (await resp.json()) as Prospect;
      setProspects(prev => prev.map(p => (p.id === row.id ? row : p)));
    } catch (err) {
      console.error(err);
      window.alert(err instanceof Error ? err.message : 'Follow-up draft failed');
    }
  };

  const handleRefreshContacts = async (prospectId: string) => {
    try {
      const resp = await apiFetch(`/api/prospects/${prospectId}/refresh-contacts`, { method: 'POST' });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      const row = data.prospect as Prospect;
      if (row?.id) {
        setProspects(prev => prev.map(p => (p.id === row.id ? row : p)));
      }
      if (!data.found) {
        window.alert('No public email found on that website (checked homepage + contact pages).');
      }
    } catch (err) {
      console.error(err);
      window.alert(err instanceof Error ? err.message : 'Could not refresh contacts');
    }
  };

  const handleSyncReplies = async () => {
    try {
      const resp = await apiFetch('/api/prospects/sync-replies', { method: 'POST' });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      const updated = (data.prospects || []) as Prospect[];
      if (updated.length) {
        const map = new Map(updated.map(p => [p.id, p]));
        setProspects(prev => prev.map(p => map.get(p.id) || p));
      }
      window.alert(`Synced ${data.synced || 0} reply(ies) from Gmail.`);
    } catch (err) {
      console.error(err);
      window.alert(err instanceof Error ? err.message : 'Reply sync failed — connect Gmail in Settings');
    }
  };

  const handleSkipOutreach = (_prospectId: string) => {
    // Inbox advances selection; draft stays for later.
  };

  const handleSaveReply = (prospectId: string, summary: string, contactAgain: boolean) => {
    const now = new Date().toISOString();
    setProspects(prev =>
      prev.map(p => {
        if (p.id !== prospectId) return p;
        const updated: Prospect = {
          ...p,
          replySummary: summary,
          lastReplyAt: now,
          contactAgain,
          stage: contactAgain ? 'Re-contact' : 'Denied',
          outreachDraft: p.outreachDraft
            ? { ...p.outreachDraft, status: 'Replied' }
            : p.outreachDraft,
          agentTimeline: [
            ...(p.agentTimeline || []),
            {
              time: now.slice(11, 16),
              action: contactAgain ? 'Reply logged — re-contact' : 'Reply logged — do not contact',
              details: summary.slice(0, 200),
            },
          ],
        };
        void persistProspect(updated);
        return updated;
      })
    );
  };

  const handleAddProspects = (list: Prospect[]) => {
    setProspects(prev => {
      const seen = new Set(prev.map(p => p.website || p.id));
      const extra = list.filter(p => !seen.has(p.website || p.id));
      return [...extra, ...prev];
    });
  };

  const handleUpdateStage = (prospectId: string, stage: Prospect['stage']) => {
    setProspects(prev =>
      prev.map(p => {
        if (p.id !== prospectId) return p;
        const updated = { ...p, stage };
        void persistProspect(updated);
        return updated;
      })
    );
  };

  const handleClearLeads = async () => {
    const resp = await apiFetch('/api/prospects/clear', { method: 'DELETE' });
    if (!resp.ok) {
      console.warn('Failed to clear leads', await resp.text());
      return;
    }
    setProspects([]);
    setSelectedProspectId(null);
  };

  const handleAddLog = (log: AgentRunLog) => {
    setAgentLogs(prev => [log, ...prev]);
  };

  const handleSaveBusiness = async (info: BusinessInfo) => {
    setBusinessInfo(info);
    const resp = await apiFetch('/api/onboarding/profile', {
      method: 'POST',
      body: JSON.stringify(info),
    });
    if (resp.ok) {
      const saved = await resp.json();
      if (saved?.id) setBusinessInfo(prev => ({ ...prev, ...saved }));
      await loadCompanies();
    }
  };

  const handleSaveProducts = async (next: Product[]) => {
    setProducts(next);
    await apiFetch('/api/products/save', {
      method: 'POST',
      body: JSON.stringify({ products: next }),
    });
  };

  const handleSaveICP = async (next: IdealCustomerProfile) => {
    setIcp(next);
    await apiFetch('/api/icp/save', {
      method: 'POST',
      body: JSON.stringify(next),
    });
  };

  const handleRestoredFromSheets = async (payload: {
    company?: BusinessInfo;
    products?: Product[];
    prospects?: Prospect[];
    activeBusinessId?: string;
  }) => {
    if (payload.activeBusinessId) {
      setActiveBusinessId(payload.activeBusinessId);
      setActiveCompanyIdState(payload.activeBusinessId);
      await apiFetch(`/api/companies/${payload.activeBusinessId}/activate`, { method: 'POST' });
    }
    await loadCompanies();
    await loadCompanyData();
    if (payload.company) {
      setBusinessInfo(prev => ({ ...prev, ...payload.company! }));
    }
    if (Array.isArray(payload.products)) {
      setProducts(payload.products);
    }
    if (Array.isArray(payload.prospects)) {
      setProspects(payload.prospects);
    }
    navigate('catalog');
  };

  const handleLogout = async () => {
    await apiFetch('/api/auth/logout', { method: 'POST' });
    setUser(null);
    setCompanies([]);
    setActiveCompanyIdState(null);
    setActiveBusinessId(null);
    setProspects(emptyProspects);
    setAgentLogs(emptyAgentLogs);
    setBusinessInfo(emptyBusinessInfo);
    setProducts(emptyProducts);
    setIcp(emptyICP);
    navigate('queue', true);
  };

  if (authLoading) {
    return (
      <div className="min-h-screen bg-canvas flex items-center justify-center text-ink-muted text-sm">
        Loading...
      </div>
    );
  }

  if (authConfigured && !user) {
    return <LoginView error={authError} />;
  }

  return (
    <div className="min-h-dvh bg-canvas text-ink flex flex-col md:flex-row">
      <header className="md:hidden sticky top-0 z-30 h-12 px-3 flex items-center justify-between gap-3 bg-surface/95 backdrop-blur border-b border-border">
        <button
          type="button"
          onClick={() => setMobileNavOpen(true)}
          className="p-2 -ml-1 rounded-md text-ink-secondary hover:bg-muted"
          aria-label="Open menu"
        >
          <Menu className="w-5 h-5" strokeWidth={1.75} />
        </button>
        <BrandLockup size="sm" className="absolute left-1/2 -translate-x-1/2 pointer-events-none" />
        <span className="w-9" aria-hidden />
      </header>

      <Sidebar
        activeTab={sidebarTabForRoute(activeRoute)}
        activeRoute={activeRoute}
        onTabChange={handleSidebarChange}
        pendingCount={pendingCount}
        draftCount={draftCount}
        companies={companies.length ? companies : [businessInfo]}
        activeCompanyId={activeCompanyId || businessInfo.id}
        onSwitchCompany={handleSwitchCompany}
        onAddCompany={handleAddCompany}
        user={user}
        onLogout={authConfigured ? handleLogout : undefined}
        mobileOpen={mobileNavOpen}
        onMobileClose={() => setMobileNavOpen(false)}
      />

      <main key={activeRoute} className="flex-1 min-w-0 px-4 py-5 sm:px-6 md:px-10 md:py-8 pb-20 md:pb-8">
        {activeRoute === 'queue' && (
          <QueueView
            prospects={prospects}
            agentLogs={agentLogs}
            onReviewProspect={id => setSelectedProspectId(id)}
            onUpdateStage={handleUpdateStage}
            onClearLeads={handleClearLeads}
            onPrepareOutreach={() => handlePrepareOutreach()}
          />
        )}
        {activeRoute === 'discover' && (
          <DiscoverView
            businessInfo={businessInfo}
            icp={icp}
            products={products}
            onAddProspects={handleAddProspects}
            onAddLog={handleAddLog}
            onRefreshProspects={async () => {
              const resp = await apiFetch('/api/prospects/');
              if (!resp.ok) return;
              const list = await resp.json();
              if (Array.isArray(list)) setProspects(list as Prospect[]);
            }}
          />
        )}
        {activeRoute === 'outreach' && (
          <OutreachInboxView
            prospects={prospects}
            onSendViaEmail={handleSendViaEmail}
            onSaveDraft={handleSaveDraft}
            onSkip={handleSkipOutreach}
            onSyncReplies={handleSyncReplies}
            onPrepareFollowUp={handlePrepareFollowUp}
            gmailConnected={Boolean(user?.gmail?.connected)}
          />
        )}
        {isSettingsRoute(activeRoute) && (
          <SettingsView
            section={activeRoute}
            onSectionChange={handleSettingsSectionChange}
            businessInfo={businessInfo}
            products={products}
            icp={icp}
            onSaveBusiness={handleSaveBusiness}
            onSaveProducts={handleSaveProducts}
            onSaveICP={handleSaveICP}
            onRestoredFromSheets={handleRestoredFromSheets}
          />
        )}
        {activeRoute === 'activity' && <ActivityView agentLogs={agentLogs} />}
      </main>

      <MobileNav
        activeTab={sidebarTabForRoute(activeRoute)}
        activeRoute={activeRoute}
        onTabChange={handleSidebarChange}
        pendingCount={pendingCount}
        draftCount={draftCount}
      />

      <ReviewDrawer
        prospect={selectedProspect}
        onClose={() => setSelectedProspectId(null)}
        onUpdateStatus={handleUpdateStatus}
        onSaveDraft={handleSaveDraft}
        onUpdateContactAgain={handleUpdateContactAgain}
        onSaveReply={handleSaveReply}
        onSendViaEmail={handleSendViaEmail}
        onPrepareOutreach={id => handlePrepareOutreach(id)}
        onPrepareFollowUp={handlePrepareFollowUp}
        onRefreshContacts={handleRefreshContacts}
        gmailConnected={Boolean(user?.gmail?.connected)}
      />
    </div>
  );
}
