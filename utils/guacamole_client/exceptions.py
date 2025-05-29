"""
The MIT License (MIT)

Copyright (c) 2014 - 2016 Mohab Usama
"""
from apps.common.exceptions import CustomException


class GuacamoleError(CustomException):
    def __init__(self, message, code=4001):
        super(GuacamoleError, self).__init__(
            code=code, message='Guacamole Protocol Error. %s' % message
        )


class InvalidInstruction(CustomException):
    def __init__(self, message, code=4002):
        super(InvalidInstruction, self).__init__(
            code=code, message='Invalid Guacamole Instruction! %s' % message
        )
