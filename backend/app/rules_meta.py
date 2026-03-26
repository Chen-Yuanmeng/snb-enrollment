from .config import config
from .rules_loader import get_rules_meta_payload


RULES_META = get_rules_meta_payload(
    sources=config.sources,
    status={
        "quoted": "已报价",
        "paid": "已缴费",
        "refund_requested": "已提交退费申请",
        "refunded": "已退费",
    },
)
