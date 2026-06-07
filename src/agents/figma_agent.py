import os
from src.agents.base_agent import BaseAgent
from src.utils.figma_utils import extract_file_key, fetch_figma_file, extract_design_summary

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

    def analyze_screens(self, figma_url: str) -> dict:
        token = os.getenv("FIGMA_TOKEN")
        if not token:
            raise RuntimeError("FIGMA_TOKEN environment variable is not set.")
        file_key = extract_file_key(figma_url)
        figma_data = fetch_figma_file(file_key, token)
        design_summary = extract_design_summary(figma_data)
        design_name = figma_data.get("name", "Figma Design")

        # Collect top-level FRAME names — handles frames nested inside SECTIONs too
        screens = []
        def _collect_frames(nodes, max_depth=2, depth=0):
            for node in nodes:
                ntype = node.get("type", "")
                if ntype == "FRAME":
                    screens.append(node.get("name", "Screen"))
                elif ntype in ("SECTION", "GROUP", "CANVAS") and depth < max_depth:
                    _collect_frames(node.get("children", []), max_depth, depth + 1)

        for page in figma_data.get("document", {}).get("children", []):
            _collect_frames(page.get("children", []))

        screen_count = len(screens)
        screen_lines = "\n".join(f"{i+1}. {s}" for i, s in enumerate(screens[:20]))
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
        """Project Overview & Architecture"""
        ctx = _context(design_summary, endpoints, repo_context, requirements)
        prompt = f"""Write Document 1 of 3: **Project Overview & Architecture** for the application: {design_name}

{ctx}

Cover only the sections below. Be specific — every decision must have a clear reason.

## 1. Project Purpose & Context
- What problem this application solves and for whom
- Key business domain concepts a developer must understand before touching any file
- Non-obvious constraints or rules that affect the entire architecture

## 2. Technology Decisions
State each technology choice as a firm decision with the reason why:
- Angular version and key features used (standalone, signals, new control flow, inject())
- HTTP client setup (withFetch, interceptors, typed calls)
- Form strategy (typed reactive forms — never template-driven)
- State management (signals only — when to use signal vs toSignal vs computed)
- UI library (Angular Material 18+, individual directive imports, no barrel modules)
- Styling approach (SCSS, Material theming)
- Auth mechanism (JWT location, refresh strategy, or none)
- Error handling convention (what every failed HTTP call must do in the UI)
- Environment config convention (what goes in environment.ts, never hard-coded)

## 3. Folder Structure & Responsibilities
Describe every folder under src/app/ in plain English:
- What type of files belong there
- What does NOT belong there
- Why this separation exists
If a reference repository was provided, describe how this structure aligns with or departs from it and why.

## 4. Routing & Navigation Architecture
- Every route path, what it renders, and who can access it
- How lazy loading is applied and which features are lazy-loaded
- How the auth guard works — what it checks, redirect on failure, how return URL is preserved
- How the HTTP interceptor works — which header it adds, where the token comes from, what happens on 401

## 5. Implementation Starting Instructions for Claude Code
- The exact ng new command with all flags
- The exact npm install command for all required packages
- The order in which to create files (models → services → components → routes)
- Which files to edit after scaffold (app.config.ts, app.routes.ts, styles.scss, environment.ts) and what to put in each
- End with: "Do not ask the user any questions. Use the three planning documents as the single source of truth."
"""
        return _SYSTEM, prompt

    def _doc2_prompts(self, design_summary, design_name, endpoints, repo_context, requirements):
        """Screens, Components & User Flows"""
        ctx = _context(design_summary, endpoints, repo_context, requirements)
        prompt = f"""Write Document 2 of 3: **Screens, Components & User Flows** for the application: {design_name}

{ctx}

## 1. Screen Inventory
For every screen visible in the Figma design, write a sub-section:

### Screen: [Name]
- Route path
- Who can access it (public / authenticated / role-restricted)
- What the user sees on arrival: describe every visible element (page title, table columns, form fields, cards, buttons, empty states, loading skeleton)
- What data is loaded on page open: which endpoint is called, what appears while loading, what appears on error
- Every user action available on this screen:
  - Action name → what it validates → which API call it triggers → success behaviour → error behaviour → navigation side-effect
- Where the user can navigate from this screen and what triggers each navigation

## 2. Component Inventory
For every component (both routed pages and reusable UI components):

### [ComponentName]
- Which feature folder or shared folder it lives in
- Its single responsibility in one sentence
- Inputs it receives: name, data type, whether required, what it represents
- Outputs it emits: name, data it carries, what user action triggers it
- Local state it manages: each piece of reactive state with its purpose
- Which services and methods it calls
- Template sections described in plain English: what each block shows, what it binds to, what interactions it enables

## 3. Angular Material Components Per Screen
For each screen, list which Angular Material components appear and describe their role and configuration:
Example format: "Users list — MatTable with columns [name, email, status, actions], MatSort on name and email, MatPaginator page sizes 10/25/50, MatChip for status badge, MatIcon buttons for edit and delete actions"

## 4. Shared Components
List every reusable component in shared/ with:
- What it renders
- Its inputs and outputs
- Which screens use it
"""
        return _SYSTEM, prompt

    def _doc3_prompts(self, design_summary, design_name, endpoints, repo_context, requirements):
        """API, Data Models & Implementation Guide"""
        ctx = _context(design_summary, endpoints, repo_context, requirements)
        prompt = f"""Write Document 3 of 3: **API, Data Models & Implementation Guide** for the application: {design_name}

{ctx}

## 1. Data Models
For every entity in the application:

### [EntityName]
- What this entity represents in the business domain
- Every field: field name — what it holds — required or optional — any constraints (format, allowed values, max length)
- Which API endpoints return or accept this entity
- Relationships to other entities (belongs to, has many, etc.)

## 2. API Integration
For every endpoint in the API specification:

### [METHOD] [path]
- Purpose: one sentence describing what this call does in the UI context
- Triggered by: which user action or page lifecycle event calls this
- Request parameters: every path param, query param, and body field with its type and whether required
- Successful response: shape of the data returned and every field the UI uses from it
- Loading state: what the UI shows while waiting (spinner location, disabled elements)
- Success behaviour: exact UI change after success (toast message text, navigation, list refresh)
- Error behaviour: what the UI shows for 400 / 401 / 403 / 404 / 500 — be specific about message text and placement

## 3. Services
For every service:

### [ServiceName]
- Single responsibility in one sentence
- Dependencies it uses (HttpClient, Router, other services) and why
- For every method:
  - Name and purpose
  - Parameters and what they represent
  - HTTP verb and exact URL template
  - Request body or query params sent
  - Return value and how the calling component uses it
  - Any transformation applied to the response before returning it

## 4. Business Rules & Validation
- Form validation rules: every field, its rules, and the exact error message to show
- Permission rules: which roles can see or perform which actions
- Data constraints: invalid combinations, mutually exclusive values
- Edge cases the UI must handle explicitly: empty list state, single-item behaviour, null optional fields, very long text truncation

## 5. Final Implementation Checklist for Claude Code
A numbered checklist of every file that must exist when the app is complete.
Format: [ ] src/app/path/to/file.ts — what it contains
Include every component, service, model, guard, interceptor, route file, and config file.
End with: "Verify the app compiles with ng build --configuration=production before considering the task complete."
"""
        return _SYSTEM, prompt

    def generate_doc(self, doc_type: int, design_summary: str, design_name: str,
                     endpoints: str, repo_context: str = "", requirements: str = "") -> str:
        """Generate a single planning document synchronously. Returns full text."""
        builders = {1: self._doc1_prompts, 2: self._doc2_prompts, 3: self._doc3_prompts}
        builder = builders.get(doc_type)
        if not builder:
            raise ValueError(f"Invalid doc_type: {doc_type}")
        system_prompt, prompt = builder(design_summary, design_name, endpoints, repo_context, requirements)
        return self.invoke_claude(prompt, system_prompt, max_tokens=3000)

    def generate_doc_stream(self, doc_type: int, design_summary: str, design_name: str,
                            endpoints: str, repo_context: str = "", requirements: str = ""):
        """Streaming path — kept for future use but falls back to sync if needed."""
        builders = {1: self._doc1_prompts, 2: self._doc2_prompts, 3: self._doc3_prompts}
        builder = builders.get(doc_type)
        if not builder:
            raise ValueError(f"Invalid doc_type: {doc_type}")
        system_prompt, prompt = builder(design_summary, design_name, endpoints, repo_context, requirements)
        yield from self.stream_claude(prompt, system_prompt, max_tokens=3000)

    # ── Legacy entry-point used by /api/analyze ───────────────────────────────

    def run(self, input_data: dict) -> dict:
        figma_url = input_data.get("figma_url")
        result = self.analyze_screens(figma_url)
        return {
            "planning_document": result["suggested_endpoints"],
            "design_name": result["design_name"],
            "screen_count": result["screen_count"],
        }
