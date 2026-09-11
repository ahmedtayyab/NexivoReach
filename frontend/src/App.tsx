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
import { recipientEmail } from './lib/leadTone';
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
import SettingsView from './components/SettingsView';
import OutreachInboxView from './components/OutreachInboxView';
import ReviewDrawer from './components/prospects/ReviewDrawer';
import ActivityView from './components/ActivityView';
import AdminView from './components/AdminView';
import SupportView from './components/SupportView';
import NotificationsRail, {
  NotificationHeaderButton,
  useNotificationUnread,
} from './components/NotificationBell';
import ToastHost, { type AppToast, type ToastKind } from './components/ToastHost';
import LoginView from './components/LoginView';
import SuspendedView from './components/SuspendedView';
import BrandLockup from './components/brand/BrandLockup';
import { Menu } from 'lucide-react';

const NOTIF_RAIL_KEY = 'nr-notif-rail-open';

export default function App() {
  const [authLoading, setAuthLoading] = useState(true);
  const [authConfigured, setAuthConfigured] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);

  const [activeRoute, setActiveRoute] = useState<AppRoute>('company');
  const [companies, setCompanies] = useState<BusinessInfo[]>([]);
  const [activeCompanyId, setActiveCompanyIdState] = useState<string | null>(null);
  const [businessInfo, setBusinessInfo] = useState<BusinessInfo>(emptyBusinessInfo);
  const [products, setProducts] = useState<Product[]>(emptyProducts);
  const [icp, setIcp] = useState<IdealCustomerProfile>(emptyICP);
  const [prospects, setProspects] = useState<Prospect[]>(emptyProspects);
  const [agentLogs, setAgentLogs] = useState<AgentRunLog[]>(emptyAgentLogs);
  const [selectedProspectId, setSelectedProspectId] = useState<string | null>(null);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [notifSheetOpen, setNotifSheetOpen] = useState(false);
  const [notifRailOpen, setNotifRailOpen] = useState(() => {
    try {
      const raw = localStorage.getItem(NOTIF_RAIL_KEY);
      if (raw === null) return true;
      return raw !== '0';
    } catch {
      return true;
    }
  });
  const [toasts, setToasts] = useState<AppToast[]>([]);
  const notifUnread = useNotificationUnread(user);

  const pushToast = useCallback((kind: ToastKind, title: string, body?: string) => {
    const id =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `toast-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setToasts(prev => [...prev.slice(-4), { id, kind, title, body }]);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const setNotifRailOpenPersist = useCallback((open: boolean) => {
    setNotifRailOpen(open);
    try {
      localStorage.setItem(NOTIF_RAIL_KEY, open ? '1' : '0');
    } catch {
      // ignore
    }
  }, []);

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
    } else if (params.get('auth') === 'invite') {
      setAuthError('Invite only — ask the operator to add your email before signing in.');
      window.history.replaceState({}, '', window.location.pathname + window.location.hash);
    } else if (params.get('auth') === 'suspended') {
      // SuspendedView renders once /me returns the suspended user session.
      window.history.replaceState({}, '', window.location.pathname + '#suspended');
    }

    (async () => {
      try {
        const resp = await apiFetch('/api/auth/me');
        if (!resp.ok) throw new Error('Auth check failed');
        const data = await resp.json();
        setAuthConfigured(Boolean(data.configured));
        setUser(data.user ?? null);
        if (data.user?.isSuspended || data.error === 'suspended') {
          // Don't bootstrap workspace data for suspended accounts.
        } else if (!data.configured || data.user) {
          await bootstrap();
        }
        if (data.user && !data.user.isSuspended) {
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
      activeRoute === 'outreach' ||
      activeRoute === 'activity' ||
      activeRoute === 'admin' ||
      activeRoute === 'support' ||
      activeRoute === 'notifications' ||
      isSettingsRoute(activeRoute);
    if (!valid) {
      navigate('company', true);
    }
    if (activeRoute === 'notifications') {
      setNotifSheetOpen(true);
      setNotifRailOpenPersist(true);
      navigate('company', true);
    }
    if (activeRoute === 'admin' && user && !user.isAdmin) {
      navigate('company', true);
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
          toEmail: overrides?.toEmail ?? recipientEmail(current),
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
        pushToast('info', 'Opened in your mail app', current?.companyName || 'Compose ready');
      } else {
        const to = recipientEmail(data.prospect as Prospect | undefined) || recipientEmail(current) || 'recipient';
        pushToast('sent', 'Message sent', `${current?.companyName || 'Lead'} · ${to}`);
      }
      if (data.prospect) {
        setProspects(prev => prev.map(p => (p.id === prospectId ? (data.prospect as Prospect) : p)));
      }
    } catch (err) {
      console.error(err);
      pushToast('error', 'Send failed', err instanceof Error ? err.message : 'Could not send email');
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
      pushToast('ok', 'Drafts prepared', `${data.prepared || 0} outreach draft(s) ready`);
    } catch (err) {
      console.error(err);
      pushToast('error', 'Prepare failed', err instanceof Error ? err.message : 'Could not prepare outreach');
    }
  };

  const handlePrepareFollowUp = async (prospectId: string) => {
    try {
      const resp = await apiFetch(`/api/prospects/${prospectId}/prepare-follow-up`, { method: 'POST' });
      if (!resp.ok) throw new Error(await resp.text());
      const row = (await resp.json()) as Prospect;
      setProspects(prev => prev.map(p => (p.id === row.id ? row : p)));
      pushToast('ok', 'Follow-up draft ready', row.companyName || 'Lead');
    } catch (err) {
      console.error(err);
      pushToast('error', 'Follow-up failed', err instanceof Error ? err.message : 'Could not prepare follow-up');
    }
  };

  const handleSendAllReady = async (mode: 'batch' | 'ready' = 'batch') => {
    if (!user?.gmail?.connected) {
      pushToast('info', 'Connect Gmail first', 'Workspace → Connect, then send in one click.');
      return;
    }
    const label = mode === 'ready'
      ? 'Resolve contact emails, prepare drafts if needed, then send best-fit via Gmail?'
      : 'Send best-fit outreach via Gmail (uses scraped contact emails)?';
    if (!window.confirm(label)) return;
    try {
      const path = mode === 'ready' ? '/api/prospects/send-ready' : '/api/prospects/send-batch';
      const resp = await apiFetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bestFitOnly: true, limit: 20 }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      const updated = (data.prospects || []) as Prospect[];
      if (updated.length) {
        const map = new Map(updated.map(p => [p.id, p]));
        setProspects(prev => prev.map(p => map.get(p.id) || p));
      }
      const failed = data.failed || 0;
      const sent = data.sent || 0;
      const extras = [
        data.prepared ? `Prepared ${data.prepared}` : '',
        data.resolvedEmails ? `Resolved ${data.resolvedEmails} email(s)` : '',
        data.skippedNoEmail ? `${data.skippedNoEmail} had no public email` : '',
        failed ? `${failed} failed` : '',
        data.errors?.[0]?.error ? `${data.errors[0].company}: ${data.errors[0].error}` : '',
      ].filter(Boolean).join(' · ');
      if (sent > 0) {
        pushToast('sent', `Sent ${sent} message${sent === 1 ? '' : 's'}`, extras || undefined);
      } else if (failed > 0) {
        pushToast('error', 'Nothing sent', extras || 'Check Gmail connection and drafts.');
      } else {
        pushToast('info', 'Nothing to send', extras || 'No ready drafts matched.');
      }
    } catch (err) {
      console.error(err);
      pushToast('error', 'Bulk send failed', err instanceof Error ? err.message : 'Could not send');
    }
  };

  const handleSendSelected = async (ids: string[]) => {
    if (!user?.gmail?.connected) {
      pushToast('info', 'Connect Gmail first', 'Workspace → Connect, then send selected emails.');
      return;
    }
    if (!ids.length) return;
    try {
      const resp = await apiFetch('/api/prospects/send-ready', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids, limit: ids.length }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      const updated = (data.prospects || []) as Prospect[];
      if (updated.length) {
        const map = new Map(updated.map(p => [p.id, p]));
        setProspects(prev => prev.map(p => map.get(p.id) || p));
      }
      const failed = data.failed || 0;
      const sent = data.sent || 0;
      const extras = [
        data.prepared ? `Prepared ${data.prepared}` : '',
        data.resolvedEmails ? `Resolved ${data.resolvedEmails} email(s)` : '',
        data.skippedNoEmail ? `${data.skippedNoEmail} had no public email` : '',
        failed ? `${failed} failed` : '',
        data.errors?.[0]?.error ? `${data.errors[0].company}: ${data.errors[0].error}` : '',
      ].filter(Boolean).join(' · ');
      if (sent > 0) {
        pushToast('sent', `Sent ${sent} message${sent === 1 ? '' : 's'}`, extras || undefined);
      } else if (failed > 0) {
        pushToast('error', 'Nothing sent', extras || 'Check recipients and drafts.');
      } else {
        pushToast('info', 'Nothing sent', extras || 'Selected leads were not ready.');
      }
    } catch (err) {
      console.error(err);
      pushToast('error', 'Send selected failed', err instanceof Error ? err.message : 'Could not send');
    }
  };

  const handleBackfillRecipients = async () => {
    try {
      const resp = await apiFetch('/api/prospects/backfill-recipients', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ limit: 25 }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      const updated = (data.prospects || []) as Prospect[];
      if (updated.length) {
        const map = new Map(updated.map(p => [p.id, p]));
        setProspects(prev => prev.map(p => map.get(p.id) || p));
      }
    } catch (err) {
      console.error(err);
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
      const synced = data.synced || 0;
      if (synced > 0) {
        const names = updated
          .slice(0, 3)
          .map(p => p.companyName)
          .filter(Boolean)
          .join(', ');
        pushToast(
          'received',
          synced === 1 ? 'Reply received' : `${synced} replies received`,
          names || 'Synced from Gmail',
        );
      } else {
        pushToast('info', 'No new replies', 'Inbox checked — nothing new yet.');
      }
    } catch (err) {
      console.error(err);
      pushToast(
        'error',
        'Reply sync failed',
        err instanceof Error ? err.message : 'Connect Gmail in Workspace → Connect',
      );
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
    pushToast(
      'received',
      'Reply logged',
      contactAgain ? 'Marked for re-contact' : 'Marked do not contact',
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

  const handleRemoveProspect = async (prospectId: string) => {
    const resp = await apiFetch(`/api/prospects/${prospectId}`, { method: 'DELETE' });
    if (!resp.ok) {
      console.warn('Failed to remove lead', await resp.text());
      return;
    }
    setProspects(prev => prev.filter(p => p.id !== prospectId));
    setSelectedProspectId(prev => (prev === prospectId ? null : prev));
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

  if (user?.isSuspended) {
    return (
      <SuspendedView
        user={user}
        onLogout={() => void handleLogout()}
      />
    );
  }

  return (
    <div className="app-shell text-ink flex flex-col md:flex-row">
      <header className="md:hidden sticky top-0 z-30 h-12 px-3 flex items-center justify-between gap-3 bg-surface border-b border-border">
        <button
          type="button"
          onClick={() => setMobileNavOpen(true)}
          className="p-2 -ml-1 text-ink-secondary hover:bg-muted"
          aria-label="Open menu"
        >
          <Menu className="w-5 h-5" strokeWidth={1.75} />
        </button>
        <BrandLockup size="sm" className="absolute left-1/2 -translate-x-1/2 pointer-events-none" />
        <NotificationHeaderButton unread={notifUnread} onClick={() => setNotifSheetOpen(true)} />
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

      <main
        key={isSettingsRoute(activeRoute) ? 'workspace' : activeRoute}
        className="app-main flex-1 min-w-0 px-4 py-5 sm:px-6 md:px-8 md:py-8 pb-20 md:pb-8"
      >
        {activeRoute === 'queue' && (
          <QueueView
            prospects={prospects}
            agentLogs={agentLogs}
            onReviewProspect={id => setSelectedProspectId(id)}
            onUpdateStage={handleUpdateStage}
            onClearLeads={handleClearLeads}
            onPrepareOutreach={() => handlePrepareOutreach()}
            onSendAllReady={() => handleSendAllReady('ready')}
            onSendSelected={handleSendSelected}
            gmailConnected={Boolean(user?.gmail?.connected)}
            onGoWorkspace={() => navigate('company')}
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
            onSendAllReady={() => handleSendAllReady('batch')}
            onPrepareAndSend={() => handleSendAllReady('ready')}
            onBackfillRecipients={handleBackfillRecipients}
            onRemoveProspect={handleRemoveProspect}
            onClearAll={handleClearLeads}
            onSendSelected={handleSendSelected}
            gmailConnected={Boolean(user?.gmail?.connected)}
            onGoWorkspace={() => navigate('company')}
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
            onAddProspects={handleAddProspects}
            onAddLog={handleAddLog}
            onFindBuyersComplete={(n) => {
              if (n > 0) navigate('queue');
            }}
            onRestoredFromSheets={handleRestoredFromSheets}
          />
        )}
        {activeRoute === 'activity' && <ActivityView agentLogs={agentLogs} />}
        {activeRoute === 'admin' && user?.isAdmin && <AdminView />}
        {activeRoute === 'support' && <SupportView />}
      </main>

      <NotificationsRail
        user={user}
        mobileOpen={notifSheetOpen}
        onMobileOpenChange={setNotifSheetOpen}
        desktopOpen={notifRailOpen}
        onDesktopOpenChange={setNotifRailOpenPersist}
        onNavigate={route => {
          navigate(normalizeRoute(route));
          setNotifSheetOpen(false);
        }}
      />

      <ToastHost toasts={toasts} onDismiss={dismissToast} />

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
        gmailConnected={Boolean(user?.gmail?.connected)}
      />
    </div>
  );
}
