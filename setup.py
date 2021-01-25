from setuptools import setup, find_packages

VERSION = '0.2.0'

setup(
    name='rest_cli',
    version=VERSION,
    description='RESTFul HTTP command-line script and modules',
    long_description="""Command-line script and modules for HTTP requests and HTML/JSON document parsing.""",
    namespace_packages=['rest_cli'],
    packages=find_packages(exclude=['tests', '*.tests']),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'pyquery==1.4.1'
    ],
    python_requires='>=3.6',
    dependency_links=[],
    entry_points={
    },
    scripts=[
        'scripts/rest'
    ]
)
