import fs from 'fs/promises';
import path from 'path';
import { Profile, ScoutData, Analytics, TierStats, CompanyStats } from './types';

const CAREER_PATH = process.env.CAREER_PATH || path.join(process.env.HOME || '', 'Downloads/Career-main/job-search');
const PIPELINE_DIR = path.join(CAREER_PATH, 'pipeline');

export async function readScoutResults(): Promise<ScoutData> {
  try {
    const actionPlanPath = path.join(PIPELINE_DIR, 'recruiter_action_plan.jsonl');
    const content = await fs.readFile(actionPlanPath, 'utf-8');
    const lines = content.trim().split('\n').filter(l => l);
    
    const profiles: Profile[] = lines.map(line => JSON.parse(line));
    
    const tier_1_count = profiles.filter(p => p.tier_candidate === 'tier_1').length;
    const tier_2_count = profiles.filter(p => p.tier_candidate === 'tier_2').length;
    const tier_3_count = profiles.filter(p => p.tier_candidate === 'tier_3').length;
    const tier_rest_count = profiles.filter(p => p.tier_candidate === 'tier_rest').length;

    return {
      total_profiles: profiles.length,
      tier_1_count,
      tier_2_count,
      tier_3_count,
      tier_rest_count,
      profiles: profiles.slice(-100), // Latest 100
      last_updated: new Date().toISOString(),
    };
  } catch (error) {
    return {
      total_profiles: 0,
      tier_1_count: 0,
      tier_2_count: 0,
      tier_3_count: 0,
      tier_rest_count: 0,
      profiles: [],
      last_updated: new Date().toISOString(),
    };
  }
}

export async function computeAnalytics(): Promise<Analytics> {
  try {
    const reportPath = path.join(PIPELINE_DIR, 'report.md');
    const content = await fs.readFile(reportPath, 'utf-8');
    
    // Parse markdown report for basic stats
    // This is a simplified parser - enhance as needed
    const scoutData = await readScoutResults();
    
    return {
      total_sent: scoutData.total_profiles,
      total_responses: 0,
      overall_response_rate: 0,
      tier_stats: [
        { tier: 'tier_1', sent: scoutData.tier_1_count, responses: 0, response_rate: 0, avg_score: 17 },
        { tier: 'tier_2', sent: scoutData.tier_2_count, responses: 0, response_rate: 0, avg_score: 13 },
        { tier: 'tier_3', sent: scoutData.tier_3_count, responses: 0, response_rate: 0, avg_score: 10 },
      ],
      company_stats: [],
      score_distribution: { '15.0+': scoutData.tier_1_count, '12.0-14.9': scoutData.tier_2_count, '8.0-11.9': scoutData.tier_3_count },
      confidence_stats: { 'clear_winner': { sent: scoutData.total_profiles, responses: 0, response_rate: 0 } },
      rows_analyzed: scoutData.total_profiles,
      last_updated: new Date().toISOString(),
    };
  } catch (error) {
    return {
      total_sent: 0,
      total_responses: 0,
      overall_response_rate: 0,
      tier_stats: [],
      company_stats: [],
      score_distribution: {},
      confidence_stats: {},
      rows_analyzed: 0,
      last_updated: new Date().toISOString(),
    };
  }
}

export async function callMCPTool(toolName: string, params: Record<string, any>) {
  try {
    // Call MCP server endpoint
    const response = await fetch(`http://localhost:8000/tools/${toolName}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    
    return await response.json();
  } catch (error) {
    console.error(`MCP call failed for ${toolName}:`, error);
    throw error;
  }
}
