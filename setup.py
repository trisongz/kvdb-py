import sys
from pathlib import Path
from setuptools import setup, find_packages
from typing import Optional

if sys.version_info.major != 3:
    raise RuntimeError("This package requires Python 3+")

pkg_name = 'kvdb-py'
gitrepo = 'trisongz/kvdb-py'
root = Path(__file__).parent
version = root.joinpath('kvdb/version.py').read_text().split('VERSION = ', 1)[-1].strip().replace('-', '').replace("'", '')


def get_requirements(
    name: Optional[str] = None,
):
    """
    Get the requirements from the `requirements` folder
    """
    if name: name = f'requirements.{name}' if 'requirements' not in name else name
    else: name = 'requirements'
    base_path = root
    if not name.endswith('.txt'): name = f'{name}.txt'
    text_lines = base_path.joinpath(name).read_text().splitlines()
    return [line.strip() for line in text_lines if ('#' not in line[:5] and line.strip())]

requirements = get_requirements()

# requirements = [
#     "anyio",
#     "pydantic",
#     "pydantic-settings",
#     "croniter",
#     "tenacity",
#     "backoff",
#     "redis",
#     "hiredis",
#     # "trio",
#     # "structlog",
#     "xxhash",
#     "makefun",
#     "lazyops>=0.2.69",
#     "typer",
#     'typing-extensions; python_version<"3.8"',
# ]

args = {
    'packages': find_packages(
        include=[
            "kvdb",
            "kvdb.*",
        ]
    ),
    'install_requires': requirements,
    'include_package_data': True,
    'long_description': root.joinpath('README.md').read_text(encoding='utf-8'),
    'entry_points': {
        'console_scripts': [
            'kvdb-task = kvdb.tasks.cli:main',
        ],
    },
    'extras_require': {
        "serialization": [
            "pysimdjson",
            "cloudpickle",
            "zstd",
        ],
        "docs": [
            "mkdocs-material",
            "mkdocstrings[python]",
            "black",
        ]
    },
    'project_urls': {
        "Documentation": "https://trisongz.github.io/kvdb-py/",
        "Changes": "https://github.com/trisongz/kvdb-py/releases",
        "Code": "https://github.com/trisongz/kvdb-py",
    },
}


setup(
    name=pkg_name,
    version=version,
    url=f'https://github.com/{gitrepo}',
    license='MIT Style',
    description='Key-Value DB Python Client Abstraction built on top of Redis',
    author='Tri Songz',
    author_email='ts@growthengineai.com',
    long_description_content_type="text/markdown",
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.7',
        'Topic :: Software Development :: Libraries',
    ],
    **args
)