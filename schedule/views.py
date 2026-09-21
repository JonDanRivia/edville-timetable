from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import render, redirect, get_object_or_404

from .models import (
    SchoolClass, Teacher, Subject, Room, BellSlot, Lesson, ParallelBlock, WORKING_DAYS,
)


MAX_CO_TEACHERS = 2  # сколько дополнительных учителей можно выбрать в ячейке редактора

# 1 поток (обед 13:15-13:55, до 7 урока) и 2 поток (обед 13:55-14:35, после
# 7 урока) — обед у них смещён из-за деления по времени приёма пищи. 7 урок
# как звонок один на всю школу (13:15-14:35), а вот "обед" на странице
# показываем по-разному в зависимости от параллели класса.
STREAM_1_GRADES = {1, 2, 3, 5, 8, 11}


# ---------- Публичные страницы (без логина) ----------

def _build_grid(lessons_qs, bell_slots, days):
    """Собирает словарь {slot_id: {day_number: lesson_or_None}} для рендера таблицы."""
    grid = {slot.id: {day: None for day, _ in days} for slot in bell_slots}
    for lesson in lessons_qs:
        grid[lesson.bell_slot_id][lesson.day_of_week] = lesson
    return grid


def home(request):
    """Главная страница: только выбор класса или учителя (переход на его
    страницу расписания). Расписание на самой главной не показывается."""
    classes = SchoolClass.objects.all()
    teachers = Teacher.objects.all()

    return render(request, "schedule/home.html", {
        "classes": classes,
        "teachers": teachers,
        "has_any_class": classes.exists(),
    })


def class_schedule(request, slug):
    school_class = get_object_or_404(SchoolClass, slug=slug)
    bell_slots = BellSlot.objects.all()
    lessons = Lesson.objects.filter(school_class=school_class).select_related(
        "subject", "teacher", "room", "bell_slot"
    ).prefetch_related("co_teachers")
    grid = _build_grid(lessons, bell_slots, WORKING_DAYS)
    return render(request, "schedule/class_schedule.html", {
        "school_class": school_class,
        "bell_slots": bell_slots,
        "days": WORKING_DAYS,
        "grid": grid,
        "all_classes": SchoolClass.objects.all(),
        "stream1_grades": STREAM_1_GRADES,
    })


def teacher_schedule(request, slug):
    teacher = get_object_or_404(Teacher, slug=slug)
    bell_slots = BellSlot.objects.all()
    # Уроки, где учитель либо основной, либо ведёт одну из групп (поток/деление).
    lessons = Lesson.objects.filter(
        Q(teacher=teacher) | Q(co_teachers=teacher)
    ).distinct().select_related(
        "subject", "school_class", "room", "bell_slot"
    ).prefetch_related("co_teachers")
    # Ячейка — СПИСОК уроков, а не один урок: у одного учителя может быть
    # больше одного урока в один и тот же день+звонок, если он ведёт группы
    # сразу в нескольких классах потока (см. ParallelBlock) — раньше здесь
    # был словарь с одним уроком на ячейку, и такие уроки молча перезаписывали
    # друг друга, пропадая со страницы учителя.
    grid = {slot.id: {day: [] for day, _ in WORKING_DAYS} for slot in bell_slots}
    has_any = False
    for lesson in lessons:
        grid[lesson.bell_slot_id][lesson.day_of_week].append(lesson)
        has_any = True
    return render(request, "schedule/teacher_schedule.html", {
        "teacher": teacher,
        "bell_slots": bell_slots,
        "days": WORKING_DAYS,
        "grid": grid,
        "grid_has_lessons": has_any,
        "all_teachers": Teacher.objects.all(),
        "stream1_grades": STREAM_1_GRADES,
    })


# ---------- Редактор для завуча (требует логина) ----------

@login_required
def editor_home(request):
    classes = SchoolClass.objects.all()
    return render(request, "schedule/editor_home.html", {"classes": classes})


@login_required
def editor_class_grid(request, slug):
    school_class = get_object_or_404(SchoolClass, slug=slug)
    bell_slots = list(BellSlot.objects.all())
    subjects = Subject.objects.all()
    teachers = Teacher.objects.all()
    rooms = Room.objects.all()
    day_names = dict(WORKING_DAYS)

    if request.method == "POST":
        warnings = []
        # Собираем, что пользователь хочет сохранить, по каждой ячейке.
        wanted = {}  # (day, slot) -> {"subject_id", "teacher_id", "co_teacher_ids", "room_id"}
        for slot in bell_slots:
            for day, _ in WORKING_DAYS:
                prefix = f"d{day}_s{slot.id}"
                subject_id = request.POST.get(f"{prefix}_subject") or None
                teacher_id = request.POST.get(f"{prefix}_teacher") or None
                room_id = request.POST.get(f"{prefix}_room") or None
                # Второй и третий учитель — когда класс делится на группы
                # (например, английский язык). Дубликаты и пустые значения
                # отбрасываем.
                co_teacher_ids = []
                for n in range(2, MAX_CO_TEACHERS + 2):
                    value = request.POST.get(f"{prefix}_teacher{n}") or None
                    if value and value != teacher_id and value not in co_teacher_ids:
                        co_teacher_ids.append(value)
                wanted[(day, slot.id)] = {
                    "subject_id": subject_id,
                    "teacher_id": teacher_id,
                    "co_teacher_ids": co_teacher_ids,
                    "room_id": room_id,
                }

        with transaction.atomic():
            for (day, slot_id), values in wanted.items():
                slot = next(s for s in bell_slots if s.id == slot_id)
                existing = Lesson.objects.filter(
                    school_class=school_class, day_of_week=day, bell_slot=slot
                ).first()
                subject_id = values["subject_id"]
                teacher_id = values["teacher_id"]
                co_teacher_ids = values["co_teacher_ids"]
                room_id = values["room_id"]

                if not subject_id or not teacher_id:
                    if existing:
                        existing.delete()
                    continue

                day_label = day_names[day]

                # Входит ли эта ячейка в поток (параллельный блок)? Если да,
                # учителя потока могут в это же время вести группы в других
                # классах потока — это не накладка, а деление на группы.
                block = ParallelBlock.objects.filter(
                    is_active=True, subject_id=subject_id, school_classes=school_class
                ).first()

                # Проверка: заняты ли выбранные учителя в это же время у другого класса
                all_teacher_ids = [teacher_id] + co_teacher_ids
                conflicts_qs = Lesson.objects.filter(
                    day_of_week=day, bell_slot=slot
                ).filter(
                    Q(teacher_id__in=all_teacher_ids) | Q(co_teachers__id__in=all_teacher_ids)
                ).exclude(school_class=school_class)
                if block:
                    # Урок того же предмета в другом классе потока — это не
                    # накладка, а параллельная группа. Проверяем не только по
                    # полю parallel_block (оно могло не проставиться, если урок
                    # создавали до появления потока или руками), но и по составу
                    # потока: тот же предмет + класс из этого же потока.
                    conflicts_qs = conflicts_qs.exclude(
                        Q(parallel_block=block)
                        | Q(subject_id=subject_id, school_class__in=block.school_classes.all())
                    )
                teacher_conflict = conflicts_qs.select_related(
                    "school_class", "teacher"
                ).distinct().first()

                # Проверка: занят ли этот кабинет в это же время у другого класса
                room_conflict = None
                if room_id:
                    room_conflict = Lesson.objects.filter(
                        day_of_week=day, bell_slot=slot, room_id=room_id
                    ).exclude(school_class=school_class).select_related("school_class", "room").first()

                if teacher_conflict:
                    busy = ", ".join(
                        t.full_name for t in teacher_conflict.all_teachers
                        if str(t.id) in {str(i) for i in all_teacher_ids}
                    ) or teacher_conflict.teacher.full_name
                    warnings.append(
                        f"{day_label}, {slot.number} урок: учитель {busy} "
                        f"уже занят в это время в классе {teacher_conflict.school_class.name} — ячейка НЕ сохранена."
                    )
                    continue

                if room_conflict:
                    warnings.append(
                        f"{day_label}, {slot.number} урок: кабинет {room_conflict.room.name} "
                        f"уже занят в это время классом {room_conflict.school_class.name} — ячейка НЕ сохранена."
                    )
                    continue

                if existing:
                    existing.subject_id = subject_id
                    existing.teacher_id = teacher_id
                    existing.room_id = room_id
                    existing.parallel_block = block
                    existing.save()
                    lesson = existing
                else:
                    lesson = Lesson.objects.create(
                        school_class=school_class,
                        day_of_week=day,
                        bell_slot=slot,
                        subject_id=subject_id,
                        teacher_id=teacher_id,
                        room_id=room_id,
                        parallel_block=block,
                    )
                lesson.co_teachers.set(co_teacher_ids)

        # Мягкое предупреждение: один и тот же предмет дважды в один день у этого класса
        # (не блокирует сохранение — сдвоенные уроки бывают нужны специально).
        saved_lessons = list(
            Lesson.objects.filter(school_class=school_class)
            .select_related("subject", "teacher", "bell_slot")
            .order_by("day_of_week", "bell_slot__number")
        )

        by_day = {}
        for lesson in saved_lessons:
            by_day.setdefault(lesson.day_of_week, []).append(lesson.subject.display_name())
        for day, subj_names in by_day.items():
            dupes = {name for name in subj_names if subj_names.count(name) > 1}
            for name in dupes:
                warnings.append(
                    f"{day_names[day]}: предмет «{name}» стоит несколько раз в этот день — проверьте, так и задумано."
                )

        # ---------- Проверки по методическим рекомендациям СанПиН РК ----------
        # Основа: приказ Министра здравоохранения РК от 5 августа 2021 года № ҚР ДСМ-76
        # «Санитарно-эпидемиологические требования к объектам образования».
        HARD_SUBJECT_THRESHOLD = 4  # балл трудности предмета (1-5), с которого считаем предмет "сложным"

        lessons_by_day = {}
        for lesson in saved_lessons:
            lessons_by_day.setdefault(lesson.day_of_week, []).append(lesson)

        # п.73: сдвоенные уроки (один и тот же предмет + учитель подряд) не допускаются в начальной школе
        if school_class.is_elementary:
            for day, day_lessons in lessons_by_day.items():
                day_lessons_sorted = sorted(day_lessons, key=lambda l: l.bell_slot.number)
                for prev, curr in zip(day_lessons_sorted, day_lessons_sorted[1:]):
                    if (
                        curr.bell_slot.number == prev.bell_slot.number + 1
                        and curr.subject_id == prev.subject_id
                        and curr.teacher_id == prev.teacher_id
                    ):
                        warnings.append(
                            f"СанПиН РК (п.73): {day_names[day]}, {prev.bell_slot.number}-{curr.bell_slot.number} уроки — "
                            f"сдвоенный урок «{curr.subject.display_name()}» не допускается в начальной школе "
                            f"(класс {school_class.name})."
                        )

        # Шкала трудности (Приложение 4): сложный предмет не должен стоять первым/последним уроком дня
        for day, day_lessons in lessons_by_day.items():
            if not day_lessons:
                continue
            min_slot = min(l.bell_slot.number for l in day_lessons)
            max_slot = max(l.bell_slot.number for l in day_lessons)
            for lesson in day_lessons:
                if lesson.subject.difficulty_score and lesson.subject.difficulty_score >= HARD_SUBJECT_THRESHOLD:
                    if lesson.bell_slot.number == min_slot:
                        warnings.append(
                            f"СанПиН РК: {day_names[day]} — сложный предмет «{lesson.subject.display_name()}» "
                            f"стоит первым уроком, рекомендуется 2-4 уроком."
                        )
                    elif lesson.bell_slot.number == max_slot and max_slot != min_slot:
                        warnings.append(
                            f"СанПиН РК: {day_names[day]} — сложный предмет «{lesson.subject.display_name()}» "
                            f"стоит последним уроком, рекомендуется 2-4 уроком."
                        )

        # Не группировать много сложных предметов в один день
        for day, day_lessons in lessons_by_day.items():
            hard_count = sum(
                1 for l in day_lessons
                if l.subject.difficulty_score and l.subject.difficulty_score >= HARD_SUBJECT_THRESHOLD
            )
            if hard_count >= 3:
                warnings.append(
                    f"СанПиН РК: {day_names[day]} — {hard_count} сложных предмета подряд в один день, "
                    f"рекомендуется распределить их по разным дням недели."
                )

        # Наибольшая нагрузка рекомендуется на вторник/среду, а не на понедельник/пятницу
        counts_by_day = {day: len(lessons) for day, lessons in lessons_by_day.items()}
        monday_count = counts_by_day.get(0, 0)
        friday_count = counts_by_day.get(4, 0)
        tuesday_count = counts_by_day.get(1, 0)
        wednesday_count = counts_by_day.get(2, 0)
        if monday_count and monday_count > tuesday_count and monday_count > wednesday_count:
            warnings.append(
                "СанПиН РК: в понедельник больше уроков, чем во вторник/среду — "
                "рекомендуется, чтобы наибольшая нагрузка приходилась на вторник-среду."
            )
        if friday_count and friday_count > tuesday_count and friday_count > wednesday_count:
            warnings.append(
                "СанПиН РК: в пятницу больше уроков, чем во вторник/среду — "
                "рекомендуется, чтобы наибольшая нагрузка приходилась на вторник-среду."
            )

        if warnings:
            for w in warnings:
                messages.warning(request, w)
        else:
            messages.success(request, f"Расписание для {school_class.name} сохранено.")
        return redirect("editor_class_grid", slug=slug)

    lessons = Lesson.objects.filter(school_class=school_class).select_related(
        "subject", "teacher", "room", "bell_slot"
    ).prefetch_related("co_teachers")
    grid = _build_grid(lessons, bell_slots, WORKING_DAYS)

    # Потоки, в которые входит этот класс — показываем завучу подсказку,
    # по каким предметам класс учится одновременно с другими классами.
    class_blocks = (
        ParallelBlock.objects.filter(is_active=True, school_classes=school_class)
        .select_related("subject").prefetch_related("school_classes", "teachers")
    )

    # Текущая нагрузка каждого учителя (сколько уроков в неделю по всей школе) —
    # чтобы завуч видел это при выборе учителя в ячейке.
    load_counts = dict(
        Lesson.objects.values("teacher_id").annotate(total=Count("id")).values_list("teacher_id", "total")
    )
    teacher_loads = {t.id: load_counts.get(t.id, 0) for t in teachers}

    return render(request, "schedule/editor_grid.html", {
        "school_class": school_class,
        "bell_slots": bell_slots,
        "days": WORKING_DAYS,
        "grid": grid,
        "subjects": subjects,
        "teachers": teachers,
        "rooms": rooms,
        "teacher_loads": teacher_loads,
        "class_blocks": class_blocks,
        "co_teacher_slots": list(range(2, MAX_CO_TEACHERS + 2)),
        "all_classes": SchoolClass.objects.all(),
        "stream1_grades": STREAM_1_GRADES,
    })
