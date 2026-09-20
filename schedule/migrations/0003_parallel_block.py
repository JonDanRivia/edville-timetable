# Потоки (параллельные блоки) + дополнительные учителя урока:
# английский язык идёт одновременно у 5-6, 7-8, 9-10 и 11 классов,
# ученики делятся на группы между несколькими учителями.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('schedule', '0002_schoolclass_grade_number_subject_difficulty_score_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='lesson',
            name='co_teachers',
            field=models.ManyToManyField(blank=True, help_text='Второй и третий учитель урока — когда класс (или поток классов) делится на группы, например по английскому языку. Основной учитель указывается в поле выше.', related_name='co_lessons', to='schedule.teacher', verbose_name='Дополнительные учителя (деление на группы)'),
        ),
        migrations.CreateModel(
            name='ParallelBlock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='Название потока')),
                ('is_active', models.BooleanField(default=True, help_text='Снимите галочку, чтобы временно отключить поток, не удаляя его.', verbose_name='Учитывать при генерации')),
                ('school_classes', models.ManyToManyField(help_text='Классы, у которых этот предмет стоит в одно и то же время.', related_name='parallel_blocks', to='schedule.schoolclass', verbose_name='Классы потока')),
                ('subject', models.ForeignKey(help_text='Предмет, который идёт одновременно у всех классов потока.', on_delete=django.db.models.deletion.CASCADE, related_name='parallel_blocks', to='schedule.subject', verbose_name='Предмет')),
                ('teachers', models.ManyToManyField(blank=True, help_text='Учителя, которые делят учеников потока на группы. Все они проставляются в каждый урок потока: первый — основным учителем, остальные — дополнительными.', related_name='parallel_blocks', to='schedule.teacher', verbose_name='Учителя потока (по группам)')),
            ],
            options={
                'verbose_name': 'Поток (параллельный блок)',
                'verbose_name_plural': 'Потоки (параллельные блоки)',
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='lesson',
            name='parallel_block',
            field=models.ForeignKey(blank=True, help_text='Если урок входит в поток, учителя этого урока могут вести группы в нескольких классах потока одновременно — это не считается накладкой.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='lessons', to='schedule.parallelblock', verbose_name='Поток'),
        ),
    ]
