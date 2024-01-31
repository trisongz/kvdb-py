"""
Dummy Tasks to test
"""

from kvdb.utils.logs import logger
from kvdb.tasks.main import TaskManager
from kvdb.tasks.abstract import TaskABC
from typing import Callable, List, Optional, Type, Any


class TestClass(TaskABC):
    
    @TaskManager.register(task_abc=True)
    def func_one(self, *args, **kwargs):
        logger.info(f'func_one {args} {kwargs}')
        return 'func_one'


class SubtestClass2(TestClass):
    

    def func_two(self, *args, **kwargs):
        logger.info(f'func_two {args} {kwargs}')
        return 'func_two'


class SubtestClass3(SubtestClass2):
    # Should only have func_one, func_two, func_three
    
    @TaskManager.register_abc
    def func_three(self, *args, **kwargs):
        logger.info(f'func_three {args} {kwargs}')
        return 'func_three'


class SubTestClass4(SubtestClass3):
    pass


class SubTestClass5(SubTestClass4):

    @TaskManager.register_abc
    def func_four(self, *args, **kwargs):
        logger.info(f'func_four {args} {kwargs}')
        return 'func_four'


class SubTestClass6(SubtestClass2):

    @TaskManager.register_abc
    def func_five(self, *args, **kwargs):
        logger.info(f'func_five {args} {kwargs}')
        return 'func_five'

@TaskManager.register_abc(silenced=True)
class SubTestClass7(SubTestClass6, SubTestClass5):
    
    @TaskManager.register_abc
    def func_six(self, *args, **kwargs):
        logger.info(f'func_six {args} {kwargs}')
        return 'func_six'


def initializer():
    x = SubTestClass7()