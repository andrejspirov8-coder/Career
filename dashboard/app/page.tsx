'use client';

import { useEffect, useState } from 'react';
import Dashboard from '@/components/Dashboard';
import { useStore } from '@/lib/store';

export default function Home() {
  const { loadData, loading, error } = useStore();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    loadData();
    
    // Reload data every 5 seconds
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, [loadData]);

  if (!mounted) return null;

  if (error) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-6 max-w-md">
          <h1 className="text-xl font-bold text-red-400 mb-2">Error Loading Dashboard</h1>
          <p className="text-slate-300 mb-4">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded font-medium"
          >
            Reload
          </button>
        </div>
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-50">
      <Dashboard loading={loading} />
    </main>
  );
}
