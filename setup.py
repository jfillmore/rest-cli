from setuptools import setup, find_packages

VERSION = '0.1.1'

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
        'restkit==4.2.2',
        'pyquery==1.4.1'
    ],
    dependency_links=[],
    entry_points={
    },
    scripts=[
        'scripts/rest'
    ]
)
