# CLAUDE.md - Pycrash Development Guide

## What This Is

Pycrash is a 2D vehicle crash simulation and accident reconstruction tool. It models vehicle motion, tire physics, and vehicular impacts using SDOF, impulse-momentum, and sideswipe collision models. Used in forensic accident reconstruction and litigation support. Published on PyPI, validated against SAE papers and NHTSA crash test data.

**License:** GPLv3 | **Python:** >=3.9 | **Version:** 0.0.18 | **Author:** Joe Cormier

## Repository Layout

```
pycrash/                        # Main package
  __init__.py                   # Exports: Impact, Vehicle, SingleMotion, KinematicsTwo, SDOF_Model, Project
  vehicle.py                    # Vehicle class - properties, dimensions, driver inputs
  impact_main.py                # Impact class - main multi-vehicle simulation controller
  sdof_model.py                 # SDOF_Model - single degree of freedom impact model
  sdof_model_mc.py              # SDOF with Monte Carlo uncertainty analysis
  kinematics.py                 # SingleMotion - single vehicle motion simulation
  kinematicstwo.py              # KinematicsTwo - two vehicle pre-impact motion
  vehicle_model.py              # Core vehicle dynamics engine (single vehicle)
  multi_vehicle_model.py        # Multi-vehicle motion calculations
  impact_vehicle_model.py       # Vehicle model during impact scenarios
  impc.py                       # Impulse-momentum planar collision (alternative entry)
  planar_motion.py              # Simplified planar motion
  project.py                    # Project management (cookiecutter + pickle persistence)
  plots.py                      # Matplotlib plotting utilities
  definitions.py                # Variable definitions dictionary

  model_calcs/                  # Core physics calculations
    tire_model.py               # Tire forces: slip angles, load transfer, lock detection
    carpenter_momentum_calcs.py # Carpenter & Welcher IMPC model
    impact_detect.py            # Point-edge impact detection geometry
    collision_plane.py          # Impact plane/edge definitions per vehicle
    sideswipe.py                # Sideswipe collision model (continuous contact + friction)
    position_data.py            # Vehicle geometry transforms, tire positioning
    momentum_optimizer.py       # Optimization for momentum calcs

  sdof_calcs/                   # SDOF model internals
    sdof_calculations.py        # Iterative SDOF solver (dt=0.0001s)
    spring_models.py            # Spring force models (constant K, table lookup)
    sodf_montecarlo.py          # Monte Carlo simulation wrapper

  visualization/                # Plotly-based interactive plots
    vehicle.py                  # Vehicle outlines, driver inputs, impact points
    kinematics.py               # Motion kinematics plots
    initial_positions.py        # Pre-simulation positioning
    vehicles_at_impact.py       # Impact moment visualization
    model_interval_two_vehicles.py  # Multi-vehicle motion intervals
    tire_details.py             # Tire force/slip plots
    model.py, model_interval.py # Trajectory plots

  functions/                    # Utilities and data processing
    ar.py                       # Accident reconstruction equations (A/B stiffness, delta-V)
    CFCFilter.py                # Channel Frequency Class filtering
    vehicle_stiffness.py        # Vehicle stiffness calculations
    process_nhtsa_loadcelldata_*.py # NHTSA crash test data parsers (4 versions)

  data/defaults/                # Default configs
    config.py                   # Simulation defaults (dt, friction, slip angles)
    definitions.py              # Column/variable definitions

  cli.py                        # Click-based CLI (pycrash info/sdof/vehicle/project)
  units.py                      # Metric unit conversion (MetricVehicle, MetricResults)

  dash/                         # Dash web interface (minimal)
    app.py

tests/                          # pytest test suite (137 tests)
  conftest.py                   # Shared fixtures and vehicle input dicts
  test_ar.py                    # AR equation tests
  test_sdof.py                  # SDOF solver and spring model tests
  test_tire_model.py            # Tire force calculation tests
  test_vehicle.py               # Vehicle class tests
  test_vehicle_model.py         # Vehicle dynamics integration tests

projects/                       # Example/validation projects (Jupyter notebooks)
  pycrash demo/                 # Basic functionality demo
  validation sdof/              # SDOF model validation against published data
  validation impact momentum/   # IMPC model validation
  validation sideswipe/         # Sideswipe validation
  multiple vehicle impact/      # Multi-impact scenarios
  Create Project Directory.ipynb
```

## Architecture & Data Flow

### Core Pipeline

```
Vehicle(properties + driver_inputs)
    |
    v
SingleMotion / KinematicsTwo      <-- Pre-impact vehicle trajectories
    |
    v
Impact.simulate()                 <-- Main simulation loop
    |-- multi_vehicle_model()     <-- Dynamics + tire forces per timestep
    |-- impact_detect()           <-- Point-edge geometry collision check
    |-- carpenter_momentum()      <-- IMPC impulse calculation on collision
    |-- update velocities         <-- Apply delta-V and angular changes
    v
vehicle.model (DataFrame)         <-- Full time-series output
    |
    v
Visualization (Plotly/Matplotlib) <-- Interactive and static plots
```

### Three Collision Models

1. **SDOF** (`SDOF_Model`): Spring-mass model. Two vehicles, iterative solver at dt=0.0001s. Uses stiffness (constant K or force-displacement table) and coefficient of restitution. Outputs crush, delta-V, energy.

2. **IMPC** (Impulse-Momentum Planar Collision): Instantaneous momentum-based collision per Carpenter & Welcher. Handles sliding friction at contact. Used inside `Impact.simulate()` when collisions are detected.

3. **Sideswipe**: Continuous contact model. Normal force from crush depth * stiffness, friction force from relative sliding. Applied at each timestep during contact.

### Vehicle Dynamics

- **Tire model**: Linear slip angle model with load transfer from lateral/longitudinal acceleration
- **4-wheel model**: LF, RF, RR, LR with independent forces and lock detection
- **Drivetrain**: FWD, RWD, AWD configurations
- **Coordinate frames**: Vehicle-local (vx, vy) and global inertial (Vx, Vy)
- **Units**: Imperial (lb, ft, ft/s, mph). Conversion: mph * 1.46667 = ft/s

### Key Output: `vehicle.model` DataFrame

Columns include: `t, vx, vy, Vx, Vy, Vr, Dx, Dy, theta_rad, oz_rad, au, av, Ax, Ay, Ar, lf_fx, lf_fy, ..., lr_fz, lf_alpha, ..., lr_lock, Fx, Fy, Mz, alphaz`

## Key Classes (Public API)

| Class | Module | Purpose |
|-------|--------|---------|
| `Vehicle` | `vehicle.py` | Vehicle properties, dimensions, driver inputs, stiffness |
| `Impact` | `impact_main.py` | Multi-vehicle impact simulation controller |
| `SDOF_Model` | `sdof_model.py` | Single degree of freedom crash model |
| `SingleMotion` | `kinematics.py` | Single vehicle motion trajectory |
| `KinematicsTwo` | `kinematicstwo.py` | Two vehicle pre-impact motion |
| `Project` | `project.py` | Project directory creation, pickle save/load |

## Build & Run

```bash
# Install
pip install -e .
# or
pip install pycrash

# Dependencies (critical ones)
numpy>=1.21  pandas==1.2.0  scipy==1.10.0  matplotlib==3.3.3
plotly==4.14.0  scikit-learn==1.5.0  cookiecutter==2.1.1  joblib==1.2.0
dash==2.15.0  tabulate==0.8.7  openpyxl==3.0.6

# Run demos via Jupyter
jupyter notebook projects/pycrash\ demo/notebooks/
```

## Testing

```bash
# Run all tests (137 tests)
python -m pytest tests/ -v

# Run specific test modules
python -m pytest tests/test_ar.py        # AR equations
python -m pytest tests/test_sdof.py      # SDOF solver + spring models
python -m pytest tests/test_vehicle.py   # Vehicle class
python -m pytest tests/test_vehicle_model.py  # Vehicle dynamics
python -m pytest tests/test_tire_model.py     # Tire forces
```

Test coverage: Vehicle creation/properties, driver inputs, SDOF solver (momentum conservation, COR, stiffness), spring models (constant + table), tire forces (FWD/RWD/AWD, slip angles, weight transfer, lock detection), vehicle dynamics (braking, coasting, turning, coordinate transforms, position integration), AR equations (A/B stiffness, delta-V, crush energy, restitution).

Additional validation via Jupyter notebooks in `projects/` comparing against published SAE papers and NHTSA crash test data.

## Default Simulation Parameters

```python
# From pycrash/data/defaults/config.py
dt_motion = 0.1       # Motion timestep (seconds)
dt_impact = 0.0001    # SDOF impact timestep (seconds)
mu_max = 0.9          # Max tire-road friction coefficient
alpha_max = 0.349066  # Max tire slip angle (20 degrees)
vehicle_mu = 0.3      # Inter-vehicle friction coefficient

# vehicle.py internal defaults
dt_motion = 0.01      # 10ms for vehicle model integration
mu_max = 0.8
alpha_max = 0.174533  # 10 degrees
```

## Development Notes

- All physics in imperial units (lb, ft, ft/s, degrees). Don't introduce metric without conversion layers.
- `vehicle.model` is the central DataFrame that accumulates all simulation results per timestep.
- Impact detection uses point-in-polygon / point-edge geometry (`impact_detect.py`). Striking vehicle corner points are tested against struck vehicle edges.
- The IMPC model transforms to a normal-tangential frame at the impact point, calculates impulse, checks sliding condition, then transforms back.
- Pickle is used for project persistence (`project.py`). JSON save/load available as safer alternative via `save_project_json()` / `load_project_json()`.
- Visualization defaults to Plotly with browser rendering. Matplotlib used for static force-displacement plots.
- Monte Carlo capability exists in `sdof_model_mc.py` / `sodf_montecarlo.py` using joblib for parallelization.
- Type hints added across all public API and core internals. Uses `TYPE_CHECKING` pattern to avoid circular imports.
- CLI available via `pycrash` command (info, sdof, vehicle, project subcommands). See `pycrash/cli.py`.
- Metric unit support via `pycrash/units.py`: `MetricVehicle(dict)` converts metric inputs to imperial, `MetricResults(df)` converts output DataFrame to metric.
- No CI/CD pipeline currently.
- The `projects/` directory uses cookiecutter templates for standardized project structure.
