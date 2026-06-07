import re
import time
import requests

FIGMA_API_BASE = "https://api.figma.com/v1"

# In-memory cache: cache_key → figma response dict (persists for the lifetime of the process)
_cache: dict = {}


def extract_file_key(url: str) -> str:
    match = re.search(r'figma\.com/(?:file|design)/([^/?#]+)', url)
    if not match:
        raise ValueError(f"Could not extract file key from Figma URL: {url}")
    return match.group(1)


def validate_figma_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    return bool(re.search(r'figma\.com/(?:file|design)/[^/?#]+', url.strip()))


def fetch_figma_file(file_key: str, token: str, max_retries: int = 2, depth: int = 4) -> dict:
    cache_key = f"{file_key}:depth{depth}"
    if cache_key in _cache:
        return _cache[cache_key]

    url = f"{FIGMA_API_BASE}/files/{file_key}?depth={depth}"
    headers = {"X-Figma-Token": token}

    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=20)
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                continue
            raise RuntimeError("Figma API timed out. The file may be too large or the API is slow.")

        if response.status_code == 403:
            raise RuntimeError("Invalid Figma token or insufficient access to this file.")
        if response.status_code == 404:
            raise RuntimeError("Figma file not found. Check the URL.")
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 2 ** (attempt + 1)))
            if attempt < max_retries - 1:
                time.sleep(min(retry_after, 10))
                continue
            raise RuntimeError(
                f"Figma API rate limit hit. Please wait {retry_after} seconds and try again."
            )

        response.raise_for_status()
        data = response.json()
        _cache[cache_key] = data
        return data

    raise RuntimeError("Failed to fetch Figma file after retries.")


def fetch_figma_nodes(file_key: str, node_ids: list, token: str, timeout: int = 25) -> dict:
    """Fetch full node trees for specific node IDs via the nodes endpoint (no depth limit)."""
    if not node_ids:
        return {}
    cache_key = f"{file_key}:nodes:{','.join(node_ids[:10])}"
    if cache_key in _cache:
        return _cache[cache_key]

    ids_str = ",".join(str(nid) for nid in node_ids[:10])
    url = f"{FIGMA_API_BASE}/files/{file_key}/nodes?ids={ids_str}"
    headers = {"X-Figma-Token": token}
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
    except requests.exceptions.Timeout:
        raise RuntimeError("Figma nodes API timed out.")
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 60))
        raise RuntimeError(f"Figma API rate limit hit. Please wait {retry_after} seconds.")
    if resp.status_code == 403:
        raise RuntimeError("Invalid Figma token or no access to this file.")
    resp.raise_for_status()
    data = resp.json()
    _cache[cache_key] = data
    return data


def _collect_all_texts(node: dict, depth: int = 0, max_depth: int = 12) -> list:
    """Collect all TEXT node content recursively — goes deeper than _extract_texts."""
    if depth > max_depth:
        return []
    texts = []
    if node.get("type") == "TEXT":
        chars = node.get("characters", "").strip()
        if chars and 1 < len(chars) < 200:
            texts.append(chars)
    for child in node.get("children", []):
        texts.extend(_collect_all_texts(child, depth + 1, max_depth))
    return texts


def _collect_named_ui_elements(node: dict, depth: int = 0, max_depth: int = 10) -> list:
    """Collect component/instance/frame nodes whose names suggest specific UI patterns."""
    if depth > max_depth:
        return []
    elements = []
    name = node.get("name", "").strip()
    ntype = node.get("type", "")
    ui_keywords = (
        "button", "btn", "input", "field", "search", "select", "dropdown",
        "table", "chart", "graph", "card", "modal", "sidebar", "header",
        "nav", "menu", "tab", "badge", "chip", "form", "filter", "export",
        "pagination", "calendar", "date", "picker", "transaction", "dashboard",
        "report", "setting", "profile", "notification", "alert", "summary",
        "balance", "income", "expense", "savings", "cash", "spending",
    )
    if ntype in ("COMPONENT", "INSTANCE", "FRAME") and name:
        if any(kw in name.lower() for kw in ui_keywords):
            elements.append(f"{ntype}:{name}")
    for child in node.get("children", []):
        elements.extend(_collect_named_ui_elements(child, depth + 1, max_depth))
    return elements


def build_screen_inventory_from_nodes(screens_meta: list, nodes_response: dict) -> list:
    """Build rich per-screen data dicts from the Figma nodes API response."""
    inventory = []
    nodes_map = nodes_response.get("nodes", {})
    for screen in screens_meta:
        node_id = screen.get("id", "")
        node_doc = nodes_map.get(node_id, {}).get("document", {})
        inventory.append({
            "name": screen.get("name", "Screen"),
            "id": node_id,
            "texts": list(dict.fromkeys(_collect_all_texts(node_doc)))[:60] if node_doc else [],
            "ui_elements": list(dict.fromkeys(_collect_named_ui_elements(node_doc)))[:30] if node_doc else [],
            "components": list(dict.fromkeys(_extract_components(node_doc)))[:20] if node_doc else [],
        })
    return inventory


def _extract_texts(node: dict, depth: int = 0) -> list:
    if depth > 5:
        return []
    texts = []
    if node.get("type") == "TEXT":
        chars = node.get("characters", "").strip()
        if chars and len(chars) < 120:
            texts.append(chars)
    for child in node.get("children", []):
        texts.extend(_extract_texts(child, depth + 1))
    return texts


def _extract_components(node: dict, depth: int = 0) -> list:
    if depth > 4:
        return []
    components = []
    if node.get("type") in ("COMPONENT", "INSTANCE", "COMPONENT_SET"):
        name = node.get("name", "").strip()
        if name:
            components.append(name)
    for child in node.get("children", []):
        components.extend(_extract_components(child, depth + 1))
    return components


def _get_top_frames(page_node: dict) -> list:
    """Return top-level screen frames from a page, handling SECTION/GROUP nesting."""
    frames = []
    for child in page_node.get("children", []):
        ctype = child.get("type", "")
        if ctype in ("FRAME", "COMPONENT"):
            frames.append(child)
        elif ctype in ("SECTION", "GROUP"):
            for grandchild in child.get("children", []):
                if grandchild.get("type") in ("FRAME", "COMPONENT"):
                    frames.append(grandchild)
    return frames


def extract_design_summary(data: dict, max_chars: int = 8000) -> str:
    document = data.get("document", {})
    pages = document.get("children", [])
    design_name = data.get("name", "Figma Design")

    lines = [f"Design file: {design_name}\n"]
    chars = len(lines[0])

    for page in pages:
        page_name = page.get("name", "Page")
        frames = _get_top_frames(page)
        if not frames:
            continue

        section = f"\n### Page: {page_name}\n"
        if chars + len(section) > max_chars:
            break
        lines.append(section)
        chars += len(section)

        for frame in frames:
            frame_name = frame.get("name", "Screen")
            texts = list(dict.fromkeys(_extract_texts(frame)))[:15]
            components = list(dict.fromkeys(_extract_components(frame)))[:10]

            entry = f"\n**{frame_name}**\n"
            if texts:
                entry += "Labels/Text: " + " | ".join(texts[:10]) + "\n"
            if components:
                entry += "Components: " + ", ".join(components[:8]) + "\n"

            if chars + len(entry) > max_chars:
                break
            lines.append(entry)
            chars += len(entry)

    return "".join(lines)
