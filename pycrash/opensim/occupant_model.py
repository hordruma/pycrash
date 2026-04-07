"""
Sets up and runs OpenSim musculoskeletal models for crash occupant analysis.

Manages the OpenSim simulation pipeline:
1. Load a whole-body musculoskeletal model (Rajagopal 2015 or Gait2392)
2. Position the occupant in a seated posture
3. Apply crash forces from CrashPulseGenerator
4. Run forward dynamics to simulate occupant motion during impact
5. Extract joint forces, muscle loads, and segment kinematics

Coordinate systems:
  pycrash:  X-forward, Y-left (2D plane, imperial)
  BeamNG:   X-east, Y-north, Z-up (metric)
  OpenSim:  X-forward, Y-up, Z-right (metric)
"""

import numpy as np
import os
from typing import Optional


# Seated posture joint angles (degrees) for a typical vehicle occupant
# Based on Schneider et al. (1983) and Park et al. (2016) seated posture data
SEATED_POSTURE_DEG = {
    'hip_flexion_r': -90,     # right hip flexed ~90 deg (seated)
    'hip_flexion_l': -90,
    'knee_angle_r': -80,      # knees bent
    'knee_angle_l': -80,
    'ankle_angle_r': 10,      # slight dorsiflexion
    'ankle_angle_l': 10,
    'lumbar_extension': -10,   # slight lumbar lordosis
    'pelvis_tilt': -5,        # slight posterior tilt in vehicle seat
}

# Standard OpenSim models suitable for crash analysis
MODELS = {
    'rajagopal_2015': {
        'description': 'Full-body 37-DOF, 80 muscles (Rajagopal et al. 2015)',
        'filename': 'Rajagopal2015.osim',
        'torso_body': 'torso',
        'pelvis_body': 'pelvis',
        'head_body': 'head',
        'dof': 37,
        'muscles': 80,
    },
    'gait2392': {
        'description': 'Lower extremity 23-DOF, 92 muscles',
        'filename': 'gait2392_simbody.osim',
        'torso_body': 'torso',
        'pelvis_body': 'pelvis',
        'head_body': None,  # no head in gait2392
        'dof': 23,
        'muscles': 92,
    },
}


class OccupantModel:
    """
    Configures and runs OpenSim occupant crash simulation.

    Workflow:
    1. Load model: OccupantModel('rajagopal_2015')
    2. Set posture: model.set_seated_posture()
    3. Apply forces: model.apply_crash_forces(pulse_generator)
    4. Run: results = model.run_forward_dynamics(duration=0.2)
    5. Analyze: model.get_joint_reactions(), model.get_body_kinematics()
    """

    def __init__(self, model_name='rajagopal_2015', model_path=None):
        """
        Args:
            model_name: Key from MODELS dict, or 'custom'
            model_path: Path to .osim file. Required if model_name='custom',
                       optional override for standard models.
        """
        self.model_name = model_name
        self._model = None
        self._state = None
        self._results = {}
        self._force_files = []

        if model_name in MODELS:
            self.model_info = MODELS[model_name]
        else:
            self.model_info = {
                'description': 'Custom model',
                'torso_body': 'torso',
                'pelvis_body': 'pelvis',
                'head_body': 'head',
            }

        self.model_path = model_path

    def load_model(self):
        """
        Load the OpenSim model from file.

        Raises:
            ImportError: if opensim package not installed
            FileNotFoundError: if model file not found
        """
        try:
            import opensim as osim
        except ImportError:
            raise ImportError(
                "opensim Python package required. Install from: "
                "https://simtk.org/projects/opensim or pip install opensim"
            )

        if self.model_path and os.path.exists(self.model_path):
            self._model = osim.Model(self.model_path)
        else:
            raise FileNotFoundError(
                f"Model file not found: {self.model_path}\n"
                f"Download standard models from https://simtk.org/projects/opensim\n"
                f"Expected: {self.model_info.get('filename', 'unknown')}"
            )

        self._model.initSystem()
        self._state = self._model.initializeState()

        print(f"Loaded OpenSim model: {self.model_name}")
        print(f"  Bodies: {self._model.getBodySet().getSize()}")
        print(f"  Joints: {self._model.getJointSet().getSize()}")
        print(f"  Muscles: {self._model.getMuscles().getSize()}")
        print(f"  DOF: {self._model.getCoordinateSet().getSize()}")

        return self

    def set_seated_posture(self, custom_angles=None):
        """
        Set the model to a vehicle-seated posture.

        Args:
            custom_angles: dict of {coordinate_name: angle_deg} to override defaults

        Returns:
            self for method chaining
        """
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        angles = SEATED_POSTURE_DEG.copy()
        if custom_angles:
            angles.update(custom_angles)

        coord_set = self._model.getCoordinateSet()

        for coord_name, angle_deg in angles.items():
            try:
                coord = coord_set.get(coord_name)
                coord.setValue(self._state, np.radians(angle_deg))
            except Exception:
                # Coordinate may not exist in all models
                pass

        self._model.assemble(self._state)
        return self

    def apply_crash_forces(self, pulse_generator, output_dir=None,
                           body_segments=None):
        """
        Apply crash forces from a CrashPulseGenerator to the model.

        Creates .sto and ExternalLoads .xml files and attaches them
        to the model for simulation.

        Args:
            pulse_generator: CrashPulseGenerator instance with pulse computed
            output_dir: Directory for force files (default: current dir)
            body_segments: List of body segments to apply forces to.
                          Default: ['torso', 'pelvis']

        Returns:
            list of generated file paths
        """
        if output_dir is None:
            output_dir = os.getcwd()

        if body_segments is None:
            body_segments = ['torso']
            if self.model_info.get('pelvis_body'):
                body_segments.append('pelvis')

        files = []
        for segment in body_segments:
            opensim_body = self.model_info.get(f'{segment}_body', segment)
            if opensim_body is None:
                continue

            sto_path = os.path.join(output_dir, f'crash_force_{segment}.sto')
            xml_path = os.path.join(output_dir, f'crash_loads_{segment}.xml')

            pulse_generator.to_opensim_sto(sto_path, body_segment=segment)
            pulse_generator.to_opensim_external_loads(
                xml_path, sto_path,
                body_segment=segment,
                opensim_body=opensim_body
            )
            files.extend([sto_path, xml_path])

        self._force_files = files
        return files

    def run_forward_dynamics(self, duration_s=0.2, output_dir=None):
        """
        Run OpenSim forward dynamics with crash forces applied.

        Forward dynamics computes occupant motion in response to
        the applied crash forces, accounting for:
        - Musculoskeletal geometry and mass distribution
        - Joint constraints and range of motion
        - Passive muscle/ligament resistance
        - Gravity

        Args:
            duration_s: Simulation duration (seconds). Crash events
                       typically 0.1-0.2s for the impact phase.
            output_dir: Directory for results files

        Returns:
            dict with result file paths and summary metrics
        """
        try:
            import opensim as osim
        except ImportError:
            raise ImportError("opensim package required")

        if self._model is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        if output_dir is None:
            output_dir = os.getcwd()

        # Set up ForwardTool
        fwd_tool = osim.ForwardTool()
        fwd_tool.setModel(self._model)
        fwd_tool.setInitialTime(0.0)
        fwd_tool.setFinalTime(duration_s)
        fwd_tool.setResultsDir(output_dir)

        # Apply external loads
        for f in self._force_files:
            if f.endswith('.xml'):
                ext_loads = osim.ExternalLoads(f, True)
                self._model.addModelComponent(ext_loads)

        # Run simulation
        fwd_tool.run()

        # Collect result files
        self._results = {
            'states': os.path.join(output_dir, 'FwdTool_states.sto'),
            'controls': os.path.join(output_dir, 'FwdTool_controls.sto'),
        }

        return self._results

    def run_inverse_dynamics(self, motion_file, output_dir=None):
        """
        Run inverse dynamics to compute joint torques from known motion.

        Use this when occupant kinematics are known (e.g., from video
        or motion capture during crash test) and you want to determine
        the joint forces/moments that produced the observed motion.

        Args:
            motion_file: Path to .mot file with occupant joint angles vs time
            output_dir: Directory for results

        Returns:
            dict with result file paths
        """
        try:
            import opensim as osim
        except ImportError:
            raise ImportError("opensim package required")

        if self._model is None:
            raise RuntimeError("Model not loaded")

        if output_dir is None:
            output_dir = os.getcwd()

        id_tool = osim.InverseDynamicsTool()
        id_tool.setModel(self._model)
        id_tool.setCoordinatesFileName(motion_file)
        id_tool.setResultsDir(output_dir)

        # Apply external loads (crash forces)
        for f in self._force_files:
            if f.endswith('.xml'):
                id_tool.setExternalLoadsFileName(f)
                break

        id_tool.run()

        return {
            'joint_torques': os.path.join(output_dir, 'inverse_dynamics.sto'),
        }

    def get_joint_reactions(self, states_file=None):
        """
        Extract joint reaction forces from simulation results.

        Joint reaction forces are critical for injury assessment:
        - Cervical spine: neck injury (whiplash, fracture)
        - Lumbar spine: back injury
        - Hip: femur/acetabulum loading
        - Knee: dashboard knee injury
        - Ankle: floorboard intrusion loading

        Returns:
            dict of {joint_name: DataFrame with Fx, Fy, Fz, Mx, My, Mz}
        """
        try:
            import opensim as osim
        except ImportError:
            raise ImportError("opensim package required")

        if self._model is None:
            raise RuntimeError("Model not loaded")

        states_file = states_file or self._results.get('states')
        if not states_file or not os.path.exists(states_file):
            raise FileNotFoundError("No states file available. Run simulation first.")

        # Set up JointReaction analysis
        jr_analysis = osim.JointReaction()
        jr_analysis.setModel(self._model)
        jr_analysis.setStatesStorage(osim.Storage(states_file))

        # Target joints relevant to crash injury
        crash_joints = [
            'back',           # lumbar spine
            'hip_r', 'hip_l',
            'knee_r', 'knee_l',
            'ankle_r', 'ankle_l',
        ]

        joint_set = self._model.getJointSet()
        available_joints = [joint_set.get(i).getName()
                          for i in range(joint_set.getSize())]

        target_joints = [j for j in crash_joints if j in available_joints]

        if target_joints:
            joint_names = osim.ArrayStr()
            for j in target_joints:
                joint_names.append(j)
            jr_analysis.setJointNames(joint_names)

        return {
            'analysis': jr_analysis,
            'target_joints': target_joints,
            'available_joints': available_joints,
        }

    def setup_analysis_pipeline(self, crash_pulse, output_dir,
                                duration_s=0.2):
        """
        One-call setup for the complete OpenSim analysis pipeline.

        Creates all necessary files and configuration for running
        the crash occupant simulation.

        Args:
            crash_pulse: CrashPulseGenerator with pulse computed
            output_dir: Directory for all files and results
            duration_s: Simulation duration

        Returns:
            dict with all file paths and configuration needed to run
        """
        os.makedirs(output_dir, exist_ok=True)

        # Generate force files
        force_files = self.apply_crash_forces(crash_pulse, output_dir)

        # Get pulse summary for reference
        pulse_summary = crash_pulse.get_pulse_summary()

        # Create setup summary
        setup = {
            'model': self.model_name,
            'model_path': self.model_path,
            'model_info': self.model_info,
            'force_files': force_files,
            'output_dir': output_dir,
            'duration_s': duration_s,
            'pulse_summary': pulse_summary,
            'posture': SEATED_POSTURE_DEG,
            'instructions': [
                "To run the simulation:",
                "1. Ensure OpenSim 4.x+ is installed with Python bindings",
                f"2. Model file: {self.model_path or self.model_info.get('filename')}",
                f"3. Force files generated in: {output_dir}",
                "4. Call model.load_model() then model.run_forward_dynamics()",
                "5. Or load the .xml files manually in OpenSim GUI",
            ],
        }

        return setup
