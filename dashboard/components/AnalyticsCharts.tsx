'use client';

import { Analytics } from '@/lib/types';
import { PieChart, Pie, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell } from 'recharts';

interface AnalyticsChartsProps {
  analytics: Analytics | null;
  fullPage?: boolean;
}

const COLORS = ['#10b981', '#f59e0b', '#f97316', '#64748b'];
const TIER_COLORS = { tier_1: '#10b981', tier_2: '#f59e0b', tier_3: '#f97316' };

export default function AnalyticsCharts({ analytics, fullPage }: AnalyticsChartsProps) {
  if (!analytics) {
    return (
      <div className="text-center py-12 text-slate-400">
        <p>No analytics data available yet.</p>
      </div>
    );
  }

  const scoreData = Object.entries(analytics.score_distribution).map(([range, count]) => ({
    name: range,
    value: count,
  }));

  const tierData = analytics.tier_stats.map((stat) => ({
    name: stat.tier.replace('tier_', 'Tier '),
    Sent: stat.sent,
    'Avg Score': stat.avg_score,
  }));

  return (
    <div className={`space-y-8 ${fullPage ? '' : ''}`}>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Score Distribution */}
        <div className="border border-slate-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">Score Distribution</h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={scoreData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, value }) => `${name}: ${value}`}
                outerRadius={100}
                fill="#8884d8"
                dataKey="value"
              >
                {COLORS.map((color, idx) => (
                  <Cell key={idx} fill={color} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Tier Statistics */}
        <div className="border border-slate-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">Profiles by Tier</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={tierData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="name" stroke="#94a3b8" />
              <YAxis stroke="#94a3b8" />
              <Tooltip
                contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569' }}
                labelStyle={{ color: '#e2e8f0' }}
              />
              <Legend />
              <Bar dataKey="Sent" fill="#3b82f6" />
              <Bar dataKey="Avg Score" fill="#10b981" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="border border-slate-800 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">Summary Statistics</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-slate-800/50 rounded p-4">
            <p className="text-slate-400 text-sm">Total Sent</p>
            <p className="text-2xl font-bold mt-1">{analytics.total_sent}</p>
          </div>
          <div className="bg-slate-800/50 rounded p-4">
            <p className="text-slate-400 text-sm">Total Responses</p>
            <p className="text-2xl font-bold mt-1">{analytics.total_responses}</p>
          </div>
          <div className="bg-slate-800/50 rounded p-4">
            <p className="text-slate-400 text-sm">Response Rate</p>
            <p className="text-2xl font-bold mt-1">{analytics.overall_response_rate.toFixed(1)}%</p>
          </div>
          <div className="bg-slate-800/50 rounded p-4">
            <p className="text-slate-400 text-sm">Profiles Analyzed</p>
            <p className="text-2xl font-bold mt-1">{analytics.rows_analyzed}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
