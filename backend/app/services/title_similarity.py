# backend/app/services/title_similarity.py
from __future__ import annotations

from rapidfuzz import fuzz


import re
from dataclasses import dataclass
from typing import List, Set


# 一组非常保守的停用词：只去掉“几乎永远不承载事件信息”的词
# （我们宁愿少删，也不要误删关键信息）
STOPWORDS: Set[str] = {
    "a", "an", "the",
    "and", "or", "but",
    "to", "of", "in", "on", "at", "for", "with", "from", "by", "as",
    "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those",
    "after", "before", "during", "over", "under",
    "up", "down", "into", "out", "off", "near",
    "new", "latest", "live", "update", "updates", "watch", "video",
}

# 用正则把“非字母数字”当作分隔符（保留数字：比如“G7”“737”“2025”有时有意义）
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

def fuzz_token_set_ratio(title_a: str, title_b: str) -> float:
    """
    返回 0~100 的分数，越高越像。
    token_set_ratio 对短标题、词序变化很鲁棒。
    """
    a = " ".join(normalize_title(title_a))
    b = " ".join(normalize_title(title_b))
    return float(fuzz.token_set_ratio(a, b))


def _simple_stem(token: str) -> str:
    """
    极简词形归一化（白盒规则，不是 ML）：
    - floods/flooding -> flood
    - killed -> kill
    - leaves -> leave
    注意：这是工程启发式，不追求语言学完美，只追求稳定性。
    """
    # 常见后缀，按“从长到短”处理更安全
    for suf in ("ing", "ed", "es", "s"):
        if token.endswith(suf) and len(token) > len(suf) + 2:
            return token[: -len(suf)]
    return token


def normalize_title(title: str) -> List[str]:
    """
    把标题归一化成“token 列表”，用于相似度计算。

    规则（可解释、可控）：
    1) 小写化（避免大小写造成假差异）
    2) 用非字母数字做切分（标点/引号/破折号等都不应影响语义）
    3) 去掉停用词（减少噪声）
    4) 去掉过短 token（如 's' 't' 这类通常是噪声）
    """
    t = title.strip().lower()
    # 把各种标点当成空格
    t = _NON_ALNUM_RE.sub(" ", t)

    raw_tokens = [tok for tok in t.split(" ") if tok]  # 去掉空字符串
    tokens: List[str] = []
    for tok in raw_tokens:
        if tok in STOPWORDS:
            continue
        if len(tok) <= 1:
            continue
        tokens.append(_simple_stem(tok))

    return tokens


def tokens_to_set(tokens: List[str]) -> Set[str]:
    """把 token 列表变成集合，用于 Jaccard。"""
    return set(tokens)


def jaccard_similarity(a: Set[str], b: Set[str]) -> float:
    """
    Jaccard 相似度 = |交集| / |并集|
    完全可解释：你能打印交集和并集看为什么像/不像。
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = a.intersection(b)
    uni = a.union(b)
    return len(inter) / len(uni)


@dataclass(frozen=True)
class TitleCompareResult:
    tokens_a: List[str]
    tokens_b: List[str]
    set_a: Set[str]
    set_b: Set[str]
    intersection: Set[str]
    union: Set[str]
    jaccard: float


def explain_jaccard(title_a: str, title_b: str) -> TitleCompareResult:
    """
    给教学/调参用：返回完整中间产物，让你看到“为什么像/不像”。
    """
    tokens_a = normalize_title(title_a)
    tokens_b = normalize_title(title_b)
    set_a = tokens_to_set(tokens_a)
    set_b = tokens_to_set(tokens_b)
    inter = set_a.intersection(set_b)
    uni = set_a.union(set_b)
    j = jaccard_similarity(set_a, set_b)
    return TitleCompareResult(
        tokens_a=tokens_a,
        tokens_b=tokens_b,
        set_a=set_a,
        set_b=set_b,
        intersection=inter,
        union=uni,
        jaccard=j,
    )


if __name__ == "__main__":
    # 你可以先用这三组示例跑通，确认归一化工作正常
    pairs = [
        ("Five killed after strong quake in Japan", "Japan earthquake leaves several dead"),
        ("Trump says tariffs will start next week", "Tariffs to begin next week, Trump says"),
        ("Live: Floods hit northern England as rain continues", "Flooding in northern England after heavy rain"),
    ]

    for a, b in pairs:
        r = explain_jaccard(a, b)
        print("=" * 80)
        print("A:", a)
        print("B:", b)
        print("tokens_a:", r.tokens_a)
        print("tokens_b:", r.tokens_b)
        print("intersection:", sorted(r.intersection))
        print("union:", sorted(r.union))
        print("jaccard:", round(r.jaccard, 3))
        print("fuzz_token_set_ratio:", round(fuzz_token_set_ratio(a, b), 1))

