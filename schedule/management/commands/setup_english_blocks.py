# -*- coding: utf-8 -*-
"""
Management-команда: создаёт (или обновляет) потоки английского языка —
параллельные блоки, в которых урок английского идёт у нескольких классов
ОДНОВРЕМЕННО, а ученики делятся на группы между несколькими учителями.

По изменениям в тарификации учителей английского:
    5-6 классы   — английский одновременно, 3 группы / 3 учителя
    7-8 классы   — английский одновременно, 3 группы / 3 учителя
    9-10 классы  — английский одновременно, 3 группы / 3 учителя
    11 классы    — 11A и 11B одновременно, ведут 3 учителя

В поток берутся только классы с буквами A и B (латиница или кириллица А/В).

Указывать учителей НЕОБЯЗАТЕЛЬНО. Без них поток задаёт только «когда»:
у каких классов английский идёт одновременно. Кто именно ведёт какую группу,
завуч выбирает вручную в /editor/<класс>/ — у каждой ячейки есть основной,
второй и третий учитель. Потоки при этом всё равно разводятся по разным дням
и урокам, чтобы одного и того же учителя можно было назначить в любой из них.

Запуск:
    python manage.py setup_english_blocks                      # без учителей
    python manage.py setup_english_blocks --teachers "Аяулым,Сапар,Иванова А."
    python manage.py setup_english_blocks --teachers-11 "Грегори,Сапар,Аяулым"
    python manage.py setup_english_blocks --letters "A,B,C" --dry-run

После запуска состав классов и список учителей в каждом потоке можно свободно
править в админке: /admin/schedule/parallelblock/
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from schedule.models import SchoolClass, Subject, Teacher, ParallelBlock

# Группы параллелей, у которых английский идёт одновременно.
DEFAULT_GROUPS = [
    ("Английский 5-6", [5, 6]),
    ("Английский 7-8", [7, 8]),
    ("Английский 9-10", [9, 10]),
    ("Английский 11", [11]),
]

# Буквы классов, входящих в поток (латиница и кириллица считаются одинаковыми).
# «C» добавлена из-за 11С: класс, не попавший в поток, не может делить учеников
# на группы с остальной параллелью — редактор считает учителя занятым в 11А/11В
# и отказывается сохранять ячейку.
DEFAULT_LETTERS = ["A", "B", "C"]

CYR_TO_LAT = {"А": "A", "В": "B", "С": "C", "Е": "E", "Н": "H", "К": "K",
              "М": "M", "О": "O", "Р": "P", "Т": "T", "Х": "X"}

ENGLISH_KEYWORDS = ["английск", "иностранн", "english"]


def normalize_letters(name):
    """'5А' -> 'A', '11B' -> 'B' (кириллица приводится к латинице)."""
    letters = "".join(ch for ch in name if not ch.isdigit() and not ch.isspace())
    return "".join(CYR_TO_LAT.get(ch.upper(), ch.upper()) for ch in letters)


def grade_of(school_class):
    """Номер параллели: из поля grade_number, иначе — из названия класса."""
    if school_class.grade_number:
        return school_class.grade_number
    digits = "".join(ch for ch in school_class.name if ch.isdigit())
    return int(digits) if digits else None


class Command(BaseCommand):
    help = "Создаёт потоки английского языка (5-6, 7-8, 9-10, 11) для одновременных уроков с делением на группы."

    def add_arguments(self, parser):
        parser.add_argument(
            "--subject", type=str, default="",
            help="Точное название предмета. Если не указать — ищется предмет со словом 'английск'/'иностранн'.",
        )
        parser.add_argument(
            "--letters", type=str, default=",".join(DEFAULT_LETTERS),
            help="Буквы классов, входящих в поток. По умолчанию 'A,B'. Пустая строка — брать все буквы.",
        )
        parser.add_argument(
            "--teachers", type=str, default="",
            help=(
                "Необязательно: учителя для потоков 5-6, 7-8, 9-10 через запятую (ФИО как в базе). "
                "Если не указывать — учителей групп выбирает завуч вручную в редакторе."
            ),
        )
        parser.add_argument(
            "--clear-teachers", action="store_true",
            help="Очистить список учителей у потоков (выбирать их вручную в редакторе).",
        )
        parser.add_argument(
            "--teachers-11", type=str, default="",
            help="Учителя для потока 11 классов через запятую. Если не указать — берутся --teachers.",
        )
        parser.add_argument("--dry-run", action="store_true", help="Только показать, ничего не записывать.")

    # ---------- вспомогательное ----------

    def resolve_subject(self, explicit_name):
        if explicit_name:
            subject = Subject.objects.filter(name=explicit_name).first()
            if not subject:
                raise CommandError(f"Предмет '{explicit_name}' не найден в базе.")
            return subject
        # Сравниваем на стороне Python: SQLite не умеет icontains для кириллицы.
        for kw in ENGLISH_KEYWORDS:
            for subject in Subject.objects.all():
                if kw in subject.name.lower():
                    return subject
        raise CommandError(
            "Не нашёл предмет английского языка в базе. Укажите его явно: "
            "--subject \"Иностранный язык\""
        )

    def resolve_teachers(self, raw):
        """'Аяулым, Сапар' -> [Teacher, ...]. Ищем по вхождению в ФИО."""
        found = []
        for piece in [p.strip() for p in raw.split(",") if p.strip()]:
            needle = piece.lower()
            matches = [t for t in Teacher.objects.all() if needle in t.full_name.lower()]
            if not matches:
                teacher = Teacher.objects.create(
                    full_name=piece,
                    slug=(slugify(piece, allow_unicode=False) or f"teacher-{Teacher.objects.count() + 1}")[:170],
                )
                self.stdout.write(self.style.WARNING(f"  учитель '{piece}' не найден — создан новый."))
                found.append(teacher)
                continue
            if len(matches) > 1:
                self.stdout.write(self.style.WARNING(
                    f"  '{piece}' совпал с несколькими учителями: "
                    f"{', '.join(t.full_name for t in matches)} — взял первого."
                ))
            found.append(matches[0])
        return found

    # ---------- основной сценарий ----------

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        subject = self.resolve_subject(options["subject"].strip())
        letters = {l.strip().upper() for l in options["letters"].split(",") if l.strip()}

        self.stdout.write(f"Предмет потоков: «{subject.name}»")
        self.stdout.write(f"Буквы классов: {', '.join(sorted(letters)) if letters else 'все'}")

        classes_by_grade = {}
        for school_class in SchoolClass.objects.all():
            grade = grade_of(school_class)
            if grade is None:
                continue
            if letters and normalize_letters(school_class.name) not in letters:
                continue
            classes_by_grade.setdefault(grade, []).append(school_class)

        if not classes_by_grade:
            raise CommandError(
                "Не нашёл ни одного подходящего класса. Сначала импортируйте РУП "
                "(python manage.py generate_schedule ...) или ослабьте --letters."
            )

        teachers_main = self.resolve_teachers(options["teachers"])
        teachers_11 = self.resolve_teachers(options["teachers_11"]) or teachers_main

        planned = []
        for block_name, grades in DEFAULT_GROUPS:
            block_classes = []
            for grade in grades:
                block_classes.extend(classes_by_grade.get(grade, []))
            if not block_classes:
                self.stdout.write(self.style.WARNING(
                    f"«{block_name}»: не нашёл классов параллелей {grades} — поток пропущен."
                ))
                continue
            block_teachers = teachers_11 if grades == [11] else teachers_main
            planned.append((block_name, block_classes, block_teachers))

        for block_name, block_classes, block_teachers in planned:
            names = ", ".join(c.name for c in block_classes)
            who = (
                "— (очищаются)" if options["clear_teachers"]
                else ", ".join(t.full_name for t in block_teachers)
                or "— (выбираются вручную в редакторе)"
            )
            self.stdout.write(f"  «{block_name}»: классы {names}; учителя: {who}")

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry-run — в базу ничего не записано."))
            return

        with transaction.atomic():
            for block_name, block_classes, block_teachers in planned:
                block, created = ParallelBlock.objects.update_or_create(
                    name=block_name, defaults={"subject": subject, "is_active": True},
                )
                block.school_classes.set(block_classes)
                if options["clear_teachers"]:
                    block.teachers.clear()
                elif block_teachers:
                    block.teachers.set(block_teachers)
                self.stdout.write(
                    ("Создан поток " if created else "Обновлён поток ") + f"«{block_name}»"
                )

        self.stdout.write(self.style.SUCCESS(
            f"Готово: {len(planned)} потоков. Состав классов и учителей можно править "
            f"в админке — /admin/schedule/parallelblock/. Затем перегенерируйте расписание "
            f"(python manage.py generate_schedule РУП.xlsx тарификация.xlsx)."
        ))
        if not any(t for _n, _c, t in planned):
            self.stdout.write(
                "Учителя потоков не заданы — это нормально: английский встанет в расписание "
                "одновременно у нужных классов, а кто ведёт какую группу, выберете сами "
                "в /editor/<класс>/ (у каждой ячейки основной, 2-й и 3-й учитель)."
            )
