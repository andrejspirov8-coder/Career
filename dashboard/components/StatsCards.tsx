'use client';

import { ScoutData } from '@/lib/types';
import { BarChart3, Users, TrendingUp, Zap } from 'lucide-react';

interface StatsCardsProps {
  scoutData: ScoutData | null;
}

export default function StatsCards({ scoutData }: StatsCardsProps) {
  const stats = [
    {
      label: 'Total Profiles',
      value: scoutData?.total_profiles || 0,
      icon: Users,
      color: 'blue',
    },
    {
      label: 'Tier 1 (High)',
      value: scoutData?.tier_1_count || 0,
      icon: Zap,
      color: 'emerald',
    },
    {
      label: 'Tier 2 (Medium)',
      value: scoutData?.tier_2_count || 0,
      icon: TrendingUp,
      color: 'amber',
    },
    {
      label: 'Tier 3 (Low)',
      value: scoutData?.tier_3_count || 0,
      icon: BarChart3,
      color: 'slate',
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      {stats.map((stat) => {
        const Icon = stat.icon;
        const colorClasses = {
          blue: 'bg-blue-900/20 border-blue-800 text-blue-400',
          emerald: 'bg-emerald-900/20 border-emerald-800 text-emerald-400',
          amber: 'bg-amber-900/20 border-amber-800 text-amber-400',
          slate: 'bg-slate-800/20 border-slate-700 text-slate-400',
        };

        return (
          <div
            key={stat.label}
            className={`border rounded-lg p-6 ${colorClasses[stat.color as keyof typeof colorClasses]}`}
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-400">{stat.label}</p>
                <p className="text-4xl font-bold mt-2">{stat.value}</p>
              </div>
              <Icon className="w-12 h-12 opacity-20" />
            </div>
          </div>
        );
      })}
    </div>
  );
}
