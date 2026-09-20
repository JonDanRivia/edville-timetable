from django.contrib import admin
from .models import SchoolClass, Teacher, Subject, Room, BellSlot, Lesson, ParallelBlock


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "grade_number", "order")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ("full_name", "slug")
    prepopulated_fields = {"slug": ("full_name",)}
    search_fields = ("full_name",)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "short_name", "difficulty_score")
    search_fields = ("name",)


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(BellSlot)
class BellSlotAdmin(admin.ModelAdmin):
    list_display = ("number", "start_time", "end_time")


@admin.register(ParallelBlock)
class ParallelBlockAdmin(admin.ModelAdmin):
    """Потоки: 5-6, 7-8, 9-10 и 11 классы, у которых английский идёт одновременно
    и ученики делятся на группы между несколькими учителями."""
    list_display = ("name", "subject", "class_names", "teacher_names", "is_active")
    list_filter = ("is_active", "subject")
    search_fields = ("name",)
    autocomplete_fields = ("subject",)
    filter_horizontal = ("school_classes", "teachers")


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    # Полная админка для точечных правок/поиска.
    # Основная повседневная работа завуча идёт через удобный редактор /editor/<class>/
    list_display = (
        "school_class", "day_of_week", "bell_slot", "subject",
        "teachers_display", "parallel_block", "room",
    )
    list_filter = ("school_class", "day_of_week", "teacher", "parallel_block")
    autocomplete_fields = ("teacher", "subject", "room")
    filter_horizontal = ("co_teachers",)
