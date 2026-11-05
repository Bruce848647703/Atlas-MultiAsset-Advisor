"""Input validation shared by the API, CLI, tools and dashboard.

Bad numbers currently reach the optimizer/backtester and either crash deep in
numpy or silently produce nonsense (negative capital, NaN contributions,
out-of-range questionnaire answers). Fail early with a message the caller can
show to the user.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Sequence


class InputValidationError(ValueError):
    """Raised when a user/API input is invalid (safe to show to the user)."""


def finite_number(value: Any, name: str, *,
                  minimum: float | None = None,
                  maximum: float | None = None) -> float:
    if isinstance(value, bool):
        raise InputValidationError(f"{name} 必须是数字 (got bool)")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise InputValidationError(f"{name} 必须是数字 (got {value!r})") from exc
    if not math.isfinite(number):
        raise InputValidationError(f"{name} 必须是有限数字 (got {value!r})")
    if minimum is not None and number < minimum:
        raise InputValidationError(f"{name} 不能小于 {minimum:g} (got {number:g})")
    if maximum is not None and number > maximum:
        raise InputValidationError(f"{name} 不能大于 {maximum:g} (got {number:g})")
    return number


def integer(value: Any, name: str, *,
            minimum: int | None = None,
            maximum: int | None = None) -> int:
    number = finite_number(value, name, minimum=minimum, maximum=maximum)
    if not number.is_integer():
        raise InputValidationError(f"{name} 必须是整数 (got {value!r})")
    return int(number)


def text_value(value: Any, name: str, *,
               max_chars: int = 4000,
               allow_empty: bool = True) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise InputValidationError(f"{name} 必须是文本 (got {type(value).__name__})")
    text = value.strip()
    if len(text) > max_chars:
        raise InputValidationError(f"{name} 过长（最多 {max_chars} 字符）")
    if not allow_empty and not text:
        raise InputValidationError(f"{name} 不能为空")
    return text


def normalize_answers(answers: Any, questions: Sequence) -> Dict[int, int]:
    """Validate/normalise {question_index: option_index} against the survey."""
    if not isinstance(answers, Mapping):
        raise InputValidationError("问卷答案 answers 必须是 {题号: 选项} 字典")
    out: Dict[int, int] = {}
    for raw_key, raw_value in answers.items():
        try:
            idx = int(raw_key)
        except (TypeError, ValueError) as exc:
            raise InputValidationError(f"问卷题号无效: {raw_key!r}") from exc
        if idx < 0 or idx >= len(questions):
            raise InputValidationError(
                f"问卷题号超出范围: {idx}（应为 0-{len(questions) - 1}）")
        try:
            option = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise InputValidationError(
                f"第 {idx} 题的选项必须是整数 (got {raw_value!r})") from exc
        choices = len(questions[idx][3])
        if option < 0 or option >= choices:
            raise InputValidationError(
                f"第 {idx} 题的选项超出范围: {option}（应为 0-{choices - 1}）")
        out[idx] = option
    return out


def fraction(value: Any, name: str, *, minimum: float = 0.0,
             maximum: float = 1.0) -> float:
    return finite_number(value, name, minimum=minimum, maximum=maximum)