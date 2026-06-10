"""Cost tracking — gom usage từ mỗi LLM response, ước lượng $ USD.

Claude Code equivalent: cost-tracker.ts
"""

from dataclasses import dataclass


PRICING = {
    "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.0},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
    "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
    "gpt-4o": {"input": 2.50, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}


@dataclass
class CostTracker:
    model: str = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_api_calls: int = 0

    def add(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_api_calls += 1

    @property
    def estimated_cost_usd(self) -> float:
        pricing = PRICING.get(self.model, {"input": 1.0, "output": 5.0})
        input_cost = (self.total_input_tokens / 1_000_000) * pricing["input"]
        output_cost = (self.total_output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost

    def summary(self) -> str:
        return (
            f"Model: {self.model} | "
            f"Tokens: {self.total_input_tokens:,} in / {self.total_output_tokens:,} out | "
            f"API calls: {self.total_api_calls} | "
            f"Cost: ~${self.estimated_cost_usd:.4f}"
        )
