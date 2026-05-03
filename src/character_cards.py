"""
SillyTavern 系角色卡 → Markdown，输出到 character/char_md。

- **PNG**：读取内嵌 **chara** 元数据块（tEXt / zTXt / iTXt）。
- **JSON**：`char_pic` 下与立绘**同名**的 `.json`（从 SillyTavern 等导出）可直接转 md；适合「配图是 JPG/WebP、卡数据在 JSON」的情况。

JPEG/WebP 等 **栅格图不含 chara**，不能从内嵌解析；请使用 ST 导出的**角色卡 PNG**，或放置同名 **`.json`**。

可命令行运行：python character_cards.py（为 char_pic 中尚无对应 md 的源文件生成 Markdown）。
"""
from __future__ import annotations

import base64
import json
import os
import zlib
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Tuple

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAR_PIC_DIR = os.path.join(_PROJECT_ROOT, "character", "char_pic")
CHAR_MD_DIR = os.path.join(_PROJECT_ROOT, "character", "char_md")

PNG_SIG = b"\x89PNG\r\n\x1a\n"

# 无 chara 的栅格立绘：需同名 .json 或由 PNG 角色卡提供数据
_RASTER_NO_CHARA_EXTS = (
    ".jpg",
    ".jpeg",
    ".JPG",
    ".JPEG",
    ".webp",
    ".WEBP",
)


@dataclass
class PicParseResult:
    stem: str
    status: str  # "ok" | "skip" | "err"
    detail: str


def _iter_png_chunks(data: bytes) -> Iterator[Tuple[bytes, bytes]]:
    pos = 8
    n = len(data)
    while pos + 8 <= n:
        length = int.from_bytes(data[pos : pos + 4], "big")
        ctype = data[pos + 4 : pos + 8]
        if pos + 12 + length > n:
            break
        chunk = data[pos + 8 : pos + 8 + length]
        yield ctype, chunk
        pos += 12 + length


def _decode_chara_text_payload(text: str) -> Dict[str, Any]:
    raw = base64.b64decode(text.strip(), validate=False)
    # SillyTavern 常见：zlib 压缩 JSON
    try:
        decompressed = zlib.decompress(raw)
        return json.loads(decompressed.decode("utf-8"))
    except (zlib.error, json.JSONDecodeError):
        pass
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass
    raise ValueError("无法将 chara 载荷解析为 JSON")


def _extract_chara_json_from_png_bytes(data: bytes) -> Dict[str, Any]:
    if not data.startswith(PNG_SIG):
        raise ValueError("不是 PNG 文件")

    for ctype, chunk in _iter_png_chunks(data):
        if ctype == b"tEXt":
            null = chunk.find(b"\x00")
            if null <= 0:
                continue
            keyword = chunk[:null].decode("latin-1", errors="replace")
            if keyword != "chara":
                continue
            text = chunk[null + 1 :].decode("latin-1", errors="replace")
            return _decode_chara_text_payload(text)

        if ctype == b"zTXt":
            null = chunk.find(b"\x00")
            if null <= 0:
                continue
            keyword = chunk[:null].decode("latin-1", errors="replace")
            if keyword != "chara":
                continue
            if null + 2 > len(chunk):
                continue
            compressed = chunk[null + 2 :]
            try:
                plain = zlib.decompress(compressed).decode("utf-8")
            except Exception as e:
                raise ValueError(f"zTXt chara 解压失败: {e}") from e
            return json.loads(plain)

        if ctype == b"iTXt":
            # keyword\0 compression_flag compression_method lang\0 trans_kw\0 text
            null = chunk.find(b"\x00")
            if null <= 0:
                continue
            keyword = chunk[:null].decode("latin-1", errors="replace")
            if keyword != "chara":
                continue
            if null + 3 > len(chunk):
                continue
            comp_flag = chunk[null + 1]
            rest = chunk[null + 3 :]
            n_lang = rest.find(b"\x00")
            if n_lang < 0:
                continue
            rest = rest[n_lang + 1 :]
            n_tr = rest.find(b"\x00")
            if n_tr < 0:
                continue
            text_bytes = rest[n_tr + 1 :]
            if comp_flag == 1:
                try:
                    text_bytes = zlib.decompress(text_bytes)
                except Exception as e:
                    raise ValueError(f"iTXt chara 解压失败: {e}") from e
            try:
                return json.loads(text_bytes.decode("utf-8"))
            except json.JSONDecodeError as e:
                raise ValueError(f"iTXt chara JSON 无效: {e}") from e

    raise ValueError(
        "PNG 中未找到 chara 角色数据块（多为普通立绘图）。请使用 SillyTavern "
        "「导出角色卡」得到的 PNG，或在 char_pic 放置同名 .json 角色数据文件。"
    )


def extract_card_dict_from_json_file(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("JSON 根节点必须是对象")
    return data


def extract_card_dict_from_png(path: str) -> Dict[str, Any]:
    with open(path, "rb") as f:
        data = f.read()
    return _extract_chara_json_from_png_bytes(data)


def card_dict_to_markdown(card: Dict[str, Any]) -> str:
    name = (card.get("name") or "").strip() or "未命名"
    lines: List[str] = [f"# {name}", ""]

    sections: List[Tuple[str, str]] = [
        ("描述", "description"),
        ("性格", "personality"),
        ("场景", "scenario"),
        ("首条消息", "first_mes"),
        ("示例对话", "mes_example"),
        ("作者备注", "creator_notes"),
        ("系统提示（卡内）", "system_prompt"),
        ("后记指令", "post_history_instructions"),
    ]
    for title, key in sections:
        val = card.get(key)
        if isinstance(val, str) and val.strip():
            lines.append(f"## {title}")
            lines.append("")
            lines.append(val.strip())
            lines.append("")

    alts = card.get("alternate_greetings")
    if isinstance(alts, list) and alts:
        lines.append("## 其它开场")
        lines.append("")
        for i, g in enumerate(alts, start=1):
            if isinstance(g, str) and g.strip():
                lines.append(f"### 开场 {i}")
                lines.append("")
                lines.append(g.strip())
                lines.append("")

    book = card.get("character_book")
    if isinstance(book, dict):
        entries = book.get("entries")
        if isinstance(entries, list) and entries:
            lines.append("## 角色书条目（摘要）")
            lines.append("")
            for i, ent in enumerate(entries[:40], start=1):
                if not isinstance(ent, dict):
                    continue
                keys = ent.get("keys")
                content = ent.get("content")
                key_part = (
                    ", ".join(keys)
                    if isinstance(keys, list)
                    else str(keys or "")
                )
                if isinstance(content, str):
                    snippet = content.strip().replace("\n", " ")
                    if len(snippet) > 200:
                        snippet = snippet[:200] + "…"
                else:
                    snippet = ""
                lines.append(f"- **{i}.** 关键词: {key_part} — {snippet}")
            if len(entries) > 40:
                lines.append(f"- … 共 {len(entries)} 条，此处仅列前 40 条")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def list_source_stems(char_pic_dir: str = CHAR_PIC_DIR) -> List[str]:
    """char_pic 下 png/jpg/jpeg/webp/json 的文件名 stem 并集。"""
    if not os.path.isdir(char_pic_dir):
        return []
    stems: set[str] = set()
    suf = (".png", ".jpg", ".jpeg", ".webp", ".json")
    for name in os.listdir(char_pic_dir):
        path = os.path.join(char_pic_dir, name)
        if not os.path.isfile(path):
            continue
        lower = name.lower()
        if any(lower.endswith(s) for s in suf):
            stems.add(os.path.splitext(name)[0])
    return sorted(stems)


def list_md_filenames(char_md_dir: str = CHAR_MD_DIR) -> List[str]:
    if not os.path.isdir(char_md_dir):
        return []
    files = []
    for name in os.listdir(char_md_dir):
        if name.lower().endswith(".md") and os.path.isfile(
            os.path.join(char_md_dir, name)
        ):
            files.append(name)
    return sorted(files)


def parse_png_to_md_file(
    png_path: str, md_path: str, overwrite: bool = False
) -> None:
    if os.path.exists(md_path) and not overwrite:
        return
    card = extract_card_dict_from_png(png_path)
    md = card_dict_to_markdown(card)
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)


def parse_json_card_to_md_file(json_path: str, md_path: str, overwrite: bool = False) -> None:
    if os.path.exists(md_path) and not overwrite:
        return
    card = extract_card_dict_from_json_file(json_path)
    md = card_dict_to_markdown(card)
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)


def parse_missing_pics(
    char_pic_dir: str = CHAR_PIC_DIR,
    char_md_dir: str = CHAR_MD_DIR,
) -> List[PicParseResult]:
    os.makedirs(char_pic_dir, exist_ok=True)
    os.makedirs(char_md_dir, exist_ok=True)
    results: List[PicParseResult] = []
    stems = list_source_stems(char_pic_dir)
    existing_md = {os.path.splitext(n)[0] for n in list_md_filenames(char_md_dir)}

    for stem in stems:
        md_path = os.path.join(char_md_dir, f"{stem}.md")
        json_path = os.path.join(char_pic_dir, f"{stem}.json")

        if stem in existing_md:
            results.append(PicParseResult(stem, "skip", "已有对应 .md"))
            continue

        if os.path.isfile(json_path):
            try:
                parse_json_card_to_md_file(json_path, md_path, overwrite=False)
                results.append(PicParseResult(stem, "ok", "已从同名 .json 写入"))
                existing_md.add(stem)
            except Exception as e:
                results.append(PicParseResult(stem, "err", f".json 解析失败: {e}"))
            continue

        png_path = os.path.join(char_pic_dir, f"{stem}.png")
        if not os.path.isfile(png_path):
            alt = os.path.join(char_pic_dir, f"{stem}.PNG")
            if os.path.isfile(alt):
                png_path = alt
        if os.path.isfile(png_path):
            try:
                parse_png_to_md_file(png_path, md_path, overwrite=False)
                results.append(PicParseResult(stem, "ok", "已从 PNG 内嵌 chara 写入"))
                existing_md.add(stem)
            except Exception as e:
                results.append(PicParseResult(stem, "err", str(e)))
            continue

        for ext in _RASTER_NO_CHARA_EXTS:
            jp = os.path.join(char_pic_dir, f"{stem}{ext}")
            if os.path.isfile(jp):
                results.append(
                    PicParseResult(
                        stem,
                        "err",
                        "仅图像立绘（JPEG/WebP 等）无法解析角色数据（无 chara，常见于 "
                        "Pixiv master1200 等导出）。请在 char_pic 放置同名 "
                        f"{stem}.json，或改用 SillyTavern 导出的含 chara 的 PNG。",
                    )
                )
                break
        else:
            results.append(PicParseResult(stem, "err", "无可用 .json / .png 数据源"))

    return results


def format_parse_report(results: List[PicParseResult]) -> str:
    if not results:
        return "character/char_pic 下没有可处理的 png/jpg/webp/json。"
    lines: List[str] = []
    for r in results:
        if r.status == "ok":
            lines.append(f"[OK] {r.stem}.md — {r.detail}")
        elif r.status == "skip":
            lines.append(f"[--] {r.stem} — 跳过（{r.detail}）")
        else:
            lines.append(f"[!!] {r.stem} — {r.detail}")
    ok = sum(1 for r in results if r.status == "ok")
    lines.append("")
    lines.append(f"完成：新解析 {ok} 个。")
    return "\n".join(lines)


def run_parse_missing_report() -> str:
    return format_parse_report(parse_missing_pics())


if __name__ == "__main__":
    print(run_parse_missing_report())
