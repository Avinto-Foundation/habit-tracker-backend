from datetime import date


class IsoDateConverter:
    """Lets URLs contain a day like /checkins/2026-11-20/ and hands the view a `date`.

    An impossible day such as 2026-02-30 raises ValueError, which Django treats as
    "this URL doesn't match", so the answer is a 404.
    """

    regex = r"\d{4}-\d{2}-\d{2}"

    def to_python(self, value: str) -> date:
        return date.fromisoformat(value)

    def to_url(self, value) -> str:
        return value.isoformat() if isinstance(value, date) else str(value)
