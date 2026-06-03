import { NextRequest, NextResponse } from 'next/server';
import { computeAnalytics } from '@/lib/data';

export async function GET(request: NextRequest) {
  try {
    const analytics = await computeAnalytics();
    return NextResponse.json(analytics);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
