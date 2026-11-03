# -*- coding: utf-8 -*

import os
from copy import deepcopy

from unittest import mock

from exporter import tasks

import pytest


class TestOrgTask(tasks.OrgTask, tasks.Task):
    NAME = 'test_org_task'
    EXT = 'csv'


class TestCourseTask(tasks.CourseTask, tasks.Task):
    NAME = 'test_course_task'
    EXT = 'csv'


@mock.patch('exporter.tasks.execute_shell')
def test_org_email_opt_in_task(mock_execute_shell):
    """ The email_opt_in_list django admin command should be invoked with multiple organizations if the config
    includes a non-empty `other_names` section. """
    kwargs = {
        'organization': 'the-org',
        'other_names': ['the-second-org', 'the-third-org'],
        'courses': ['course-1', 'coursé-2'],
        'lms_config': 'the-lms-config',
        'studio_config': 'the-studio-config',
        'django_admin': 'the-django-admin',
        'django_settings': 'the-django-setings',
        'django_pythonpath': 'the-django-python-path',
    }
    filename = 'the-filename'
    dry_run = False

    command = tasks.OrgEmailOptInTask.run(filename, dry_run, **kwargs)

    assert command.endswith('the-filename the-org the-second-org the-third-org --courses=course-1,coursé-2 --email-optin-chunk-size=10000')
    assert 'email_opt_in_list' in command
    expected_kwargs = deepcopy(kwargs)
    expected_kwargs['all_organizations'] = 'the-org the-second-org the-third-org'
    expected_kwargs['comma_sep_courses'] = 'course-1,coursé-2'
    expected_kwargs['max_tries'] = 3
    mock_execute_shell.assert_called_once_with(command, **expected_kwargs)


def test_get_filename_org_task():
    kwargs = {
        'name': 'test-analytics',
        'work_dir': '/tmp/workdir/',
        'organization': 'testx',
    }
    assert '/tmp/workdir/testx-test_org_task-test-analytics.csv' == TestOrgTask.get_filename(**kwargs)


def test_get_filename_course_task():
    kwargs = {
        'name': 'test-analytics',
        'work_dir': '/tmp/workdir/',
        'course': 'course-v1:edX+DemoX+Demo_Course',
    }
    assert '/tmp/workdir/edX-DemoX-Demo_Course-test_course_task-test-analytics.csv' == TestCourseTask.get_filename(**kwargs)


def test_get_non_ascii_filename_course_task():
    kwargs = {
        'name': 'test-analytics',
        'work_dir': '/tmp/workdir/',
        'course': 'course-v1:edX+DemoX+Démo_Course',
    }
    assert '/tmp/workdir/edX-DemoX-D_mo_Course-test_course_task-test-analytics.csv' == TestCourseTask.get_filename(**kwargs)

@pytest.mark.parametrize(
    'name',
    [
        'a',
        'a' * (255 - 1 - len(TestCourseTask.EXT)),
        'a' * (256 - 1 - len(TestCourseTask.EXT)),
        'a' * (1000 - 1 - len(TestCourseTask.EXT)),
    ]
)
def test_course_task_get_filename_on_multiple_sizes(name):
    """
    Test TestCourseTask.get_filename with multiple name sizes
    """
    kwargs = {
        'name': name,
        'work_dir': '/tmp/workdir/',
        'course': 'course-v1:edX+DemoX+Demo_Course',
    }
    with mock.patch('exporter.tasks._get_max_filename_length', return_value=255):
        file_name = os.path.basename(TestCourseTask.get_filename(**kwargs))
        # The base name without an extension should have a length that is
        # less than or equal to 255 - 20
        assert len(os.path.splitext(file_name)[0]) <= 235


def test_course_task_get_filename_on_similar_names():
    """
    Test that 3 very long names with a one character difference don't end up
    having duplicate file names.
    """
    kwargs = {
        'work_dir': '/tmp/workdir/',
        'course': 'course-v1:edX+DemoX+Demo_Course',
    }
    with mock.patch('exporter.tasks._get_max_filename_length', return_value=255):
        kwargs['name'] = 'a' * 1000
        file_name1 = os.path.basename(TestCourseTask.get_filename(**kwargs))
        # Change the leading 'a' to 'b'
        kwargs['name'] = ('a' * 1000).replace('a', 'b', 1)
        file_name2 = os.path.basename(TestCourseTask.get_filename(**kwargs))
        # Change the trailing 'a' to 'b'
        kwargs['name'] = ('a' * 999) + 'b'
        file_name3 = os.path.basename(TestCourseTask.get_filename(**kwargs))
        assert len(set([file_name1, file_name2, file_name3])) == 3

def test_normalize_value_with_null_character():
    """
    Test that a null character is removed from a string.
    """
    mysql_task = tasks.MysqlDumpQueryToTSV(
        host='localhost',
        username='root',
        password='password',
        database='test',
        destination_filename='test.tsv',
    )
    assert mysql_task._normalize_value('abc\x00') == 'abc'


FORUM_KWARGS = {
    'course': 'course-v1:edX+DemoX+Demo_Course',
    'sql_host': 'the-sql-host',
    'sql_user': 'the-sql-user',
    'sql_password': 'the-sql-password',
    'sql_db': 'the-sql-db',
    'mongo_host': 'the-mongo-host',
    'mongo_db': 'the-mongo-db',
    'mongo_user': 'the-mongo-user',
    'mongo_password': 'the-mongo-password',
    'mongo_collection': 'the-mongo-collection',
}

@pytest.fixture(autouse=True)
def clear_forum_backend_cache():
    tasks._forum_on_mysql.cache.clear()


@pytest.mark.parametrize('value, expected', [(1, True), (0, False), (None, False), ('1', True), ('0', False)])
@mock.patch('exporter.tasks.MysqlDumpQueryToTSV')
def test_forum_on_mysql(mock_mysql, value, expected):
    """ The forum backend flag is read from the course and org overrides and the flag itself. """
    mock_mysql.return_value.fetch_value.return_value = value

    assert tasks.forum_on_mysql(**FORUM_KWARGS) is expected

    mock_mysql.assert_called_once_with('the-sql-host', 'the-sql-user', 'the-sql-password', 'the-sql-db', None)
    query = mock_mysql.return_value.fetch_value.call_args[0][0]
    assert "waffle_flag='forum_v2.enable_mysql_backend' AND course_id='course-v1:edX+DemoX+Demo_Course'" in query
    assert "waffle_flag='forum_v2.enable_mysql_backend' AND org='edX'" in query
    assert "FROM waffle_flag WHERE name='forum_v2.enable_mysql_backend'" in query


@mock.patch('exporter.tasks.MysqlDumpQueryToTSV')
def test_forum_on_mysql_is_checked_once_per_course(mock_mysql):
    """ All forum tasks for a course must agree, so the flag is read once per course. """
    mock_mysql.return_value.fetch_value.return_value = 1

    assert tasks.forum_on_mysql(**FORUM_KWARGS)
    assert tasks.forum_on_mysql(**dict(FORUM_KWARGS, name='another-task-kwarg'))
    assert mock_mysql.return_value.fetch_value.call_count == 1

    tasks.forum_on_mysql(**dict(FORUM_KWARGS, course='course-v1:OtherX+Other+2026'))
    assert mock_mysql.return_value.fetch_value.call_count == 2


@pytest.mark.parametrize('on_mysql, exported', [(False, True), (True, False)])
@mock.patch('exporter.tasks.execute_shell')
@mock.patch('exporter.tasks.forum_on_mysql')
def test_forums_task_exports_mongodb_only_when_forum_is_in_mongodb(mock_on_mysql, mock_execute_shell, on_mysql, exported):
    mock_on_mysql.return_value = on_mysql

    tasks.ForumsTask.run('the-filename', False, **FORUM_KWARGS)

    assert mock_execute_shell.called is exported
    if exported:
        assert 'mongoexport' in mock_execute_shell.call_args[0][0]


@pytest.mark.parametrize('on_mysql, exported', [(True, True), (False, False)])
@mock.patch('exporter.tasks.MysqlDumpQueryToTSV')
@mock.patch('exporter.tasks.forum_on_mysql')
def test_forum_mysql_task_exports_only_when_forum_is_in_mysql(mock_on_mysql, mock_mysql, on_mysql, exported):
    mock_on_mysql.return_value = on_mysql

    tasks.ForumMySQLTask.run('the-filename', False, **FORUM_KWARGS)

    assert mock_mysql.return_value.execute.called is exported
    if exported:
        mock_mysql.assert_called_once_with('the-sql-host', 'the-sql-user', 'the-sql-password', 'the-sql-db', 'the-filename')
        query = mock_mysql.return_value.execute.call_args[0][0]
        assert "t.course_id='course-v1:edX+DemoX+Demo_Course'" in query
        assert "c.course_id='course-v1:edX+DemoX+Demo_Course'" in query


@mock.patch('exporter.tasks.forum_on_mysql')
def test_forum_tasks_dry_run_does_not_check_backend(mock_on_mysql, capsys):
    for task in [tasks.ForumsTask, tasks.ForumMySQLTask]:
        task.run('the-filename', True, **FORUM_KWARGS)

    assert not mock_on_mysql.called
    output = capsys.readouterr().out
    assert output.count('SQL: ') == 1
    assert 'MONGO: ' in output


def test_get_filename_forum_mysql_task():
    kwargs = {
        'name': 'test-analytics',
        'work_dir': '/tmp/workdir/',
        'course': 'course-v1:edX+DemoX+Demo_Course',
    }
    expected = '/tmp/workdir/edX-DemoX-Demo_Course-forum-test-analytics.sql'
    assert expected == tasks.ForumMySQLTask.get_filename(**kwargs)
