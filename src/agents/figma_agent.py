import os
from src.agents.base_agent import BaseAgent
from src.utils.figma_utils import (
    extract_file_key,
    fetch_figma_file,
    fetch_figma_nodes,
    build_screen_inventory_from_nodes,
    extract_design_summary,
)

_SYSTEM = (
    "You are a senior product engineer writing a context engineering planning document. "
    "Your goal is NOT to write code — it is to describe the application so completely in plain language "
    "that an AI coding assistant (Claude Code or GitHub Copilot) reading this document will understand "
    "exactly what to build, why each piece exists, how the pieces connect, and what conventions to follow. "
    "Write in clear prose and structured bullet lists. No code blocks, no TypeScript or HTML syntax. "
    "Every description must be specific enough that there is only one sensible way to implement it. "
    "Vague words like 'handle errors appropriately' or 'use best practices' are not allowed — "
    "always state exactly what should happen."
)

_CONTEXT_BLOCK = """\
━━━ FIGMA DESIGN ANALYSIS ━━━
{design_summary}

━━━ API SPECIFICATION ━━━
{endpoints}
{repo_block}
━━━ USER REQUIREMENTS ━━━
{requirements}
"""


def _context(design_summary, endpoints, repo_context, requirements):
    repo_block = (
        f"\n━━━ REFERENCE REPOSITORY ARCHITECTURE ━━━\n{repo_context}\n"
        if repo_context else ""
    )
    req = requirements.strip() or "None specified — use sensible Angular 22 defaults."
    return _CONTEXT_BLOCK.format(
        design_summary=design_summary,
        endpoints=endpoints,
        repo_block=repo_block,
        requirements=req,
    )


class FigmaAgent(BaseAgent):
    def __init__(self, model_id: str):
        super().__init__(name="figma", description="Figma design analysis agent", model_id=model_id)

    # ── Stage 1: Figma analysis ──────────────────────────────────────────────

    def _ai_describe_design(self, design_name: str, screen_inventory: list) -> str:
        """Use Claude to turn raw Figma node data into a structured, developer-ready screen description."""
        raw_data = f"Application: {design_name}\n\n"
        for screen in screen_inventory:
            raw_data += f"=== Frame: {screen['name']} ===\n"
            if screen["texts"]:
                raw_data += f"Text labels found: {' | '.join(screen['texts'][:50])}\n"
            if screen["ui_elements"]:
                raw_data += f"Named UI elements: {', '.join(screen['ui_elements'][:25])}\n"
            if screen["components"]:
                raw_data += f"Component instances: {', '.join(screen['components'][:20])}\n"
            raw_data += "\n"

        prompt = f"""You are a senior product engineer analyzing a Figma design for "{design_name}".
Below is raw data extracted directly from the Figma API (text labels, element names, component instances).

{raw_data}

Your task: produce a precise, developer-ready screen inventory that will be the single source of truth for Angular 22 implementation planning.

━━━ CRITICAL STEP FIRST — Identify the Navigation Structure ━━━

Before describing any screen, scan ALL text labels for navigation patterns.
If you find a group of labels that look like page names (e.g. "Dashboard", "Transactions", "Reports", "Settings", "Home", "Analytics", "Profile", "Users", "Orders", "Payments", "Overview", "History"), these are sidebar or top-navigation items.

Write this section FIRST at the top of your output:

## Application Layout & Navigation

**Navigation type:** [Left sidebar | Top navigation bar | Bottom tab bar | None detected]

**Shell layout:** [Describe the overall frame: e.g., "Fixed left sidebar (240px wide) + main content area that fills remaining width. Sidebar is visible on all authenticated screens."]

**Navigation items (in order as they appear):**
- [Item 1 label] → route: /[path] — [what this screen shows]
- [Item 2 label] → route: /[path] — [what this screen shows]
- (list every item found)

**Shared header (if present):** [Describe: app name/logo, date/time display, user avatar, notification bell, any other persistent header elements]

━━━ Then describe each screen ━━━

Rules:
- If all text comes from one large frame (HTML-imported design), identify distinct visual panels and treat each as a named screen.
- Use the exact text labels from the raw data — do not paraphrase or invent values.
- Infer routes from nav item names (Dashboard → /dashboard, Transactions → /transactions).
- Do NOT write code. Describe in structured plain English.

For each screen write:

### Screen: [Name]
**Route:** /[path]
**Content sections:**
- [Section name]: [Exact description — card labels, chart type+axes, table columns, list format, etc.]
**Actionable elements:** [Every button, link, filter, or clickable element and what it does]
**Data requirements:** [What API data this screen fetches on load]

Be thorough. A developer must be able to implement every screen and the full navigation shell without ever seeing the original Figma file."""

        return self.invoke_claude(prompt, _SYSTEM, max_tokens=3500)

    def analyze_screens(self, figma_url: str) -> dict:
        token = os.getenv("FIGMA_TOKEN")
        if not token:
            raise RuntimeError("FIGMA_TOKEN environment variable is not set.")

        file_key = extract_file_key(figma_url)
        figma_data = fetch_figma_file(file_key, token)
        design_name = figma_data.get("name", "Figma Design")

        # Collect top-level FRAME names + IDs (handles SECTION nesting)
        screens_meta = []
        def _collect_frames(nodes, max_depth=3, depth=0):
            for node in nodes:
                ntype = node.get("type", "")
                if ntype == "FRAME":
                    screens_meta.append({
                        "name": node.get("name", "Screen"),
                        "id": node.get("id", ""),
                    })
                elif ntype in ("SECTION", "GROUP", "CANVAS") and depth < max_depth:
                    _collect_frames(node.get("children", []), max_depth, depth + 1)

        for page in figma_data.get("document", {}).get("children", []):
            _collect_frames(page.get("children", []))

        # Fetch detailed node content so we get full text/component data
        screen_inventory = []
        if screens_meta:
            screen_ids = [s["id"] for s in screens_meta if s["id"]]
            try:
                nodes_response = fetch_figma_nodes(file_key, screen_ids[:5], token)
                screen_inventory = build_screen_inventory_from_nodes(screens_meta, nodes_response)
            except Exception:
                # Fallback: minimal inventory from the shallow file data
                screen_inventory = [
                    {"name": s["name"], "id": s["id"], "texts": [], "ui_elements": [], "components": []}
                    for s in screens_meta
                ]

        # Use Claude to convert raw Figma data into a structured design description
        try:
            design_summary = self._ai_describe_design(design_name, screen_inventory)
        except Exception:
            design_summary = extract_design_summary(figma_data)

        screen_count = len(screens_meta)
        screen_lines = "\n".join(f"{i+1}. {s['name']}" for i, s in enumerate(screens_meta[:20]))
        suggested_endpoints = (
            f"Screens found in your design ({screen_count} total):\n\n"
            + (screen_lines or "(No named screens detected — please describe your screens in the next step)")
            + ("\n…and more" if screen_count > 20 else "")
        )

        return {
            "design_summary": design_summary,
            "design_name": design_name,
            "screen_count": screen_count,
            "suggested_endpoints": suggested_endpoints,
        }

    # ── Stage 2: Three focused planning documents ────────────────────────────

    def _doc1_prompts(self, design_summary, design_name, endpoints, repo_context, requirements):
        ctx = _context(design_summary, endpoints, repo_context, requirements)
        prompt = f"""Write Document 1 of 3: **Project Overview & Architecture** for the application: {design_name}

{ctx}

The FIGMA DESIGN ANALYSIS above contains a complete screen inventory. Use it as the definitive reference for every architectural decision below.

## 1. Project Purpose & Context
- Exactly what problem this application solves and for whom (derive from the design and domain)
- Every business concept a developer must understand before touching code — define financial terms, domain rules, or data relationships as needed
- Non-obvious constraints that affect the entire architecture (e.g., "all monetary values display with 2 decimal places and a $ prefix", "all dates display as MM/DD/YYYY")

## 2. Technology Decisions
State every decision as a firm, non-negotiable rule with the exact reason:
- Angular version: Angular 22 with standalone components — NgModules are forbidden everywhere
- Component creation: standalone: true on every component, directive, and pipe — no exceptions
- Dependency injection: inject() function only — never constructor injection parameters
- Template control flow: @if, @for, @switch only — *ngIf, *ngFor, NgIf pipe, AsyncPipe in templates are all forbidden
- Signals: use signal() for writable local state, computed() for derived values, toSignal() to convert HttpClient observables, effect() only for DOM side effects — never for state updates
- HTTP: HttpClient with withFetch() in provideHttpClient() in app.config.ts; every call typed with a generic, e.g. this.http.get<DashboardSummary>('/api/dashboard/summary')
- Forms: ReactiveFormsModule only; every form is FormGroup with a typed shape interface; no untyped FormControl or AbstractControl
- UI library: Angular Material 18+ with individual component imports (e.g., import MatButton from @angular/material/button — MatButtonModule is forbidden)
- Styling: SCSS with Material Design tokens (--mat-*) for all colors and typography — no hardcoded hex values or pixel font sizes in component styles
- Error handling: every failed HTTP call shows a MatSnackBar with the server's error message or "Something went wrong. Please try again." if the server returns no message; 401 responses clear the auth token and redirect to /login preserving the current URL as ?returnUrl=
- Auth: JWT stored in a memory variable inside AuthService (never localStorage or sessionStorage); sent as "Authorization: Bearer <token>" header by an HTTP interceptor
- Environment: only apiUrl lives in environment.ts — all API base URLs are derived from it; no other URL is ever hardcoded

## 3. Folder Structure
Describe every folder under src/app/ with: what belongs there, what is explicitly forbidden, and why the boundary exists:
- core/ — services, interceptors, guards — no components, no template files
- features/ — one subfolder per route (dashboard/, transactions/, reports/, settings/) — each contains its component file, service file, and model file; no cross-feature imports
- shared/ — reusable presentational components only (e.g., metric-card, stat-badge) — no business logic, no API calls
- models/ — TypeScript interfaces only, no classes, no decorators — one file per domain entity
If a reference repository was provided, state exactly where this structure aligns or departs from it.

## 4. Routing & Navigation Architecture
- If the Figma design has a sidebar or top navigation, ALL feature routes must be children of a ShellComponent (path: '', loadComponent: AppShellComponent). The shell renders the sidebar + <router-outlet>. Feature components render inside the outlet, never standalone.
- Route tree structure:
  - path: '' → AppShellComponent (shell with sidebar)
    - path: '' → redirectTo: 'dashboard', pathMatch: 'full'
    - path: 'dashboard' → loadComponent: DashboardComponent
    - path: 'transactions' → loadComponent: TransactionsComponent
    - (repeat for every nav item from the Figma design)
  - path: 'login' → loadComponent: LoginComponent (no shell, no sidebar)
- Auth guard: canActivate checks AuthService.isAuthenticated(); redirects to /login with returnUrl query param on failure; applied to the shell route so all children are protected in one place
- HTTP interceptor: adds Authorization: Bearer header on every request; on 401, calls AuthService.logout() then navigates to /login?returnUrl=<current_url>
- All feature routes are lazy-loaded with loadComponent() to reduce initial bundle size

## 5. Bootstrap Instructions for Claude Code
Provide the EXACT sequence of terminal commands and file edits — no options, no alternatives:
1. Exact ng new command with every flag
2. Exact ng add @angular/material command
3. Exact npm install command for all additional packages (charts, etc.)
4. Exact content to add to app.config.ts (providers array)
5. Exact content to add to app.routes.ts (all routes with lazy loading)
6. Exact content to add to styles.scss (Material theme import + global resets)
7. Exact content to add to environment.ts
8. File creation order: models → services → guards → interceptors → shared components → feature components

End with exactly this sentence: "Do not ask the user any questions. Use the three planning documents as the single source of truth."
"""
        return _SYSTEM, prompt

    def _doc2_prompts(self, design_summary, design_name, endpoints, repo_context, requirements):
        ctx = _context(design_summary, endpoints, repo_context, requirements)
        prompt = f"""Write Document 2 of 3: **Screens, Components & User Flows** for the application: {design_name}

{ctx}

CRITICAL: The FIGMA DESIGN ANALYSIS above contains the authoritative screen inventory. Every screen, every section, every UI element described there must appear in this document. Do not invent screens that are not in the design. Do not omit screens that are in the design.

## 0. Application Shell & Navigation Layout

This section must be completed first, before any screen. It defines the layout frame that wraps every authenticated screen.

### AppShellComponent
- **File path:** src/app/core/layout/app-shell.component.ts
- **Responsibility:** renders the full-page layout — sidebar on the left, main content router-outlet on the right — for every authenticated screen
- **Template structure:** outer flex container (height: 100vh), left child is SidebarNavComponent (fixed width from design), right child is a flex-1 div containing the page header (if present) and <router-outlet>
- **Which routes use this shell:** all authenticated feature routes as children (dashboard, transactions, reports, settings, and any others from the design)

### SidebarNavComponent
- **File path:** src/app/core/layout/sidebar-nav.component.ts
- **Responsibility:** renders the vertical list of navigation items; highlights the active route
- **Nav items:** list every item exactly as it appears in the Figma design — item label, Material icon name (infer: Dashboard→dashboard, Transactions→receipt_long, Reports→bar_chart, Settings→settings), routerLink path
- **Active state:** routerLinkActive directive on each nav item applies an active CSS class (accent background, bold label)
- **Inputs:** none (reads Router state directly via routerLinkActive)
- **Angular Material used:** MatListModule with mat-nav-list and mat-list-item; MatIconModule for icons

### AppHeaderComponent (if the design has a persistent top header inside the shell)
- **File path:** src/app/core/layout/app-header.component.ts
- **Responsibility:** renders the top bar inside the main content area — app name/logo, current date, user avatar, notification icon, or any other persistent header elements visible in the design
- **Inputs:** pageTitle: string — the current page name, passed from each feature component via a HeaderService or @Input
- **Angular Material used:** MatToolbar, MatIconButton, MatIcon

## 1. Screen Inventory
For every screen in the FIGMA DESIGN ANALYSIS, write a sub-section in this exact format:

### Screen: [Name from Figma]
- **Route:** [exact path, e.g. /dashboard]
- **Access:** [public | requires authentication]
- **On arrival:** Describe every visible region — sidebar state, page title, every card (label + value type), every chart (type, axes, data shown), every table (column names and data type in each column), every button and its label
- **Loading state:** Which spinner or skeleton shows where while data loads; which elements are disabled
- **Error state:** Exact message shown if the API call fails; where it appears (inline, snackbar, etc.)
- **Empty state:** What appears if the API returns an empty list or zero values
- **User actions on this screen:** For each action — Action label → validation check (if any) → API call triggered → what the UI shows while waiting → exact success outcome (message text, navigation, list refresh) → exact error outcome
- **Navigation from this screen:** Every link, button, or nav item that navigates away; destination route

## 2. Component Inventory
For every standalone component (both routed pages and reusable pieces):

### [ComponentName] (e.g., DashboardComponent, MetricCardComponent)
- **File path:** src/app/features/[feature]/[name].component.ts or src/app/shared/[name]/[name].component.ts
- **Responsibility:** one sentence
- **Inputs:** each input — name, type, required/optional, what it represents
- **Outputs:** each output — name, EventEmitter type, what user action triggers it
- **Signals:** each signal or computed signal — name, type, purpose
- **Services injected:** service name and which methods are called
- **Template structure:** describe each @if block, each @for loop, each mat-* component, each button — no HTML syntax, just plain English

## 3. Angular Material Components Per Screen
For each screen, list every Angular Material component used with exact configuration:
- MatTable: list every column definition (columnDef name, header label, cell data field, pipe applied if any); state whether MatSort and MatPaginator are included and their page-size options
- MatCard: describe content (title, subtitle, body, actions)
- MatButton: label text, color attribute (primary/accent/warn), whether it is raised/flat/stroked
- MatFormField: label, input type, validators applied, error message for each validator
- MatChip: label source, color logic
- MatSnackBar: duration, action label, position (bottom-center)
- Charts: if using ngx-charts, name the chart type, xAxis/yAxis labels, colorScheme; if using Chart.js, name the chart type and dataset configuration

## 4. Shared Components
For every reusable component in shared/:
- What it renders in one sentence
- Every input with its type and purpose
- Every output with its type and trigger
- Which screens use it
"""
        return _SYSTEM, prompt

    def _doc3_prompts(self, design_summary, design_name, endpoints, repo_context, requirements):
        ctx = _context(design_summary, endpoints, repo_context, requirements)
        prompt = f"""Write Document 3 of 3: **API, Data Models & Implementation Guide** for the application: {design_name}

{ctx}

## 1. Data Models
For every entity, write its complete TypeScript interface definition in plain English — name every field, its type, whether it is required or optional, and any constraint:

### [EntityName]
- What this entity represents in the business domain
- Every field: fieldName — TypeScript type — required or optional — constraint or format (e.g., "ISO 8601 date string", "positive number", "one of: income | expense | transfer")
- Which API endpoints return or accept this entity
- Relationships to other entities

Example format (do NOT use code blocks — describe the fields as a bullet list):
- id: string — required — UUID from the server, never generated on the client
- amount: number — required — monetary value in dollars (positive for income, negative for expenses)
- category: string — required — one of the allowed category values returned by GET /api/categories
- date: string — required — ISO 8601 format, displayed as MM/DD/YYYY in the UI
- description: string — optional — free text, max 255 characters, truncated to 40 chars in table cells

## 2. API Integration
For every endpoint in the API specification:

### [METHOD] [path]
- **Purpose:** one sentence describing what this call does in the UI
- **Triggered by:** which page lifecycle (ngOnInit) or user action calls this
- **Request:** every path param, query param, and body field with type and required/optional
- **Response shape:** every field the UI reads from the response, its type, and how the UI uses it
- **Loading state:** exact UI behavior while the call is in-flight (spinner location, disabled buttons, skeleton rows)
- **Success:** exact UI change — if a snackbar: the exact message text; if navigation: the destination route; if list refresh: whether it re-fetches or updates in-place
- **Errors:** exact message for 400 (validation), 401 (redirect to login), 403 ("You do not have permission to perform this action."), 404 ("Record not found."), 500 ("Something went wrong. Please try again.") — each displayed in a MatSnackBar at bottom-center for 4000ms

## 3. Services
For every service file:

### [ServiceName] (e.g., DashboardService, TransactionService)
- **File path:** src/app/features/[feature]/[name].service.ts or src/app/core/[name].service.ts
- **Responsibility:** one sentence
- **Dependencies:** list every injected dependency and why it is needed
- For every method:
  - Method name and purpose
  - Parameters with types
  - HTTP verb, exact URL template (using this.env.apiUrl prefix)
  - Request body or query params
  - Return type (Observable<T>)
  - Any transformation applied before returning (e.g., map response.data to typed array)
  - Error handling: whether it catches and rethrows, or lets the component handle via catchError in the template

## 4. Business Rules & Validation
- Every reactive form field: field name — validator list — exact error message string for each validator (used in mat-error)
- Permission rules: which routes or actions require which roles; what happens when a user without permission tries to access them
- Data display rules: currency formatting (always 2 decimal places, $ prefix), date formatting (MM/DD/YYYY), percentage formatting (always 1 decimal place with % suffix), negative number display (red color, parentheses or minus sign)
- Edge cases the UI must handle: empty list message text, single-item list (no pagination), null optional fields (display "-" or "N/A"), very long text in table cells (truncate with ellipsis at 40 characters, show full text in MatTooltip)

## 5. Complete Implementation Checklist for Claude Code
A numbered checklist of every file that must exist when the app is complete. Format exactly as:
[ ] src/app/path/to/file.ts — what it contains in one phrase

Include in this order:
1. environment file
2. app.config.ts
3. app.routes.ts
4. Core layout files (REQUIRED if the design has a sidebar):
   - src/app/core/layout/app-shell.component.ts
   - src/app/core/layout/sidebar-nav.component.ts
   - src/app/core/layout/app-header.component.ts (if design has a header)
5. Every model interface file
6. Every service file
7. Every guard file
8. Every interceptor file
9. Every shared component file
10. Every feature component file (one per route/screen)
11. styles.scss

End with exactly this sentence: "Verify the app compiles with ng build --configuration=production before considering the task complete."
"""
        return _SYSTEM, prompt

    def generate_doc(self, doc_type: int, design_summary: str, design_name: str,
                     endpoints: str, repo_context: str = "", requirements: str = "") -> str:
        builders = {1: self._doc1_prompts, 2: self._doc2_prompts, 3: self._doc3_prompts}
        builder = builders.get(doc_type)
        if not builder:
            raise ValueError(f"Invalid doc_type: {doc_type}")
        system_prompt, prompt = builder(design_summary, design_name, endpoints, repo_context, requirements)
        return self.invoke_claude(prompt, system_prompt, max_tokens=4000)

    def generate_doc_stream(self, doc_type: int, design_summary: str, design_name: str,
                            endpoints: str, repo_context: str = "", requirements: str = ""):
        builders = {1: self._doc1_prompts, 2: self._doc2_prompts, 3: self._doc3_prompts}
        builder = builders.get(doc_type)
        if not builder:
            raise ValueError(f"Invalid doc_type: {doc_type}")
        system_prompt, prompt = builder(design_summary, design_name, endpoints, repo_context, requirements)
        yield from self.stream_claude(prompt, system_prompt, max_tokens=4000)

    # ── Legacy entry-point used by /api/analyze ───────────────────────────────

    def run(self, input_data: dict) -> dict:
        figma_url = input_data.get("figma_url")
        result = self.analyze_screens(figma_url)
        return {
            "planning_document": result["suggested_endpoints"],
            "design_name": result["design_name"],
            "screen_count": result["screen_count"],
        }
