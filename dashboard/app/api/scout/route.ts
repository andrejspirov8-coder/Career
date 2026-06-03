import { NextRequest, NextResponse } from 'next/server';
import { readScoutResults } from '@/lib/data';

export async function GET(request: NextRequest) {
  try {
    const data = await readScoutResults();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
