"""
CLI entry point for the pycrash vehicle crash simulation package.

Usage:
    pycrash info
    pycrash sdof --config config.json
    pycrash vehicle --config vehicle.json [--output results.csv]
    pycrash project --name MyProject --path /some/dir
    pycrash project --load MyProject --path /some/dir
"""
import click
import json
import sys
import os


@click.group()
@click.version_option(version="0.0.18", prog_name="pycrash")
def main():
    """Pycrash - 2D vehicle crash simulation and accident reconstruction tool."""
    pass


@main.command()
def info():
    """Show package version and available simulation models."""
    click.echo("pycrash - 2D vehicle crash simulation and accident reconstruction tool")
    click.echo("Version: 0.0.18")
    click.echo("Author: Joe Cormier")
    click.echo("License: GPLv3")
    click.echo("")
    click.echo("Available simulation models:")
    click.echo("  SDOF         - Single Degree of Freedom impact model")
    click.echo("  IMPC         - Impulse-Momentum Planar Collision model")
    click.echo("  Sideswipe    - Continuous contact sideswipe collision model")
    click.echo("")
    click.echo("Available tools:")
    click.echo("  Vehicle      - Vehicle properties and driver inputs")
    click.echo("  SingleMotion - Single vehicle motion trajectory")
    click.echo("  KinematicsTwo - Two vehicle pre-impact motion")
    click.echo("  Impact       - Multi-vehicle impact simulation")
    click.echo("  Project      - Project management (save/load)")


@main.command()
@click.option("--config", required=True, type=click.Path(exists=True),
              help="Path to JSON config file with veh1, veh2, and model_inputs.")
def sdof(config):
    """Run an SDOF simulation from a JSON configuration file.

    The JSON file should contain:

    \b
      {
        "veh1": {"name": "Vehicle 1", "weight": 3000, "vx_initial": 30, "brake": 0, "k": 1500, ...},
        "veh2": {"name": "Vehicle 2", "weight": 3500, "vx_initial": 0, "brake": 0, "k": 1200, ...},
        "model_inputs": {"name": "Run1", "k": 1200, "cor": 0.15, "tstop": 0.3}
      }
    """
    try:
        with open(config, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        click.echo(f"Error: Invalid JSON in config file: {e}", err=True)
        sys.exit(1)

    for key in ("veh1", "veh2", "model_inputs"):
        if key not in data:
            click.echo(f"Error: Config file missing required key '{key}'.", err=True)
            sys.exit(1)

    from pycrash.vehicle import Vehicle
    from pycrash.sdof_model import SDOF_Model

    veh1_data = data["veh1"]
    veh2_data = data["veh2"]
    model_inputs = data["model_inputs"]

    veh1_name = veh1_data.pop("name", "Vehicle 1")
    veh2_name = veh2_data.pop("name", "Vehicle 2")

    veh1 = Vehicle(veh1_name, input_dict=veh1_data)
    veh2 = Vehicle(veh2_name, input_dict=veh2_data)

    sdof_model = SDOF_Model(veh1, veh2, model_inputs=model_inputs)

    click.echo("")
    click.echo("=" * 50)
    click.echo("SDOF Simulation Results")
    click.echo("=" * 50)

    model = sdof_model.model

    # Delta-V results
    if hasattr(model, "v1") and hasattr(model, "v2"):
        v1_initial = model.v1.iloc[0] if len(model.v1) > 0 else 0
        v1_final = model.v1.iloc[-1] if len(model.v1) > 0 else 0
        v2_initial = model.v2.iloc[0] if len(model.v2) > 0 else 0
        v2_final = model.v2.iloc[-1] if len(model.v2) > 0 else 0
        dv1 = abs(v1_final - v1_initial)
        dv2 = abs(v2_final - v2_initial)
        click.echo(f"Vehicle 1 Delta-V: {dv1:.2f} mph")
        click.echo(f"Vehicle 2 Delta-V: {dv2:.2f} mph")

    # Peak acceleration
    if hasattr(model, "a1"):
        peak_a1 = max(abs(model.a1))
        click.echo(f"Vehicle 1 Peak Accel: {peak_a1:.2f} g")
    if hasattr(model, "a2"):
        peak_a2 = max(abs(model.a2))
        click.echo(f"Vehicle 2 Peak Accel: {peak_a2:.2f} g")

    # Mutual crush
    if hasattr(model, "dx"):
        max_crush = min(model.dx)
        click.echo(f"Peak Mutual Crush: {max_crush * -12:.2f} inches")

    # Duration
    if hasattr(model, "t"):
        duration = model.t.iloc[-1]
        click.echo(f"Impact Duration: {duration:.4f} seconds")

    click.echo("=" * 50)


@main.command()
@click.option("--config", required=True, type=click.Path(exists=True),
              help="Path to JSON config file with vehicle properties.")
@click.option("--output", default=None, type=click.Path(),
              help="Optional output CSV file path to save vehicle data.")
def vehicle(config, output):
    """Create a vehicle from a JSON config and display its properties.

    The JSON file should contain vehicle properties, for example:

    \b
      {
        "name": "Sedan",
        "year": 2020,
        "make": "Toyota",
        "model": "Camry",
        "weight": 3400,
        "width": 6.1,
        "length": 16.0,
        ...
      }
    """
    try:
        with open(config, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        click.echo(f"Error: Invalid JSON in config file: {e}", err=True)
        sys.exit(1)

    from pycrash.vehicle import Vehicle, veh_inputs

    veh_name = data.pop("name", "Vehicle")
    veh = Vehicle(veh_name, input_dict=data)

    click.echo("")
    click.echo("=" * 50)
    click.echo(f"Vehicle: {veh.name}")
    click.echo("=" * 50)

    for attr in veh_inputs:
        if hasattr(veh, attr):
            click.echo(f"  {attr}: {getattr(veh, attr)}")

    if output:
        import pandas as pd
        props = {}
        for attr in veh_inputs:
            if hasattr(veh, attr):
                props[attr] = [getattr(veh, attr)]
        df = pd.DataFrame(props)
        df.to_csv(output, index=False)
        click.echo("")
        click.echo(f"Vehicle properties saved to: {output}")

    click.echo("=" * 50)


@main.command()
@click.option("--name", default=None, help="Project name (for creating a new project).")
@click.option("--path", default=None, help="Path to project directory.")
@click.option("--load", "load_name", default=None,
              help="Name of project to load (mutually exclusive with --name).")
def project(name, path, load_name):
    """Create or load a pycrash project.

    \b
    Create a new project:
        pycrash project --name MyProject --path /path/to/projects

    Load an existing project:
        pycrash project --load MyProject --path /path/to/projects
    """
    if name and load_name:
        click.echo("Error: Use either --name (create) or --load (load), not both.", err=True)
        sys.exit(1)

    if not name and not load_name:
        click.echo("Error: Provide --name to create a project or --load to load one.", err=True)
        sys.exit(1)

    if load_name:
        # Load an existing project
        from pycrash.project import project_info, load_project

        proj_path = path if path else os.path.join(os.getcwd(), "data", "archive")
        click.echo(f"Loading project '{load_name}' from: {proj_path}")
        click.echo("")

        try:
            project_info(load_name, proj_dir=proj_path)
            result = load_project(load_name, proj_dir=proj_path)
            if hasattr(result, "show"):
                result.show()
            elif isinstance(result, list) and len(result) > 0 and hasattr(result[0], "show"):
                result[0].show()
        except FileNotFoundError:
            click.echo(f"Error: Project file '{load_name}.pkl' not found at {proj_path}.", err=True)
            sys.exit(1)
        except Exception as e:
            click.echo(f"Error loading project: {e}", err=True)
            sys.exit(1)
    else:
        # Create a new project
        if not path:
            click.echo("Error: --path is required when creating a project.", err=True)
            sys.exit(1)

        from pycrash.project import Project

        project_input = {
            "name": name,
            "project_path": path,
            "pdesc": "",
            "sim_type": "SV",
            "impact_type": None,
            "note": "Created via pycrash CLI",
        }

        try:
            proj = Project(project_input=project_input)
            click.echo("")
            click.echo("Project created successfully.")
            proj.show()
        except Exception as e:
            click.echo(f"Error creating project: {e}", err=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
