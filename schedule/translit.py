"""Транслитерация кириллицы и казахских букв в латиницу для slug'ов.

Django's ``slugify(..., allow_unicode=False)`` вырезает все не-ASCII символы,
поэтому для ФИО на кириллице она возвращает пустую строку. Импорт в этом
случае откатывался на ``teacher``/``teacher-2``/... — ссылки получались
нечитаемыми и, что хуже, зависели от порядка импорта: при повторном импорте
тот же адрес мог достаться другому учителю.

Здесь мы транслитерируем ФИО, чтобы у каждого учителя был осмысленный и
стабильный адрес вида ``/teacher/zhansulu-azhmaganbetova/``.
"""
from django.utils.text import slugify

# Русский алфавит + казахские буквы (Ә Ғ Қ Ң Ө Ұ Ү Һ І).
RU_KK_TO_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    # казахские
    "ә": "a", "ғ": "g", "қ": "q", "ң": "n", "ө": "o", "ұ": "u", "ү": "u",
    "һ": "h", "і": "i",
}


def translit(text: str) -> str:
    """Возвращает латинскую транслитерацию строки."""
    out = []
    for ch in text:
        lower = ch.lower()
        if lower in RU_KK_TO_LAT:
            mapped = RU_KK_TO_LAT[lower]
            out.append(mapped.upper() if ch.isupper() and mapped else mapped)
        else:
            out.append(ch)
    return "".join(out)


def teacher_slug(full_name: str, taken=()) -> str:
    """Уникальный читаемый slug для ФИО учителя.

    ``taken`` — уже занятые slug'и; при совпадении добавляется суффикс -2, -3...
    """
    base = slugify(translit(full_name), allow_unicode=False) or "teacher"
    base = base[:160]
    slug = base
    n = 2
    taken = set(taken)
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    return slug[:170]
