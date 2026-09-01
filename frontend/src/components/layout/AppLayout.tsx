import React from 'react';
import Sidebar from './Sidebar';
import TopHeader from './TopHeader';

interface Props {
  activeTab: string;
  onTabChange: (tab: string) => void;
  productsCount: number;
  prospectsCount: number;
  pendingApprovalsCount: number;
  businessName: string;
  onOpenDiscovery: () => void;
  children: React.ReactNode;
}

export default function AppLayout({
  activeTab,
  onTabChange,
  productsCount,
  prospectsCount,
  pendingApprovalsCount,
  businessName,
  onOpenDiscovery,
  children
}: Props) {
  return (
    <div className="min-h-screen bg-[#0f172a] text-slate-100 flex font-sans">
      {/* Left Vertical Sidebar */}
      <Sidebar
        activeTab={activeTab}
        onTabChange={onTabChange}
        productsCount={productsCount}
        prospectsCount={prospectsCount}
        pendingApprovalsCount={pendingApprovalsCount}
      />

      {/* Main Content Body */}
      <div className="flex-1 flex flex-col min-w-0">
        <TopHeader
          businessName={businessName}
          onOpenDiscovery={onOpenDiscovery}
        />

        <main className="flex-1 p-6 max-w-7xl w-full mx-auto space-y-6">
          {children}
        </main>
      </div>
    </div>
  );
}
