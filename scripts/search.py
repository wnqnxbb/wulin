#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""武林外传台词搜索引擎 - 纯标准库实现"""

import argparse
import json
import math
import os
import random
import re
import sys
from collections import Counter
from difflib import SequenceMatcher

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "lines.jsonl")


def load_data():
    """加载JSONL数据"""
    data = []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


# ============ BM25 搜索 ============

def tokenize(text):
    """字符级 bigram + 单字分词（适合中文无分词器场景）"""
    tokens = []
    # 单字
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff':
            tokens.append(ch)
    # bigram
    for i in range(len(text) - 1):
        if '\u4e00' <= text[i] <= '\u9fff' and '\u4e00' <= text[i + 1] <= '\u9fff':
            tokens.append(text[i] + text[i + 1])
    return tokens


class BM25:
    def __init__(self, documents, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.docs = documents
        self.doc_tokens = [tokenize(d) for d in documents]
        self.doc_lens = [len(t) for t in self.doc_tokens]
        self.avgdl = sum(self.doc_lens) / len(self.doc_lens) if self.doc_lens else 1
        self.N = len(documents)

        # 建立倒排索引
        self.df = Counter()
        self.tf = []
        for tokens in self.doc_tokens:
            tf = Counter(tokens)
            self.tf.append(tf)
            for token in set(tokens):
                self.df[token] += 1

    def score(self, query):
        query_tokens = tokenize(query)
        scores = []
        for i in range(self.N):
            s = 0.0
            dl = self.doc_lens[i]
            for qt in query_tokens:
                if qt not in self.tf[i]:
                    continue
                tf_val = self.tf[i][qt]
                df_val = self.df.get(qt, 0)
                idf = math.log((self.N - df_val + 0.5) / (df_val + 0.5) + 1)
                tf_norm = (tf_val * (self.k1 + 1)) / (tf_val + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
                s += idf * tf_norm
            scores.append(s)
        return scores


def cmd_search(data, query, top_n=10):
    """关键词搜索台词"""
    lines = [d["line"] for d in data]
    bm25 = BM25(lines)
    scores = bm25.score(query)

    ranked = sorted(enumerate(scores), key=lambda x: -x[1])
    results = []
    for idx, score in ranked[:top_n]:
        if score > 0:
            results.append({
                "line": data[idx]["line"],
                "char": data[idx]["char"],
                "ep": data[idx]["ep"],
                "score": round(score, 2),
            })
    return results


# ============ 模糊匹配 ============

def fuzzy_match(data, query, top_n=5, threshold=0.4):
    """用 SequenceMatcher 做模糊匹配"""
    results = []
    for d in data:
        ratio = SequenceMatcher(None, query, d["line"]).ratio()
        if ratio >= threshold:
            results.append({
                "line": d["line"],
                "char": d["char"],
                "ep": d["ep"],
                "seq": d["seq"],
                "score": round(ratio, 3),
            })
    results.sort(key=lambda x: -x["score"])
    return results[:top_n]


def cmd_match(data, query, top_n=5):
    """模糊匹配找原句"""
    return fuzzy_match(data, query, top_n=top_n)


# ============ 接龙 ============

def cmd_next(data, query, adapt=None, top_n=3):
    """接龙：找到匹配的台词，返回下一句"""
    # 先模糊匹配找到原句
    matches = fuzzy_match(data, query, top_n=5, threshold=0.3)
    if not matches:
        return []

    # 建立 (ep, seq) -> data 的索引
    ep_seq_map = {}
    for d in data:
        ep_seq_map[(d["ep"], d["seq"])] = d

    results = []
    seen = set()
    for m in matches:
        ep, seq = m["ep"], m["seq"]
        # 找同集的下一句
        next_d = ep_seq_map.get((ep, seq + 1))
        if next_d and next_d["line"] not in seen:
            next_line = next_d["line"]
            # 名词替换
            if adapt:
                for pair in adapt.split(","):
                    if "=" in pair:
                        old, new = pair.split("=", 1)
                        next_line = next_line.replace(old.strip(), new.strip())
            seen.add(next_d["line"])
            results.append({
                "matched": m["line"],
                "matched_char": m["char"],
                "matched_score": m["score"],
                "next_line": next_line,
                "next_char": next_d["char"],
                "ep": ep,
            })
    return results[:top_n]


# ============ 随机 ============

def cmd_random(data, char=None, n=1):
    """随机台词"""
    pool = data
    if char:
        pool = [d for d in data if char in d["char"]]
        if not pool:
            return []

    # 过滤掉太短的台词
    pool = [d for d in pool if len(d["line"]) >= 4]
    samples = random.sample(pool, min(n, len(pool)))
    return [{"line": s["line"], "char": s["char"], "ep": s["ep"]} for s in samples]


# ============ CLI ============

def format_output(results, mode="search"):
    """格式化输出"""
    if not results:
        print("No results found.")
        return

    for i, r in enumerate(results, 1):
        if mode == "next":
            print(f"[{i}] Match ({r['matched_score']:.1%}): {r['matched_char']}: {r['matched']}")
            print(f"    Next: {r['next_char']}: {r['next_line']}")
        elif mode == "random":
            print(f"{r['line']}")
        else:
            line = r["line"]
            char = r["char"]
            ep = r["ep"]
            score = r.get("score", "")
            print(f"[{i}] (E{ep:02d}, {score}) {char}: {line}")


def main():
    parser = argparse.ArgumentParser(description="武林外传台词搜索")
    sub = parser.add_subparsers(dest="command")

    # search
    p_search = sub.add_parser("search", help="关键词搜索台词")
    p_search.add_argument("query", help="搜索关键词")
    p_search.add_argument("-n", "--top", type=int, default=10, help="返回条数")

    # match
    p_match = sub.add_parser("match", help="模糊匹配找原句")
    p_match.add_argument("query", help="台词（可能不完整或改编过）")
    p_match.add_argument("-n", "--top", type=int, default=5, help="返回条数")

    # next
    p_next = sub.add_parser("next", help="接龙找下一句")
    p_next.add_argument("query", help="台词")
    p_next.add_argument("--adapt", help="名词替换，格式: 旧=新,旧2=新2")
    p_next.add_argument("-n", "--top", type=int, default=3, help="返回条数")

    # random
    p_random = sub.add_parser("random", help="随机台词")
    p_random.add_argument("--char", help="角色名过滤")
    p_random.add_argument("-n", "--count", type=int, default=1, help="数量")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    data = load_data()

    if args.command == "search":
        results = cmd_search(data, args.query, top_n=args.top)
        format_output(results, "search")
    elif args.command == "match":
        results = cmd_match(data, args.query, top_n=args.top)
        format_output(results, "match")
    elif args.command == "next":
        results = cmd_next(data, args.query, adapt=args.adapt, top_n=args.top)
        format_output(results, "next")
    elif args.command == "random":
        results = cmd_random(data, char=args.char, n=args.count)
        format_output(results, "random")


if __name__ == "__main__":
    main()
