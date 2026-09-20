"""Загружает расписание в пустую базу — и только в пустую.

Нужна при первом старте на хостинге: том с базой сначала пустой, миграции
создают таблицы, а данных в них нет. Команда безопасна для повторного
запуска — если уроки уже есть, она ничего не делает, поэтому её можно
держать в команде запуска контейнера: при каждом перезапуске и
редеплое существующее расписание остаётся нетронутым.

    python manage.py seed_if_empty
    python manage.py seed_if_empty --fixture production_data
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand

from schedule.models import Lesson


class Command(BaseCommand):
    help = "Загружает фикстуру расписания, если в базе ещё нет уроков."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fixture", default="production_data",
            help="Имя фикстуры (по умолчанию production_data).",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Загрузить, даже если уроки уже есть (перезапишет по pk).",
        )

    def handle(self, *args, **options):
        existing = Lesson.objects.count()
        if existing and not options["force"]:
            self.stdout.write(
                f"В базе уже {existing} уроков — загрузка пропущена "
                f"(это защита расписания от перезаписи при редеплое)."
            )
            return

        call_command("loaddata", options["fixture"], verbosity=1)
        self.stdout.write(self.style.SUCCESS(
            f"Расписание загружено: {Lesson.objects.count()} уроков."
        ))
