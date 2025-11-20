## Market Intelligence Swarm Client

React/Vite single-page interface that streams insights from the Market Intelligence Swarm backend. It opens a Server-Sent Events (SSE) connection (configurable via `VITE_SERVER_URL`) to display agent activity logs and a final markdown-style report.

### Environment Variables
- `VITE_SERVER_URL` (optional, default `http://127.0.0.1:5000`): base URL for the Flask API. Required when running inside Docker or any non-localhost environment. Create a `.env` file in this directory (Vite automatically loads it) with:
```
VITE_SERVER_URL=http://server:5000
```

### Prerequisites
- Node.js 20+ (Vite 7 and ESLint 9 expect modern runtimes)
- npm 10+ (ships with Node 20)
- Backend from `server/` running locally on port 5000

### Install Dependencies
From the repo root or `client/`:
```
cd client
npm install
```
Packages include React 19, lucide-react icons, TailwindCSS, and eslint/postcss toolchain (see `package.json` for the full list).

### Develop
```
npm run dev
```
Launches Vite dev server (default `http://127.0.0.1:5173`). The UI assumes the Flask backend is reachable at `http://127.0.0.1:5000`. To target another host, edit the `const url = ...` line inside `src/App.jsx`.

### Build & Preview
```
npm run build
npm run preview
```
`build` emits production assets in `client/dist/`. `preview` serves the built bundle locally.

### Lint
```
npm run lint
```
Runs ESLint with the config defined in `package.json` (`eslint .`), covering JSX and hooks rules.

### Feature Highlights
- Live agent activity console (SSE stream of `agent_message` payloads)
- Markdown rendering of the final report
- Manual stop control for the stream
- Example prompts baked into the empty state for quick starts
# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Babel](https://babeljs.io/) (or [oxc](https://oxc.rs) when used in [rolldown-vite](https://vite.dev/guide/rolldown)) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.
