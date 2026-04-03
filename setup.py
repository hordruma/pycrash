import setuptools

try:
    with open("README.md", "r") as fh:
        long_description = fh.read()
except FileNotFoundError:
    long_description = ""

setuptools.setup(
    name="pycrash",
    version="0.0.18",
    author="Joe Cormier",
    author_email="joemcormier@outlook.com",
    description="software tool for simulating vehicle motion and impacts based on \
    fundamental physics and accident reconstruction techniques",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/joe-cormier/pycrash",
    packages=setuptools.find_packages(exclude=("__pycache__", )),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    license="GPL-3.0-only",
    python_requires='>=3.9',
)
