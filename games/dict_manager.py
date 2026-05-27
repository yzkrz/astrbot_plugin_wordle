import json
import os
import re

from astrbot.api import logger


class Wordlist:
    def __init__(self, name: str, path: str, display_name: str):
        self.name = name
        self.path = path
        self.display_name = display_name


class Dictionary:
    def __init__(self, name: str, path: str, display_name: str):
        self.name = name
        self.path = path
        self.display_name = display_name
        self.wordlists: dict[str, Wordlist] = {}


def _read_meta(meta_path: str) -> dict | None:
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"读取词库 meta 失败 {meta_path}: {e!s}")
        return None


class DictManager:
    """管理所有词典与词库，并持久化每个词典的启用词库。"""

    DEFAULT_WORDLIST = "all"

    def __init__(self, data_root: str, config_path: str):
        self.data_root = data_root
        self.config_path = config_path
        self.dictionaries: dict[str, Dictionary] = {}
        self.active: dict[str, str] = {}
        self._load_dicts()
        self._load_config()

    def _load_dicts(self) -> None:
        if not os.path.isdir(self.data_root):
            logger.warning(f"词典数据目录不存在: {self.data_root}")
            return
        for dname in sorted(os.listdir(self.data_root)):
            dpath = os.path.join(self.data_root, dname)
            if not os.path.isdir(dpath):
                continue
            meta_path = os.path.join(dpath, "meta.json")
            all_path = os.path.join(dpath, self.DEFAULT_WORDLIST)
            if not os.path.isfile(meta_path) or not os.path.isdir(all_path):
                continue
            meta = _read_meta(meta_path) or {}
            dictionary = Dictionary(dname, dpath, meta.get("display_name", dname))
            for wname in sorted(os.listdir(dpath)):
                wpath = os.path.join(dpath, wname)
                if not os.path.isdir(wpath):
                    continue
                wmeta_path = os.path.join(wpath, "meta.json")
                if not os.path.isfile(wmeta_path):
                    continue
                wmeta = _read_meta(wmeta_path) or {}
                dictionary.wordlists[wname] = Wordlist(
                    wname, wpath, wmeta.get("display_name", wname)
                )
            if self.DEFAULT_WORDLIST in dictionary.wordlists:
                self.dictionaries[dname] = dictionary

    def _load_config(self) -> None:
        try:
            if os.path.isfile(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.active = dict(data.get("active", {}))
        except Exception as e:
            logger.error(f"加载词库配置失败: {e!s}")
        for name, d in self.dictionaries.items():
            if self.active.get(name) not in d.wordlists:
                self.active[name] = self.DEFAULT_WORDLIST

    def _save_config(self) -> None:
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump({"active": self.active}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存词库配置失败: {e!s}")

    def get_dict(self, name: str) -> Dictionary | None:
        return self.dictionaries.get(name)

    def get_wordlist(self, dict_name: str, wordlist_name: str) -> Wordlist | None:
        d = self.get_dict(dict_name)
        return d.wordlists.get(wordlist_name) if d else None

    def get_active(self, dict_name: str) -> str | None:
        return self.active.get(dict_name)

    def get_active_wordlist(self, dict_name: str) -> Wordlist | None:
        return self.get_wordlist(dict_name, self.active.get(dict_name, self.DEFAULT_WORDLIST))

    def get_all_wordlist(self, dict_name: str) -> Wordlist | None:
        return self.get_wordlist(dict_name, self.DEFAULT_WORDLIST)

    def set_active(self, dict_name: str, wordlist_name: str) -> bool:
        if dict_name not in self.dictionaries:
            return False
        if wordlist_name not in self.dictionaries[dict_name].wordlists:
            return False
        self.active[dict_name] = wordlist_name
        self._save_config()
        return True


def load_english_words(wordlist: Wordlist, length: int) -> list[str]:
    """读取词库目录中长度为 length 的英文单词。

    优先使用 ``{length}_letters_words.txt``（如 all 词库的格式）；否则扫描全部
    ``*.txt`` 文件后按长度过滤（如 gaokao 这种扁平词表）。
    """
    bucket_file = os.path.join(wordlist.path, f"{length}_letters_words.txt")
    if os.path.isfile(bucket_file):
        with open(bucket_file, "r", encoding="utf-8") as f:
            return [
                w.strip().upper()
                for w in f
                if w.strip() and len(w.strip()) == length
            ]

    words: list[str] = []
    if not os.path.isdir(wordlist.path):
        return words
    for fname in os.listdir(wordlist.path):
        if not fname.lower().endswith(".txt"):
            continue
        try:
            with open(os.path.join(wordlist.path, fname), "r", encoding="utf-8") as f:
                for line in f:
                    # 剥离非字母字符并归一为大写，兼容带撇号、连字符等情况
                    w = re.sub(r'[^a-zA-Z]', '', line.strip()).upper()
                    if w and len(w) == length:
                        words.append(w)
        except Exception as e:
            logger.error(f"读取词库文件失败 {fname}: {e!s}")
    # 去重（保持顺序），避免归一化后出现重复词
    return list(dict.fromkeys(words))


def load_chengyu_full(wordlist: Wordlist) -> tuple[dict[str, list[list]], dict[str, dict[str, str]]]:
    """读取完整成语 JSON（含拼音与释义）。

    返回 ``(idioms, meta)``。``idioms[name] = pinyin``，``meta[name] = {explanation, source}``。
    """
    idioms: dict[str, list[list]] = {}
    meta: dict[str, dict[str, str]] = {}
    if not os.path.isdir(wordlist.path):
        return idioms, meta
    for fname in os.listdir(wordlist.path):
        if not fname.lower().endswith(".json") or fname == "meta.json":
            continue
        try:
            with open(os.path.join(wordlist.path, fname), "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                continue
            for x in data:
                if not isinstance(x, dict) or "name" not in x or "pinyin" not in x:
                    continue
                idioms[x["name"]] = x["pinyin"]
                meta[x["name"]] = {
                    "explanation": x.get("explanation", ""),
                    "source": x.get("source", ""),
                }
        except Exception as e:
            logger.error(f"读取成语词库失败 {fname}: {e!s}")
    return idioms, meta


def load_chengyu_names(wordlist: Wordlist) -> list[str]:
    """读取一个非 all 成语词库的名称列表。

    支持两种格式：
    - ``*.json``：可以是字符串列表，或是含 ``name`` 字段的对象列表。
    - ``*.txt``：每行一个成语。
    """
    names: list[str] = []
    if not os.path.isdir(wordlist.path):
        return names
    for fname in os.listdir(wordlist.path):
        fpath = os.path.join(wordlist.path, fname)
        lower = fname.lower()
        if lower == "meta.json":
            continue
        try:
            if lower.endswith(".json"):
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for x in data:
                        if isinstance(x, str):
                            names.append(x)
                        elif isinstance(x, dict) and "name" in x:
                            names.append(x["name"])
            elif lower.endswith(".txt"):
                with open(fpath, "r", encoding="utf-8") as f:
                    for line in f:
                        w = line.strip()
                        if w:
                            names.append(w)
        except Exception as e:
            logger.error(f"读取成语词库失败 {fname}: {e!s}")
    return names
