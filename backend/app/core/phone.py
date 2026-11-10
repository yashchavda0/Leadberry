import re


def normalize_phone(value: str) -> str:
    number = value.strip()
    if not number or not re.fullmatch(r"[+0-9()\s.-]+", number):
        return number
    compact = re.sub(r"[()\s.-]", "", number)
    if re.fullmatch(r"(?:\+91|0091|91)[0-9]{10}", compact):
        return compact[-10:]
    if re.fullmatch(r"[0-9]{10}", compact):
        return compact
    return number