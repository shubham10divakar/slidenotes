"""Word notes: anchors are invisible bookmarks named `sn_<slug>`.

Safety rules:
- Only the main document part (word/document.xml) is ever changed, and only by inserting
  or removing <w:bookmarkStart>/<w:bookmarkEnd> elements. Every other zip entry is copied
  unchanged.
- Before the first write the original is copied once to `.slidenotes/backup/`.
- A document open in Word (a `~$` lock file, or the file can't be opened for writing) is never written.
"""

from __future__ import annotations

import re
import shutil
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from lxml import etree

from slidenotes.errors import LockedError, ToolMissing, UsageError
from slidenotes.notes.base import Section, normalize, short_label
from slidenotes.util.config import work_dir
from slidenotes.util.files import atomic_write_bytes
from slidenotes.util.paths import display

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
REL_OFFICE_DOC = "/officeDocument"
_SKIP_CONTAINERS = {W + "txbxContent", MC + "Fallback"}
_FALSE = {"0", "false", "off", "none"}
BOLD_MAX_CHARS = 150
BOOKMARK_MAX = 40


@dataclass
class _Para:
    el: etree._Element
    text: str
    level: int            # 1-9 for headings, 0 otherwise
    bold: bool            # every run is bold (a "bold-text heading")
    bookmarks: list[str] = field(default_factory=list)

    @property
    def sn_bookmark(self) -> str | None:
        for b in self.bookmarks:
            if b.startswith("sn_"):
                return b
        return None

    @property
    def user_bookmark(self) -> str | None:
        for b in self.bookmarks:
            if not b.startswith("_"):
                return b
        return None


def bookmark_name(text: str, taken: set[str]) -> str:
    """`2.1 One-Hot Representation` -> `sn_2_1_one_hot_representation` (<= 40 chars, unique)."""
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    limit = BOOKMARK_MAX - 3
    if len(s) > limit:
        s = s[:limit]
        if "_" in s[limit // 2:]:
            s = s[: s.rfind("_")]
        s = s.strip("_")
    base = "sn_" + (s or "section")
    taken_cf = {t.casefold() for t in taken}
    name = base
    n = 2
    while name.casefold() in taken_cf:
        suffix = f"_{n}"
        name = base[: BOOKMARK_MAX - len(suffix)] + suffix
        n += 1
    return name


def lock_files(path: Path) -> list[Path]:
    """Word's owner files: `~$` + name, with 1 or 2 leading characters replaced for long names."""
    name = path.name
    cands = {"~$" + name, "~$" + name[1:], "~$" + name[2:]}
    return [path.with_name(c) for c in cands]


def check_unlocked(path: Path) -> None:
    for lock in lock_files(path):
        if lock.exists():
            raise LockedError(f"{display(path)}: file is open in Word ({lock.name} exists); close it and rerun")
    try:
        with open(path, "r+b"):
            pass
    except PermissionError as e:
        raise LockedError(f"{display(path)}: file is locked or read-only; close it in Word and rerun") from e


def backup_once(path: Path) -> Path | None:
    dest = work_dir(path) / "backup" / path.name
    if dest.exists():
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    return dest


class DocxNotes:
    def __init__(self, path: Path):
        self.path = path
        self._loaded = False
        self.last_backup: Path | None = None

    # -- loading -----------------------------------------------------------
    def _load(self) -> None:
        if self._loaded:
            return
        try:
            with zipfile.ZipFile(self.path) as z:
                names = set(z.namelist())
                self._part = self._main_part(z, names)
                self._doc_bytes = z.read(self._part)
                styles_name = str(PurePosixPath(self._part).parent / "styles.xml")
                styles = z.read(styles_name) if styles_name in names else None
        except FileNotFoundError:
            raise
        except (zipfile.BadZipFile, KeyError, OSError) as e:
            raise LockedError(f"{display(self.path)}: not a readable .docx ({e})") from e
        parser = etree.XMLParser(huge_tree=True, remove_blank_text=False, resolve_entities=False)
        self._root = etree.fromstring(self._doc_bytes, parser)
        self._styles = self._parse_styles(etree.fromstring(styles, parser) if styles else None)
        self._paras = self._collect()
        self._loaded = True

    @staticmethod
    def _main_part(z: zipfile.ZipFile, names: set[str]) -> str:
        if "_rels/.rels" in names:
            rels = etree.fromstring(z.read("_rels/.rels"))
            for rel in rels:
                if str(rel.get("Type", "")).endswith(REL_OFFICE_DOC):
                    target = str(rel.get("Target", "")).lstrip("/")
                    if target in names:
                        return target
        if "word/document.xml" in names:
            return "word/document.xml"
        raise KeyError("word/document.xml")

    def _parse_styles(self, root) -> dict[str, dict]:
        styles: dict[str, dict] = {}
        if root is None:
            return styles
        for st in root.iter(W + "style"):
            sid = st.get(W + "styleId")
            if not sid:
                continue
            name_el = st.find(W + "name")
            based = st.find(W + "basedOn")
            outline = st.find(f"{W}pPr/{W}outlineLvl")
            b = st.find(f"{W}rPr/{W}b")
            styles[sid] = {
                "name": (name_el.get(W + "val") if name_el is not None else sid) or sid,
                "based_on": based.get(W + "val") if based is not None else None,
                "outline": _int(outline.get(W + "val")) if outline is not None else None,
                "bold": (b is not None and str(b.get(W + "val", "1")).lower() not in _FALSE),
            }
        return styles

    def _style_chain(self, sid: str | None):
        seen = set()
        while sid and sid in self._styles and sid not in seen:
            seen.add(sid)
            yield self._styles[sid]
            sid = self._styles[sid]["based_on"]

    def _style_level(self, sid: str | None) -> int:
        for st in self._style_chain(sid):
            m = re.fullmatch(r"heading\s*(\d)", st["name"].strip(), re.IGNORECASE)
            if m:
                return int(m.group(1))
            if st["name"].strip().lower() == "title":
                return 1
            if st["outline"] is not None and st["outline"] < 9:
                return st["outline"] + 1
        return 0

    def _style_bold(self, sid: str | None) -> bool:
        return any(st["bold"] for st in self._style_chain(sid))

    @staticmethod
    def _in_skipped(el) -> bool:
        p = el.getparent()
        while p is not None:
            if p.tag in _SKIP_CONTAINERS:
                return True
            p = p.getparent()
        return False

    def _walk(self, el, out_text: list[str], runs: list, depth: int = 0) -> None:
        for child in el:
            tag = child.tag
            if tag in _SKIP_CONTAINERS or not isinstance(tag, str):
                continue
            if tag == W + "t":
                out_text.append(child.text or "")
            elif tag == W + "tab":
                out_text.append("\t")
            elif tag in (W + "br", W + "cr"):
                out_text.append(" ")
            elif tag == W + "noBreakHyphen":
                out_text.append("-")
            elif tag in (W + "del", W + "moveFrom"):
                continue
            else:
                if tag == W + "r":
                    runs.append(child)
                self._walk(child, out_text, runs, depth + 1)

    def _run_bold(self, r, para_bold: bool) -> bool:
        rpr = r.find(W + "rPr")
        if rpr is not None:
            b = rpr.find(W + "b")
            if b is not None:
                return str(b.get(W + "val", "1")).lower() not in _FALSE
            rs = rpr.find(W + "rStyle")
            if rs is not None and self._style_bold(rs.get(W + "val")):
                return True
        return para_bold

    def _make_para(self, p, pending: list[str]) -> _Para:
        text_parts: list[str] = []
        runs: list = []
        self._walk(p, text_parts, runs)
        text = normalize("".join(text_parts))
        ppr = p.find(W + "pPr")
        sid = None
        level = 0
        if ppr is not None:
            ps = ppr.find(W + "pStyle")
            sid = ps.get(W + "val") if ps is not None else None
            ol = ppr.find(W + "outlineLvl")
            if ol is not None and _int(ol.get(W + "val")) is not None and _int(ol.get(W + "val")) < 9:
                level = _int(ol.get(W + "val")) + 1
        if not level:
            level = self._style_level(sid)
        para_bold = self._style_bold(sid)
        text_runs = [r for r in runs if "".join(t.text or "" for t in r.iter(W + "t")).strip()]
        bold = bool(text) and len(text) <= BOLD_MAX_CHARS and bool(text_runs) and all(
            self._run_bold(r, para_bold) for r in text_runs)
        marks = list(pending)
        for bm in p.iter(W + "bookmarkStart"):
            if not self._in_skipped(bm) and bm.get(W + "name"):
                marks.append(bm.get(W + "name"))
        return _Para(el=p, text=text, level=level if text else 0, bold=bold and not level, bookmarks=marks)

    def _collect(self) -> list[_Para]:
        body = self._root.find(W + "body")
        if body is None:
            return []
        paras: list[_Para] = []
        pending: list[str] = []
        for el in body.iter(W + "p", W + "bookmarkStart"):
            if self._in_skipped(el):
                continue
            if el.tag == W + "bookmarkStart":
                parent = el.getparent()
                inside_p = False
                while parent is not None and parent is not body:
                    if parent.tag == W + "p":
                        inside_p = True
                        break
                    parent = parent.getparent()
                if not inside_p and el.get(W + "name"):
                    pending.append(el.get(W + "name"))
                continue
            paras.append(self._make_para(el, pending))
            pending = []
        return paras

    @property
    def paragraphs(self) -> list[_Para]:
        self._load()
        return self._paras

    def all_bookmarks(self) -> set[str]:
        self._load()
        return {str(b.get(W + "name")) for b in self._root.iter(W + "bookmarkStart") if b.get(W + "name")}

    def _index_of(self, anchor: str) -> int | None:
        for i, p in enumerate(self.paragraphs):
            if anchor in p.bookmarks:
                return i
        return None

    # -- adapter interface -------------------------------------------------
    def _section(self, i: int, p: _Para) -> Section:
        if p.level:
            kind = "heading"
        elif p.bold:
            kind = "bold"
        elif p.user_bookmark:
            kind = "bookmark"
        else:
            kind = "paragraph"
        return Section(label=p.text, anchor=p.sn_bookmark or p.user_bookmark, level=p.level, index=i, kind=kind)

    def sections(self, all: bool = False) -> list[Section]:
        out = []
        for i, p in enumerate(self.paragraphs):
            if not p.text and not p.user_bookmark:
                continue
            if p.level or p.user_bookmark or (all and p.bold):
                out.append(self._section(i, p))
        return out

    def find(self, target: str) -> list[Section]:
        t = normalize(target)
        tf = t.casefold()
        paras = list(enumerate(self.paragraphs))
        headish = [(i, p) for i, p in paras if p.text and (p.level or p.bold)]
        tiers = [
            [(i, p) for i, p in paras if t in p.bookmarks],
            [(i, p) for i, p in headish if p.text == t],
            [(i, p) for i, p in headish if p.text.casefold() == tf],
            [(i, p) for i, p in paras if p.text and p.text.casefold() == tf],
            [(i, p) for i, p in paras if tf and p.text.casefold().startswith(tf)],
        ]
        for tier in tiers:
            if tier:
                return [self._section(i, p) for i, p in tier]
        return []

    def ensure_anchor(self, section: Section, dry_run: bool = False) -> str:
        p = self.paragraphs[section.index]
        if p.sn_bookmark:
            return p.sn_bookmark
        name = bookmark_name(p.text or section.label, self.all_bookmarks())
        if dry_run:
            return name
        self._prepare_write()
        self._insert_bookmark(p.el, name)
        self._save()
        return name

    def remove_bookmark(self, anchor: str, dry_run: bool = False) -> bool:
        self._load()
        starts = [b for b in self._root.iter(W + "bookmarkStart") if b.get(W + "name") == anchor]
        if not starts:
            return False
        if dry_run:
            return True
        self._prepare_write()
        for start in starts:
            bid = start.get(W + "id")
            start.getparent().remove(start)
            for end in list(self._root.iter(W + "bookmarkEnd")):
                if end.get(W + "id") == bid:
                    end.getparent().remove(end)
        self._save()
        return True

    def has_anchor(self, anchor: str) -> bool:
        return self._index_of(anchor) is not None

    def label_for(self, anchor: str) -> str | None:
        i = self._index_of(anchor)
        return short_label(self.paragraphs[i].text) if i is not None else None

    def section_end(self, i: int) -> int:
        paras = self.paragraphs
        start = paras[i]
        for j in range(i + 1, len(paras)):
            q = paras[j]
            if not q.text:
                continue
            if start.level:
                if q.level and q.level <= start.level:
                    return j
            elif q.level or q.bold:
                return j
        return len(paras)

    def extract(self, anchor: str) -> str | None:
        i = self._index_of(anchor)
        if i is None:
            return None
        end = self.section_end(i)
        return "\n".join(p.text for p in self.paragraphs[i:end] if p.text)

    # -- pagination (optional, LibreOffice) ---------------------------------
    def paragraph_pages(self) -> list[int | None]:
        """Approximate page of each paragraph via a LibreOffice PDF. Raises ToolMissing."""
        from pypdf import PdfReader

        from slidenotes.util.office import cached_pdf, find_soffice

        if not find_soffice():
            raise ToolMissing(f"{display(self.path)}: page numbers need LibreOffice (soffice), which is not installed",
                              fix=None)
        pdf = cached_pdf(self.path)
        assert pdf is not None
        reader = PdfReader(str(pdf))
        squash = lambda s: re.sub(r"\s+", "", s).casefold()  # noqa: E731
        texts = [squash(page.extract_text() or "") for page in reader.pages]
        starts, combined, pos = [], [], 0
        for t in texts:
            starts.append(pos)
            combined.append(t)
            pos += len(t)
        whole = "".join(combined)
        result: list[int | None] = []
        cursor = 0
        for p in self.paragraphs:
            key = squash(p.text)[:40]
            if len(key) < 3:
                result.append(None)
                continue
            at = whole.find(key, cursor)
            if at < 0:
                result.append(None)
                continue
            page = max(k for k, s in enumerate(starts) if s <= at) + 1
            result.append(page)
            cursor = at + len(key)
        return result

    def section_on_page(self, page: int) -> Section:
        pages = self.paragraph_pages()
        for i, (p, pg) in enumerate(zip(self.paragraphs, pages)):
            if pg == page and p.text:
                return self._section(i, p)
        raise UsageError(f"{display(self.path)}: no paragraph starts on page {page} "
                         f"(LibreOffice found {max([x for x in pages if x] or [0])} pages)")

    def approx_page(self, anchor: str) -> int | None:
        i = self._index_of(anchor)
        if i is None:
            return None
        try:
            return self.paragraph_pages()[i]
        except Exception:
            return None

    # -- writing -----------------------------------------------------------
    def _prepare_write(self) -> None:
        check_unlocked(self.path)
        self.last_backup = backup_once(self.path) or self.last_backup

    def _insert_bookmark(self, p, name: str) -> None:
        ids = [_int(b.get(W + "id")) for b in self._root.iter(W + "bookmarkStart")]
        bid = str(max([i for i in ids if i is not None] + [-1]) + 1)
        # SubElement keeps the document's own `w:` prefix; then move the start into place.
        start = etree.SubElement(p, W + "bookmarkStart")
        start.set(W + "id", bid)
        start.set(W + "name", name)
        ppr = p.find(W + "pPr")
        p.remove(start)
        p.insert(list(p).index(ppr) + 1 if ppr is not None else 0, start)
        end = etree.SubElement(p, W + "bookmarkEnd")
        end.set(W + "id", bid)

    def _serialize(self) -> bytes:
        body = etree.tostring(self._root, encoding="UTF-8", xml_declaration=False)
        m = re.match(rb"\s*<\?xml[^>]*\?>\s*", self._doc_bytes)
        decl = m.group(0) if m else b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        return decl + body

    def _save(self) -> None:
        data = self._serialize()
        import io

        buf = io.BytesIO()
        with zipfile.ZipFile(self.path) as zin, zipfile.ZipFile(buf, "w") as zout:
            for item in zin.infolist():
                payload = data if item.filename == self._part else zin.read(item.filename)
                zout.writestr(item, payload)
        try:
            atomic_write_bytes(self.path, buf.getvalue())
        except PermissionError as e:
            raise LockedError(f"{display(self.path)}: cannot write (open in Word?); close it and rerun") from e
        self._loaded = False


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
