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


DAY_SHORT = {
    "Понедельник": "Пн", "Вторник": "Вт", "Среда": "Ср",
    "Четверг": "Чт", "Пятница": "Пт", "Суббота": "Сб",
}


@register.filter
def day_short(day_name):
    """Полное название дня -> двухбуквенное сокращение для вкладок на телефоне."""
    return DAY_SHORT.get(day_name, (day_name or "")[:2])


@register.filter
def dow_w_to_workday(w_str):
    """{% now "w" %} (0=вс..6=сб) -> индекс буднего дня 0=пн..4=пт, для выбора
    вкладки "сегодня" в мобильном виде расписания класса. Выходные -> 0 (пн)."""
    try:
        w = int(w_str)
    except (TypeError, ValueError):
        return 0
    return w - 1 if 1 <= w <= 5 else 0


@register.filter
def display_lesson_number(lesson, stream1_grades):
    """Номер урока, как он показан на странице КЛАССА этого урока (после
    обеденного звонка номер сдвигается на -1 — обед не считается отдельным
    уроком). У разных потоков обед стоит на разных звонках (см.
    schedule.views.STREAM_1_GRADES), поэтому на странице УЧИТЕЛЯ, где в одной
    строке могут быть уроки в разных классах/потоках, этот номер нужно
    считать отдельно для каждого урока, а не один раз на всю строку —
    иначе он не совпадал бы с тем, что показано на странице класса."""
    grade = getattr(lesson.school_class, "grade_number", None)
    n = lesson.bell_slot.number
    threshold = 7 if grade in stream1_grades else 8
    return n - 1 if n >= threshold else n
