from .config import config
from .rules_loader import get_rules_meta_payload


RULES_META = get_rules_meta_payload(
    sources=config.sources,
    status={
        "unconfirmed": "未确认",
        "confirmed": "已确认",
        "pending_adjustment": "待调整",
        "adjusted": "已调整",
        "increased": "已增报",
        "partial_refunded": "已部分退费",
        "refunded": "已退费",
    },
)
