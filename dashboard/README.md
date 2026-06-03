# 🎯 Career Dashboard - MCP-Integrated

Full-stack Next.js dashboard for recruiter automation with Model Context Protocol (MCP) integration.

## Features

✅ **Real-Time Scout Monitoring** — Watch profile discovery live  
✅ **Interactive Profiles Table** — Sort, filter, and explore recruiter profiles  
✅ **Analytics Dashboard** — Visualize tier distribution and performance metrics  
✅ **Dispatch Queue** — Approve/reject profiles before sending connections  
✅ **MCP Integration** — Call career workspace tools from the dashboard  

## Architecture

```
Next.js App Router
├── Pages (React Components)
│   ├── /          → Dashboard overview
│   ├── /profiles  → Profile explorer
│   ├── /analytics → Full analytics view
│   └── /dispatch  → Queue management
├── API Routes (Next.js)
│   ├── /api/scout      → Scout progress
│   ├── /api/analytics  → Analytics data
│   └── /api/mcp        → MCP tool calls
└── Data Layer
    └── lib/data.ts → JSONL file reader + MCP client
```

## Setup

### 1. Install Dependencies

```bash
cd ~/Career/dashboard
npm install
# or
pnpm install
```

### 2. Start MCP Server (in another terminal)

```bash
cd ~/Downloads/Career-main/job-search
python3 -m mcp.server
```

### 3. Start Dashboard

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

## Configuration

Edit `.env.local`:

```env
MCP_SERVER_URL=http://localhost:8000
CAREER_PATH=/Users/andrejspirov/Downloads/Career-main/job-search
NEXT_PUBLIC_API_URL=http://localhost:3000
```

## Usage

### View Scout Progress

```
Dashboard → Overview tab
Automatically updates every 5 seconds
Shows tier distribution in real-time
```

### Explore Profiles

```
Dashboard → Profiles tab
Sort by Name, Company, Score, Tier
Click name to open LinkedIn profile
```

### Check Analytics

```
Dashboard → Analytics tab
View score distribution pie chart
See tier statistics bar chart
Check response rate predictions
```

### Manage Dispatch

```
Dashboard → Dispatch tab
Approve profiles to send
Reject profiles to skip
Send bulk connections
```

## MCP Integration

The dashboard can call MCP tools directly:

```typescript
// Example: Score a profile
await fetch('/api/mcp', {
  method: 'POST',
  body: JSON.stringify({
    tool: 'score_recruiter',
    params: {
      headline: 'VP People @ Michael Kors',
      name: 'Jane Doe',
      company: 'Michael Kors',
      profile_url: 'https://...',
    },
  }),
});
```

## Technology Stack

- **Framework:** Next.js 15 (React 19)
- **Language:** TypeScript
- **Styling:** CSS + Tailwind patterns
- **Charts:** Recharts
- **Icons:** Lucide React
- **State:** Zustand
- **API Client:** Axios

## Development

```bash
npm run dev      # Start dev server
npm run build    # Build for production
npm run start    # Start production server
npm run lint     # Run linter
```

## Deployment

### Vercel (Recommended)

```bash
vercel
```

### Self-Hosted

```bash
npm run build
npm run start
```

Set `MCP_SERVER_URL` to your remote MCP server endpoint.

## Features Roadmap

- [ ] Real-time WebSocket updates
- [ ] Profile approval workflow  
- [ ] Bulk dispatch scheduling
- [ ] Response tracking integration
- [ ] LangGraph agent visualization
- [ ] Desktop Commander integration

---

**Built with ❤️ for the Career workspace**
