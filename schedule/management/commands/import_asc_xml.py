# -*- coding: utf-8 -*-
"""
Management-команда: импортирует расписание из экспорта aSc Timetables (XML,
формат "aSc Timetables 2012 XML") — файл со звонками, классами, предметами,
учителями и уже готовой раскладкой уроков по дням/урокам (<lessons> + <cards>).

ВАЖНО про номера уроков: времена звонков, зашитые в самом XML (элемент
<periods>), не совпадают с реальным расписанием звонков школы, которое уже
используется на сайте (см. REAL_BELL_TIMES в import_rup.py) — в частности,
7-й урок в XML почему-то разбит на два разных "периода":
  - period=7 ("Обед", 13:15-13:55) — на самом деле это время 7-го урока для
    большинства классов;
  - period=8 ("7", 13:55-14:35) — то же самое время 7-го урока, но со сдвигом
    (обед/урок в этих 20 минутах у разных потоков идёт по-разному) — в данных
    он использован только для 6А.
Оба физически укладываются в единый 7-й звонок сайта (13:15-14:35), который
как раз и завёлся объединённым по этой причине — поэтому здесь period=7 и
period=8 сводятся в один и тот же BellSlot(7), а не в два разных урока.
Дальше, period=9 ("8", 14:40-15:20) в XML — это факт. 8-й урок по счёту,
поэтому он ложится в BellSlot(8), даже если в комментариях к сайту это время
подписано как "Study time": раз в XML на это время реально стоят уроки —
значит, это и есть настоящий 8-й урок, а не окно самоподготовки.
Значения period 10+ в файле не встречаются (проверено на исходном экспорте);
если попадутся — команда выдаст предупреждение, а не тихо пропустит урок.

Запуск:
    python manage.py import_asc_xml /путь/к/export.xml
    python manage.py import_asc_xml /путь/к/export.xml --dry-run
"""
import xml.etree.ElementTree as ET
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from schedule.translit import teacher_slug

from schedule.models import SchoolClass, Subject, Teacher, BellSlot, Lesson, ParallelBlock
from schedule.management.commands.import_rup import (
    REAL_BELL_TIMES, class_label_to_slug, guess_difficulty,
)

# period (атрибут в <periods>/<cards>) -> номер BellSlot на сайте.
# 7 и 8 сведены в один и тот же 7-й урок (см. пояснение в модуле выше).
PERIOD_TO_BELLSLOT = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 7, 9: 8}

DAYMASK_TO_DAY = {"10000": 0, "01000": 1, "00100": 2, "00010": 3, "00001": 4}

# Класс полностью исключён из системы (нет ни одной реальной нагрузки) —
# то же решение, что уже принято для РУП/тарификации (см. README).
EXCLUDED_CLASS_NAMES = {"4А", "4A"}


def parse_asc_xml(path):
    """Возвращает разобранные справочники и список карточек с уже
    подставленными именами (а не внутренними id из файла)."""
    tree = ET.parse(path)
    root = tree.getroot()

    subjects_by_id = {s.get("id"): s.get("name") for s in root.find("subjects")}
    teachers_by_id = {t.get("id"): t.get("name") for t in root.find("teachers")}
    classes_by_id = {
        c.get("id"): c.get("name") for c in root.find("classes")
        if c.get("name") not in EXCLUDED_CLASS_NAMES
    }

    lessons = {}
    for lesson in root.find("lessons"):
        class_ids = [c for c in lesson.get("classids", "").split(",") if c]
        class_names = [classes_by_id[c] for c in class_ids if c in classes_by_id]
        if not class_names:
            continue  # урок только у исключённого класса (4А) — пропускаем
        teacher_ids = [t for t in lesson.get("teacherids", "").split(",") if t]
        teacher_names = [teachers_by_id[t] for t in teacher_ids if t in teachers_by_id]
        lessons[lesson.get("id")] = {
            "subject": subjects_by_id.get(lesson.get("subjectid"), "???"),
            "class_names": class_names,
            "teacher_names": teacher_names,
        }

    cards = []
    unknown_periods = set()
    bad_days = []
    for card in root.find("cards"):
        lesson = lessons.get(card.get("lessonid"))
        if lesson is None:
            continue
        period = int(card.get("period"))
        bell = PERIOD_TO_BELLSLOT.get(period)
        if bell is None:
            unknown_periods.add(period)
            continue
        days = card.get("days", "")
        day = DAYMASK_TO_DAY.get(days)
        if day is None:
            bad_days.append(days)
            continue
        cards.append({
            "subject": lesson["subject"],
            "class_names": lesson["class_names"],
            "teacher_names": lesson["teacher_names"],
            "day": day,
            "bell": bell,
        })

    return cards, unknown_periods, bad_days


class Command(BaseCommand):
    help = "Импортирует готовое расписание из экспорта aSc Timetables (XML), сверяя номера уроков со звонками сайта."

    def add_arguments(self, parser):
        parser.add_argument("xml_path", type=str)
        parser.add_argument("--dry-run", action="store_true", help="Только показать, что будет сделано.")

    def handle(self, *args, **options):
        path = options["xml_path"]
        dry_run = options["dry_run"]

        try:
            cards, unknown_periods, bad_days = parse_asc_xml(path)
        except ET.ParseError as e:
            raise CommandError(f"Не смог разобрать XML: {e}")

        if not cards:
            raise CommandError("В файле не нашлось ни одной карточки урока для известных классов.")

        if unknown_periods:
            self.stdout.write(self.style.WARNING(
                f"Встретились номера периода без сопоставления с уроком сайта: "
                f"{sorted(unknown_periods)} — соответствующие карточки пропущены."
            ))
        if bad_days:
            self.stdout.write(self.style.WARNING(
                f"Встретились карточки с непонятной маской дня: {sorted(set(bad_days))} — пропущены."
            ))

        # ---------- Группировка по "потокам" (несколько классов в одном уроке) ----------
        # Ключ: (предмет, отсортированный кортеж классов) -> пул учителей (в порядке
        # первого встреченного варианта из XML — на нём строится деление на группы).
        block_pool = {}
        block_key_of = {}
        for c in cards:
            if len(c["class_names"]) > 1:
                key = (c["subject"], tuple(sorted(c["class_names"])))
                block_key_of[id(c)] = key
                if key not in block_pool:
                    block_pool[key] = c["teacher_names"]

        class_names = sorted({cn for c in cards for cn in c["class_names"]})
        subject_names = sorted({c["subject"] for c in cards})
        teacher_names = sorted({t for c in cards for t in c["teacher_names"]})

        self.stdout.write(f"Классов: {len(class_names)}, предметов: {len(subject_names)}, "
                           f"учителей: {len(teacher_names)}, потоков: {len(block_pool)}, карточек: {len(cards)}")

        # ---------- Построение записей уроков (ещё без сохранения в БД) ----------
        planned = []  # (class_name, day, bell, subject, teacher_name, [co_teacher_names], block_key|None)
        seen_slots = defaultdict(dict)  # class_name -> {(day, bell): card} для проверки коллизий
        conflicts = []

        for c in cards:
            if len(c["class_names"]) > 1:
                key = (c["subject"], tuple(sorted(c["class_names"])))
                pool = block_pool[key]
                members = sorted(c["class_names"])
                for cn in c["class_names"]:
                    shift = members.index(cn) % len(pool) if pool else 0
                    rotated = pool[shift:] + pool[:shift] if pool else []
                    teacher = rotated[0] if rotated else None
                    co_teachers = rotated[1:]
                    slot = (c["day"], c["bell"])
                    if slot in seen_slots[cn]:
                        conflicts.append((cn, slot, seen_slots[cn][slot], c))
                        continue
                    seen_slots[cn][slot] = c
                    planned.append((cn, c["day"], c["bell"], c["subject"], teacher, co_teachers, key))
            else:
                cn = c["class_names"][0]
                teacher = c["teacher_names"][0] if c["teacher_names"] else None
                co_teachers = c["teacher_names"][1:]
                slot = (c["day"], c["bell"])
                if slot in seen_slots[cn]:
                    conflicts.append((cn, slot, seen_slots[cn][slot], c))
                    continue
                seen_slots[cn][slot] = c
                planned.append((cn, c["day"], c["bell"], c["subject"], teacher, co_teachers, None))

        if conflicts:
            self.stdout.write(self.style.ERROR(
                f"Обнаружено {len(conflicts)} коллизий (два урока одного класса на один и тот же "
                f"день+звонок после сведения period 7/8 в один урок) — вторая карточка пропущена:"
            ))
            for cn, (day, bell), first, second in conflicts[:20]:
                self.stdout.write(
                    f"    {cn}, день {day}, урок {bell}: уже «{first['subject']}», "
                    f"конфликтует с «{second['subject']}»"
                )

        if dry_run:
            for cn, day, bell, subj, teacher, co_teachers, key in planned[:40]:
                extra = f" + {', '.join(co_teachers)}" if co_teachers else ""
                self.stdout.write(f"  {cn} день{day} урок{bell}: {subj} — {teacher}{extra}")
            if len(planned) > 40:
                self.stdout.write(f"  ... и ещё {len(planned) - 40}")
            self.stdout.write(self.style.SUCCESS("Dry-run — в базу ничего не записано."))
            return

        with transaction.atomic():
            # 1. Звонки — реальные времена сайта, если их ещё нет.
            if not BellSlot.objects.exists():
                for n, (start_t, end_t) in enumerate(REAL_BELL_TIMES, start=1):
                    BellSlot.objects.create(number=n, start_time=start_t, end_time=end_t)
            bell_slots_by_number = {b.number: b for b in BellSlot.objects.all()}

            # 2. Классы.
            classes_by_name = {}
            for order, name in enumerate(sorted(
                class_names,
                key=lambda n: (int("".join(ch for ch in n if ch.isdigit()) or 0), n),
            )):
                digits = "".join(ch for ch in name if ch.isdigit())
                grade = int(digits) if digits else None
                slug = class_label_to_slug(name)
                obj, _ = SchoolClass.objects.update_or_create(
                    slug=slug, defaults={"name": name, "order": order, "grade_number": grade},
                )
                classes_by_name[name] = obj

            # 3. Предметы.
            subjects_by_name = {}
            for name in subject_names:
                obj, created = Subject.objects.get_or_create(
                    name=name, defaults={"difficulty_score": guess_difficulty(name)},
                )
                if not created and obj.difficulty_score is None:
                    obj.difficulty_score = guess_difficulty(name)
                    obj.save(update_fields=["difficulty_score"])
                subjects_by_name[name] = obj

            # 4. Учителя (ищем по ФИО среди уже существующих — чтобы не плодить
            # дублей с теми, что уже созданы через import_rup/generate_schedule;
            # если не нашли, создаём нового с уникальным slug).
            teachers_by_name = {}
            existing_slugs = set(Teacher.objects.values_list("slug", flat=True))
            for name in teacher_names:
                obj = Teacher.objects.filter(full_name=name).first()
                if obj is None:
                    # ФИО на кириллице slugify() обнуляет — транслитерируем,
                    # иначе адрес выродится в teacher-2/teacher-3 и при
                    # повторном импорте достанется другому учителю.
                    slug = teacher_slug(name, existing_slugs)
                    obj = Teacher.objects.create(full_name=name, slug=slug)
                    existing_slugs.add(obj.slug)
                teachers_by_name[name] = obj

            # 5. Потоки (несколько классов на одном уроке — например, английский).
            blocks_by_key = {}
            for (subject_name, class_tuple), pool in block_pool.items():
                block_name = f"{subject_name} ({', '.join(class_tuple)})"
                block, _ = ParallelBlock.objects.update_or_create(
                    name=block_name,
                    defaults={"subject": subjects_by_name[subject_name], "is_active": True},
                )
                block.school_classes.set([classes_by_name[c] for c in class_tuple])
                block.teachers.set([teachers_by_name[t] for t in pool if t in teachers_by_name])
                blocks_by_key[(subject_name, class_tuple)] = block

            # 6. Очищаем старые уроки затронутых классов и записываем новые.
            Lesson.objects.filter(school_class__in=classes_by_name.values()).delete()

            created = 0
            for cn, day, bell, subj, teacher_name, co_teacher_names, key in planned:
                bell_slot = bell_slots_by_number.get(bell)
                if bell_slot is None:
                    continue
                teacher_obj = teachers_by_name.get(teacher_name) if teacher_name else None
                lesson = Lesson.objects.create(
                    school_class=classes_by_name[cn],
                    day_of_week=day,
                    bell_slot=bell_slot,
                    subject=subjects_by_name[subj],
                    teacher=teacher_obj,
                    parallel_block=blocks_by_key.get(key) if key else None,
                )
                co_ids = [teachers_by_name[t].id for t in co_teacher_names if t in teachers_by_name]
                if co_ids:
                    lesson.co_teachers.set(co_ids)
                created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Готово. Создано {created} уроков для {len(classes_by_name)} классов, "
            f"{len(blocks_by_key)} потоков. Номера уроков 7 и 8 из XML сведены в 7-й звонок сайта, "
            f"а «8-й» из XML (14:40-15:20 в исходнике) записан как реальный 8-й урок сайта."
        ))
