"""Conservative title adapters. Unknown formats stay at application level."""
from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class Identity:
    key: str
    app: str
    context: str = ""
    kind: str = "app"


def process_key(process: str) -> str:
    return process.replace("\\", "/").rsplit("/", 1)[-1].casefold().removesuffix(".exe")


def content_title(title, suffix=None):
    if suffix:
        match = re.match(rf"^(.+?)\s+[—–-]\s+(?:{suffix})(?:\s+\[.*\])?$", title, re.I)
        return match[1] if match else ""
    # Custom programs opt into the common "content - application" title format.
    parts = re.split(r"\s+[—–-]\s+", title)
    return " - ".join(parts[:-1]) if len(parts) > 1 else ""


def classify(process: str, title: str, settings: dict) -> Identity:
    key = process_key(process) or "unknown"
    app = settings["displayNames"].get(key, process.removesuffix(".exe") or "未知程序")
    context, kind = "", "app"
    title = title.strip().removeprefix("● ").removeprefix("• ")
    if settings["splitIde"] and key in settings["ideProcesses"]:
        suffix = {"code": "Visual Studio Code|VSCode|Code", "cursor": "Cursor", "pycharm64": "PyCharm", "idea64": "IntelliJ IDEA"}.get(key)
        content = content_title(title, suffix)
        if content:
            # VS Code: file - project - editor. JetBrains: only known suffix format.
            context = re.split(r"\s+[—–-]\s+", content)[-1].strip()
            context = re.sub(r"\s+\[(?:WSL|SSH|Dev Container).*\]$", "", context).strip()
            if re.search(r"\.(?:py|tsx?|jsx?|json|md|cpp|h|rs|html|css)$", context, re.I):
                context = ""
            kind = "project" if context else "app"
    elif settings["splitDocuments"] and key in settings["documentProcesses"]:
        suffix = {"winword": r"(?:Microsoft\s+)?Word", "excel": r"(?:Microsoft\s+)?Excel", "powerpnt": r"(?:Microsoft\s+)?PowerPoint", "onenote": r"(?:Microsoft\s+)?OneNote"}.get(key)
        content = content_title(title, suffix)
        if content:
            context = re.sub(r"\s*[\[（(](?:兼容模式|兼容性模式|受保护的视图|只读).*?[\]）)]", "", content)
            context = re.sub(r"\s+-\s+(?:兼容性?模式|受保护的视图|只读)$", "", context)
            context = re.sub(r"\.(?:docx?|xlsx?|pptx?|docm|xlsm|pptm)$", "", context, flags=re.I).strip()
            kind = "document" if context else "app"
    elif settings["splitSites"] and key in settings["browserProcesses"]:
        folded = title.casefold()
        for site in sorted(settings["siteNames"], key=len, reverse=True):
            if site.casefold() in folded:
                context, kind = site, "site"
                break
    return Identity(key, app, context, kind)
