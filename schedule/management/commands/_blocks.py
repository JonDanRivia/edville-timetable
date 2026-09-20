# -*- coding: utf-8 -*-
"""Вспомогательные функции для потоков (параллельных блоков).

Поток — это несколько классов, у которых один предмет (обычно английский язык)
идёт ОДНОВРЕМЕННО: в один и тот же день и в один и тот же по счёту урок.
Ученики потока делятся на группы, каждую группу ведёт свой учитель, поэтому
"учитель в нескольких классах одновременно" внутри потока — это норма, а не
накладка.

Здесь собрана вся арифметика выравнивания: как перенести уроки предмета на
нужные дни и как поставить их на один и тот же номер урока у всех классов
потока.
"""


# ---------- 1. Выравнивание по ДНЯМ ----------

def _group_subject(items, subject):
    """Собирает все вхождения предмета в дне рядом друг с другом
    (чтобы сдвоенный урок остался сдвоенным после переносов)."""
    if items.count(subject) < 2:
        return items
    first = items.index(subject)
    rest = [x for i, x in enumerate(items) if not (x == subject and i != first)]
    insert_at = rest.index(subject)
    extra = [subject] * (items.count(subject) - 1)
    return rest[:insert_at + 1] + extra + rest[insert_at + 1:]


def _move_one(day_subjects, subject, day_from, day_to):
    """Переносит один урок предмета из day_from в day_to, меняя его местами
    с каким-нибудь другим предметом (чтобы длина дня не изменилась).
    Если менять не с чем — просто переносит."""
    src = day_subjects.get(day_from, [])
    dst = day_subjects.get(day_to, [])
    if subject not in src:
        return False

    i = src.index(subject)
    partner = None
    for j, name in enumerate(dst):
        if name == subject:
            continue
        # по возможности не создаём в дне-источнике второй такой же предмет
        if name in src:
            continue
        partner = j
        break
    if partner is None:
        for j, name in enumerate(dst):
            if name != subject:
                partner = j
                break

    if partner is None:
        src.pop(i)
        dst.append(subject)
    else:
        src[i], dst[partner] = dst[partner], src[i]

    day_subjects[day_from] = _group_subject(src, subject)
    day_subjects[day_to] = _group_subject(dst, subject)
    return True


def _move_block(day_subjects, subject, day_from, day_to):
    """Переносит из day_from в day_to СРАЗУ ВЕСЬ блок предмета (одиночный или
    сдвоенный урок — сколько бы вхождений подряд ни было), а не одно
    вхождение, как _move_one. Нужна там, где предмет должен идти сдвоенными
    уроками (например, при переносе урока на предпочтительный день учителя):
    _move_one в этом случае переносил бы только один из двух уроков пары,
    оставляя в исходном дне одиночный "хвост" — сдвоенный урок разваливался
    бы на два одиночных.

    Меняет местами с таким же числом уроков дня day_to, чтобы длины дней не
    менялись. Возвращает False и ничего не меняет, если в day_to не хватает
    уроков на замену (пару целиком переставить некуда)."""
    src = day_subjects.get(day_from, [])
    dst = day_subjects.get(day_to, [])
    if subject not in src:
        return False

    i = src.index(subject)
    j = i
    while j < len(src) and src[j] == subject:
        j += 1
    width = j - i

    others_idx = [k for k, name in enumerate(dst) if name != subject]
    if len(others_idx) < width:
        return False

    take_idx = others_idx[:width]
    displaced = [dst[k] for k in take_idx]
    block = src[i:j]

    src[i:j] = displaced
    for k in sorted(take_idx, reverse=True):
        dst.pop(k)
    dst.extend(block)

    day_subjects[day_from] = src
    day_subjects[day_to] = _group_subject(dst, subject)
    return True


def plan_block_days(block_infos, num_days):
    """Распределяет уроки потоков по дням недели ГЛОБАЛЬНО.

    Без этого шага все потоки съезжаются в одни и те же дни (алгоритм раскладки
    у всех классов одинаковый), и тогда в один день нужно провести английский
    сразу у 5-6, 7-8, 9-10 и 11 — а учителя-то одни и те же. Здесь каждый урок
    потока отправляется в день, где меньше всего других потоков с ТЕМИ ЖЕ
    учителями и меньше общая загрузка.

    block_infos: элементы со списком 'units' (ширины уроков: 2 — сдвоенный,
    1 — одиночный), 'teacher_keys' и 'id'.
    Возвращает {block_id: {день: сколько уроков предмета в этот день}}.
    """
    day_blocks = {d: [] for d in range(num_days)}
    plan = {}
    for info in sorted(block_infos, key=lambda b: (-sum(b["units"]), b["name"])):
        keys = set(info["teacher_keys"])
        used_days = set()
        target = {}
        for width in info["units"]:
            def cost(day):
                shared = sum(1 for other_keys, _w in day_blocks[day] if other_keys & keys)
                load = sum(w for _k, w in day_blocks[day])
                return (day in used_days, shared, load, day)

            day = min(range(num_days), key=cost)
            used_days.add(day)
            day_blocks[day].append((keys, width))
            target[day] = target.get(day, 0) + width
        plan[info["id"]] = target
    return plan


def align_block_days(day_subjects_by_class, class_slugs, subject, num_days, target=None):
    """Делает так, чтобы у всех классов потока предмет стоял в одни и те же дни.

    target — желаемое распределение {день: сколько уроков}. Если не задано,
    за образец берётся класс с наибольшим числом уроков этого предмета.
    Возвращает число выполненных переносов.
    """
    present = [cs for cs in class_slugs if cs in day_subjects_by_class]
    if len(present) < 2:
        return 0

    def counts_for(cs):
        return {d: day_subjects_by_class[cs].get(d, []).count(subject) for d in range(num_days)}

    per_class = {cs: counts_for(cs) for cs in present}
    if target is None:
        reference = max(present, key=lambda cs: (sum(per_class[cs].values()), cs))
        target = per_class[reference]
    else:
        reference = None

    moves = 0
    for cs in present:
        if cs == reference:
            continue
        current = per_class[cs]
        deficit, surplus = [], []
        for d in range(num_days):
            diff = target.get(d, 0) - current.get(d, 0)
            if diff > 0:
                deficit.extend([d] * diff)
            elif diff < 0:
                surplus.extend([d] * (-diff))
        for day_from, day_to in zip(surplus, deficit):
            if _move_one(day_subjects_by_class[cs], subject, day_from, day_to):
                moves += 1
    return moves


# ---------- 2. Выравнивание по НОМЕРУ УРОКА ----------

def blocks_from_items(items):
    """Группирует подряд идущие одинаковые элементы в один «урочный блок»
    (сдвоенный урок = один блок из двух элементов)."""
    result = []
    i = 0
    while i < len(items):
        j = i + 1
        while j < len(items) and items[j] == items[i]:
            j += 1
        result.append(items[i:j])
        i = j
    return result


def achievable_starts(widths):
    """Какие позиции (номера урока, считая с 0) может занять закреплённый блок,
    если перед ним стоит какое-то подмножество остальных блоков.
    widths — ширины остальных блоков дня."""
    sums = {0}
    for w in widths:
        sums |= {s + w for s in sums}
    return sums


def split_for_target(other_blocks, target_start):
    """Делит остальные блоки дня на (до закреплённого, после), так чтобы
    суммарная ширина «до» была ровно target_start. Возвращает None, если
    точно набрать не получается."""
    if target_start == 0:
        return [], list(other_blocks)

    # Классический subset-sum с восстановлением ответа (блоков мало — 5-8 штук).
    reachable = {0: None}  # сумма -> (предыдущая сумма, индекс блока)
    for idx, block in enumerate(other_blocks):
        width = len(block)
        for total in sorted(reachable, reverse=True):
            new_total = total + width
            if new_total <= target_start and new_total not in reachable:
                reachable[new_total] = (total, idx)
        if target_start in reachable:
            break

    if target_start not in reachable:
        return None

    chosen = set()
    total = target_start
    while reachable[total] is not None:
        prev_total, idx = reachable[total]
        chosen.add(idx)
        total = prev_total

    before = [b for i, b in enumerate(other_blocks) if i in chosen]
    after = [b for i, b in enumerate(other_blocks) if i not in chosen]
    return before, after


def pin_block(day_blocks, pinned_index, target_start):
    """Переставляет блоки дня так, чтобы закреплённый блок начинался
    с урока номер target_start (считая с 0).
    Возвращает (новый список блоков, новый индекс закреплённого блока)
    или None, если точно поставить не получилось."""
    pinned = day_blocks[pinned_index]
    others = [b for i, b in enumerate(day_blocks) if i != pinned_index]
    split = split_for_target(others, target_start)
    if split is None:
        return None
    before, after = split
    return before + [pinned] + after, len(before)
