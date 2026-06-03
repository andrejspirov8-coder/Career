'use client';

import { create } from 'zustand';
import { DashboardState, ScoutData, Analytics } from './types';
import axios from 'axios';

interface Store extends DashboardState {
  loadData: () => Promise<void>;
  setError: (error: string | null) => void;
}

export const useStore = create<Store>((set) => ({
  scoutData: null,
  analytics: null,
  loading: false,
  error: null,
  lastUpdated: null,

  loadData: async () => {
    set({ loading: true, error: null });
    try {
      const [scoutRes, analyticsRes] = await Promise.all([
        axios.get('/api/scout'),
        axios.get('/api/analytics'),
      ]);

      set({
        scoutData: scoutRes.data,
        analytics: analyticsRes.data,
        loading: false,
        lastUpdated: new Date().toISOString(),
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load data';
      set({
        error: message,
        loading: false,
      });
    }
  },

  setError: (error) => set({ error }),
}));
