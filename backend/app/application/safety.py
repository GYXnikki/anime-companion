import re
from dataclasses import dataclass

from app.domain.events import SafetyCategory

SAFETY_RESPONSE = (
    "我很在意你现在的感受。如果你正处在危险中，请先保证自己的安全："
    "立即拨打 120 或 110，或联系身边可信的人陪着你。"
    "我是 AI，不能替代专业帮助，也不会继续追问细节。"
)

CRISIS_KEYWORDS: tuple[str, ...] = (
    "自杀",
    "自残",
    "不想活",
    "活着没意思",
    "结束生命",
    "伤害自己",
    "杀了自己",
    "跳楼",
    "割腕",
    "想消失",
)

_WHITESPACE = re.compile(r"[\s\u200b\u200c\u200d\ufeff]+")


@dataclass(frozen=True)
class SafetyHit:
    category: SafetyCategory
    matched_keyword: str


@dataclass(frozen=True)
class SafetyDecision:
    hit: SafetyHit | None = None

    @property
    def triggered(self) -> bool:
        return self.hit is not None


def normalize_text(text: str) -> str:
    """Remove whitespace and zero-width characters before keyword matching."""
    return _WHITESPACE.sub("", text).lower()


class SafetyService:
    """Deterministic crisis check that runs before any LLM call."""

    def __init__(self, keywords: tuple[str, ...] = CRISIS_KEYWORDS) -> None:
        self._keywords = tuple(normalize_text(keyword) for keyword in keywords)

    def check(self, text: str) -> SafetyDecision:
        normalized = normalize_text(text)
        for keyword in self._keywords:
            if keyword and keyword in normalized:
                return SafetyDecision(
                    hit=SafetyHit(category="self_harm", matched_keyword=keyword)
                )
        return SafetyDecision()
