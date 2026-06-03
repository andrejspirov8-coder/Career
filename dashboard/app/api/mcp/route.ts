import { NextRequest, NextResponse } from 'next/server';
import axios from 'axios';

const MCP_SERVER_URL = process.env.MCP_SERVER_URL || 'http://localhost:8000';

interface MCPToolCall {
  tool: string;
  params?: Record<string, any>;
}

export async function POST(request: NextRequest) {
  try {
    const { tool, params } = (await request.json()) as MCPToolCall;

    // Call MCP server
    const response = await axios.post(`${MCP_SERVER_URL}/tools/${tool}`, params || {});
    
    return NextResponse.json(response.data);
  } catch (error) {
    console.error('MCP error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'MCP call failed' },
      { status: 500 }
    );
  }
}
