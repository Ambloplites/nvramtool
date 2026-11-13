from setuptools import setup

setup(
    name="nvramtool",
    description="Tool for working with AVS2's \"nvram\" and \"nvram2\" filesystems",
    version="0.0.1",
    entry_points={
        "console_scripts": ["nvramtool=nvramtool:main"],
    },
    packages=["nvramtool"],
    requires=["pycryptodome"],
)
