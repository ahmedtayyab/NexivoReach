import { useState } from 'react';

import { initialBusinessInfo, initialProducts, initialICP, initialProspects, initialAgentLogs } from './data/mockData';
import type { BusinessInfo, Product, IdealCustomerProfile, Prospect, AgentRunLog } from './types';

// Layout & Views
import AppLayout from './components/layout/AppLayout';
import DashboardView from './components/DashboardView';
import ProspectsView from './components/ProspectsView';
import OutreachView from './components/OutreachView';
import OnboardingView from './components/OnboardingView';
import CatalogView from './components/CatalogView';
import ICPView from './components/ICPView';
import DiscoveryView from './components/DiscoveryView';
import ActivityView from './components/ActivityView';
import ProspectDrawer from './components/prospects/ProspectDrawer';

export default function App() {
  const [activeTab, setActiveTab] = useState<string>('dashboard');
  
  // App State
  const [businessInfo, setBusinessInfo] = useState<BusinessInfo>(initialBusinessInfo);
  const [products, setProducts] = useState<Product[]>(initialProducts);
  const [icp, setIcp] = useState<IdealCustomerProfile>(initialICP);
  const [prospects, setProspects] = useState<Prospect[]>(initialProspects);
  const [agentLogs, setAgentLogs] = useState<AgentRunLog[]>(initialAgentLogs);
  
  // Slide-Over Drawer State
  const [selectedProspectId, setSelectedProspectId] = useState<string | null>(null);

  const handleSelectProspect = (id: string) => {
    setSelectedProspectId(id);
  };

  const handleCloseDrawer = () => {
    setSelectedProspectId(null);
  };

  const handleAddProspect = (newProspect: Prospect) => {
    setProspects(prev => [newProspect, ...prev]);
    setSelectedProspectId(newProspect.id);
  };

  const handleAddAgentLog = (newLog: AgentRunLog) => {
    setAgentLogs(prev => [newLog, ...prev]);
  };

  const handleUpdateProspectStatus = (prospectId: string, status: NonNullable<Prospect['outreachDraft']>['status']) => {
    setProspects(prev => prev.map(p => {
      if (p.id === prospectId && p.outreachDraft) {
        return {
          ...p,
          stage: status === 'Approved' ? 'Qualified' : status === 'Sent' ? 'Contacted' : p.stage,
          outreachDraft: {
            ...p.outreachDraft,
            status
          }
        };
      }
      return p;
    }));
  };

  const selectedProspect = prospects.find(p => p.id === selectedProspectId) || null;
  const pendingApprovalsCount = prospects.filter(p => p.outreachDraft && p.outreachDraft.status === 'Draft').length;

  return (
    <AppLayout
      activeTab={activeTab}
      onTabChange={setActiveTab}
      productsCount={products.length}
      prospectsCount={prospects.length}
      pendingApprovalsCount={pendingApprovalsCount}
      businessName={businessInfo.name}
      onOpenDiscovery={() => setActiveTab('discovery')}
    >
      {activeTab === 'dashboard' && (
        <DashboardView 
          prospects={prospects} 
          products={products} 
          agentLogs={agentLogs}
          onSelectProspect={handleSelectProspect}
          onNavigate={setActiveTab}
          onUpdateStatus={handleUpdateProspectStatus}
        />
      )}

      {activeTab === 'prospects' && (
        <ProspectsView 
          prospects={prospects}
          selectedProspectId={selectedProspectId || ''}
          onSelectProspect={handleSelectProspect}
          onUpdateStatus={handleUpdateProspectStatus}
          onNavigateToDiscovery={() => setActiveTab('discovery')}
        />
      )}

      {activeTab === 'outreach' && (
        <OutreachView 
          prospects={prospects}
          onUpdateStatus={handleUpdateProspectStatus}
          onSelectProspect={handleSelectProspect}
        />
      )}

      {activeTab === 'onboarding' && (
        <OnboardingView 
          businessInfo={businessInfo} 
          onSave={(info) => setBusinessInfo(info)}
          onNext={() => setActiveTab('catalog')}
        />
      )}

      {activeTab === 'catalog' && (
        <CatalogView 
          products={products} 
          onSaveProducts={(prods) => setProducts(prods)}
          onNext={() => setActiveTab('icp')}
        />
      )}

      {activeTab === 'icp' && (
        <ICPView 
          icp={icp} 
          onSaveICP={(updated) => setIcp(updated)}
          onNext={() => setActiveTab('discovery')}
        />
      )}

      {activeTab === 'discovery' && (
        <DiscoveryView 
          businessInfo={businessInfo}
          products={products}
          icp={icp}
          onAddProspect={handleAddProspect}
          onAddLog={handleAddAgentLog}
          onViewProspect={(id) => handleSelectProspect(id)}
        />
      )}

      {activeTab === 'activity' && (
        <ActivityView agentLogs={agentLogs} />
      )}

      {/* Global Slide-Over Prospect Drawer */}
      <ProspectDrawer
        prospect={selectedProspect}
        onClose={handleCloseDrawer}
        onUpdateStatus={handleUpdateProspectStatus}
      />
    </AppLayout>
  );
}
