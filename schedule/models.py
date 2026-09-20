from django.db import models
from django.urls import reverse


DAYS_OF_WEEK = [
    (0, "Понедельник"),
    (1, "Вторник"),
    (2, "Среда"),
    (3, "Четверг"),
    (4, "Пятница"),
    (5, "Суббота"),
]

# Школа работает 5 дней — используем этот список везде, где строится сетка
# расписания, чтобы пустой столбец "Суббота" нигде не показывался.
WORKING_DAYS = DAYS_OF_WEEK[:5]


class SchoolClass(models.Model):
    """Класс, например '7B' или '9A'."""
    name = models.CharField("Название класса", max_length=20, unique=True)
    slug = models.SlugField("Ссылка (slug)", max_length=30, unique=True)
    order = models.PositiveIntegerField("Порядок сортировки", default=0)
    grade_number = models.PositiveSmallIntegerField(
        "Параллель (класс), 1-12", null=True, blank=True,
        help_text=(
            "Например, для '7B' указать 7. Нужно для проверки норм СанПиН РК "
            "(приказ МЗ РК № ҚР ДСМ-76) — например, запрет сдвоенных уроков "
            "в начальной школе (1-4 классы). Если не указать — эти проверки "
            "для класса просто не будут выполняться."
        )
    )

    class Meta:
        verbose_name = "Класс"
        verbose_name_plural = "Классы"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("class_schedule", args=[self.slug])

    @property
    def is_elementary(self):
        """Начальная школа (1-4 классы) — для проверки п.73 СанПиН РК (запрет сдвоенных уроков)."""
        return self.grade_number is not None and 1 <= self.grade_number <= 4


class Teacher(models.Model):
    """Учитель."""
    full_name = models.CharField("ФИО", max_length=150)
    slug = models.SlugField("Ссылка (slug)", max_length=170, unique=True)

    class Meta:
        verbose_name = "Учитель"
        verbose_name_plural = "Учителя"
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name

    def get_absolute_url(self):
        return reverse("teacher_schedule", args=[self.slug])


class Subject(models.Model):
    """Предмет."""
    name = models.CharField("Название предмета", max_length=100, unique=True)
    short_name = models.CharField(
        "Короткое название", max_length=20, blank=True,
        help_text="Например 'Матем.' — если пусто, используется полное название"
    )
    difficulty_score = models.PositiveSmallIntegerField(
        "Балл трудности (СанПиН РК), 1-5", null=True, blank=True,
        help_text=(
            "1 — самый лёгкий предмет (физкультура, музыка, труд), 5 — самый "
            "сложный (математика, языки, физика). Основано на шкале трудности "
            "предметов из Приложения 4 к приказу МЗ РК № ҚР ДСМ-76. "
            "Используется, чтобы предупреждать, если сложный предмет стоит "
            "первым/последним уроком или таких предметов слишком много в один "
            "день. Можно не указывать — тогда проверка для предмета не работает."
        )
    )

    class Meta:
        verbose_name = "Предмет"
        verbose_name_plural = "Предметы"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def display_name(self):
        return self.short_name or self.name


class Room(models.Model):
    """Кабинет."""
    name = models.CharField("Кабинет", max_length=50, unique=True)

    class Meta:
        verbose_name = "Кабинет"
        verbose_name_plural = "Кабинеты"
        ordering = ["name"]

    def __str__(self):
        return self.name


class BellSlot(models.Model):
    """Урок по счёту в течение дня (звонок), с временем начала/конца.
    Общий для всей школы (один и тот же 1-й урок у всех классов)."""
    number = models.PositiveSmallIntegerField("№ урока", unique=True)
    start_time = models.TimeField("Начало")
    end_time = models.TimeField("Конец")

    class Meta:
        verbose_name = "Урок (звонок)"
        verbose_name_plural = "Расписание звонков"
        ordering = ["number"]

    def __str__(self):
        return f"{self.number} урок ({self.start_time:%H:%M}\u2013{self.end_time:%H:%M})"


class ParallelBlock(models.Model):
    """Поток (параллельный блок) — несколько классов, у которых один и тот же
    предмет идёт ОДНОВРЕМЕННО (в один день и один и тот же урок по счёту),
    потому что ученики этих классов делятся на группы по уровню, и каждую
    группу ведёт свой учитель.

    Пример (изменения в тарификации учителей английского языка):
        «Английский 5-6»  — классы 5A, 5B, 6A, 6B, учителя: Аяулым, Сапар, +1
        «Английский 7-8»  — классы 7A, 7B, 8A, 8B
        «Английский 9-10» — классы 9A, 9B, 10A, 10B
        «Английский 11»   — классы 11A, 11B, учителя: Грегори, Сапар, Аяулым

    Генератор расписания ставит уроки этого предмета у всех классов потока в
    одни и те же слоты, а проверка накладок понимает, что учитель потока может
    одновременно «числиться» у нескольких классов — это не конфликт, а деление
    на группы.
    """
    name = models.CharField("Название потока", max_length=100, unique=True)
    subject = models.ForeignKey(
        "Subject", verbose_name="Предмет", on_delete=models.CASCADE,
        related_name="parallel_blocks",
        help_text="Предмет, который идёт одновременно у всех классов потока.",
    )
    school_classes = models.ManyToManyField(
        "SchoolClass", verbose_name="Классы потока", related_name="parallel_blocks",
        help_text="Классы, у которых этот предмет стоит в одно и то же время.",
    )
    teachers = models.ManyToManyField(
        "Teacher", verbose_name="Учителя потока (по группам)", blank=True,
        related_name="parallel_blocks",
        help_text=(
            "Учителя, которые делят учеников потока на группы. Все они "
            "проставляются в каждый урок потока: первый — основным учителем, "
            "остальные — дополнительными."
        ),
    )
    is_active = models.BooleanField(
        "Учитывать при генерации", default=True,
        help_text="Снимите галочку, чтобы временно отключить поток, не удаляя его.",
    )

    class Meta:
        verbose_name = "Поток (параллельный блок)"
        verbose_name_plural = "Потоки (параллельные блоки)"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def class_names(self):
        return ", ".join(c.name for c in self.school_classes.all())
    class_names.short_description = "Классы"

    def teacher_names(self):
        return ", ".join(t.full_name for t in self.teachers.all())
    teacher_names.short_description = "Учителя"


class Lesson(models.Model):
    """Конкретный урок в расписании: класс + день + номер урока -> предмет/учитель/кабинет."""
    school_class = models.ForeignKey(
        SchoolClass, verbose_name="Класс", on_delete=models.CASCADE, related_name="lessons"
    )
    day_of_week = models.PositiveSmallIntegerField("День недели", choices=DAYS_OF_WEEK)
    bell_slot = models.ForeignKey(
        BellSlot, verbose_name="Урок по счёту", on_delete=models.CASCADE, related_name="lessons"
    )
    subject = models.ForeignKey(
        Subject, verbose_name="Предмет", on_delete=models.CASCADE, related_name="lessons"
    )
    teacher = models.ForeignKey(
        Teacher, verbose_name="Учитель", on_delete=models.CASCADE, related_name="lessons"
    )
    co_teachers = models.ManyToManyField(
        Teacher, verbose_name="Дополнительные учителя (деление на группы)",
        related_name="co_lessons", blank=True,
        help_text=(
            "Второй и третий учитель урока — когда класс (или поток классов) "
            "делится на группы, например по английскому языку. Основной "
            "учитель указывается в поле выше."
        ),
    )
    parallel_block = models.ForeignKey(
        ParallelBlock, verbose_name="Поток", on_delete=models.SET_NULL,
        related_name="lessons", null=True, blank=True,
        help_text=(
            "Если урок входит в поток, учителя этого урока могут вести группы "
            "в нескольких классах потока одновременно — это не считается накладкой."
        ),
    )
    room = models.ForeignKey(
        Room, verbose_name="Кабинет", on_delete=models.SET_NULL, related_name="lessons",
        null=True, blank=True
    )

    class Meta:
        verbose_name = "Урок в расписании"
        verbose_name_plural = "Уроки в расписании"
        ordering = ["school_class", "day_of_week", "bell_slot__number"]
        constraints = [
            models.UniqueConstraint(
                fields=["school_class", "day_of_week", "bell_slot"],
                name="unique_class_day_slot",
            ),
        ]

    def __str__(self):
        return f"{self.school_class} / {self.get_day_of_week_display()} / {self.bell_slot.number} урок"

    @property
    def all_teachers(self):
        """Все учителя урока: основной + дополнительные (деление на группы)."""
        result = [self.teacher] if self.teacher_id else []
        result.extend(self.co_teachers.all())
        return result

    def teachers_display(self):
        """'Аяулым, Сапар, Грегори' — для вывода в расписании."""
        return ", ".join(t.full_name for t in self.all_teachers)
    teachers_display.short_description = "Учителя"

    @property
    def co_teacher_ids(self):
        """Список id дополнительных учителей — чтобы шаблон редактора мог
        отметить их в выпадающих списках."""
        return [t.id for t in self.co_teachers.all()]
