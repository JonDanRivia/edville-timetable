# -*- coding: utf-8 -*-
"""Тесты потоков (параллельных блоков) — деление на группы по английскому языку.

Запуск:  python manage.py test schedule
"""
from datetime import time

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from schedule.models import (
    SchoolClass, Subject, Teacher, BellSlot, Lesson, ParallelBlock,
)
from schedule.management.commands._blocks import (
    align_block_days, plan_block_days, blocks_from_items,
    achievable_starts, pin_block,
)


class BlockMathTests(TestCase):
    """Арифметика выравнивания — без базы."""

    def test_achievable_starts(self):
        # Соседние блоки шириной 1, 1 и 2 -> урок потока можно начать с 0,1,2,3,4.
        self.assertEqual(achievable_starts([1, 1, 2]), {0, 1, 2, 3, 4})

    def test_pin_block_puts_lesson_on_requested_period(self):
        day = [["Математика"], ["Английский", "Английский"], ["История"], ["Биология"]]
        pinned, index = pin_block(day, pinned_index=1, target_start=2)
        start = sum(len(b) for b in pinned[:index])
        self.assertEqual(start, 2)
        self.assertEqual(pinned[index], ["Английский", "Английский"])
        self.assertEqual(len(pinned), len(day))

    def test_blocks_from_items_keeps_double_lesson_together(self):
        items = ["Мат", "Англ", "Англ", "Био"]
        self.assertEqual(blocks_from_items(items), [["Мат"], ["Англ", "Англ"], ["Био"]])

    def test_plan_block_days_spreads_blocks_with_shared_teachers(self):
        infos = [
            {"id": "1", "name": "5-6", "units": [2, 2], "teacher_keys": ["a", "b"]},
            {"id": "2", "name": "7-8", "units": [2, 2], "teacher_keys": ["a", "b"]},
        ]
        plan = plan_block_days(infos, num_days=5)
        # Потоки ведут одни и те же учителя -> дни не должны совпадать.
        self.assertFalse(set(plan["1"]) & set(plan["2"]))

    def test_align_block_days_moves_subject_to_target_days(self):
        day_subjects = {
            "5a": {0: ["Англ", "Англ", "Мат"], 1: ["Био", "История"], 2: [], 3: [], 4: []},
            "5b": {0: ["Мат", "Био"], 1: ["Англ", "Англ", "История"], 2: [], 3: [], 4: []},
        }
        align_block_days(day_subjects, ["5a", "5b"], "Англ", num_days=5, target={0: 2})
        self.assertEqual(day_subjects["5a"][0].count("Англ"), 2)
        self.assertEqual(day_subjects["5b"][0].count("Англ"), 2)
        self.assertEqual(day_subjects["5b"][1].count("Англ"), 0)


class BlockEditorTests(TestCase):
    """Редактор завуча: доп. учителя и проверка накладок с учётом потоков."""

    def setUp(self):
        self.english = Subject.objects.create(name="Иностранный язык", difficulty_score=5)
        self.math = Subject.objects.create(name="Математика", difficulty_score=5)
        self.slot = BellSlot.objects.create(number=1, start_time=time(8, 30), end_time=time(9, 10))

        self.c5a = SchoolClass.objects.create(name="5A", slug="5a", grade_number=5, order=1)
        self.c5b = SchoolClass.objects.create(name="5B", slug="5b", grade_number=5, order=2)
        self.c9a = SchoolClass.objects.create(name="9A", slug="9a", grade_number=9, order=3)

        self.t1 = Teacher.objects.create(full_name="Аяулым", slug="ayaulym")
        self.t2 = Teacher.objects.create(full_name="Сапар", slug="sapar")
        self.t3 = Teacher.objects.create(full_name="Грегори", slug="gregory")

        self.block = ParallelBlock.objects.create(name="Английский 5-6", subject=self.english)
        self.block.school_classes.set([self.c5a, self.c5b])
        self.block.teachers.set([self.t1, self.t2, self.t3])

        self.user = User.objects.create_superuser("zavuch", "z@example.com", "pass")
        self.client.force_login(self.user)

    def _post(self, school_class, subject, teacher, co_teachers=()):
        prefix = f"d0_s{self.slot.id}"
        data = {
            f"{prefix}_subject": subject.id,
            f"{prefix}_teacher": teacher.id,
        }
        for i, co in enumerate(co_teachers):
            data[f"{prefix}_teacher{i + 2}"] = co.id
        return self.client.post(
            reverse("editor_class_grid", args=[school_class.slug]), data, follow=True
        )

    def test_saves_second_and_third_teacher(self):
        self._post(self.c5a, self.english, self.t1, [self.t2, self.t3])
        lesson = Lesson.objects.get(school_class=self.c5a)
        self.assertEqual(lesson.teacher, self.t1)
        self.assertEqual(
            sorted(t.full_name for t in lesson.co_teachers.all()), ["Грегори", "Сапар"]
        )
        self.assertEqual(lesson.parallel_block, self.block)
        # Доп. учителя выводятся по алфавиту (сортировка модели Teacher).
        self.assertEqual(lesson.teachers_display(), "Аяулым, Грегори, Сапар")

    def test_same_teachers_allowed_in_two_classes_of_one_block(self):
        self._post(self.c5a, self.english, self.t1, [self.t2, self.t3])
        response = self._post(self.c5b, self.english, self.t1, [self.t2, self.t3])
        self.assertNotContains(response, "уже занят")
        self.assertEqual(Lesson.objects.filter(subject=self.english).count(), 2)

    def test_teacher_of_block_still_conflicts_outside_the_block(self):
        self._post(self.c5a, self.english, self.t1, [self.t2, self.t3])
        response = self._post(self.c9a, self.math, self.t1)
        self.assertContains(response, "уже занят")
        self.assertFalse(Lesson.objects.filter(school_class=self.c9a).exists())

    def test_blocks_without_teachers_still_get_a_shared_key(self):
        """Если учителя потока не заданы (завуч выберет их сам), потоки по этому
        предмету всё равно должны разводиться по разным дням и урокам."""
        from schedule.management.commands.generate_schedule import Command

        self.block.teachers.clear()
        second = ParallelBlock.objects.create(name="Английский 9-10", subject=self.english)
        second.school_classes.set([self.c9a, self.c5b])

        infos = Command().load_blocks(
            {"5a", "5b", "9a"}, {"Иностранный язык", "Математика"}
        )
        self.assertEqual(len(infos), 2)
        shared = set(infos[0]["teacher_keys"]) & set(infos[1]["teacher_keys"])
        self.assertTrue(shared, "потоки без учителей должны считаться пересекающимися")

        plan = plan_block_days(
            [{**info, "units": [2, 2]} for info in infos], num_days=5
        )
        days = [set(plan[info["id"]]) for info in infos]
        self.assertFalse(days[0] & days[1], "потоки должны стоять в разные дни")

    def test_co_teacher_sees_the_lesson_in_own_schedule(self):
        self._post(self.c5a, self.english, self.t1, [self.t2])
        response = self.client.get(reverse("teacher_schedule", args=[self.t2.slug]))
        self.assertContains(response, "Иностранный язык")


class TeacherSlugTests(TestCase):
    """Slug'и учителей: кириллица не должна превращаться в teacher-2."""

    def test_cyrillic_name_is_transliterated(self):
        from schedule.translit import teacher_slug
        self.assertEqual(teacher_slug("Жансұлу Ажмаганбетова"), "zhansulu-azhmaganbetova")
        self.assertEqual(teacher_slug("Әбілмансұр Қазыбек"), "abilmansur-qazybek")

    def test_similar_names_do_not_collide(self):
        from schedule.translit import teacher_slug
        first = teacher_slug("Адиль Егинбай")
        second = teacher_slug("Адиль Егинбай", taken={first})
        self.assertNotEqual(first, second)
        self.assertTrue(second.startswith(first))

    def test_slug_matches_django_url_converter(self):
        """<slug:...> принимает только [-a-zA-Z0-9_] — иначе страница отдаст 404."""
        import re
        from schedule.translit import teacher_slug
        for name in ["Нургайша Каликова", "Ануар Қабдулқақ", "Эльдар Закенаев"]:
            self.assertRegex(teacher_slug(name), re.compile(r"^[-a-zA-Z0-9_]+$"))

    def test_teacher_page_opens_by_transliterated_slug(self):
        from schedule.translit import teacher_slug
        name = "Мадина Токтаганова"
        teacher = Teacher.objects.create(full_name=name, slug=teacher_slug(name))
        response = self.client.get(
            reverse("teacher_schedule", args=[teacher.slug]), secure=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, name)

    def test_home_page_links_every_teacher_by_slug(self):
        """Учитель должен находить себя из списка, а не угадывать адрес."""
        name = "Рахат Кенесбеков"
        teacher = Teacher.objects.create(full_name=name, slug="rakhat-kenesbekov")
        response = self.client.get(reverse("home"), secure=True)
        self.assertContains(response, teacher.get_absolute_url())


class SeedIfEmptyTests(TestCase):
    """seed_if_empty не должен затирать уже существующее расписание."""

    def test_refuses_to_overwrite_existing_lessons(self):
        from io import StringIO
        from django.core.management import call_command

        school_class = SchoolClass.objects.create(name="7А", slug="7a", order=1)
        subject = Subject.objects.create(name="Математика")
        teacher = Teacher.objects.create(full_name="Тест", slug="test")
        slot = BellSlot.objects.create(number=1, start_time=time(8, 30), end_time=time(9, 10))
        Lesson.objects.create(
            school_class=school_class, subject=subject, teacher=teacher,
            bell_slot=slot, day_of_week=0,
        )

        out = StringIO()
        call_command("seed_if_empty", stdout=out)
        self.assertIn("пропущена", out.getvalue())
        self.assertEqual(Lesson.objects.count(), 1)
