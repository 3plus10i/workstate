from copy import deepcopy

IDLE_SECONDS = 60

DEFAULT_PROGRAMS = {
    "ideProcesses": ["code", "cursor", "pycharm64", "idea64"],
    "documentProcesses": ["winword", "excel", "powerpnt", "onenote"],
    "browserProcesses": ["chrome", "msedge", "firefox"],
}
LEGACY_PROGRAM_KEYS = {"customIdeProcesses": "ideProcesses", "customDocumentProcesses": "documentProcesses", "customBrowserProcesses": "browserProcesses"}

DEFAULTS = {
    "dayStartHour": 4,
    "idleSeconds": IDLE_SECONDS,
    "expandContexts": False,
    "detailThreshold": 15,
    "splitIde": True,
    "splitDocuments": True,
    "splitSites": True,
    **deepcopy(DEFAULT_PROGRAMS),
    "excludedProcesses": ["LockApp // Windows锁屏", "LogonUI // Windows登录"],
    "siteNames": ["GitHub", "ChatGPT", "Claude", "Google Scholar", "arXiv", "YouTube", "Wikipedia", "哔哩哔哩", "bilibili", "知乎", "中国知网"],
    "displayNames": {"code": "Visual Studio Code", "cursor": "Cursor", "chrome": "Google Chrome", "msedge": "Microsoft Edge", "firefox": "Firefox", "winword": "Microsoft Word", "excel": "Microsoft Excel", "powerpnt": "PowerPoint", "onenote": "Microsoft OneNote", "explorer": "文件资源管理器", "zotero": "Zotero", "weixin": "微信", "wechatappex": "微信", "python": "Python", "workstate": "WorkState", "pcstate": "PCState", "pcstatemonitor": "PCState"},
}


def excluded_processes(settings):
    return {
        name.casefold().removesuffix(".exe")
        for line in settings["excludedProcesses"]
        if (name := line.split("//", 1)[0].strip())
    }


def validate_settings(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) - set(DEFAULTS) - set(LEGACY_PROGRAM_KEYS):
        raise ValueError("设置包含未知字段")
    value = deepcopy(value)
    if any(key in value for key in LEGACY_PROGRAM_KEYS) and isinstance(value.get('displayNames'), dict):
        value['displayNames'].setdefault('workstate', 'WorkState')
        value['displayNames'].setdefault('onenote', 'Microsoft OneNote')
    for old, current in LEGACY_PROGRAM_KEYS.items():
        if old in value:
            custom = value.pop(old)
            if not isinstance(custom, list):
                raise ValueError("程序名单格式无效")
            if current not in value:
                value[current] = DEFAULT_PROGRAMS[current] + custom
    result = deepcopy(DEFAULTS)
    result.update(value)
    for key in ("expandContexts", "splitIde", "splitDocuments", "splitSites"):
        if type(result[key]) is not bool:
            raise ValueError("开关必须为布尔值")
    for key, low, high in (("dayStartHour", 0, 23), ("idleSeconds", 30, 600), ("detailThreshold", 1, 120)):
        if type(result[key]) is not int or not low <= result[key] <= high:
            raise ValueError(f"{key} 必须在 {low}–{high} 之间")
    # Accept old preferences but always use the fixed one-minute interval.
    result["idleSeconds"] = IDLE_SECONDS
    for key in ("siteNames", "excludedProcesses"):
        values = result[key]
        if not isinstance(values, list) or len(values) > 200 or any(not isinstance(v, str) or not v.strip() or len(v) > 100 for v in values):
            raise ValueError("规则列表必须包含有效名称，最多 200 项")
        result[key] = list(dict.fromkeys(v.strip() for v in values))
    occupied = set()
    for key in DEFAULT_PROGRAMS:
        values = result[key]
        if not isinstance(values, list) or len(values) > 100 or any(not isinstance(v, str) or not v.strip() or len(v) > 100 for v in values):
            raise ValueError("程序名格式无效，每类最多 100 项")
        names = list(dict.fromkeys(v.strip().casefold().removesuffix(".exe") for v in values))
        if any(not name or any(c in name for c in '\\/:') or any(ord(c) < 32 for c in name) for name in names):
            raise ValueError("请填写程序进程名，不要填写文件路径")
        for name in names:
            if name in occupied:
                raise ValueError(f"程序 {name} 不能同时属于多个细分类型")
        result[key] = names
        occupied.update(names)
    names = result["displayNames"]
    if not isinstance(names, dict) or len(names) > 200 or any(not isinstance(k, str) or not isinstance(v, str) or not k.strip() or not v.strip() or max(len(k), len(v)) > 100 for k, v in names.items()):
        raise ValueError("程序显示名格式无效")
    result["displayNames"] = {k.strip().casefold().removesuffix(".exe"): v.strip() for k, v in names.items()}
    return result
