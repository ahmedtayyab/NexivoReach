import { useState } from 'react';
import type { BusinessInfo, Product, IdealCustomerProfile, Prospect, AgentRunLog } from './types';

import { initialBusinessInfo, initialProducts, initialICP, initialProspects, initialAgentLogs } from './data/mockData';

import Sidebar from './components/layout/Sidebar';
import QueueView from './components/QueueView';
import DiscoverView from './components/DiscoverView';
import SettingsView from './components/SettingsView';
import ReviewDrawer from './components/prospects/ReviewDrawer';
import ActivityView from './components/ActivityView';

type TabId = 'queue' | 'discover' | 'catalog' | 'settings' | 'activity';

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>('queue');

  // Core state
  const [businessInfo, setBusinessInfo] = useState<BusinessInfo>(initialBusinessInfo);
  const [products, setProducts] = useState<Product[]>(initialProducts);
  const [icp, setIcp] = useState<IdealCustomerProfile>(initialICP);
  const [prospects, setProspects] = useState<Prospect[]>(initialProspects);
  const [agentLogs, setAgentLogs] = useState<AgentRunLog[]>(initialAgentLogs);

  // Drawer state
  const [selectedProspectId, setSelectedProspectId] = useState<string | null>(null);

  const selectedProspect = prospects.find(p => p.id === selectedProspectId) ?? null;

  const pendingCount = prospects.filter(
    p => !p.outreachDraft || p.outreachDraft.status === 'Draft'
  ).length;

  const handleUpdateStatus = (
    prospectId: string,
    status: NonNullable<Prospect['outreachDraft']>['status']
  ) => {
    setProspects(prev =>
      prev.map(p => {
        if (p.id !== prospectId || !p.outreachDraft) return p;
        return {
          ...p,
          stage: status === 'Approved' ? 'Qualified' : status === 'Sent' ? 'Contacted' : p.stage,
          outreachDraft: { ...p.outreachDraft, status },
        };
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

  const handleTabChange = (tab: string) => {
    setActiveTab(tab as TabId);
  };

  return (
    <div className="min-h-screen bg-[#F8FAFC] text-slate-900 flex">
      <Sidebar
        activeTab={activeTab}
        onTabChange={handleTabChange}
        pendingCount={pendingCount}
      />

      <main className="flex-1 min-w-0 px-10 py-8">
        {activeTab === 'queue' && (
          <QueueView
            prospects={prospects}
            agentLogs={agentLogs}
            onReviewProspect={id => setSelectedProspectId(id)}
          />
        )}
        {activeTab === 'discover' && (
          <DiscoverView
            businessInfo={businessInfo}
            icp={icp}
            onAddProspect={handleAddProspect}
            onAddLog={handleAddLog}
          />
        )}
        {(activeTab === 'catalog' || activeTab === 'settings') && (
          <SettingsView
            businessInfo={businessInfo}
            products={products}
            icp={icp}
            onSaveBusiness={setBusinessInfo}
            onSaveProducts={setProducts}
            onSaveICP={setIcp}
          />
        )}
        {activeTab === 'activity' && <ActivityView agentLogs={agentLogs} />}
      </main>

      {/* Global Prospect Review Drawer */}
      <ReviewDrawer
        prospect={selectedProspect}
        onClose={() => setSelectedProspectId(null)}
        onUpdateStatus={handleUpdateStatus}
      />
    </div>
  );
}
