from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Позволяет обращаться по динамическому ключу в шаблоне: {{ mydict|get_item:key }}"""
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def list_index(values, index):
    """Элемент списка по индексу: {{ my_list|list_index:idx }}.
    Нужен, чтобы в редакторе отметить 2-го и 3-го учителя урока."""
    try:
        return values[int(index)]
    except (IndexError, TypeError, ValueError):
        return None


# Категории предметов для цветовой раскраски расписания (в стиле EduPage) —
# сопоставление по ключевым словам в названии предмета.
SUBJECT_CATEGORY_KEYWORDS = [
    ("lang", ["язык", "литератур", "букварь", "чтение"]),
    ("math", ["математик", "алгебр", "геометр"]),
    ("science", ["физик", "хими", "биолог", "естествозн", "географ"]),
    ("social", ["истори", "право", "закон и порядок", "конституц", "безопасност", "познание мира"]),
    ("tech", ["информатик", "цифров", "нвп", "военн"]),
    ("pe", ["физическая культур", "спортивн"]),
    ("art", ["музык", "изобразительн", "труд", "художественн"]),
]

CATEGORY_EMOJI = {
    "lang": "🟥",
    "math": "🟦",
    "science": "🟪",
    "social": "🟨",
    "tech": "🟦",
    "pe": "🟧",
    "art": "🟩",
    "other": "⬜",
}


def _category_for(name):
    if not name:
        return "other"
    lower = name.lower()
    for category, keywords in SUBJECT_CATEGORY_KEYWORDS:
        if any(kw in lower for kw in keywords):
            return category
    return "other"


@register.filter
def subject_category(subject):
    """Subject или строка -> ключ категории ('lang', 'math', ...) для CSS-класса."""
    name = getattr(subject, "name", subject)
    return _category_for(name)


@register.filter
def subject_emoji(subject_name):
    """Строка-название предмета -> цветной кружок-эмодзи для <option> в select."""
    return CATEGORY_EMOJI.get(_category_for(subject_name), CATEGORY_EMOJI["other"])
