# SEO Agent UI

A modern chat interface for the SEO Agent with real-time tool visualization and memory inspection.

## Features

- **Streaming responses** - See agent responses as they're generated
- **Tool call visualization** - Watch tools execute in real-time with status indicators
- **File uploads** - Attach MD, CSV, PDF, DOC, DOCX, and TXT files
- **Memory panel** - Inspect the agent's persistent knowledge base (facts, learnings, decisions, tasks)
- **Markdown rendering** - Rich text formatting in responses

## Quick Start

### 1. Install Backend Dependencies

```bash
cd api
pip install -r requirements.txt
```

### 2. Start Backend Server

```bash
cd api
python main.py
```

The API server will start on `http://localhost:8000`.

### 3. Install Frontend Dependencies

```bash
cd ui
npm install
```

### 4. Start Frontend Development Server

```bash
cd ui
npm run dev
```

The UI will be available at `http://localhost:3000`.

## Usage

1. Open `http://localhost:3000` in your browser
2. Type your SEO question or upload files
3. Watch the agent think and execute tools in real-time
4. Click "Show Memory" to inspect the agent's knowledge base

## Example Queries

- "Analyze productpirates.club and suggest content pillars"
- "What keywords should I target for an AI product management community?"
- "Create a content calendar for Q1 2026"
- "Audit my blog's SEO performance"

## Architecture

```
┌─────────────┐
│  Next.js UI │ (Port 3000)
│   (React)   │
└──────┬──────┘
       │ HTTP/SSE
       ▼
┌─────────────┐
│  FastAPI    │ (Port 8000)
│   Backend   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Orchestrator│
│    Agent    │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  SEO Agent  │ (33 tools)
└─────────────┘
```

## Deployment to Vercel

The UI is built with Next.js and can be deployed to Vercel:

```bash
cd ui
vercel deploy
```

**Note:** You'll need to update the `API_BASE` in `ui/lib/api.ts` to point to your deployed backend.

## Development

### File Structure

```
ui/
├── app/
│   ├── globals.css       # Global styles
│   ├── layout.tsx        # Root layout
│   └── page.tsx          # Main chat page
├── components/
│   ├── ChatMessage.tsx   # Message display
│   ├── FileUpload.tsx    # File attachment
│   └── MemoryPanel.tsx   # Memory inspector
├── lib/
│   └── api.ts            # API client
└── types/
    └── index.ts          # TypeScript types

api/
└── main.py               # FastAPI server
```

### Environment Variables

Create a `.env.local` file in the `ui/` directory:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Troubleshooting

### Backend won't start

- Ensure Python 3.11+ is installed
- Check that all dependencies are installed: `pip install -r requirements.txt`
- Verify port 8000 is not in use

### Frontend won't start

- Ensure Node.js 18+ is installed
- Clear node_modules and reinstall: `rm -rf node_modules && npm install`
- Check for TypeScript errors: `npm run build`

### Can't connect to backend

- Verify backend is running on port 8000
- Check CORS settings in `api/main.py`
- Ensure `NEXT_PUBLIC_API_URL` is set correctly

## License

MIT
