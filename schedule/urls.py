from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("class/<slug:slug>/", views.class_schedule, name="class_schedule"),
    path("teacher/<slug:slug>/", views.teacher_schedule, name="teacher_schedule"),

    path("editor/", views.editor_home, name="editor_home"),
    path("editor/<slug:slug>/", views.editor_class_grid, name="editor_class_grid"),
]
