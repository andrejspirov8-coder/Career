'use client';

import { BarChart3, Users, TrendingUp, Send } from 'lucide-react';

type Tab = 'overview' | 'profiles' | 'analytics' | 'dispatch';

interface NavigationProps {
  activeTab: Tab;
  onChange: (tab: Tab) => void;
}

export default function Navigation({ activeTab, onChange }: NavigationProps) {
  const tabs: { id: Tab; label: string; icon: typeof BarChart3 }[] = [
    { id: 'overview', label: 'Overview', icon: BarChart3 },
    { id: 'profiles', label: 'Profiles', icon: Users },
    { id: 'analytics', label: 'Analytics', icon: TrendingUp },
    { id: 'dispatch', label: 'Dispatch', icon: Send },
  ];

  return (
    <div className="border-b border-slate-800 bg-slate-900/50 backdrop-blur">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <nav className="flex gap-8" aria-label="Main navigation">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => onChange(tab.id)}
                className={`flex items-center gap-2 px-4 py-4 border-b-2 font-medium transition-colors ${
                  isActive
                    ? 'border-blue-500 text-blue-400'
                    : 'border-transparent text-slate-400 hover:text-slate-300'
                }`}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
