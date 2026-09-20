"""Чинит нечитаемые slug'и учителей (teacher-2, teacher-3, ...).

Ранние импорты не транслитерировали ФИО на кириллице, поэтому адреса вида
/teacher/teacher-14/ не говорят ничего и зависят от порядка импорта. Команда
пересобирает их через schedule.translit.teacher_slug.

    python manage.py fix_teacher_slugs --dry-run   # только показать
    python manage.py fix_teacher_slugs             # применить

Расписание не трогается: меняется только поле slug.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from schedule.models import Teacher
from schedule.translit import teacher_slug


class Command(BaseCommand):
    help = "Пересобирает slug'и учителей с транслитерацией кириллицы."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Показать изменения, ничего не записывая.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        teachers = list(Teacher.objects.all().order_by("pk"))

        # Slug'и, которые уже читаемы, остаются за своими владельцами.
        keep = {t.pk: t.slug for t in teachers if not _is_degenerate(t.slug)}
        taken = set(keep.values())

        changes = []
        for t in teachers:
            if t.pk in keep:
                continue
            new_slug = teacher_slug(t.full_name, taken)
            taken.add(new_slug)
            changes.append((t, t.slug, new_slug))

        for t, old, new in changes:
            self.stdout.write(f"  {t.full_name:34s} {old:16s} -> {new}")
            if not dry_run:
                t.slug = new
                t.save(update_fields=["slug"])

        if not changes:
            self.stdout.write(self.style.SUCCESS("Все slug'и уже читаемы."))
        elif dry_run:
            self.stdout.write(self.style.WARNING(f"\n--dry-run: {len(changes)} шт. не записано."))
        else:
            self.stdout.write(self.style.SUCCESS(f"\nОбновлено: {len(changes)}."))


def _is_degenerate(slug: str) -> bool:
    """teacher / teacher-2 / teacher-17 — результат неудавшейся slugify()."""
    if slug == "teacher":
        return True
    return slug.startswith("teacher-") and slug[len("teacher-"):].isdigit()
