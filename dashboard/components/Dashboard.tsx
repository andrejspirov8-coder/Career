'use client';

import { useStore } from '@/lib/store';
import StatsCards from './StatsCards';
import ProfilesTable from './ProfilesTable';
import AnalyticsCharts from './AnalyticsCharts';
import DispatchQueue from './DispatchQueue';
import Navigation from './Navigation';
import { useState } from 'react';

type Tab = 'overview' | 'profiles' | 'analytics' | 'dispatch';

interface DashboardProps {
  loading?: boolean;
}

export default function Dashboard({ loading: initialLoading }: DashboardProps) {
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const { scoutData, analytics, loading } = useStore();

  const isLoading = initialLoading || loading;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
      {/* Header */}
      <header className="sticky top-0 z-40 border-b border-slate-800 bg-slate-950/80 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">
                Career Dashboard
              </h1>
              <p className="text-slate-400 text-sm mt-1">MCP-Integrated Recruiter Automation</p>
            </div>
            {isLoading && (
              <div className="flex items-center gap-2">
                <div className="animate-spin">⚙️</div>
                <span className="text-sm text-slate-400">Loading...</span>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Navigation */}
      <Navigation activeTab={activeTab} onChange={setActiveTab} />

      {/* Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === 'overview' && (
          <div className="space-y-8">
            <StatsCards scoutData={scoutData} />
            <AnalyticsCharts analytics={analytics} />
          </div>
        )}

        {activeTab === 'profiles' && (
          <ProfilesTable profiles={scoutData?.profiles || []} />
        )}

        {activeTab === 'analytics' && (
          <AnalyticsCharts analytics={analytics} fullPage />
        )}

        {activeTab === 'dispatch' && (
          <DispatchQueue profiles={scoutData?.profiles || []} />
        )}
      </main>
    </div>
  );
}
