from attpc_engine.detector import Config
from attpc_engine.detector.response import get_response
from attpc_engine.detector.writer import convert_to_spyral
from spyral_utils.nuclear.nuclear_map import NucleusData

from pathlib import Path
import h5py as h5
import numpy as np


class SpyralWriter_e20009:
    """
    Custom writer for e20009 to ensure compliance with its analysis. Writes the
    simulated data into multiple files to take advantage of Spyral multiprocessing.

    Parameters
    ----------
    directory_path: Path
        Path to directory to store simulated point cloud files.
    config: Config
        The simulation configuration.
    max_file_size: int
        The maximum file size of a point cloud file in bytes. Defualt values is 10 Gb.

    Attributes
    ----------
    response: np.ndarray
        Array of response of GET electronics.
    run_number: int
        Run number of current point cloud file being written to.
    file_path: Path
        Path to current point cloud file being written to.
    file: h5.File
        h5 file object. It is the actual point cloud file currently
        being written to.
    cloud_group: h5.Group
        "cloud" group in current point cloud file.

    Methods
    -------
    create_file() -> None:
        Creates a new point cloud file.
    write(data: np.ndarray, config: Config, event_number: int) -> None
        Writes a simulated point cloud to the point cloud file.
    set_number_of_events(n_events: int) -> None
        Not currently used, but required to have this method.
    get_filename() -> Path
        Returns directory that point cloud files are written to.
    """

    def __init__(self, directory_path: Path, config: Config, max_file_size: int = 10e9):
        self.directory_path = directory_path
        self.response = get_response(config).copy()
        self.max_file_size = max_file_size
        self.run_number = 0
        self.event_number_low = 0  # Kinematics generator always starts with event 0
        self.create_file()

    def create_file(self) -> None:
        """
        Creates a new point cloud file.
        """
        self.run_number += 1
        path = self.directory_path / f"run_{self.run_number:04d}.h5"
        self.file_path = path
        self.file = h5.File(path, "w")
        self.cloud_group = self.file.create_group("cloud")

    def write(self, data: np.ndarray, config: Config, event_number: int) -> None:
        """
        Writes a simulated point cloud to the point cloud file.

        Parameters
        ----------
        data: np.ndarray
            An Nx3 array representing the point cloud. Each row is a point, with elements
            [pad id, time bucket, electrons].
        config: Config
            The simulation configuration.
        event_number: int
            Event number of simulated event from the kinematics file.
        """
        if config.pad_centers is None:
            raise ValueError("Pad centers are not assigned at write!")
        spyral_format = convert_to_spyral(
            data,
            config.elec_params.windows_edge,
            config.elec_params.micromegas_edge,
            config.det_params.length,
            self.response,
            config.pad_centers,
            config.elec_params.adc_threshold,
        )

        self.event_number_high = event_number

        dset = self.cloud_group.create_dataset(
            f"cloud_{event_number}", data=spyral_format
        )

        # If current file is too large, make a new one
        if self.file_path.stat().st_size > self.max_file_size:
            self.set_number_of_events()
            self.create_file()

        # No ic stuff from simulation
        dset.attrs["ic_amplitude"] = -1.0
        dset.attrs["ic_multiplicity"] = -1.0
        dset.attrs["ic_integral"] = -1.0
        dset.attrs["ic_centroid"] = -1.0

        # This is needed for experiment e20009
        dset.attrs["ic_sca_centroid"] = -1.0
        dset.attrs["ic_sca_multiplicity"] = -1.0

    def set_number_of_events(self) -> None:
        """
        Writes the first and last written events as attributes to the current
        point cloud file.
        """
        self.cloud_group.attrs["min_event"] = self.event_number_low
        self.cloud_group.attrs["max_event"] = self.event_number_high
        self.event_number_low = self.event_number_high

    def get_directory_name(self) -> Path:
        """
        Returns directory that point cloud files are written to.
        """
        return self.directory_path


# Used to determine the maximum energy for ExcitationUniform
def max_reaction_excitation_energy(reaction: dict[str:NucleusData], beam_energy: float):
    """
    Calculates the max excitation energy in MeV that can be given to a single nucleus in the exit
    channel of the nuclear reaction A + B -> C + D + F ... by solving the relativistic
    minimum beam kinetic energy condition. See https://web.physics.utah.edu/~jui/5110/hw/kin_rel.

    Parameters
    ----------
    reaction: dict[str: spyral_utils.nuclear.nuclear_map.NucleusData]
        Dictionary of reaction nuclei. The keys are strings that must be "beam", "target",
        and "products". The beam and target keys hold one NucleusData instance, while the
        products key is a list of NucleusData instances, one for each product.
    beam_energy: float
        Beam kinetic energy of beam nucleus in MeV.
    """
    # Calculate sum of all rest masses of exit channel nuclei
    M = 0
    for nucleus in reaction["products"]:
        M += nucleus.mass

    # Quadratic formula variables
    a = 1
    b = 2 * M
    c = (
        M**2
        - (reaction["beam"].mass + reaction["target"].mass) ** 2
        - 2 * reaction["target"].mass * beam_energy
    )

    # Maximum excitation energy
    ex = (-b + np.sqrt(b**2 - 4 * a * c)) / 2 / a

    return ex


def state_shape(points, Ei, gamma):
    """
    Probabilty density function of finding a decaying quantum mechanical state in final state of
    an energy E, P(E). This gives the theoretical shape of a state as a function of energy.
    """
    prob = []
    for point in points:
        value: float = 1 / ((point - Ei) ** 2 + gamma**2 / 4)
        prob.append(value)

    return prob


def detector_response():
    """
    Calculates the detector response by convolving the simulated response of a delta function
    state with the theoretically expected shape of a
    """
    pass
