import json
import logging
from datetime import timedelta

import pytest
from pytest_django.fixtures import SettingsWrapper

from task_processor.decorators import (
    register_recurring_task,
    register_task_handler,
)
from task_processor.exceptions import InvalidArgumentsError
from task_processor.models import RecurringTask
from task_processor.task_registry import get_task
from task_processor.task_run_method import TaskRunMethod


def test_register_task_handler_run_in_thread(mocker, caplog):
    # Given
    # caplog doesn't allow you to capture logging outputs from loggers that don't
    # propagate to root. Quick hack here to get the task_processor logger to
    # propagate.
    # TODO: look into using loguru.
    task_processor_logger = logging.getLogger("task_processor")
    task_processor_logger.propagate = True
    # Assume required level for the logger.
    task_processor_logger.setLevel(logging.INFO)
    caplog.set_level(logging.INFO)

    @register_task_handler()
    def my_function(*args, **kwargs):
        pass

    mock_thread = mocker.MagicMock()
    mock_thread_class = mocker.patch(
        "task_processor.decorators.Thread", return_value=mock_thread
    )

    args = ("foo",)
    kwargs = {"bar": "baz"}

    # When
    my_function.run_in_thread(args=args, kwargs=kwargs)

    # Then
    mock_thread_class.assert_called_once_with(
        target=my_function.unwrapped, args=args, kwargs=kwargs, daemon=True
    )
    mock_thread.start.assert_called_once()

    assert len(caplog.records) == 1
    assert (
        caplog.records[0].message == "Running function my_function in unmanaged thread."
    )


def test_register_recurring_task(mocker, db, run_by_processor):
    # Given
    task_kwargs = {"first_arg": "foo", "second_arg": "bar"}
    run_every = timedelta(minutes=10)
    task_identifier = "test_unit_task_processor_decorators.a_function"

    # When
    @register_recurring_task(
        run_every=run_every,
        kwargs=task_kwargs,
    )
    def a_function(first_arg, second_arg):
        return first_arg + second_arg

    # Then
    task = RecurringTask.objects.get(task_identifier=task_identifier)
    assert task.serialized_kwargs == json.dumps(task_kwargs)
    assert task.run_every == run_every

    assert get_task(task_identifier)
    assert task.run() == "foobar"


def test_register_recurring_task_does_nothing_if_not_run_by_processor(mocker, db):
    # Given

    task_kwargs = {"first_arg": "foo", "second_arg": "bar"}
    run_every = timedelta(minutes=10)
    task_identifier = "test_unit_task_processor_decorators.some_function"

    # When
    @register_recurring_task(
        run_every=run_every,
        kwargs=task_kwargs,
    )
    def some_function(first_arg, second_arg):
        return first_arg + second_arg

    # Then
    assert not RecurringTask.objects.filter(task_identifier=task_identifier).exists()
    with pytest.raises(KeyError):
        assert get_task(task_identifier)


def test_register_task_handler_validates_inputs() -> None:
    # Given
    @register_task_handler()
    def my_function(*args, **kwargs):
        pass

    class NonSerializableObj:
        pass

    # When
    with pytest.raises(InvalidArgumentsError):
        my_function(NonSerializableObj())


@pytest.mark.parametrize(
    "task_run_method", (TaskRunMethod.SEPARATE_THREAD, TaskRunMethod.SYNCHRONOUSLY)
)
def test_inputs_are_validated_when_run_without_task_processor(
    settings: SettingsWrapper, task_run_method: TaskRunMethod
) -> None:
    # Given
    settings.TASK_RUN_METHOD = task_run_method

    @register_task_handler()
    def my_function(*args, **kwargs):
        pass

    class NonSerializableObj:
        pass

    # When
    with pytest.raises(InvalidArgumentsError):
        my_function.delay(args=(NonSerializableObj(),))
