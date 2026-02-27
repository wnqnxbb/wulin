#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从武林外传PDF提取台词到JSONL格式"""

import json
import re
import sys

import pdfplumber

PDF_PATH = "/Users/zhaomingxuan/tmp/MyOwnSwordsman/武林外传全剧本.pdf"
OUTPUT_PATH = "/Users/zhaomingxuan/.claude/skills/wulin/data/lines.jsonl"

# 已知角色名（含简称），用于辅助识别
KNOWN_CHARS = {
    "佟湘玉", "白展堂", "吕秀才", "郭芙蓉", "李大嘴", "莫小贝", "邢育森",
    "燕小六", "祝无双", "钱夫人", "老白", "老邢", "小贝", "小郭", "大嘴",
    "秀才", "掌柜", "展堂", "无双", "小六", "佟掌柜", "吕轻侯",
    "众 人", "众人", "白、郭、吕", "白、郭、吕、李",
    "小 青", "小青", "赛貂蝉", "扈十娘", "展红绫", "杨蕙兰",
    "钱掌柜", "老钱", "雌雄双煞", "公孙乌龙", "姬无命",
    "包大仁", "谢步东", "平谷一点红", "追风", "凌腾云",
    "柳星雨", "柳月云", "杜子俊", "吕圣人", "王豆豆",
    "慕容嫣", "辛普森", "郭蔷薇", "郭芙蓉父", "佟石头",
    "侯三", "雷老五", "老吴", "江小道", "金湘玉", "白母",
    "南宫残花", "韩娟", "断指轩辕", "胡一菲", "诸葛孔方",
}


def extract_text(pdf_path):
    """提取PDF全文，跳过目录和制作说明页"""
    full_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            # 跳过封面、制作说明、目录（前7页左右）
            if i < 7:
                continue
            text = page.extract_text()
            if text:
                full_text.append(text)
    return "\n".join(full_text)


def parse_lines(text):
    """解析台词，返回结构化数据列表"""
    lines_data = []
    current_ep = 0
    seq = 0

    # 按行处理
    raw_lines = text.split("\n")

    # 集数标题正则
    ep_pattern = re.compile(r"第\s*([一二三四五六七八九十百零\d]+)\s*回\s")
    # 台词行正则：角色名 + 中文冒号 + 台词
    # 角色名可能包含空格（如"众 人"）、顿号（如"白、郭、吕"）
    dialogue_pattern = re.compile(r"^([^\s：]{1,8}(?:[、\s][^\s：]{1,6})*)\s*：(.+)$")
    # 页码行
    page_num_pattern = re.compile(r"^\d+$")
    # 场景标记
    scene_pattern = re.compile(r"^【.+】$")

    current_char = None
    current_line_text = None

    def flush_line():
        """保存当前累积的台词"""
        nonlocal current_char, current_line_text, seq
        if current_char and current_line_text:
            # 清理台词：去除括号内的动作描述，但保留有意义的内容
            cleaned = clean_dialogue(current_line_text)
            if cleaned and len(cleaned) >= 2:
                seq += 1
                lines_data.append({
                    "id": len(lines_data) + 1,
                    "ep": current_ep,
                    "seq": seq,
                    "char": current_char.replace(" ", ""),
                    "line": cleaned,
                })
        current_char = None
        current_line_text = None

    def clean_dialogue(text):
        """清理台词文本"""
        # 去除纯动作描述的括号内容
        text = re.sub(r"（[^）]*）", "", text)
        text = re.sub(r"\([^)]*\)", "", text)
        # 清理多余空格和标点
        text = text.strip()
        text = re.sub(r"\s+", "", text)
        # 替换特殊省略号
        text = text.replace("„„", "……")
        text = text.replace("...", "……")
        text = text.replace("~", "～")
        return text

    for raw_line in raw_lines:
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        # 跳过页码
        if page_num_pattern.match(raw_line):
            continue

        # 跳过场景标记
        if scene_pattern.match(raw_line):
            flush_line()
            continue

        # 检测集数标题
        ep_match = ep_pattern.search(raw_line)
        if ep_match:
            flush_line()
            ep_str = ep_match.group(1)
            current_ep = cn_num_to_int(ep_str)
            seq = 0
            continue

        # 检测台词行
        dlg_match = dialogue_pattern.match(raw_line)
        if dlg_match:
            char_name = dlg_match.group(1).strip()
            dialogue_text = dlg_match.group(2).strip()

            # 验证是否为合理的角色名（排除误匹配）
            normalized = char_name.replace(" ", "")
            if is_valid_char(normalized):
                flush_line()
                current_char = char_name
                current_line_text = dialogue_text
                continue

        # 续行（不以角色名开头的对话继续）
        if current_char and current_line_text:
            # 如果当前行不像是场景描述或纯括号动作
            if not raw_line.startswith("（") or "）" not in raw_line:
                current_line_text += raw_line

    flush_line()
    return lines_data


def is_valid_char(name):
    """检查是否是合理的角色名"""
    # 已知角色直接通过
    if name in KNOWN_CHARS:
        return True
    # 2-4个中文字符的名字
    if re.match(r"^[\u4e00-\u9fff]{2,6}$", name):
        return True
    # 含顿号的多人
    if "、" in name:
        return True
    return False


def cn_num_to_int(s):
    """中文数字转阿拉伯数字"""
    if s.isdigit():
        return int(s)

    cn_map = {
        "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
        "十": 10, "百": 100,
    }

    result = 0
    current = 0
    for ch in s:
        if ch in cn_map:
            val = cn_map[ch]
            if val >= 10:
                if current == 0:
                    current = 1
                result += current * val
                current = 0
            else:
                current = val
    result += current
    return result


def main():
    print(f"Reading PDF: {PDF_PATH}")
    text = extract_text(PDF_PATH)
    print(f"Extracted {len(text)} characters of text")

    print("Parsing dialogue lines...")
    lines_data = parse_lines(text)
    print(f"Found {len(lines_data)} dialogue lines across {max(d['ep'] for d in lines_data)} episodes")

    # 写入JSONL
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for item in lines_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"Written to {OUTPUT_PATH}")

    # 抽查
    print("\n--- Sample lines ---")
    import random
    samples = random.sample(lines_data, min(10, len(lines_data)))
    for s in sorted(samples, key=lambda x: x["id"]):
        print(f"  [E{s['ep']:02d} #{s['seq']:03d}] {s['char']}: {s['line'][:60]}")

    # 统计
    chars = {}
    for d in lines_data:
        chars[d["char"]] = chars.get(d["char"], 0) + 1
    print("\n--- Top characters ---")
    for char, count in sorted(chars.items(), key=lambda x: -x[1])[:15]:
        print(f"  {char}: {count} lines")


if __name__ == "__main__":
    main()
