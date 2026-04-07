from .project import Project, project_info, load_project
from .impact_main import Impact
from .vehicle import Vehicle
from .kinematics import SingleMotion
from .kinematicstwo import KinematicsTwo
from .sdof_model import SDOF_Model
from .definitions import definitions

__all__ = ["Impact", "Project", "Vehicle", "SingleMotion", "KinematicsTwo", "SDOF_Model", "definitions"]

# BeamNG.tech integration (optional - requires beamngpy)
try:
    from . import beamng
except ImportError:
    pass

# OpenSim biomechanical integration (optional - requires opensim)
try:
    from . import opensim
except ImportError:
    pass
