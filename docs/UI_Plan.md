# Context Engineering Planning Agent — UI Planning Document
## For Claude Code (VS Code Plugin)

---

## 1. What to Build

A full-stack web application that looks exactly like the screenshots:
- Screen 1: "Connect Your Repository" form
- Screen 2: "Agent Chat" interface with AI responses
- Backend: Flask API already running at http://127.0.0.1:5001

---

## 2. Tech Stack

| Layer     | Technology                        |
|-----------|-----------------------------------|
| Frontend  | Plain HTML + CSS + Vanilla JS     |
| Backend   | Flask (already built, port 5001)  |
| Fonts     | Inter (Google Fonts)              |
| Icons     | None needed — use emoji           |
| Styling   | CSS variables, no frameworks      |

---

## 3. File Structure to Create

```
src/
└── static/
    └── index.html        ← Single file, entire UI
```

That's it — one file only.

---

## 4. Screen 1 — Connect Your Repository

### Layout
- White background, centered card (max-width 700px)
- Title: "Connect Your Repository" (bold, large)
- Subtitle: "Let's analyze your source code to generate documentation and plans"

### Info box
- Light blue background box
- Icon: ℹ️
- Title: "About This Step"
- Text: "We need your GitHub repository URL to analyze your codebase.
  You can find this on your repository's Code button using the HTTPS option.
  We support GitHub, GitLab, and Bitbucket repositories."

### Form fields (in order)
1. Repository URL * (required, red asterisk)
   - Placeholder: https://github.com/myorg/my-awesome-app
   - Tip below: "💡 Tip: Use HTTPS URL from the 'Code' button on your repository"

2. Project Name
   - Placeholder: my-awesome-app
   - Note below: "Optional. Will be auto-populated from GitHub URL if not provided."

3. Default Branch
   - Placeholder: non-prod
   - Note below: "Optional. Defaults to 'non-prod' if not specified."

4. Repository Path
   - Placeholder: (empty)
   - Note below: "Auto-generated from GitHub URL. This is where the repository will be cloned."
   - Value: auto-filled when user types GitHub URL

### Buttons (bottom right, side by side)
- "Create Project" — dark/black background, white text, rounded
- "Cancel" — dark/black background, white text, rounded

### Behavior
- When user types in Repository URL → auto-fill Project Name and Repository Path
- Project Name = last part of URL (e.g. "my-awesome-app")
- Repository Path = /tmp/repos/my-awesome-app
- Click "Create Project" → validate URL is not empty → go to Screen 2

---

## 5. Screen 2 — Agent Chat

### Header
- Title: "Agent Chat" (bold)
- Two pill badges side by side:
  - "Project: context-eng-planning-agent.iam" (with label "Project:")
  - "Branch: main" (with label "Branch:")

### Chat area
- White background, scrollable
- First message always shown (from agent):
  - Avatar: robot emoji 🤖 in a colored circle (left side)
  - Content:
    - "🌿 Welcome to Project Assistant for project `{project-name}`"
    - "↗ Available Integrations: Confluence, Figma"
    - "💡 Start Here: I can analyze this repository to understand
      its structure. Just ask me to 'analyze this repository'
      or 'create documentation'."
  - Timestamp: shown bottom right (current time HH:MM)

### Chat input (bottom)
- Full width text input
- Placeholder: "Type your message..."
- Send button or Enter key to send

### Agent commands that trigger real API calls
When user types any of these → call POST /api/analyze:

| User types | Agent does |
|---|---|
| "analyze this repository" | calls API with agent_type: "snapshot" |
| "create documentation" | calls API with agent_type: "snapshot" |
| "create a plan" | calls API with agent_type: "planning" |
| "plan features" | calls API with agent_type: "feature" |
| anything else | shows: "I can help you analyze this repository. Try: 'analyze this repository' or 'create a plan'" |

### Agent response display
- Show "🤖 Thinking..." with animated dots while API call is running
- When response arrives → render the planning_document as formatted markdown
- Show timestamp after each message

---

## 6. Full CSS Design Specification

### Colors
```css
--bg: #f5f5f5;
--white: #ffffff;
--dark: #1a1a1a;
--border: #e0e0e0;
--blue-light: #e8f4fd;
--blue-border: #b8d4e8;
--blue-text: #1565c0;
--text-primary: #1a1a1a;
--text-secondary: #666666;
--text-hint: #888888;
--accent: #1a1a1a;
--pill-bg: #f0f0f0;
--pill-border: #d0d0d0;
--red: #e53e3e;
```

### Typography
```css
font-family: 'Inter', sans-serif;
Title: 28px, font-weight: 700
Subtitle: 15px, color: var(--text-secondary)
Label: 14px, font-weight: 600
Input: 14px
Hint: 12px, color: var(--text-hint), font-style: italic
Button: 14px, font-weight: 500
```

### Form inputs
```css
width: 100%;
padding: 12px 14px;
border: 1px solid var(--border);
border-radius: 8px;
font-size: 14px;
outline: none;
transition: border-color 0.2s;
/* on focus: border-color: #1a1a1a */
```

### Buttons
```css
padding: 12px 24px;
background: #1a1a1a;
color: white;
border: none;
border-radius: 25px;
font-size: 14px;
font-weight: 500;
cursor: pointer;
```

### Info box
```css
background: #e8f4fd;
border: 1px solid #b8d4e8;
border-radius: 8px;
padding: 16px;
```

### Pills (Project / Branch badges)
```css
background: #f0f0f0;
border: 1px solid #d0d0d0;
border-radius: 6px;
padding: 6px 12px;
font-size: 13px;
display: inline-flex;
gap: 4px;
```

### Chat message
```css
display: flex;
gap: 12px;
padding: 20px;
background: white;
border-bottom: 1px solid #f0f0f0;
```

### Avatar circle
```css
width: 40px;
height: 40px;
border-radius: 50%;
background: #6c63ff;
color: white;
display: flex;
align-items: center;
justify-content: center;
font-size: 18px;
flex-shrink: 0;
```

---

## 7. Markdown Rendering

When agent response arrives, render these patterns:
- `# text` → `<h1>`
- `## text` → `<h2>` with bottom border
- `### text` → `<h3>`
- `**text**` → `<strong>`
- `- item` → `<li>` inside `<ul>`
- `1. item` → `<li>` inside `<ol>`
- `` `code` `` → `<code>` with gray background
- ` ```code block``` ` → `<pre><code>` with dark background
- `\n\n` → `<br><br>`

---

## 8. API Integration

### Endpoint
```
POST http://127.0.0.1:5001/api/analyze
Content-Type: application/json
```

### Request body
```json
{
  "github_url": "https://github.com/username/repo",
  "agent_type": "planning",
  "options": {
    "include_features": true,
    "include_architecture": true,
    "include_implementation_plan": true
  }
}
```

### Response
```json
{
  "status": "success",
  "planning_document": "# Project Plan\n...",
  "metadata": {
    "files_analyzed": 42,
    "languages": ["Python"]
  }
}
```

### Error handling
- If fetch fails → show "❌ Could not connect to server. Make sure Flask is running."
- If status != success → show error message from response

---

## 9. Step-by-Step Implementation Instructions for Claude Code

Execute in this exact order:

### Step 1: Create folder
```
mkdir -p src/static
```

### Step 2: Create src/static/index.html
Build the complete single-page app with:
- Screen 1 (Connect Repository form) visible by default
- Screen 2 (Agent Chat) hidden initially
- JavaScript to switch between screens
- All CSS inline in <style> tag
- All JS inline in <script> tag
- Google Fonts Inter imported in <head>
- Real API calls to http://127.0.0.1:5001

### Step 3: Serve from Flask
Add this route to src/app.py:

```python
from flask import send_from_directory

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')
```

### Step 4: Restart Flask
```bash
python src/app.py
```

### Step 5: Open in browser
```
http://127.0.0.1:5001
```

---

## 10. Exact Claude Code Prompts

### Prompt 1 — Build the UI:
```
Read UI_PLAN.md carefully. Create the file src/static/index.html
with the complete UI exactly matching the screenshots described.
Screen 1 is the Connect Repository form. Screen 2 is the Agent Chat.
Use plain HTML, CSS, and JavaScript only — no frameworks.
Match the exact colors, fonts, layout, and form fields described.
Include real fetch() calls to http://127.0.0.1:5001/api/analyze.
```

### Prompt 2 — Add Flask route to serve it:
```
In src/app.py, add a route for GET / that serves
src/static/index.html using Flask's send_from_directory.
Also add a route for GET /static/<path:filename> to serve
static files. Then restart the server.
```

### Prompt 3 — Test it:
```
Open http://127.0.0.1:5001 in the browser.
Fill in a GitHub URL and click Create Project.
Type "analyze this repository" in the chat.
Verify the API call goes to /api/analyze and
the response renders as formatted markdown.
Fix any issues found.
```