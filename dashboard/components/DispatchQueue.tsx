'use client';

import { Profile } from '@/lib/types';
import { useState } from 'react';
import { Check, X, Send } from 'lucide-react';

interface DispatchQueueProps {
  profiles: Profile[];
}

export default function DispatchQueue({ profiles }: DispatchQueueProps) {
  const [approved, setApproved] = useState<Set<string>>(new Set());
  const [rejected, setRejected] = useState<Set<string>>(new Set());

  const toggleApprove = (url: string) => {
    const newApproved = new Set(approved);
    if (newApproved.has(url)) {
      newApproved.delete(url);
    } else {
      newApproved.add(url);
    }
    setApproved(newApproved);
  };

  const toggleReject = (url: string) => {
    const newRejected = new Set(rejected);
    if (newRejected.has(url)) {
      newRejected.delete(url);
    } else {
      newRejected.add(url);
    }
    setRejected(newRejected);
  };

  const tier1Profiles = profiles.filter((p) => p.tier_candidate === 'tier_1').slice(0, 10);
  const approvedCount = approved.size;
  const rejectedCount = rejected.size;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="border border-slate-800 rounded-lg p-4 bg-slate-900/50">
          <p className="text-slate-400 text-sm">Ready to Send</p>
          <p className="text-3xl font-bold mt-2">{tier1Profiles.length}</p>
        </div>
        <div className="border border-emerald-800 rounded-lg p-4 bg-emerald-900/20">
          <p className="text-emerald-400 text-sm">Approved</p>
          <p className="text-3xl font-bold mt-2">{approvedCount}</p>
        </div>
        <div className="border border-red-800 rounded-lg p-4 bg-red-900/20">
          <p className="text-red-400 text-sm">Rejected</p>
          <p className="text-3xl font-bold mt-2">{rejectedCount}</p>
        </div>
      </div>

      <div className="border border-slate-800 rounded-lg overflow-hidden">
        <div className="bg-slate-900/50 px-6 py-4 border-b border-slate-800">
          <h3 className="font-semibold flex items-center gap-2">
            <Send className="w-4 h-4" />
            Tier 1 Dispatch Queue (Next 10)
          </h3>
        </div>

        <div className="divide-y divide-slate-800">
          {tier1Profiles.length === 0 ? (
            <div className="px-6 py-12 text-center text-slate-400">
              <p>No Tier 1 profiles available for dispatch.</p>
            </div>
          ) : (
            tier1Profiles.map((profile) => (
              <div key={profile.profile_url} className="px-6 py-4 hover:bg-slate-800/30">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <h4 className="font-semibold">{profile.name}</h4>
                    <p className="text-sm text-slate-400">{profile.company}</p>
                    <p className="text-sm text-slate-500 mt-2">{profile.headline}</p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => toggleApprove(profile.profile_url)}
                      className={`p-2 rounded ${
                        approved.has(profile.profile_url)
                          ? 'bg-emerald-900/40 border border-emerald-700 text-emerald-400'
                          : 'bg-slate-800/50 border border-slate-700 text-slate-400 hover:text-emerald-400'
                      }`}
                    >
                      <Check className="w-5 h-5" />
                    </button>
                    <button
                      onClick={() => toggleReject(profile.profile_url)}
                      className={`p-2 rounded ${
                        rejected.has(profile.profile_url)
                          ? 'bg-red-900/40 border border-red-700 text-red-400'
                          : 'bg-slate-800/50 border border-slate-700 text-slate-400 hover:text-red-400'
                      }`}
                    >
                      <X className="w-5 h-5" />
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {approvedCount > 0 && (
        <div className="flex gap-4">
          <button className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-3 rounded-lg flex items-center justify-center gap-2">
            <Send className="w-4 h-4" />
            Send {approvedCount} Connection(s)
          </button>
        </div>
      )}
    </div>
  );
}
