"""Token + image cost accumulator."""
from decimal import Decimal
from typing import Optional

from app.utils.logging import get_logger

log = get_logger(__name__)

# OpenAI pricing (USD) — update as needed
PRICE_GPT4O_INPUT = Decimal("0.000005")   # per token
PRICE_GPT4O_OUTPUT = Decimal("0.000015")  # per token
PRICE_DALLE3_STANDARD = Decimal("0.040")  # per image (1024x1792)
PRICE_TTS_1 = Decimal("0.000015")         # per character


class CostTracker:
    """Accumulates costs for a single run."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._total = Decimal("0")

    @property
    def total_usd(self) -> Decimal:
        return self._total

    def add_gpt4o(self, prompt_tokens: int, completion_tokens: int) -> Decimal:
        cost = (
            Decimal(prompt_tokens) * PRICE_GPT4O_INPUT
            + Decimal(completion_tokens) * PRICE_GPT4O_OUTPUT
        )
        self._total += cost
        log.debug("cost.gpt4o", cost=float(cost), total=float(self._total))
        return cost

    def add_dalle3(self, count: int = 1) -> Decimal:
        cost = PRICE_DALLE3_STANDARD * count
        self._total += cost
        log.debug("cost.dalle3", count=count, cost=float(cost), total=float(self._total))
        return cost

    def add_tts(self, char_count: int) -> Decimal:
        cost = PRICE_TTS_1 * char_count
        self._total += cost
        log.debug("cost.tts", chars=char_count, cost=float(cost), total=float(self._total))
        return cost

    def add_raw(self, amount: Decimal, label: Optional[str] = None) -> Decimal:
        self._total += amount
        log.debug("cost.raw", label=label, amount=float(amount), total=float(self._total))
        return amount

    def flush_to_db(self, db_session, run_id: Optional[str] = None) -> None:
        """Persist accumulated cost to the runs table."""
        from app.db.models import Run
        rid = run_id or self.run_id
        run = db_session.get(Run, rid)
        if run:
            run.cost_usd = self._total
            db_session.flush()
