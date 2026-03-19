import re

with open('src/houndmind_ai/optional/telemetry_dashboard.py', 'r') as f:
    content = f.read()

new_html = """_DASHBOARD_HTML = \"\"\"
<!doctype html>
<html lang="en" data-theme="system">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>HoundMind Control Panel</title>
    <style>
        /* Design Token System Foundation */
        :root {
            /* Light Theme Tokens */
            --bg-primary: #f8fafc;
            --bg-secondary: #ffffff;
            --text-primary: #0f172a;
            --text-secondary: #475569;
            --border-color: #e2e8f0;
            --accent-primary: #3b82f6;
            --accent-hover: #2563eb;
            --card-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);

            /* Typography Scale */
            --text-xs: 0.75rem;
            --text-sm: 0.875rem;
            --text-base: 1rem;
            --text-lg: 1.125rem;
            --text-xl: 1.25rem;

            /* Spacing System */
            --space-1: 0.25rem;
            --space-2: 0.5rem;
            --space-3: 0.75rem;
            --space-4: 1rem;
            --space-6: 1.5rem;
            --space-8: 2rem;

            /* Layout System */
            --container-max: 1280px;
            --border-radius: 12px;
            --transition-speed: 0.3s;
        }

        /* Dark Theme Tokens */
        [data-theme="dark"] {
            --bg-primary: #020617;
            --bg-secondary: #0f172a;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --border-color: #1e293b;
            --accent-primary: #38bdf8;
            --accent-hover: #7dd3fc;
            --card-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.3), 0 2px 4px -2px rgb(0 0 0 / 0.3);
        }

        /* System Theme Preference */
        @media (prefers-color-scheme: dark) {
            :root:not([data-theme="light"]) {
                --bg-primary: #020617;
                --bg-secondary: #0f172a;
                --text-primary: #f8fafc;
                --text-secondary: #94a3b8;
                --border-color: #1e293b;
                --accent-primary: #38bdf8;
                --accent-hover: #7dd3fc;
                --card-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.3), 0 2px 4px -2px rgb(0 0 0 / 0.3);
            }
        }

        /* Base Reset & Typography */
        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.5;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            transition: background-color var(--transition-speed), color var(--transition-speed);
        }

        /* Layout Architecture */
        .container {
            width: 100%;
            max-width: var(--container-max);
            margin: 0 auto;
            padding: var(--space-4);
            display: flex;
            flex-direction: column;
            gap: var(--space-6);
            flex: 1;
        }

        .header {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: var(--space-4);
            padding: var(--space-4) 0;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: var(--space-2);
        }

        .header-title {
            display: flex;
            align-items: center;
            gap: var(--space-3);
        }

        .header h1 {
            font-size: var(--text-xl);
            font-weight: 600;
            letter-spacing: -0.025em;
        }

        .header-controls {
            display: flex;
            align-items: center;
            gap: var(--space-4);
            flex-wrap: wrap;
        }

        /* Component: Cards */
        .card {
            background-color: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--border-radius);
            padding: var(--space-6);
            box-shadow: var(--card-shadow);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            display: flex;
            flex-direction: column;
            gap: var(--space-4);
            overflow: hidden;
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: var(--space-3);
            margin-bottom: var(--space-2);
        }

        .card-title {
            font-size: var(--text-lg);
            font-weight: 600;
        }

        .meta {
            color: var(--text-secondary);
            font-size: var(--text-sm);
        }

        /* Grid Patterns */
        .grid-main {
            display: grid;
            grid-template-columns: 1fr;
            gap: var(--space-6);
        }

        @media (min-width: 1024px) {
            .grid-main {
                grid-template-columns: 3fr 2fr;
                align-items: start;
            }
        }

        .grid-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: var(--space-4);
        }

        .stat-item {
            background-color: var(--bg-primary);
            padding: var(--space-3);
            border-radius: calc(var(--border-radius) / 1.5);
            border: 1px solid var(--border-color);
            text-align: center;
        }

        .stat-value {
            font-size: var(--text-lg);
            font-weight: 700;
            color: var(--accent-primary);
            margin-top: var(--space-1);
        }

        /* Media / Camera Feed */
        .camera-container {
            background-color: #000;
            border-radius: calc(var(--border-radius) - 4px);
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 300px;
            position: relative;
        }

        #camera {
            width: 100%;
            height: auto;
            max-height: 600px;
            object-fit: contain;
        }

        /* Typography / Code Output */
        pre {
            background-color: var(--bg-primary);
            color: var(--text-primary);
            padding: var(--space-4);
            border-radius: calc(var(--border-radius) / 1.5);
            border: 1px solid var(--border-color);
            font-family: 'JetBrains Mono', monospace, Consolas;
            font-size: var(--text-xs);
            overflow-x: auto;
            max-height: 400px;
            white-space: pre-wrap;
            word-break: break-all;
        }

        /* Buttons & Interactions */
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: var(--space-2);
            padding: var(--space-2) var(--space-4);
            font-size: var(--text-sm);
            font-weight: 500;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s ease;
            border: 1px solid transparent;
            text-decoration: none;
        }

        .btn-primary {
            background-color: var(--accent-primary);
            color: #ffffff;
        }

        .btn-primary:hover {
            background-color: var(--accent-hover);
            transform: translateY(-1px);
        }

        .btn-outline {
            background-color: transparent;
            border-color: var(--border-color);
            color: var(--text-primary);
        }

        .btn-outline:hover {
            background-color: var(--bg-primary);
            border-color: var(--accent-primary);
            color: var(--accent-primary);
        }

        .btn:focus-visible {
            outline: 2px solid var(--accent-primary);
            outline-offset: 2px;
        }

        /* Theme Toggle Component */
        .theme-toggle {
            display: inline-flex;
            align-items: center;
            background-color: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 24px;
            padding: 4px;
            gap: 2px;
        }

        .theme-toggle-option {
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: var(--text-xs);
            font-weight: 500;
            color: var(--text-secondary);
            background: transparent;
            border: none;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .theme-toggle-option:hover {
            color: var(--text-primary);
        }

        .theme-toggle-option.active {
            background-color: var(--accent-primary);
            color: #ffffff;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }

        .status-indicator {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: #10b981; /* Success Green */
            box-shadow: 0 0 8px #10b981;
        }

        .status-indicator.offline {
            background-color: #ef4444; /* Error Red */
            box-shadow: 0 0 8px #ef4444;
        }

        /* Badges */
        .badge {
            display: inline-flex;
            align-items: center;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: var(--text-xs);
            font-weight: 500;
            background-color: var(--bg-primary);
            border: 1px solid var(--border-color);
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header & Top Navigation -->
        <header class="header">
            <div class="header-title">
                <div class="status-indicator" id="connection_status" title="Connection Status"></div>
                <h1>HoundMind Control Panel</h1>
                <span class="badge" id="trace_id" title="Current Trace ID">Waiting for data...</span>
                <button id="copy_trace" class="btn btn-outline" style="padding: 2px 6px; font-size: 0.7rem;" aria-label="Copy Trace ID">Copy ID</button>
            </div>

            <div class="header-controls">
                <button id="download_bundle" class="btn btn-outline" aria-label="Download Support Bundle">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                    Support Bundle
                </button>

                <!-- Theme Toggle -->
                <div class="theme-toggle" role="radiogroup" aria-label="Theme selection">
                    <button class="theme-toggle-option" data-theme="light" role="radio" aria-checked="false" aria-label="Light mode">☀️</button>
                    <button class="theme-toggle-option" data-theme="dark" role="radio" aria-checked="false" aria-label="Dark mode">🌙</button>
                    <button class="theme-toggle-option active" data-theme="system" role="radio" aria-checked="true" aria-label="System mode">💻</button>
                </div>
            </div>
        </header>

        <!-- Main Content Grid -->
        <main class="grid-main">
            <!-- Left Column: Camera Feed & Quick Stats -->
            <div style="display: flex; flex-direction: column; gap: var(--space-6);">
                <section class="card" aria-labelledby="camera-title">
                    <div class="card-header">
                        <h2 id="camera-title" class="card-title">Live Vision</h2>
                        <span class="badge"><span id="vision_fps">--</span> FPS</span>
                    </div>
                    <div class="camera-container">
                        <img id="camera" src="{{CAMERA_PATH}}" alt="Live camera feed from robot"/>
                    </div>
                </section>

                <section class="card" aria-labelledby="stats-title">
                    <div class="card-header">
                        <h2 id="stats-title" class="card-title">Performance Telemetry</h2>
                    </div>
                    <div class="grid-stats">
                        <div class="stat-item">
                            <div class="meta">Tick Rate</div>
                            <div class="stat-value"><span id="tick_rate">--</span> Hz</div>
                        </div>
                        <div class="stat-item">
                            <div class="meta">Memory Used</div>
                            <div class="stat-value"><span id="mem_used">--</span>%</div>
                        </div>
                        <div class="stat-item">
                            <div class="meta">CPU Load (1m)</div>
                            <div class="stat-value"><span id="cpu_load">--</span></div>
                        </div>
                        <div class="stat-item">
                            <div class="meta">CPU Temp</div>
                            <div class="stat-value"><span id="cpu_temp">--</span>°C</div>
                        </div>
                    </div>
                </section>
            </div>

            <!-- Right Column: Data Streams & Controls -->
            <div style="display: flex; flex-direction: column; gap: var(--space-6);">
                <section class="card" aria-labelledby="snapshot-title">
                    <div class="card-header">
                        <div>
                            <h2 id="snapshot-title" class="card-title">State Snapshot</h2>
                            <div class="meta">Synchronizes every 500ms</div>
                        </div>
                        <button id="refresh" class="btn btn-primary" aria-label="Refresh Data Streams">Refresh</button>
                    </div>
                    <pre id="output" tabindex="0" aria-label="Raw snapshot JSON output">Connecting to telemetry stream...</pre>
                </section>

                <section class="card" aria-labelledby="slam-title">
                    <div class="card-header">
                        <h2 id="slam-title" class="card-title">SLAM Data</h2>
                        <div style="display: flex; gap: var(--space-2);">
                            <button id="download_map" class="btn btn-outline btn-sm" aria-label="Download Map">Map</button>
                            <button id="download_traj" class="btn btn-outline btn-sm" aria-label="Download Trajectory">Trajectory</button>
                        </div>
                    </div>
                    <pre id="slam" tabindex="0" aria-label="SLAM data output">No SLAM data available</pre>
                </section>
            </div>
        </main>
    </div>

    <script>
        // --- Theme Management System (ArchitectUX Standard) ---
        class ThemeManager {
            constructor() {
                this.currentTheme = this.getStoredTheme() || 'system';
                this.applyTheme(this.currentTheme);
                this.initializeToggle();

                // Listen for system theme changes
                window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
                    if (this.currentTheme === 'system') {
                        // The CSS handles the visual switch, but we might want to trigger events if needed
                    }
                });
            }

            getStoredTheme() {
                return localStorage.getItem('houndmind-theme');
            }

            applyTheme(theme) {
                if (theme === 'system') {
                    document.documentElement.setAttribute('data-theme', 'system');
                } else {
                    document.documentElement.setAttribute('data-theme', theme);
                }
                localStorage.setItem('houndmind-theme', theme);
                this.currentTheme = theme;
                this.updateToggleUI();
            }

            initializeToggle() {
                const options = document.querySelectorAll('.theme-toggle-option');
                options.forEach(opt => {
                    opt.addEventListener('click', (e) => {
                        const newTheme = e.currentTarget.dataset.theme;
                        this.applyTheme(newTheme);
                    });
                });
            }

            updateToggleUI() {
                const options = document.querySelectorAll('.theme-toggle-option');
                options.forEach(option => {
                    const isActive = option.dataset.theme === this.currentTheme;
                    option.classList.toggle('active', isActive);
                    option.setAttribute('aria-checked', isActive.toString());
                });
            }
        }

        // Initialize theme
        document.addEventListener('DOMContentLoaded', () => {
            new ThemeManager();
        });

        // --- Application Logic ---
        const camera = document.getElementById('camera');
        const out = document.getElementById('output');

        // Stats elements
        const fpsLabel = document.getElementById('vision_fps');
        const tickRate = document.getElementById('tick_rate');
        const memUsed = document.getElementById('mem_used');
        const cpuLoad = document.getElementById('cpu_load');
        const cpuTemp = document.getElementById('cpu_temp');
        const statusIndicator = document.getElementById('connection_status');

        let consecutiveErrors = 0;

        async function tick() {
            try {
                const res = await fetch('/snapshot');
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();

                // Update Connection Status
                consecutiveErrors = 0;
                statusIndicator.classList.remove('offline');

                // Output raw JSON
                out.textContent = JSON.stringify(data, null, 2);

                // Update Trace ID
                const traceEl = document.getElementById('trace_id');
                traceEl.textContent = data.trace_id || 'N/A';

                // Update Performance Telemetry
                const perf = data.performance_telemetry || {};
                fpsLabel.textContent = perf.vision_fps ? perf.vision_fps.toFixed(1) : '--';
                tickRate.textContent = perf.tick_hz_actual ? perf.tick_hz_actual.toFixed(1) : '--';
                memUsed.textContent = perf.mem_used_pct ? perf.mem_used_pct.toFixed(1) : '--';
                cpuLoad.textContent = perf.cpu_load_1m ? perf.cpu_load_1m.toFixed(2) : '--';
                cpuTemp.textContent = perf.cpu_temp_c ? perf.cpu_temp_c.toFixed(1) : '--';

                // Update SLAM Data
                const slamEl = document.getElementById('slam');
                if(data.slam_map_data || data.slam_trajectory) {
                    slamEl.textContent = JSON.stringify({
                        map: data.slam_map_data ? "Map data available" : null,
                        trajectory: data.slam_trajectory ? "Trajectory available" : null
                    }, null, 2);
                } else {
                    slamEl.textContent = 'No SLAM data available';
                }
            } catch(e) {
                consecutiveErrors++;
                if(consecutiveErrors > 2) {
                    statusIndicator.classList.add('offline');
                }
                out.textContent = 'Connection Error: ' + e.message;
            }
        }

        // Avoid caching single-frame camera endpoints
        function reloadCamera() {
            const base = camera.getAttribute('src').split('?')[0];
            camera.src = base + '?ts=' + Date.now();
        }

        // Event Listeners
        document.getElementById('refresh').addEventListener('click', () => {
            tick();
            reloadCamera();
        });

        document.getElementById('copy_trace').addEventListener('click', () => {
            const txt = document.getElementById('trace_id').textContent || '';
            if(!txt || txt === 'Waiting for data...' || txt === 'N/A') return;
            try {
                navigator.clipboard.writeText(txt);
                const btn = document.getElementById('copy_trace');
                const origText = btn.textContent;
                btn.textContent = 'Copied!';
                setTimeout(() => btn.textContent = origText, 2000);
            } catch(e) {
                alert('Copy failed: ' + e);
            }
        });

        document.getElementById('download_bundle').addEventListener('click', async () => {
            const txt = document.getElementById('trace_id').textContent || '';
            if(!txt || txt === 'Waiting for data...' || txt === 'N/A') {
                alert('No trace ID available. Cannot generate bundle.');
                return;
            }
            try {
                const btn = document.getElementById('download_bundle');
                const origHtml = btn.innerHTML;
                btn.innerHTML = 'Downloading...';
                btn.disabled = true;

                const res = await fetch('/download_support_bundle?trace_id=' + encodeURIComponent(txt));
                if(!res.ok) {
                    const err = await res.json().catch(()=>null);
                    alert('Failed to create bundle: ' + (err && err.error ? err.error : res.statusText));
                } else {
                    const blob = await res.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `support_bundle_${txt}.zip`;
                    a.click();
                    URL.revokeObjectURL(url);
                }
                btn.innerHTML = origHtml;
                btn.disabled = false;
            } catch(e) {
                alert('Download failed: ' + e);
                document.getElementById('download_bundle').disabled = false;
            }
        });

        document.getElementById('download_map').addEventListener('click', async () => {
            const res = await fetch('/download_slam_map');
            if(res.ok) {
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url; a.download = 'slam_map.json'; a.click();
            } else { alert('No map data available on server') }
        });

        document.getElementById('download_traj').addEventListener('click', async () => {
            const res = await fetch('/download_slam_trajectory');
            if(res.ok) {
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url; a.download = 'slam_trajectory.json'; a.click();
            } else { alert('No trajectory data available on server') }
        });

        // Main Loop
        setInterval(() => { tick(); reloadCamera(); }, 500);
        tick();
    </script>
</body>
</html>
\"\"\""""

# Replace the HTML block inside the python file
pattern = r'_DASHBOARD_HTML = """(.*?)"""'
new_content = re.sub(pattern, new_html.replace('\\', '\\\\'), content, flags=re.DOTALL)

with open('src/houndmind_ai/optional/telemetry_dashboard.py', 'w') as f:
    f.write(new_content)

print("Dashboard UI updated.")
