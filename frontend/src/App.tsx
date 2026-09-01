import { useState } from 'react';
import { 
  Building2, 
  Package, 
  Target, 
  Bot, 
  Users, 
  Send, 
  Activity, 
  LayoutDashboard,
  ShieldCheck
} from 'lucide-react';

import { initialBusinessInfo, initialProducts, initialICP, initialProspects, initialAgentLogs } from './data/mockData';
import type { BusinessInfo, Product, IdealCustomerProfile, Prospect, AgentRunLog } from './types';

// View components
import OnboardingView from './components/OnboardingView';
import CatalogView from './components/CatalogView';
import ICPView from './components/ICPView';
import DiscoveryView from './components/DiscoveryView';
import ProspectsView from './components/ProspectsView';
import OutreachView from './components/OutreachView';
import ActivityView from './components/ActivityView';
import DashboardView from './components/DashboardView';

export default function App() {
  const [activeTab, setActiveTab] = useState<string>('dashboard');
  
  // App state
  const [businessInfo, setBusinessInfo] = useState<BusinessInfo>(initialBusinessInfo);
  const [products, setProducts] = useState<Product[]>(initialProducts);
  const [icp, setIcp] = useState<IdealCustomerProfile>(initialICP);
  const [prospects, setProspects] = useState<Prospect[]>(initialProspects);
  const [agentLogs, setAgentLogs] = useState<AgentRunLog[]>(initialAgentLogs);
  const [selectedProspectId, setSelectedProspectId] = useState<string>('prospect-1');

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'onboarding', label: '1. Business', icon: Building2 },
    { id: 'catalog', label: '2. Product Catalog', icon: Package, badge: products.length },
    { id: 'icp', label: '3. ICP & Signals', icon: Target },
    { id: 'discovery', label: '4. Discovery Agent', icon: Bot, highlight: true },
    { id: 'prospects', label: '5. Prospects', icon: Users, badge: prospects.length },
    { id: 'outreach', label: '6. Outreach', icon: Send, badge: prospects.filter(p => p.outreachDraft && p.outreachDraft.status === 'Draft').length },
    { id: 'activity', label: '7. Activity Log', icon: Activity },
  ];

  const handleSelectProspect = (id: string) => {
    setSelectedProspectId(id);
    setActiveTab('prospects');
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

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-100 flex flex-col font-sans">
      {/* Top Header Bar */}
      <header className="border-b border-slate-800 bg-[#0c1220]/90 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-blue-600 via-indigo-600 to-emerald-500 flex items-center justify-center shadow-lg shadow-blue-500/20">
              <Bot className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-lg tracking-tight text-white">NexivoReach</span>
                <span className="text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
                  AI Sales Agent
                </span>
              </div>
              <p className="text-xs text-slate-400">Turn products into prospects</p>
            </div>
          </div>

          {/* Active Business Banner */}
          <div className="hidden md:flex items-center space-x-4 bg-slate-900/80 border border-slate-800 rounded-lg px-3 py-1.5 text-xs">
            <div className="flex items-center space-x-2">
              <Building2 className="w-4 h-4 text-emerald-400" />
              <div>
                <span className="text-slate-400">Active Business:</span>{' '}
                <span className="font-semibold text-slate-200">{businessInfo.name}</span>
              </div>
            </div>
            <div className="h-4 w-px bg-slate-800" />
            <div className="flex items-center space-x-1.5 text-slate-400">
              <Package className="w-3.5 h-3.5 text-indigo-400" />
              <span>{products.length} Products</span>
            </div>
            <div className="h-4 w-px bg-slate-800" />
            <div className="flex items-center space-x-1 text-emerald-400 font-medium">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Gemini Agent Active</span>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 border-t border-slate-800/60 overflow-x-auto scrollbar-none">
          <nav className="flex space-x-1 py-2">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id)}
                  className={`flex items-center space-x-2 px-3 py-2 rounded-md text-xs font-medium transition-all whitespace-nowrap ${
                    isActive
                      ? 'bg-blue-600/15 text-blue-400 border border-blue-500/30 shadow-sm'
                      : item.highlight
                      ? 'text-indigo-300 hover:bg-slate-800/80 border border-indigo-500/20'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 border border-transparent'
                  }`}
                >
                  <Icon className={`w-4 h-4 ${isActive ? 'text-blue-400' : 'text-slate-400'}`} />
                  <span>{item.label}</span>
                  {item.badge !== undefined && (
                    <span className={`ml-1 px-1.5 py-0.2 rounded-full text-[10px] font-bold ${
                      isActive ? 'bg-blue-500 text-white' : 'bg-slate-800 text-slate-400'
                    }`}>
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {activeTab === 'dashboard' && (
          <DashboardView 
            prospects={prospects} 
            products={products} 
            agentLogs={agentLogs}
            onSelectProspect={handleSelectProspect}
            onNavigate={(tab) => setActiveTab(tab)}
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
        {activeTab === 'prospects' && (
          <ProspectsView 
            prospects={prospects}
            selectedProspectId={selectedProspectId}
            onSelectProspect={setSelectedProspectId}
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
        {activeTab === 'activity' && (
          <ActivityView agentLogs={agentLogs} />
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 py-4 bg-[#070a12] text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <div>
            <span className="font-semibold text-slate-400">NexivoReach v1.0</span> — Turn products into prospects through multi-step AI agents.
          </div>
          <div className="flex items-center space-x-4 text-slate-400">
            <span>Primary AI: <strong className="text-emerald-400 font-normal">Gemini 1.5 Pro</strong></span>
            <span>Secondary: <strong className="text-slate-300 font-normal">Groq Llama-3</strong></span>
            <span>Human Approval: <strong className="text-blue-400 font-normal">Required</strong></span>
          </div>
        </div>
      </footer>
    </div>
  );
}
