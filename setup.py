"Home Assistant add-ons repository updater setup."
from setuptools import find_packages, setup

from repositoryupdater import APP_DESCRIPTION, APP_NAME, APP_VERSION

setup(
    name=APP_NAME,
    version=APP_VERSION,
    author="Franck Nijhof",
    author_email="frenck@addons.community",
    description=APP_DESCRIPTION.split("\n")[0],
    long_description=APP_DESCRIPTION,
    license="MIT",
    url="https://github.com/hassio-addons/repository-updater",
    keywords=[
        "addons",
        "repository",
        "home assistant",
        "home-assistant",
        "add-ons",
        "frenck",
    ],
    platforms="any",
    classifiers=[
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3",
        "Topic :: Software Development :: Build Tools",
        "Topic :: Utilities",
    ],
    packages=find_packages(),
    install_requires=[
        "click==8.3.1",
        "crayons==0.4.0",
        "emoji==2.15.0",
        "GitPython==3.1.45",
        "Jinja2==3.1.6",
        "PyGithub==2.8.1",
        "python-dateutil==2.9.0.post0",
        "PyYAML==6.0.3",
        "semver==3.0.4",
    ],
    entry_points="""
        [console_scripts]
            repository-updater=repositoryupdater.cli:repository_updater
            repository-updater-git-askpass=repositoryupdater.cli:git_askpass
    """,
)
