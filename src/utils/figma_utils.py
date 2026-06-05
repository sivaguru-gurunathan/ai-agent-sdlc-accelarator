import re
import requests

FIGMA_API_BASE = "https://api.figma.com/v1"


def extract_file_key(url: str) -> str:
    match = re.search(r'figma\.com/(?:file|design)/([^/?#]+)', url)
    if not match:
        raise ValueError(f"Could not extract file key from Figma URL: {url}")
    return match.group(1)


def validate_figma_url(url: str) -> bool:
    if not isinstance(url, str):
        return False
    return bool(re.search(r'figma\.com/(?:file|design)/[^/?#]+', url.strip()))


def fetch_figma_file(file_key: str, token: str) -> dict:
    url = f"{FIGMA_API_BASE}/files/{file_key}"
    headers = {"X-Figma-Token": token}
    response = requests.get(url, headers=headers, timeout=30)
    if response.status_code == 403:
        raise RuntimeError("Invalid Figma token or insufficient access to this file.")
    if response.status_code == 404:
        raise RuntimeError("Figma file not found. Check the URL.")
    response.raise_for_status()
    return response.json()


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


def extract_design_summary(data: dict, max_chars: int = 6000) -> str:
    document = data.get("document", {})
    pages = document.get("children", [])
    design_name = data.get("name", "Figma Design")

    lines = [f"Design file: {design_name}\n"]
    chars = len(lines[0])

    for page in pages:
        page_name = page.get("name", "Page")
        frames = [c for c in page.get("children", []) if c.get("type") in ("FRAME", "COMPONENT")]
        if not frames:
            continue

        section = f"\n### Page: {page_name}\n"
        if chars + len(section) > max_chars:
            break
        lines.append(section)
        chars += len(section)

        for frame in frames:
            frame_name = frame.get("name", "Screen")
            texts = list(dict.fromkeys(_extract_texts(frame)))[:12]
            components = list(dict.fromkeys(_extract_components(frame)))[:8]

            entry = f"\n**{frame_name}**\n"
            if texts:
                entry += "Labels/Text: " + " | ".join(texts[:8]) + "\n"
            if components:
                entry += "Components: " + ", ".join(components[:6]) + "\n"

            if chars + len(entry) > max_chars:
                break
            lines.append(entry)
            chars += len(entry)

    return "".join(lines)
