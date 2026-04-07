import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

# Core dependencies (always required)
install_requires = [
    'numpy>=1.21',
    'pandas>=1.2',
    'scipy>=1.7',
    'matplotlib>=3.3',
    'plotly>=4.14',
]

# Optional dependencies for extended functionality
extras_require = {
    # BeamNG.tech integration for 3D crash simulation and validation
    'beamng': [
        'beamngpy>=1.26',
    ],
    # OpenSim integration for occupant biomechanical analysis
    'opensim': [
        'opensim>=4.4',
    ],
    # Full pipeline: pycrash + BeamNG + OpenSim
    'full': [
        'beamngpy>=1.26',
        'opensim>=4.4',
    ],
    # Development / testing
    'dev': [
        'pytest>=7.0',
        'pytest-cov',
    ],
}

setuptools.setup(
    name="pycrash",
    version="0.1.0",
    author="Joe Cormier",
    author_email="joemcormier@outlook.com",
    description="Vehicle crash reconstruction with BeamNG.drive 3D simulation "
                "and OpenSim occupant injury analysis",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/joe-cormier/pycrash",
    packages=setuptools.find_packages(exclude=("__pycache__", )),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering",
        "Topic :: Scientific/Engineering :: Physics",
    ],
    python_requires='>=3.8',
    install_requires=install_requires,
    extras_require=extras_require,
)
