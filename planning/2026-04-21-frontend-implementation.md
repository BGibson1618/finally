# Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FinAlly frontend — a distinctive, production-grade trading workstation UI — as a Next.js TypeScript static export that integrates cleanly with the existing FastAPI backend on a single origin at `/api/*`. The finished product is a dense, dark, amber-on-black trading terminal with live SSE prices, a portfolio heatmap, trade execution, and a docked AI chat assistant.

**Architecture:** A single-page Next.js 15 App Router application, built with `output: 'export'` so the resulting static bundle can be served directly by FastAPI in production. Data layer is split: a Zustand store owns the hot-path SSE price stream and per-ticker ring buffers; TanStack Query owns request/response state for portfolio, watchlist, trades, chat, and P&L history. Charts use TradingView's Lightweight Charts for time-series (main ticker chart, P&L line) and visx for the treemap heatmap. Dev runs Next on port 3000 with a proxy rewrite of `/api/*` → `http://localhost:8000`; prod mounts the exported bundle under FastAPI's `StaticFiles`.

**Authority note:** This document is the source of truth for frontend-facing product behavior and visual design. When this file disagrees with older notes in `planning/PLAN.md`, this file wins until a later revision replaces it.

**Aesthetic charter:** Neo-Bloomberg Amber CRT. Monospace everywhere, amber-yellow (`#ecad0a`) dominant on near-black (`#0a0a0a`), 1px hard borders with zero radius, ASCII-style dividers, subtle CRT scanline overlay + phosphor text-glow. Blue (`#209dd7`) and purple (`#753991`) used sparingly as punctuation — never as backgrounds. This charter is binding: every task must honor it. Deviations need a written justification in the commit message.

**Tech stack:** Next.js 15, TypeScript, React 19, Tailwind CSS v4, Zustand, TanStack Query v5, Lightweight Charts v4, `@visx/hierarchy` + `@visx/treemap`, Motion (formerly Framer Motion), Vitest + React Testing Library.

---

## Starting State (verify before you begin)

- Working dir: `/home/bgibs/projects/finally`
- `backend/` is complete (health + market SSE + portfolio + watchlist + chat routers wired in `backend/app/main.py`). Do NOT modify backend code except for the single, explicit change in Task 16 (static file mount).
- `backend/app/market/` provides the SSE stream at `GET /api/stream/prices`. Do NOT modify.
- `frontend/` does **not** exist yet.
- `test/` does **not** exist yet — E2E infrastructure is out of scope for this plan (note it as a follow-up).
- `db/finally.db` may or may not exist; backend creates it lazily on first request.
- Node 20 LTS and `pnpm` or `npm` must be available. This plan uses `npm` for portability with the existing Docker multi-stage build in `PLAN.md` §11.

**Setup verification commands** (run once at start):

```bash
cd /home/bgibs/projects/finally/backend
uv run --extra dev pytest -q
# Expected: all tests pass.

cd /home/bgibs/projects/finally
node --version   # must be >= 20
npm --version    # must be >= 10
```

---

## Aesthetic Charter (binding — re-read before each task)

**Palette**

| Token                | Hex       | Where it's used                                                  |
|----------------------|-----------|------------------------------------------------------------------|
| `--bg-void`          | `#0a0a0a` | Page background                                                  |
| `--bg-panel`         | `#101010` | Panel surfaces (one shade up from void)                          |
| `--bg-panel-raised`  | `#151515` | Hover state for interactive rows, selected watchlist row         |
| `--fg-amber`         | `#ecad0a` | Primary text, borders, tick marks, prompt chevrons               |
| `--fg-amber-dim`     | `#8a650a` | Secondary labels, inactive columns, dividers                     |
| `--fg-amber-faint`   | `#3d2d05` | Gridlines on charts, disabled elements                           |
| `--fg-phosphor`      | `#fff4c2` | Live numbers that just changed (flash target)                    |
| `--accent-blue`      | `#209dd7` | Connection OK, buys, positive metadata                           |
| `--accent-purple`    | `#753991` | Submit buttons, chat "assistant" role indicator                  |
| `--signal-green`     | `#3fb950` | Upticks, positive P&L                                            |
| `--signal-red`       | `#f85149` | Downticks, negative P&L, error states                            |
| `--signal-amber`     | `#d29922` | Reconnecting status, warnings                                    |

**Typography — single-typeface discipline**

- Load **IBM Plex Mono** from Google Fonts with weights `300, 400, 500, 600, 700`. It is the ONLY font in the entire application.
- No sans-serif companion. No serif. The monoculture IS the aesthetic.
- Size scale (rem, base = 14px): `xs 0.75 / sm 0.8125 / base 0.875 / md 1 / lg 1.25 / xl 1.625 / 2xl 2.5 / 3xl 4`.
- Letter-spacing: `-0.01em` on display sizes (≥ `xl`); `0.04em` uppercase tracking on labels.
- Line-height: 1.3 on data rows, 1.5 on paragraph text.

**Borders, radius, shadows**

- Radius: `0` everywhere. No rounded corners anywhere. This is non-negotiable.
- Borders: 1px solid `var(--fg-amber-dim)` is the default panel border. Interactive hover raises to `var(--fg-amber)`.
- Shadows: no drop-shadows. Depth comes from border contrast and subtle background shifts only.
- Focus ring: 1px outset solid `var(--fg-amber)` with 1px offset (no blur).

**Dividers**

- Horizontal dividers within panels: a row of ASCII glyphs (`─` or `═`) rendered in `--fg-amber-dim`, full-width, no solid `<hr>`.
- Section heads may use `╔════ TITLE ════╗` style with the title inlaid into the top border.

**Motion**

- Price flash: on new tick, apply a flash class for 450ms; bg fades from `--signal-green/30` (or red) to transparent via CSS keyframes. Text color briefly jumps to `--fg-phosphor`.
- Page load: staggered reveal of panels using Motion. Each panel fades from `opacity: 0 / translate-y: 4px` with 40ms stagger. Full choreography completes in under 400ms.
- Cursor blink (for prompts): 1.1s interval, 50% duty cycle.
- Scanlines: static (no animation). Attempting to animate them will trigger motion sickness for many users — do not.

**Background effects**

- Fixed-position `::before` on `<body>` with `repeating-linear-gradient(0deg, transparent 0, transparent 2px, rgba(236, 173, 10, 0.04) 2px, rgba(236, 173, 10, 0.04) 3px)` — 1px amber lines every 3px, at 4% opacity. This is the scanline layer.
- Fixed-position `::after` with an SVG noise texture (generated via feTurbulence) at 3% opacity, `mix-blend-mode: overlay`. Provides film grain.
- `prefers-reduced-motion: reduce` disables the scanline overlay (replaces with solid bg).

**Iconography**

- No SVG icon libraries. Glyphs are Unicode box-drawing and geometric characters: `▲▼●○◉◎◆◇▌█░▓═║╔╗╚╝─│┌┐└┘├┤┬┴┼▄▀`.
- Status dots: `●` in the relevant color. That's it.

**Anti-patterns (will be rejected in review)**

- Rounded corners anywhere.
- Gradients except inside chart fills.
- Any non-mono font, especially Inter.
- Emoji used as UI (text content is fine if it's the user's own chat message).
- Heavy drop-shadows, neumorphism, glassmorphism.
- Purple-on-white anything.
- Loading spinners that rotate — use a Knight-Rider amber sweep or a blinking `░▒▓█▓▒░` instead.

---

## Directory Structure (to be created)

```
frontend/
├── .gitignore
├── package.json
├── package-lock.json                   # committed
├── tsconfig.json
├── next.config.ts
├── next-env.d.ts                       # auto-generated
├── postcss.config.mjs
├── tailwind.config.ts                  # v4 config-in-CSS is preferred; file kept minimal for type-safety
├── vitest.config.ts
├── README.md                           # brief: dev/build/test commands
├── public/
│   └── favicon.svg                     # amber ● on black
├── src/
│   ├── app/
│   │   ├── layout.tsx                  # root layout: fonts, providers, scanline overlay
│   │   ├── page.tsx                    # single-page workstation assembly
│   │   ├── globals.css                 # Tailwind imports, CSS custom properties, scanline, noise
│   │   └── providers.tsx               # QueryClientProvider, price-stream bootstrap
│   ├── lib/
│   │   ├── api/
│   │   │   ├── client.ts               # typed fetch helper
│   │   │   ├── types.ts                # backend response types
│   │   │   ├── portfolio.ts            # portfolio queries/mutations
│   │   │   ├── watchlist.ts            # watchlist queries/mutations
│   │   │   ├── chat.ts                 # chat mutation
│   │   │   └── history.ts              # P&L history query
│   │   ├── stream/
│   │   │   ├── priceStore.ts           # zustand store (prices, buffers, status)
│   │   │   ├── eventSource.ts          # EventSource wrapper + reconnect logic
│   │   │   └── useLiveTicker.ts        # selector hook for one ticker
│   │   ├── format.ts                   # price / percent / currency formatters
│   │   └── utils.ts                    # small helpers (clsx, etc.)
│   ├── design/
│   │   ├── tokens.ts                   # TS re-export of CSS custom props for charts
│   │   ├── Panel.tsx                   # bordered container primitive
│   │   ├── AsciiDivider.tsx
│   │   ├── StatusDot.tsx
│   │   ├── Glyph.tsx                   # wrapper for Unicode glyphs with accessible labels
│   │   ├── KeyCap.tsx                  # [ BUY ] / [ SELL ] / keyboard-chip style
│   │   ├── Marquee.tsx                 # big display numbers with phosphor glow
│   │   ├── PriceFlash.tsx              # HOC/hook for price flash
│   │   └── ScanlineOverlay.tsx         # optional react-side overlay wrapper (CSS-only fallback in globals)
│   ├── features/
│   │   ├── header/
│   │   │   ├── Header.tsx
│   │   │   └── Clock.tsx
│   │   ├── watchlist/
│   │   │   ├── Watchlist.tsx
│   │   │   ├── WatchlistRow.tsx
│   │   │   ├── Sparkline.tsx           # canvas sparkline
│   │   │   └── AddTickerInput.tsx
│   │   ├── chart/
│   │   │   ├── MainChart.tsx           # lightweight-charts wrapper
│   │   │   └── ChartFrame.tsx          # decorative border + scanlines over chart
│   │   ├── positions/
│   │   │   └── PositionsTable.tsx
│   │   ├── heatmap/
│   │   │   └── PortfolioHeatmap.tsx    # visx treemap
│   │   ├── pnl/
│   │   │   └── PnLChart.tsx
│   │   ├── trade/
│   │   │   ├── TradeBar.tsx
│   │   │   └── useTrade.ts             # mutation hook with optimistic update
│   │   └── chat/
│   │       ├── ChatPanel.tsx
│   │       ├── ChatMessage.tsx
│   │       ├── ChatInput.tsx
│   │       ├── ChatActionCard.tsx      # inline trade/watchlist confirmation
│   │       └── useChat.ts
│   └── test/
│       ├── setup.ts                    # vitest + RTL setup
│       └── mocks/
│           ├── server.ts               # MSW handlers for API
│           └── eventSource.ts          # EventSource mock
└── tests/                              # unit tests mirror src/ structure
    ├── lib/stream/priceStore.test.ts
    ├── lib/stream/eventSource.test.ts
    ├── features/watchlist/Watchlist.test.tsx
    ├── features/positions/PositionsTable.test.tsx
    ├── features/trade/useTrade.test.ts
    ├── features/chat/ChatPanel.test.tsx
    └── ...                             # per-task tests listed in each task
```

---

## Ground Rules for the Implementing Agent

1. **TDD for non-visual logic.** For pure logic modules (store, EventSource wrapper, formatters, query hooks) — write test first, watch it fail, implement minimum, watch it pass, commit. For visual components, write a rendering smoke test alongside implementation; full visual correctness is verified by the human eye in the dev server.
2. **Run unit tests after every task**: `cd frontend && npm test -- --run`. Never let the suite go red.
3. **Run the type checker after every task**: `npm run typecheck` (alias for `tsc --noEmit`).
4. **Run the linter after every task**: `npm run lint` (Next's built-in ESLint).
5. **Run `npm run build` after every task that touches `next.config.ts`, layout, routing, or global providers.** Static export has pitfalls (no server components that fetch at runtime, no dynamic routes without `generateStaticParams`); breaking the build silently is the #1 risk here.
6. **Manually verify in the browser after any UI-touching task.** Start backend (`cd backend && uv run uvicorn app.main:create_app --factory --reload`) and frontend (`cd frontend && npm run dev`), open `http://localhost:3000`, exercise the feature. Type checking and unit tests verify correctness of code, not correctness of UI — confirm with your eyes.
7. **Commit messages** use the existing conventional style: `feat: …`, `fix: …`, `test: …`, `chore: …`, `style: …`, `refactor: …`. Example: `feat(frontend): add Zustand price stream store with ring buffers`.
8. **Aesthetic fidelity is a correctness property.** A task is not done if its output does not honor the Aesthetic Charter above. If a choice isn't covered by the charter, err toward severity and monospaced minimalism.
9. **No defensive programming.** Trust the backend contract as documented in `backend/CLAUDE.md` and PLAN.md §8. Surface errors at system boundaries (fetch failures, SSE disconnects) — don't wrap every line in try/catch.
10. **No abstractions ahead of their second use.** Three similar rows is fine; extract only on the fourth.
11. **No unrequested polish.** Features not listed in PLAN.md §10 must not appear.

---

## Task 1: Scaffold the Next.js project

**Files:**
- Create: `frontend/` (entire directory)
- Modify: `/home/bgibs/projects/finally/.gitignore` (add Next build artifacts if not covered)

- [ ] **Step 1: Generate the Next.js app**

```bash
cd /home/bgibs/projects/finally
npx create-next-app@latest frontend \
  --typescript --tailwind --eslint --app \
  --no-src-dir=false --src-dir \
  --import-alias "@/*" --use-npm \
  --turbopack=false --no-turbopack
```

Answer any interactive prompts consistent with the flags: TypeScript yes, ESLint yes, Tailwind yes, `src/` yes, App Router yes, custom alias `@/*`, no Turbopack. Expected: `frontend/` exists with a working Next.js starter.

- [ ] **Step 2: Pin React 19 and Next 15** (if the generator picked earlier versions). Verify `frontend/package.json` has `"next": "^15.x"` and `"react": "^19.x"`. If not, upgrade:

```bash
cd frontend
npm install next@latest react@latest react-dom@latest
```

- [ ] **Step 3: Configure static export.** Edit `frontend/next.config.ts`:

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  async rewrites() {
    // Dev-only: proxy /api/* to the FastAPI backend.
    // Ignored in static export builds.
    return [
      { source: "/api/:path*", destination: "http://localhost:8000/api/:path*" },
    ];
  },
};

export default nextConfig;
```

Note: `rewrites()` are a dev-server convenience; the static export does not use them. In prod FastAPI serves both the static bundle and `/api/*` on the same origin, so no rewrite is needed.

- [ ] **Step 4: Strip the starter chrome.** Delete `frontend/src/app/page.tsx` contents and replace with:

```tsx
export default function Page() {
  return <main className="min-h-screen">FINALLY</main>;
}
```

Delete any starter-generated CSS except `globals.css` itself (we'll rewrite it in Task 2). Delete the default favicon; we'll add ours in Task 2.

- [ ] **Step 5: Smoke test.**

```bash
cd /home/bgibs/projects/finally/frontend
npm run dev
# In another shell:
curl -s http://localhost:3000/ | grep -q FINALLY && echo OK
npm run build
ls out/ | head   # should include index.html
```

Expected: dev server boots, curl finds `FINALLY`, build emits `out/`. Kill the dev server.

- [ ] **Step 6: Commit.** `feat(frontend): scaffold next.js 15 app with static export`

---

## Task 2: Aesthetic foundation — tokens, globals, fonts, scanlines

**Files:**
- Create/overwrite: `frontend/src/app/globals.css`
- Create: `frontend/src/app/layout.tsx` (overwrite scaffold)
- Create: `frontend/public/favicon.svg`
- Create: `frontend/src/design/tokens.ts`
- Modify: `frontend/tailwind.config.ts`

- [ ] **Step 1: Load IBM Plex Mono via `next/font`.** In `frontend/src/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import { IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers"; // created in Task 3

const plex = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "FINALLY — the finance ally",
  description: "AI-powered trading workstation",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={plex.variable}>
      <body className="font-mono bg-[var(--bg-void)] text-[var(--fg-amber)] antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
```

- [ ] **Step 2: Write `frontend/src/app/globals.css`** with the full token set, Tailwind v4 imports, scanline overlay, grain overlay, and reduced-motion handling. Use the Aesthetic Charter above as the authoritative source of truth for values.

Required pieces:
- `@import "tailwindcss";`
- `@theme { ... }` block mapping Tailwind color tokens to CSS vars (e.g., `--color-amber: var(--fg-amber);`)
- `:root { ... }` with every color variable from the charter
- `html, body { background: var(--bg-void); color: var(--fg-amber); font-family: var(--font-mono), ui-monospace, monospace; }`
- `body::before { … repeating-linear-gradient for scanlines … }` — fixed, `pointer-events: none`, `z-index: 9998`
- `body::after { … SVG noise via `url("data:image/svg+xml;utf8,<svg…feTurbulence…/>")` … }` — fixed, `pointer-events: none`, `z-index: 9999`, 3% opacity, `mix-blend-mode: overlay`
- `@media (prefers-reduced-motion: reduce) { body::before { display: none; } }`
- Price-flash keyframes: `@keyframes flash-up { from { background: rgba(63,185,80,0.35); color: var(--fg-phosphor); } to { background: transparent; color: inherit; } }` — and the red counterpart. 450ms linear.
- Cursor blink keyframes: `@keyframes blink { 50% { opacity: 0; } }`, 1.1s infinite.
- Phosphor text-shadow utility class: `.glow-phosphor { text-shadow: 0 0 6px rgba(236, 173, 10, 0.55), 0 0 1px rgba(255, 244, 194, 0.9); }`
- Utility `.no-radius *, .no-radius { border-radius: 0 !important; }` applied on body so no third-party library can sneak in rounded corners.

- [ ] **Step 3: Extend Tailwind** in `frontend/tailwind.config.ts` to expose spacing and the color tokens under `amber`, `signal-green`, `signal-red`, `accent-blue`, `accent-purple`, `bg-void`, `bg-panel`, `fg-amber-dim`, etc. Keep the file minimal; most theming lives in `@theme {}` inside `globals.css`.

- [ ] **Step 4: Favicon.** Write a tiny SVG to `frontend/public/favicon.svg` — solid `#0a0a0a` square with a centered `#ecad0a` circle (r=30%). No text.

- [ ] **Step 5: TS token export.** In `frontend/src/design/tokens.ts`, re-export the color palette as TypeScript constants for use in chart libraries that can't read CSS custom properties:

```ts
export const tokens = {
  bgVoid: "#0a0a0a",
  bgPanel: "#101010",
  fgAmber: "#ecad0a",
  fgAmberDim: "#8a650a",
  fgAmberFaint: "#3d2d05",
  fgPhosphor: "#fff4c2",
  accentBlue: "#209dd7",
  accentPurple: "#753991",
  signalGreen: "#3fb950",
  signalRed: "#f85149",
} as const;
```

- [ ] **Step 6: Manual verification.** `npm run dev`, open `http://localhost:3000`, confirm:
  - Page is near-black with faint amber scanlines visible.
  - The text "FINALLY" from Task 1 renders in IBM Plex Mono, amber.
  - Grain is subtle — almost imperceptible, not sandpaper.
  - Reduced-motion in DevTools emulation removes the scanlines.

- [ ] **Step 7: Commit.** `feat(frontend): aesthetic foundation (tokens, scanlines, plex mono)`

---

## Task 3: Data layer — providers, API client, types

**Files:**
- Create: `frontend/src/app/providers.tsx`
- Create: `frontend/src/lib/api/client.ts`
- Create: `frontend/src/lib/api/types.ts`
- Create: `frontend/src/lib/format.ts`
- Create: `frontend/src/lib/utils.ts`
- Modify: `frontend/package.json` (add deps)

- [ ] **Step 1: Install dependencies.**

```bash
cd frontend
npm install zustand @tanstack/react-query @tanstack/react-query-devtools \
  motion lightweight-charts@^4 \
  @visx/hierarchy @visx/treemap @visx/group @visx/scale @visx/tooltip
npm install --save-dev vitest @vitest/ui @testing-library/react @testing-library/jest-dom \
  @testing-library/user-event jsdom msw
```

- [ ] **Step 2: Define backend response types** in `frontend/src/lib/api/types.ts`. Mirror the shapes returned by the FastAPI endpoints documented in PLAN.md §8 and `backend/CLAUDE.md`. You **must** inspect the actual backend Pydantic models under `backend/app/portfolio/models.py`, `backend/app/chat/models.py`, and the watchlist/portfolio route handlers to get field names and types exactly right. Do not guess. If a field's type is ambiguous, cross-reference with an actual response:

```bash
cd ../backend && uv run uvicorn app.main:create_app --factory --port 8001 &
curl -s http://localhost:8001/api/portfolio | jq .
curl -s http://localhost:8001/api/watchlist | jq .
curl -s http://localhost:8001/api/portfolio/history | jq .
kill %1
```

Minimum exported types (align fields to the backend exactly): `PriceUpdateEvent`, `PriceStreamBatch`, `Portfolio`, `Position`, `TradeRequest`, `TradeResult`, `WatchlistEntry`, `ChatRequest`, `ChatResponse`, `ProposedAction`, `ExecutedAction`, `PortfolioSnapshot`.

- [ ] **Step 3: Typed fetch helper** in `frontend/src/lib/api/client.ts`:

```ts
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body || res.statusText);
  }
  return (await res.json()) as T;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
```

No retry, no timeout, no auth headers. The backend is same-origin in prod and proxied in dev.

- [ ] **Step 4: Providers** in `frontend/src/app/providers.tsx`:

```tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useState } from "react";
import { PriceStreamBootstrap } from "@/lib/stream/PriceStreamBootstrap"; // created in Task 4

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 5_000, refetchOnWindowFocus: false, retry: 1 },
          mutations: { retry: 0 },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <PriceStreamBootstrap />
      {children}
      {process.env.NODE_ENV === "development" && <ReactQueryDevtools />}
    </QueryClientProvider>
  );
}
```

- [ ] **Step 5: Formatters** in `frontend/src/lib/format.ts` — `formatPrice(n)` (2-decimal fixed), `formatChange(n)` (signed, 2dp), `formatPercent(n)` (signed, 2dp with `%`), `formatCurrency(n)` (no `$` fractional cents hidden above $10k — decide consistently and test), `formatCompact(n)` (e.g. 1.2M). Tests first:
  - Create `frontend/tests/lib/format.test.ts` with cases for zero, negative, large numbers, very small prices.

- [ ] **Step 6: Vitest config.**
  - `frontend/vitest.config.ts` with `environment: "jsdom"`, setup file, path aliases mirroring `tsconfig.json`.
  - `frontend/src/test/setup.ts` with `import "@testing-library/jest-dom"`.
  - Add scripts to `package.json`: `"test": "vitest"`, `"test:run": "vitest run"`, `"typecheck": "tsc --noEmit"`.

- [ ] **Step 7: Run tests + typecheck + build.**

```bash
npm run test:run
npm run typecheck
npm run build
```

All must pass. Fix anything red before committing.

- [ ] **Step 8: Commit.** `feat(frontend): data layer foundation — query client, api helpers, formatters`

---

## Task 4: SSE store + EventSource wrapper + price flash

**Files:**
- Create: `frontend/src/lib/stream/priceStore.ts`
- Create: `frontend/src/lib/stream/eventSource.ts`
- Create: `frontend/src/lib/stream/PriceStreamBootstrap.tsx`
- Create: `frontend/src/lib/stream/useLiveTicker.ts`
- Create: `frontend/src/design/PriceFlash.tsx`
- Create: `frontend/src/test/mocks/eventSource.ts`
- Create: `frontend/tests/lib/stream/priceStore.test.ts`
- Create: `frontend/tests/lib/stream/eventSource.test.ts`

**Design notes (read before coding):**

- The store holds three slices: `prices: Record<string, PriceUpdateEvent>`, `buffers: Record<string, Float32Array>` (ring buffer of the last N prices per ticker for sparklines and the main chart initial window), `status: "idle" | "connecting" | "open" | "reconnecting" | "closed"`.
- Buffer size: **240** entries per ticker. At ~500ms cadence that's ~2 minutes of history — enough for a sparkline and an initial main-chart window.
- The ring buffer is a Float32Array with a write-head index stored alongside. Reading yields a chronological slice.
- The store uses **direct mutation for hot path**: `setPrice` mutates the Float32Array in-place and bumps a `version` counter. Subscribers re-render via `useSyncExternalStore` (Zustand's default) keyed on `version`. This avoids reallocating a new map on every tick.
- Reconnect: exponential backoff starting 500ms, doubling to 10s max, reset on successful open. EventSource has native retry but adding our own lets us expose `status` to the UI.

- [ ] **Step 1: Write failing tests first** in `frontend/tests/lib/stream/priceStore.test.ts`:
  - `setPrice appends to ring buffer and updates latest`
  - `ring buffer wraps around after 240 entries`
  - `getSparkline returns entries in chronological order when wrapped`
  - `setStatus updates status slice`
  - Use a mock EventSource (next step) — but these first tests exercise the store directly without any EventSource.

- [ ] **Step 2: Implement `priceStore.ts`**. Use Zustand's `create` with `subscribeWithSelector` middleware. Export hooks: `usePriceStore`, `useLatestPrice(ticker)`, `useSparkline(ticker)`, `useConnectionStatus`.

- [ ] **Step 3: EventSource mock** at `frontend/src/test/mocks/eventSource.ts` — a class matching the DOM `EventSource` surface with `dispatch(event)` for tests to inject messages.

- [ ] **Step 4: Write failing tests** in `frontend/tests/lib/stream/eventSource.test.ts`:
  - `connects and transitions to open on first message`
  - `writes received prices into store`
  - `transitions to reconnecting on error, backs off, retries`
  - `stop() closes the EventSource and sets status to closed`

- [ ] **Step 5: Implement `eventSource.ts`** — a class `PriceStream` with `start(url)`, `stop()`, private reconnect logic. It parses `MessageEvent.data` as JSON and calls `priceStore.setPrice(...)` for **each ticker in the batch payload**. Expected event shape: inspect `backend/app/market/stream.py` to confirm the exact fields streamed. Match that exact batch shape here.

  **Verify the SSE event shape with a live call before writing the parser:**
  ```bash
  cd backend && uv run uvicorn app.main:create_app --factory --port 8001 &
  curl -N http://localhost:8001/api/stream/prices | head -5
  kill %1
  ```

- [ ] **Step 6: Bootstrap component** `PriceStreamBootstrap.tsx` — a `"use client"` component that `useEffect`s `priceStream.start("/api/stream/prices")` on mount and `stop()` on unmount. Renders nothing. Mounted from `providers.tsx`.

- [ ] **Step 7: `useLiveTicker(ticker)` hook** — combines latest price + backend-derived change metadata. Prefer the latest SSE event's `change` / `change_percent` values over recomputing from the ring buffer unless the backend contract lacks them. Keep this hook cheap — downstream components subscribe to it per row.

- [ ] **Step 8: `PriceFlash` component** at `frontend/src/design/PriceFlash.tsx` — a `<span>` wrapper that watches a `value` prop and applies `flash-up`/`flash-down` classes for 450ms when it changes. Uses a `key`-based remount with CSS animation to avoid manual setTimeout cleanup.

- [ ] **Step 9: Run tests.** All green.

- [ ] **Step 10: Manual verification.** Temporarily render a `<div>` in `page.tsx` that displays `useLatestPrice("AAPL")?.price`; start backend; confirm prices tick in the browser. Remove the temporary render before committing.

- [ ] **Step 11: Commit.** `feat(frontend): SSE price store with ring buffers and reconnect`

---

## Task 5: Design primitives (Panel, AsciiDivider, StatusDot, Glyph, KeyCap, Marquee)

**Files:**
- Create: `frontend/src/design/Panel.tsx`
- Create: `frontend/src/design/AsciiDivider.tsx`
- Create: `frontend/src/design/StatusDot.tsx`
- Create: `frontend/src/design/Glyph.tsx`
- Create: `frontend/src/design/KeyCap.tsx`
- Create: `frontend/src/design/Marquee.tsx`
- Create: `frontend/tests/design/*.test.tsx` (smoke tests — render + snapshot of critical classNames)

**Specs**

- **Panel**: a bordered container. Props: `title?: string`, `tone?: "default" | "accent"`, `dense?: boolean`. Render:
  - Top border embeds the title: `╔═══ TITLE ═════════╗` style using CSS (pseudo-element with border + absolutely-positioned title chip overlapping the border).
  - Body is `padding: 12px 14px` default, `8px 10px` when `dense`.
  - Accent tone uses `--accent-blue` border instead of amber-dim.

- **AsciiDivider**: horizontal `─` repeated, full-width, `--fg-amber-faint`. Variant prop for `═`.

- **StatusDot**: `●` colored by `status` prop (`ok | warn | error | idle`), with `aria-label`. Animated pulse when `warn`.

- **Glyph**: accessible wrapper that takes a Unicode char and a required `label` for screen readers.

- **KeyCap**: `[ LABEL ]`-style chip with 1px border, hover raises bg. `variant: "buy" | "sell" | "default"` — `buy` uses `--accent-blue` border, `sell` uses `--signal-red`, default uses amber.

- **Marquee**: big display number with `.glow-phosphor` class, optional leading label. Props `value`, `label?`, `tone: "neutral" | "positive" | "negative"`.

- [ ] **Step 1: Write a smoke test** per component — it mounts, renders expected text, has no forbidden rounded corners (grep the computed style for `border-radius: 0px`). Snapshot tests are OK but keep them tight.

- [ ] **Step 2: Implement components.**

- [ ] **Step 3: Run tests + typecheck + lint.** Green.

- [ ] **Step 4: Manual verification.** Add a throwaway route or temporarily fill `page.tsx` with one of each component to eyeball them in the dev server. Remove before committing.

- [ ] **Step 5: Commit.** `feat(frontend): terminal design primitives (Panel, divider, KeyCap, Marquee)`

---

## Task 6: Header bar

**Files:**
- Create: `frontend/src/features/header/Header.tsx`
- Create: `frontend/src/features/header/Clock.tsx`
- Modify: `frontend/src/app/page.tsx` (assemble header at top)
- Tests: `frontend/tests/features/header/Header.test.tsx`

**Spec (from PLAN.md §10 + charter)**

- Full-width strip, 56px tall, `--bg-panel` bg, 1px bottom border amber-dim.
- Left: `FINALLY` (weight 600, tracking +4%) + a `●` status dot driven by `useConnectionStatus()` + a UTC clock updating every second (only h:m:s shown).
- Center: subtle tagline in `--fg-amber-dim`, smaller size: `the finance ally · $SIM`.
- Right: NAV marquee (big, `Marquee` component, computed from `portfolio.total_value`) + P&L % (colored green/red) + cash balance (smaller, dim).
- NAV updates live: pull `Portfolio` via TanStack Query for cash + positions, but recompute total as `cash + Σ (qty × latest SSE price)` so NAV ticks as prices do. This matters — if you only pull from `/api/portfolio` you get a stale value.

- [ ] **Step 1: Clock** — `Clock.tsx` renders a `<time>` updated on a 1s interval. Uses `toLocaleTimeString("en-GB", { hour12: false, timeZone: "UTC" })`.

- [ ] **Step 2: `useLiveNav()` hook** in `frontend/src/features/header/useLiveNav.ts` — selector that combines the portfolio query result with the price store to produce a live NAV number.

- [ ] **Step 3: Test** `Header.test.tsx` — renders with mock portfolio + store, shows `$10,247.33` when cash=10k and positions[AAPL qty=10 price=24.733]. Shows `●` in `--accent-blue` when status is open.

- [ ] **Step 4: Implement `Header.tsx`.**

- [ ] **Step 5: Mount in `page.tsx`.** At this stage `page.tsx` is `<main><Header /></main>`.

- [ ] **Step 6: Manual verify.** Start stack, confirm NAV ticks in sync with SSE.

- [ ] **Step 7: Commit.** `feat(frontend): header bar with live NAV, clock, status dot`

---

## Task 7: Watchlist panel with sparklines

**Files:**
- Create: `frontend/src/features/watchlist/Watchlist.tsx`
- Create: `frontend/src/features/watchlist/WatchlistRow.tsx`
- Create: `frontend/src/features/watchlist/Sparkline.tsx`
- Create: `frontend/src/features/watchlist/AddTickerInput.tsx`
- Create: `frontend/src/lib/api/watchlist.ts`
- Create: `frontend/src/lib/state/selection.ts` (Zustand store for selected ticker)
- Tests: `frontend/tests/features/watchlist/*.test.tsx`

**Specs**

- Rendered inside a `Panel title="WATCHLIST"`.
- One `WatchlistRow` per ticker. Columns: ticker (bold, amber), live price (flash on change), change (signed, green/red), change % (same color), sparkline (canvas, ~120px wide × 28px tall), weight bar (1-row ASCII like `██████▌  12.3%`), remove glyph `✕` on hover (small, dim).
- Clicking a row toggles it as the **selected ticker** (used by main chart). Keyboard accessible: Up/Down arrow keys navigate, Enter selects.
- An `AddTickerInput` at the bottom of the panel — terminal-prompt style: `> _` with blinking cursor. Submits uppercase-only text, validates A-Z only, posts `/api/watchlist`.
- Selection store is a tiny Zustand slice: `{ selected: string | null, setSelected: (t: string | null) => void }`. Initial value is the first watchlist ticker on first fetch.

**Sparkline spec**

- Canvas-backed, not SVG. Subscribes to `useSparkline(ticker)` — redraws only when that ticker's buffer version changes.
- Line only, 1px amber (`--fg-amber`); min/max markers NOT shown.
- If the buffer has fewer than 2 points, render a dashed baseline in `--fg-amber-faint` instead.
- No anti-aliasing tricks; rely on device pixel ratio (set `canvas.width = rect.width * dpr` etc.).

- [ ] **Step 1: API hooks** in `frontend/src/lib/api/watchlist.ts` — `useWatchlist()` (GET `/api/watchlist`), `useAddTicker()`, `useRemoveTicker()`. Both mutations invalidate `["watchlist"]`.

- [ ] **Step 2: Selection store** — small and sharp. Test it first.

- [ ] **Step 3: Tests for `WatchlistRow`** — renders with mock data, flashes on price change (test via `fireEvent` + re-render with new price prop), applies selected class when `selected === ticker`.

- [ ] **Step 4: Implement components** in dependency order: `Sparkline` → `WatchlistRow` → `AddTickerInput` → `Watchlist` (assembly).

- [ ] **Step 5: Mount in `page.tsx`** alongside the header. For now, stack them vertically inside a simple grid — Task 12 will rework the layout.

- [ ] **Step 6: Manual verify** — boot the stack, see 10 tickers streaming, sparklines drawing progressively, flash on tick, add a ticker (e.g. `CRWD`) and see it appear with no sparkline yet.

- [ ] **Step 7: Commit.** `feat(frontend): watchlist panel with live sparklines and add/remove`

---

## Task 8: Main chart area

**Files:**
- Create: `frontend/src/features/chart/MainChart.tsx`
- Create: `frontend/src/features/chart/ChartFrame.tsx`
- Tests: `frontend/tests/features/chart/MainChart.test.tsx` (smoke only — lightweight-charts doesn't play well with jsdom; mock the module)

**Spec**

- Takes a `ticker` prop. Subscribes to the ring buffer for that ticker and renders a Lightweight Charts line/area chart.
- On ticker change, re-seed the chart from the current buffer (up to 240 points), then feed live updates via `series.update({ time, value })`.
- Chart styling — hand-tune to match the charter:
  - background: `var(--bg-panel)`, grid: `var(--fg-amber-faint)` (barely visible), text: `var(--fg-amber-dim)`.
  - line color: `--fg-amber`, line width 1, area fill gradient from `rgba(236,173,10,0.25)` at top to transparent at bottom.
  - crosshair color `--fg-amber`, label bg `--bg-panel-raised`.
  - time axis: short ticks, no fractional seconds, 24-hr.
  - price axis: right side, 2 decimal places.
- `ChartFrame` wraps the chart in a `Panel title="SELECTED.{TICKER}"` and overlays CSS scanlines specifically over the chart area (the body scanlines don't show through canvas cleanly — paint them with a `::after` on the frame).
- Ticker info block above the chart: giant `Marquee` with the current price + change + change%. When no ticker is selected, show `[ SELECT A TICKER FROM THE WATCHLIST ]` centered in `--fg-amber-dim`.
- Above the marquee: metadata row — 1D range (min/max of buffer), tick count, last update timestamp. All in `--fg-amber-dim` xs size.

- [ ] **Step 1: Install & import**. (Already installed in Task 3.) Read Lightweight Charts v4 docs via Context7 if unfamiliar: `mcp__plugin_context7_context7__query-docs` with libraryId `/tradingview/lightweight-charts` and query "create line chart with live updates, custom styling, remove watermark".

- [ ] **Step 2: `MainChart` smoke test** — mounts with mocked `lightweight-charts` module, asserts it calls `createChart` with the right options and `addAreaSeries` (or `addLineSeries`) is called.

- [ ] **Step 3: Implement `MainChart`**:
  - `useEffect` to create chart on mount, destroy on unmount, resize observer for container.
  - `useEffect` keyed on `ticker` to re-seed series from buffer.
  - `useEffect` with a store subscription to push live updates.

- [ ] **Step 4: `ChartFrame`** — `Panel` wrapper + scanline `::after` pseudo-element (added via a className hook to its inner div).

- [ ] **Step 5: Wire selection** — `MainChart` reads `useSelection()` for the ticker.

- [ ] **Step 6: Manual verify** — click between watchlist tickers, see chart re-seed and resume streaming; resize window, see chart reflow.

- [ ] **Step 7: Commit.** `feat(frontend): main chart with lightweight-charts and CRT frame`

---

## Task 9: Positions table

**Files:**
- Create: `frontend/src/features/positions/PositionsTable.tsx`
- Create: `frontend/src/lib/api/portfolio.ts`
- Tests: `frontend/tests/features/positions/PositionsTable.test.tsx`

**Spec**

- Rendered inside `Panel title="POSITIONS"`.
- Columns: `TICKER | QTY | AVG COST | LAST | UNREAL P&L | %`.
- `LAST` comes from the price store (`useLatestPrice(ticker)`) so it ticks live. Unrealized P&L and % recompute on each tick.
- Sortable by any column (click header to sort; default sort is by `|unrealized_pnl|` descending).
- Empty state: a single row `— NO POSITIONS — BUY SOMETHING BELOW —` in `--fg-amber-dim`.
- Numbers right-aligned; `TICKER` left-aligned bold; alternating rows get `--bg-panel-raised` at 40% opacity.
- Uses tabular-nums (`font-variant-numeric: tabular-nums`) so digits line up.

- [ ] **Step 1: API** — `usePortfolio()` query hook. Invalidate keys defined here (`["portfolio"]`) from trade & chat mutations later.

- [ ] **Step 2: Test** — renders with 3 mock positions, shows correct rows, sorts by column header click.

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Manual verify** with a manual trade via `curl -X POST …/api/portfolio/trade` — positions should appear and update live.

- [ ] **Step 5: Commit.** `feat(frontend): live positions table`

---

## Task 10: Trade bar

**Files:**
- Create: `frontend/src/features/trade/TradeBar.tsx`
- Create: `frontend/src/features/trade/useTrade.ts`
- Tests: `frontend/tests/features/trade/useTrade.test.ts`, `frontend/tests/features/trade/TradeBar.test.tsx`

**Spec**

- A horizontal strip at the bottom of the main pane (above the chat panel at the right edge; Task 12 finalizes placement).
- Terminal-prompt aesthetic: `> ` chevron followed by three fields: `TICKER` (uppercased, 4-6 chars), `QTY` (numeric, supports fractional), then two `KeyCap` buttons `[ BUY ]` (accent blue) and `[ SELL ]` (signal red).
- Keyboard first: Enter with focus on QTY submits `BUY`. Cmd/Ctrl+Enter submits `SELL`. Esc clears.
- Ticker defaults to current selection; user can type to override. When ticker typed matches a current position, the `SELL` button becomes active; otherwise it's disabled.
- Optimistic update on submit: deduct cash from portfolio cache, append/merge position; roll back on error. Show result as a transient amber toast strip at the top of the trade bar (`> FILLED: BUY 10 AAPL @ 190.42` or `> REJECTED: insufficient cash`).
- Toast lives 2.4s.

- [ ] **Step 1: `useTrade` mutation** in `useTrade.ts` — wraps TanStack Query's `useMutation` with optimistic `onMutate`, `onError` rollback, `onSuccess` invalidate `["portfolio"]` + `["portfolio", "history"]`. Test it with MSW handlers.

- [ ] **Step 2: Tests** — submit with valid ticker + qty, shows loading, then success, invalidates cache (assert refetch happened).

- [ ] **Step 3: Implement `TradeBar.tsx`.**

- [ ] **Step 4: Mount + manual verify** — buy, see cash decrease, position appear, P&L show; sell more than owned, see error toast.

- [ ] **Step 5: Commit.** `feat(frontend): trade bar with optimistic execution and keyboard shortcuts`

---

## Task 11: Portfolio heatmap (visx treemap)

**Files:**
- Create: `frontend/src/features/heatmap/PortfolioHeatmap.tsx`
- Create: `frontend/src/features/heatmap/heatColor.ts` (pure: P&L % → color)
- Tests: `frontend/tests/features/heatmap/heatColor.test.ts`

**Spec**

- `Panel title="ALLOCATION"`.
- visx `Treemap` with positions sized by `|value|` (market value), colored by unrealized P&L %: green above 0, red below 0, brightness scaled by magnitude (clamped at ±10%).
- Each cell shows `TICKER\n+2.47%` in amber — if cell is too small, show only ticker; if even smaller, hide text.
- Hover → tooltip (visx `useTooltip`) with full details.
- Click → set selected ticker (synced with watchlist & main chart).
- If cash is > 10% of total, render a `CASH` cell too, colored neutral amber-dim.
- Treemap recomputes on every portfolio invalidation; cell colors also track live P&L from the price store (subscribe selectively).

- [ ] **Step 1: `heatColor` pure function** with unit tests — cases: 0% → neutral amber, +5% → mid green, +10% → full green, -3% → mid red. Use `hsl()` interpolation.

- [ ] **Step 2: Heatmap component** using Context7 for visx docs if unfamiliar. libraryId `/hshoff/vx` or search "visx treemap".

- [ ] **Step 3: Tests** — renders 3 cells with correct pixel sizes relative to weights.

- [ ] **Step 4: Manual verify** — execute 2-3 trades, watch heatmap rebalance, colors track P&L on each tick.

- [ ] **Step 5: Commit.** `feat(frontend): portfolio heatmap with live P&L coloring`

---

## Task 12: P&L chart

**Files:**
- Create: `frontend/src/features/pnl/PnLChart.tsx`
- Create: `frontend/src/lib/api/history.ts`
- Tests: `frontend/tests/features/pnl/PnLChart.test.tsx` (smoke)

**Spec**

- `Panel title="NAV HISTORY"`.
- Lightweight Charts line (NOT area — visually distinguish from main chart by using flat line styling in `--accent-blue`).
- Time window toggles: `[ 1H ][ 1D ][ 7D ][ ALL ]` as `KeyCap` buttons in the panel header. Filters client-side from the fetched history.
- Latest point is **augmented in real-time** from the live NAV: every price tick, append `{ time: now, value: liveNav }` to the series (throttled to 1/sec).
- On trade completion, invalidate `["portfolio", "history"]` to pick up the server's new snapshot.

- [ ] **Step 1: History API** — `usePortfolioHistory()` with 15s stale time. Pull `/api/portfolio/history`.

- [ ] **Step 2: Implement `PnLChart`.**

- [ ] **Step 3: Manual verify** — leave running for a few minutes, execute trades, observe line grow and window toggles filter correctly.

- [ ] **Step 4: Commit.** `feat(frontend): P&L history chart with window controls`

---

## Task 13: AI chat panel

**Files:**
- Create: `frontend/src/features/chat/ChatPanel.tsx`
- Create: `frontend/src/features/chat/ChatMessage.tsx`
- Create: `frontend/src/features/chat/ChatInput.tsx`
- Create: `frontend/src/features/chat/ChatActionCard.tsx`
- Create: `frontend/src/features/chat/useChat.ts`
- Create: `frontend/src/lib/api/chat.ts`
- Tests: `frontend/tests/features/chat/*.test.tsx`

**Spec**

- Collapsible right sidebar, default width 360px, min 320, max 520 (drag handle on left edge). Collapse to 32px toggle strip.
- When collapsed: a vertical strip with the word `CHAT` rotated 90° and a message-count badge.
- When open: top of panel says `AI // FINALLY` in accent-purple, below it a thin ASCII divider, then a scroll container with messages, then a fixed input at the bottom.
- Message list — user messages right-aligned with `> ` prefix in `--fg-amber`; assistant messages left-aligned with `◆` prefix in `--accent-purple`; messages take full width.
- The chat flow is **two-turn confirmation**. A normal `/api/chat` message may return `proposed_actions`; these are not executed until the client sends a second request with `confirm_actions`. The UI must make this explicit.
- Assistant messages with **proposed** actions render a `ChatActionCard` beneath the text showing the proposal plus `[ CONFIRM ]` and `[ CANCEL ]` controls.
- Assistant messages with **executed** actions (from `ChatResponse.executed_actions`) render a `ChatActionCard` beneath the text — a small amber-bordered block like:
  ```
  ┌─ PROPOSED / EXECUTED ───────┐
  │ BUY  10 AAPL                │
  │ ADD  PYPL to watchlist      │
  └─────────────────────────────┘
  ```
- Input: a multi-line growable textarea with `> _` prompt and blinking cursor. Enter submits (Shift+Enter for newline). Auto-grows to max 6 lines.
- Sending state: input is disabled, prompt shows an amber sweep (`░▒▓█▓▒░` animated), clearly blocking. The backend returns the full response in one shot (Cerebras fast path) — there is no streaming.
- On success, append assistant message + action cards. On error, append a red system line `!! ERROR: {message}`.
- Chat history is session-local on the frontend (store messages in a Zustand slice). Backend maintains its own `chat_messages` history for LLM context independently. The frontend does not refetch history from the backend unless such an endpoint exists (check PLAN.md §8 — only POST is listed, so we don't fetch).
- Confirm posts `{ "message": "confirm", "confirm_actions": <pending proposed_actions> }`. Cancel is frontend-local and simply clears the pending proposal.
- Portfolio and watchlist invalidation happen **after a successful confirmation turn that returns `executed_actions`**, not on every proposed response.
- Auto-scroll to bottom on new message.

- [ ] **Step 1: Chat store** — `useChatStore` (Zustand slice) holding messages, pending network state, and at most one pending proposal bundle. Test the reducer logic.

- [ ] **Step 2: API hooks** in `frontend/src/lib/api/chat.ts` / `useChat.ts`:
  - `useSendChat()` posts a normal user message to `/api/chat`.
  - `useConfirmChatActions()` posts the confirmation turn with `confirm_actions`.
  - On a proposal response, push the assistant message plus proposed action card into the store and mark the proposal pending.
  - On a confirmation response, push the assistant message plus executed action card into the store, clear the pending proposal, and invalidate `["portfolio"]` and `["watchlist"]`.
  - On cancel, clear the pending proposal locally with no network call.

- [ ] **Step 3: Component tests**:
  - `ChatMessage` renders user vs assistant correctly.
  - `ChatActionCard` renders trade and watchlist actions.
  - `ChatInput` submits on Enter, preserves content on Shift+Enter, disabled while pending.
  - `ChatPanel` scrolls to bottom on new message.

- [ ] **Step 4: Implement** in this order: `ChatMessage` → `ChatActionCard` → `ChatInput` → `ChatPanel`.

- [ ] **Step 5: Manual verify** — with `LLM_MOCK=true` in the backend env for determinism:
  - Send "what's my portfolio?" — expect a response.
  - Send "buy 5 shares of NVDA" — expect a **proposal** card and confirm that the positions table does **not** update yet.
  - Click `[ CONFIRM ]` on that proposal — expect an executed card and then observe the positions table update.
  - Send "add PYPL to watchlist" — expect a proposal card; confirm it and watch the watchlist refresh.
  - Click `[ CANCEL ]` on a proposal and confirm no portfolio/watchlist change occurs.
  - Disconnect backend, send a message, expect a red error line.

- [ ] **Step 6: Commit.** `feat(frontend): AI chat panel with inline action cards`

---

## Task 14: Layout assembly + page-load choreography

**Files:**
- Modify: `frontend/src/app/page.tsx`
- Create: `frontend/src/features/layout/Workstation.tsx`

**Spec — the composed workstation**

Desktop grid (min-width 1280px):

```
┌──────────────────────── HEADER ───────────────────────────┐
│                                                            │
├──────────┬──────────────────────────────────┬─────────────┤
│          │                                  │             │
│ WATCHLIST│          MAIN CHART              │  AI //      │
│  (20%)   │             (55%)                │  FINALLY    │
│          │                                  │   (25%)     │
│          ├──────────────────────────────────┤             │
│          │   ALLOCATION     │  NAV HISTORY  │             │
│          │      (27.5%)     │    (27.5%)    │             │
│          ├──────────────────┴───────────────┤             │
│          │           POSITIONS              │             │
│          │                                  │             │
│          ├──────────────────────────────────┤             │
│          │          TRADE BAR               │             │
└──────────┴──────────────────────────────────┴─────────────┘
```

- Use CSS grid with named areas. Rows: `56px | 1fr | 1fr | auto | 52px`. Columns: `20% | 1fr | 1fr | 360px` (chat collapses to 32px variant).
- Below 1280px: the right chat panel becomes a collapsed strip by default.
- Below 1024px: stack vertically — mobile is not a target but don't break.
- **Staggered reveal on first paint** using Motion — children animate from `opacity 0, y 8` with 40ms stagger in the order: header → watchlist → chart → heatmap → p&l → positions → trade → chat. Total duration < 500ms. Respect `prefers-reduced-motion`.

- [ ] **Step 1: `Workstation.tsx`** — the grid composition. Imports every panel.
- [ ] **Step 2: Motion choreography** — a `motion.div` per grid cell with ordered `delay`. Disable via `useReducedMotion()` when set.
- [ ] **Step 3: Update `page.tsx`** to render `<Workstation />`.
- [ ] **Step 4: Responsive QA** — narrow the window through breakpoints, confirm no clipping or overlap.
- [ ] **Step 5: Full-feature smoke** — at this point the app is substantially done. Click around, trade, chat, add/remove tickers. Note anything misaligned for Task 15.
- [ ] **Step 6: Commit.** `feat(frontend): workstation layout with staggered page-load choreography`

---

## Task 15: Polish pass

**Files:** various (touch as needed)

Aesthetic + interaction polish. This task has no new components — only refinements. Keep commits atomic per concern.

- [ ] **Custom cursor** for the main chart and heatmap areas: `cursor: crosshair` with a tiny amber SVG cursor defined in `globals.css` via `url(data:image/svg+xml;...)`. Falls back to `crosshair` keyword if SVG cursor unsupported.
- [ ] **Focus ring audit** — tab through every interactive element; confirm amber outline is visible and consistent.
- [ ] **Empty states** — empty watchlist, empty positions, empty chat all show appropriate amber-dim placeholders.
- [ ] **Loading skeletons** — where TanStack Query is pending on first load, show `░▒▓█▓▒░` amber sweep placeholders instead of spinners. Single reusable `<SweepLoader />` component in `src/design/`.
- [ ] **Error surfaces** — when a REST call fails, show an inline banner at the top of the affected panel. Do not toast errors from the top-level.
- [ ] **Connection-lost banner** — when the SSE status is `reconnecting` or `closed`, show a fixed-top amber banner: `!! LINK LOST — RECONNECTING …` that disappears on reconnect.
- [ ] **Tab title** — update document title dynamically to `● $10,247.33 — FINALLY` so the tab shows the NAV at a glance.
- [ ] **Keyboard shortcuts** — `/` focuses the trade bar ticker field; `c` toggles the chat panel; `?` shows a small key-cheat overlay.
- [ ] **No-JS fallback** — not required; app is JS-only.
- [ ] **Accessibility sweep** — all icons have aria-labels, all interactive elements are `<button>` or have `role="button"` + keyboard handlers, color is not the sole channel for meaning (every green/red also has a ▲/▼ glyph).

After each change: `npm run test:run && npm run typecheck && npm run lint && npm run build`.

- [ ] **Commit per concern**, e.g. `style(frontend): crosshair cursor over chart areas`, `feat(frontend): connection-lost banner`, etc.

---

## Task 16: Backend integration — static mount + docker wiring

**Files:**
- Modify: `backend/app/main.py` (one block added)
- Modify: `Dockerfile` (if exists) or create one per PLAN.md §11
- Create/modify: `backend/static/` (build output copy destination; `.gitignore` this)

**This is the only task that modifies backend code.**

- [ ] **Step 1: Build the frontend.**

```bash
cd frontend
npm run build
ls out/   # confirms index.html + _next/ exist
```

- [ ] **Step 2: Add a static mount to `backend/app/main.py`.** Append at the end of `create_app()` **after** all routers are registered (order matters — API routes must win):

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

static_dir = Path(__file__).resolve().parent.parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
```

The `if static_dir.exists()` guard ensures development without a built frontend still works (backend-only tests pass).

- [ ] **Step 3: Copy build output to `backend/static/` for local combined testing.**

```bash
cd /home/bgibs/projects/finally
rm -rf backend/static
cp -r frontend/out backend/static
```

- [ ] **Step 4: Verify.**

```bash
cd backend
uv run uvicorn app.main:create_app --factory
# Different terminal:
curl -sI http://localhost:8000/ | head -1         # expect 200
curl -sI http://localhost:8000/api/health | head  # expect 200
```

Open `http://localhost:8000/` in a browser — the full workstation should render and stream prices, with no dev server running.

- [ ] **Step 5: Update `.gitignore`** — add `backend/static/` so the build output isn't committed.

- [ ] **Step 6: Update backend test suite** if the static mount import introduced any warnings. The guard makes the mount a no-op without `static/`; existing tests should pass unchanged. Run:

```bash
cd backend
uv run --extra dev pytest -q
```

- [ ] **Step 7: Commit** in two parts:
  - `feat(backend): mount frontend static export under /` (backend-only changes)
  - `chore(frontend): gitignore backend/static build copy`

---

## Task 17: Documentation + developer ergonomics

**Files:**
- Create: `frontend/README.md`
- Create: `frontend/CLAUDE.md` (mirrors `backend/CLAUDE.md` pattern — short, agent-oriented)
- Modify: root `README.md` (add frontend quickstart section)

- [ ] **`frontend/README.md`** — 50-100 lines, covers:
  - Prereqs (Node 20+, the backend running on :8000)
  - `npm install && npm run dev`
  - `npm run build` (outputs to `out/`)
  - `npm run test`
  - Where to find things (src/app, src/features, src/design)
  - Aesthetic charter pointer — "See `planning/2026-04-21-frontend-implementation.md` §Aesthetic Charter."

- [ ] **`frontend/CLAUDE.md`** — 20-40 lines, targeted at future agents:
  - Where SSE is wired
  - Where queries invalidate on trade/chat
  - How to add a new ticker-column without re-architecting the store
  - "Never use anything other than IBM Plex Mono"

- [ ] **Root `README.md`** — add a short "Frontend" section linking to `frontend/README.md`.

- [ ] **Commit.** `docs: frontend README and agent-facing notes`

---

## Completion Checklist

Before declaring the plan complete, the implementing agent must verify:

- [ ] `cd frontend && npm run test:run` — green
- [ ] `cd frontend && npm run typecheck` — green
- [ ] `cd frontend && npm run lint` — green
- [ ] `cd frontend && npm run build` — green, `out/index.html` exists
- [ ] `cd backend && uv run --extra dev pytest -q` — green
- [ ] Manual walk-through in a browser at `http://localhost:8000/` (combined mode):
  - [ ] Header shows live NAV ticking; clock updates every second; status dot green.
  - [ ] Watchlist shows 10 default tickers; prices flash; sparklines fill in over ~1 minute.
  - [ ] Clicking a ticker updates the main chart.
  - [ ] Main chart re-seeds and streams.
  - [ ] Heatmap renders once positions exist, colors track P&L live.
  - [ ] P&L chart shows a line; time-window toggles filter.
  - [ ] Positions table shows live P&L.
  - [ ] Trade bar executes buys and sells; errors show inline.
  - [ ] Chat panel (with `LLM_MOCK=true`) sends and receives; proposal cards render; confirm executes; cancel discards; portfolio/watchlist invalidate only after confirmation.
  - [ ] Connection-lost banner appears when backend killed, disappears when restored.
  - [ ] Tab through the entire app — focus ring is visible on every control.
  - [ ] Toggle `prefers-reduced-motion` — scanlines disappear, stagger animation stills.
- [ ] Git history is clean: one commit per task (or sub-concern in Task 15), conventional style.
- [ ] No file outside `frontend/`, `backend/app/main.py`, `.gitignore`, and the root `README.md` was modified.

---

## Known deferrals (explicitly out of scope)

- Playwright E2E tests and `test/docker-compose.test.yml` (PLAN.md §12). Track separately.
- Dockerfile and `scripts/start_*.sh` / `scripts/stop_*.sh`. Track separately.
- Mobile layout below 1024px beyond "does not break".
- Theme switcher / light mode. None.
- Settings panel. None.

---

## Rejection Criteria (the reviewer will look for these)

The implementation will be sent back if any of these are observed:

1. Any `border-radius` other than `0` on a surface, button, or input.
2. Any font other than IBM Plex Mono rendered anywhere in the app.
3. A modal with a white background.
4. A loading spinner that rotates (use the amber sweep).
5. A gradient on a surface background (chart fills are fine).
6. Price updates that don't flash on change.
7. SSE reconnect that doesn't surface a status to the user.
8. A trade that blocks the UI with a synchronous dialog.
9. A 404 route, a `/dashboard` path, or any navigation chrome — this is a single-page app.
10. Commits that batch multiple tasks into one.

---

## Notes on library version currency

When implementing anything that touches an external library for the first time, use the Context7 MCP server to fetch current docs. Do NOT rely on training-data memory for:
- Next.js 15 App Router edge cases (static export limitations, client component boundaries)
- TanStack Query v5 API (renamed hooks vs v4)
- Tailwind CSS v4 (`@theme` block, `@import` syntax — very different from v3)
- Lightweight Charts v4 (series API changes)
- Motion (renamed from Framer Motion — package is now `motion`, many APIs preserved)

Example query: `mcp__plugin_context7_context7__resolve-library-id` with `libraryName: "TanStack Query"`, then query for "useMutation optimistic update onMutate onError rollback".
