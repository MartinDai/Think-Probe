import os

from dotenv import load_dotenv

load_dotenv(override=False)


def get_env_variable(var_name, default=None):
    return os.getenv(var_name, default)


on_debug = "True" == get_env_variable("ON_DEBUG")
