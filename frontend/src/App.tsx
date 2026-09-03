import { useState, useEffect } from 'react';
import type { BusinessInfo, Product, IdealCustomerProfile, Prospect, AgentRunLog, AuthUser } from './types';
import {
  emptyBusinessInfo,
  emptyProducts,
  emptyICP,
  emptyProspects,
  emptyAgentLogs,
} from './data/defaults';
import { apiFetch } from './lib/api';
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
import QueueView from './components/QueueView';
import DiscoverView from './components/DiscoverView';
import SettingsView from './components/SettingsView';
import ReviewDrawer from './components/prospects/ReviewDrawer';
import ActivityView from './components/ActivityView';
import LoginView from './components/LoginView';

export default function App() {
  const [authLoading, setAuthLoading] = useState(true);
  const [authConfigured, setAuthConfigured] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);

  const [activeRoute, setActiveRoute] = useState<AppRoute>('queue');
  const [businessInfo, setBusinessInfo] = useState<BusinessInfo>(emptyBusinessInfo);
  const [products, setProducts] = useState<Product[]>(emptyProducts);
  const [icp, setIcp] = useState<IdealCustomerProfile>(emptyICP);
  const [prospects, setProspects] = useState<Prospect[]>(emptyProspects);
  const [agentLogs, setAgentLogs] = useState<AgentRunLog[]>(emptyAgentLogs);
  const [selectedProspectId, setSelectedProspectId] = useState<string | null>(null);

  const selectedProspect = prospects.find(p => p.id === selectedProspectId) ?? null;

  const pendingCount = prospects.filter(
    p => !p.outreachDraft || p.outreachDraft.status === 'Draft'
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

  const loadWorkspace = async () => {
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
    }
    if (logsResp.ok) {
      const logs = await logsResp.json();
      if (Array.isArray(logs)) setAgentLogs(logs as AgentRunLog[]);
    }
    if (profileResp.ok) {
      setBusinessInfo(parseProfileResponse(await profileResp.json()));
    }
    if (productsResp.ok) {
      const catalog = await productsResp.json();
      if (Array.isArray(catalog)) setProducts(catalog as Product[]);
    }
    if (icpResp.ok) {
      setIcp(parseIcpResponse(await icpResp.json()));
    }
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('auth') === 'error') {
      setAuthError('Sign-in failed. Check your Google OAuth settings and try again.');
      window.history.replaceState({}, '', window.location.pathname);
    }

    (async () => {
      try {
        const resp = await apiFetch('/api/auth/me');
        if (!resp.ok) throw new Error('Auth check failed');
        const data = await resp.json();
        setAuthConfigured(Boolean(data.configured));
        setUser(data.user ?? null);
        if (!data.configured || data.user) {
          await loadWorkspace();
        }
        if (data.user) {
          const initialRoute = resolveRouteFromLocation();
          setActiveRoute(initialRoute);
          window.history.replaceState({ route: initialRoute }, '', `#${initialRoute}`);
        }
      } catch {
        setAuthConfigured(false);
        setUser(null);
      } finally {
        setAuthLoading(false);
      }
    })();
  }, []);

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
      activeRoute === 'activity' ||
      isSettingsRoute(activeRoute);
    if (!valid) {
      navigate('queue', true);
    }
  }, [activeRoute, authLoading, user]);

  const handleSidebarChange = (tab: string) => {
    navigate(routeFromSidebarTab(tab));
  };

  const handleSettingsSectionChange = (section: SettingsSection) => {
    navigate(section);
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
        const updated = {
          ...p,
          stage: status === 'Approved' ? 'Qualified' : status === 'Sent' ? 'Contacted' : p.stage,
          outreachDraft: { ...p.outreachDraft, status },
        };
        void persistProspect(updated);
        return updated;
      })
    );
  };

  const handleSaveDraft = (prospectId: string, subject: string, body: string) => {
    setProspects(prev =>
      prev.map(p => {
        if (p.id !== prospectId || !p.outreachDraft) return p;
        const updated = {
          ...p,
          outreachDraft: { ...p.outreachDraft, subject, body },
        };
        void persistProspect(updated);
        return updated;
      })
    );
  };

  const handleAddProspect = (p: Prospect) => {
    setProspects(prev => [p, ...prev]);
    setSelectedProspectId(p.id);
  };

  const handleAddLog = (log: AgentRunLog) => {
    setAgentLogs(prev => [log, ...prev]);
  };

  const handleSaveBusiness = (info: BusinessInfo) => {
    setBusinessInfo(info);
    void apiFetch('/api/onboarding/profile', {
      method: 'POST',
      body: JSON.stringify(info),
    });
  };

  const handleSaveProducts = (next: Product[]) => {
    setProducts(next);
    void apiFetch('/api/products/save', {
      method: 'POST',
      body: JSON.stringify({ products: next }),
    });
  };

  const handleSaveICP = (next: IdealCustomerProfile) => {
    setIcp(next);
    void apiFetch('/api/icp/save', {
      method: 'POST',
      body: JSON.stringify(next),
    });
  };

  const handleLogout = async () => {
    await apiFetch('/api/auth/logout', { method: 'POST' });
    setUser(null);
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
    <div className="min-h-screen bg-canvas text-ink flex">
      <Sidebar
        activeTab={sidebarTabForRoute(activeRoute)}
        activeRoute={activeRoute}
        onTabChange={handleSidebarChange}
        pendingCount={pendingCount}
        workspaceName={businessInfo.name || 'Workspace'}
        user={user}
        onLogout={authConfigured ? handleLogout : undefined}
      />

      <main className="flex-1 min-w-0 px-10 py-8">
        {activeRoute === 'queue' && (
          <QueueView
            prospects={prospects}
            agentLogs={agentLogs}
            onReviewProspect={id => setSelectedProspectId(id)}
          />
        )}
        {activeRoute === 'discover' && (
          <DiscoverView
            businessInfo={businessInfo}
            icp={icp}
            onAddProspect={handleAddProspect}
            onAddLog={handleAddLog}
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
          />
        )}
        {activeRoute === 'activity' && <ActivityView agentLogs={agentLogs} />}
      </main>

      <ReviewDrawer
        prospect={selectedProspect}
        onClose={() => setSelectedProspectId(null)}
        onUpdateStatus={handleUpdateStatus}
        onSaveDraft={handleSaveDraft}
      />
    </div>
  );
}
