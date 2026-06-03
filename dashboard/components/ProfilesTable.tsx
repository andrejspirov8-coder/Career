'use client';

import { Profile } from '@/lib/types';
import { useState } from 'react';
import { ChevronUp, ChevronDown } from 'lucide-react';

interface ProfilesTableProps {
  profiles: Profile[];
}

type SortField = 'name' | 'company' | 'primary_score' | 'tier_candidate';

export default function ProfilesTable({ profiles }: ProfilesTableProps) {
  const [sortField, setSortField] = useState<SortField>('primary_score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const sorted = [...profiles].sort((a, b) => {
    const aVal = a[sortField];
    const bVal = b[sortField];
    const cmp = aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
    return sortDir === 'asc' ? cmp : -cmp;
  });

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <span className="opacity-20">⇅</span>;
    return sortDir === 'asc' ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />;
  };

  const getTierColor = (tier: string) => {
    switch (tier) {
      case 'tier_1':
        return 'bg-emerald-900/30 text-emerald-300 border-emerald-700';
      case 'tier_2':
        return 'bg-amber-900/30 text-amber-300 border-amber-700';
      case 'tier_3':
        return 'bg-orange-900/30 text-orange-300 border-orange-700';
      default:
        return 'bg-slate-800/30 text-slate-300 border-slate-700';
    }
  };

  return (
    <div className="border border-slate-800 rounded-lg overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-900/50">
              <th className="px-6 py-4 text-left">
                <button onClick={() => handleSort('name')} className="flex items-center gap-2 font-semibold">
                  Name <SortIcon field="name" />
                </button>
              </th>
              <th className="px-6 py-4 text-left">
                <button onClick={() => handleSort('company')} className="flex items-center gap-2 font-semibold">
                  Company <SortIcon field="company" />
                </button>
              </th>
              <th className="px-6 py-4 text-left">
                <button onClick={() => handleSort('primary_score')} className="flex items-center gap-2 font-semibold">
                  Score <SortIcon field="primary_score" />
                </button>
              </th>
              <th className="px-6 py-4 text-left">
                <button onClick={() => handleSort('tier_candidate')} className="flex items-center gap-2 font-semibold">
                  Tier <SortIcon field="tier_candidate" />
                </button>
              </th>
              <th className="px-6 py-4 text-left font-semibold">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((profile, idx) => (
              <tr key={idx} className="border-b border-slate-800/50 hover:bg-slate-800/20">
                <td className="px-6 py-4">
                  <a href={profile.profile_url} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline">
                    {profile.name}
                  </a>
                </td>
                <td className="px-6 py-4 text-slate-300">{profile.company}</td>
                <td className="px-6 py-4">
                  <span className="font-semibold">{profile.primary_score.toFixed(1)}</span>
                </td>
                <td className="px-6 py-4">
                  <span className={`px-3 py-1 rounded-full text-sm border ${getTierColor(profile.tier_candidate)}`}>
                    {profile.tier_candidate}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <span className={`text-sm ${profile.confidence === 'clear_winner' ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {profile.confidence}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {profiles.length === 0 && (
        <div className="px-6 py-12 text-center text-slate-400">
          <p>No profiles discovered yet. Scout is running or no results available.</p>
        </div>
      )}
    </div>
  );
}
