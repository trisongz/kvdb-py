import sys
from pathlib import Path
from setuptools import setup, find_packages

if sys.version_info.major != 3:
    raise RuntimeError("This package requires Python 3+")

pkg_name = 'kvdbpy'
gitrepo = 'trisongz/kvdb-py'
root = Path(__file__).parent
version = root.joinpath('kvdb/version.py').read_text().split('VERSION = ', 1)[-1].strip().replace('-', '').replace("'", '')

requirements = [
    "anyio",
    "pydantic",
    "pydantic-settings",
    "croniter",
    "tenacity",
    "backoff",
    "redis",
    "hiredis",
    # "structlog",
    "xxhash",
    "makefun",
    "lazyops>=0.2.67",
    'typing-extensions; python_version<"3.8"',
]

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
    'entry_points': {},
    'extras_require': {
        "hiredis": ["hiredis>=1.0.0"],
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