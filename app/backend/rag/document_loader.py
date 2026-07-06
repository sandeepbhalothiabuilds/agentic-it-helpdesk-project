from pathlib import Path
from typing import Dict, List
import json

from docx import Document
from pypdf import PdfReader


def load_manifest(manifest_path: str) -> Dict[str, str]:
    """
    Returns a filename -> workflow mapping.
    """
    path = Path(manifest_path)
    if not path.exists():
        return {}

    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["file"]: item.get("workflow", "general") for item in data}


def extract_text_from_file(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")

    if suffix == ".docx":
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    if suffix == ".pdf":
        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(pages)

    return ""


def load_documents(folder: str, manifest_path: str) -> List[dict]:
    """
    Load documents and attach workflow labels from the manifest.
    """
    folder_path = Path(folder)
    workflow_map = load_manifest(manifest_path)
    docs: List[dict] = []

    for path in sorted(folder_path.iterdir()):
        if not path.is_file():
            continue

        text = extract_text_from_file(path)
        if not text.strip():
            continue

        docs.append(
            {
                "source": path.name,
                "workflow": workflow_map.get(path.name, "general"),
                "text": text,
            }
        )

    return docs