# This script simulates R2S method of shut down dose rate
# on a simple sphere model.

import numpy as np
import openmc
import openmc.deplete
from pathlib import Path
import math
from matplotlib.colors import LogNorm

# users might want to change these to use specific xml files to use particular decay data or transport cross sections
# the chain file was downloaded with
# pip install openmc_data
# download_endf_chain -r b8.0
# openmc.config['chain_file'] = '/nuclear_data/chain-endf-b8.0.xml'
# openmc.config['cross_sections'] = 'cross_sections.xml'
openmc.config['chain_file'] = '/home/jshimwell/ENDF-B-VIII.0-NNDC/chain-nndc-b8.0.xml'

# a few user settings
# Set up the folders to save all the data in
n_particles = 1_00000
p_particles = 1_000
statepoints_folder = Path('statepoints_folder')


al_sphere_radius = 7
iron_sphere_radius = 4

# We make a iron material which should produce a few activation products
mat_iron = openmc.Material()
mat_iron.id = 1
mat_iron.add_nuclide("Fe56", 1.0)
mat_iron.add_nuclide("Fe57", 1.0)
mat_iron.set_density("g/cm3", 7.7)
# must set the depletion to True to deplete the material
mat_iron.depletable = True
# volume must set the volume as well as openmc calculates number of atoms
mat_iron.volume = (4 / 3) * math.pi * math.pow(iron_sphere_radius, 3)

# We make a Al material which should produce a few different activation products
mat_aluminum = openmc.Material()
mat_aluminum.id = 2
mat_aluminum.add_element("Al", 1.0)
mat_aluminum.set_density("g/cm3", 2.7)
# must set the depletion to True to deplete the material
mat_aluminum.depletable = True
# volume must set the volume as well as openmc calculates number of atoms
mat_aluminum.volume = (4 / 3) * math.pi * math.pow(al_sphere_radius, 3)



# First we make a simple geometry with three cells, (two with material)
sphere_surf_1 = openmc.Sphere(r=20)
sphere_surf_2 = openmc.Sphere(r=iron_sphere_radius, z0=10)
sphere_surf_3 = openmc.Sphere(r=al_sphere_radius, z0=-5)

sphere_region_1 = -sphere_surf_1 & +sphere_surf_2 & +sphere_surf_3  # void space
sphere_region_2 = -sphere_surf_2
sphere_region_3 = -sphere_surf_3

sphere_cell_1 = openmc.Cell(region=sphere_region_1)
sphere_cell_2 = openmc.Cell(region=sphere_region_2,fill = mat_iron)
sphere_cell_3 = openmc.Cell(region=sphere_region_3,fill = mat_aluminum)

box = openmc.model.RectangularParallelepiped(
    xmin=-20, xmax=20, ymin=-20, ymax=20, zmin=-20, zmax=20, boundary_type="vacuum"
)
sphere_cell_4 = openmc.Cell(region=-box & +sphere_surf_1, fill=mat_aluminum)

my_geometry = openmc.Geometry([sphere_cell_1, sphere_cell_2, sphere_cell_3, sphere_cell_4])

# plot = my_geometry.plot(basis='xz')
# import matplotlib.pyplot as plt
# plt.show()

my_materials = openmc.Materials([mat_iron, mat_aluminum])

pristine_mat_iron = mat_iron.clone()
pristine_mat_aluminium = mat_aluminum.clone()

# 14MeV neutron source that activates material
my_source = openmc.IndependentSource()
my_source.space = openmc.stats.Point((0, 0, 0))
my_source.angle = openmc.stats.Isotropic()
my_source.energy = openmc.stats.Discrete([14.06e6], [1])
my_source.particle = "neutron"

# settings for the neutron simulation(s)
my_neutron_settings = openmc.Settings()
my_neutron_settings.run_mode = "fixed source"
my_neutron_settings.particles = n_particles
my_neutron_settings.batches = 10
my_neutron_settings.source = my_source
my_neutron_settings.photon_transport = False

# Create mesh which will be used for tally
regular_mesh = openmc.RegularMesh().from_domain(
    my_geometry, # the corners of the mesh are being set automatically to surround the geometry
    dimension=[10,10,10] # 10
)

model_neutron = openmc.Model(my_geometry, my_materials, my_neutron_settings)





model_neutron.export_to_xml(directory=statepoints_folder/ "neutrons")
model_neutron.export_to_xml()

all_nuclides = []
for material in my_geometry.get_all_materials().values():
    for nuclide in material.get_nuclides():
        if nuclide not in all_nuclides:
            all_nuclides.append(nuclide)
# print(set(all_nuclides))

# this does perform transport but just to get the flux and micro xs
flux_in_each_group, all_micro_xs = openmc.deplete.get_microxs_and_flux(
    model=model_neutron,
    domains=regular_mesh,
    energies=[0,30e6], # different group structures see this file for all the groups available https://github.com/openmc-dev/openmc/blob/develop/openmc/mgxs/__init__.py
    nuclides=all_nuclides,
    chain_file=openmc.config['chain_file']
)

model_neutron.export_to_model_xml()

import openmc.lib
openmc.lib.init()


lib_mesh = openmc.lib.RegularMesh()
lib_mesh.dimension = regular_mesh.dimension
lib_mesh.set_parameters(
    lower_left=regular_mesh.lower_left,
    upper_right=regular_mesh.upper_right
)

mesh_material_volumes = lib_mesh.material_volumes(n_samples = 1000000)

mesh_voxel_material = []

mat_number_offset = 100
alls_mats = my_geometry.get_all_materials()
volume_of_material_in_voxel = []
material_in_voxel = []

selective_flux_in_each_group = []
selective_micro_xs = []

for i, (mesh_material_volume, micro_xs, flux_in_group) in enumerate(zip(mesh_material_volumes, all_micro_xs, flux_in_each_group) ):
    print(mesh_material_volume)
    materials_in_voxel = []
    volumes_in_voxel = []
    for material_volume_tuple in mesh_material_volume:
        material = material_volume_tuple[0]
        if material != None:
            volume_in_cm3 = material_volume_tuple[1]
            print(f'   {material.id}, {volume_in_cm3}')      
            materials_in_voxel.append(alls_mats[material.id])
            volumes_in_voxel.append(volume_in_cm3)
    
    volume_of_material_in_voxel.append(sum(volumes_in_voxel))

    print(materials_in_voxel, volumes_in_voxel)
    if len(materials_in_voxel)==1:
        print('2 materials found')
        voxel_mat = materials_in_voxel[0].clone() #TODO find out why cloning crashes code
        selective_flux_in_each_group.append(flux_in_group)
        selective_micro_xs.append(micro_xs)

        voxel_mat.volume = sum(volumes_in_voxel)
        voxel_mat.id = i+mat_number_offset
        voxel_mat.depletable = True
        material_in_voxel.append(voxel_mat)

    elif len(materials_in_voxel)>1:
        # todo check this volume fraction is correct

        norm_fracs = [v*(1/sum(volumes_in_voxel)) for v in volumes_in_voxel]
        print('1 material found')
        voxel_mat = openmc.Material.mix_materials(materials_in_voxel, norm_fracs)
        selective_flux_in_each_group.append(flux_in_group)
        selective_micro_xs.append(micro_xs)

        voxel_mat.volume = sum(volumes_in_voxel)
        voxel_mat.id = i+mat_number_offset
        voxel_mat.depletable = True
        material_in_voxel.append(voxel_mat)

    else:
        print('no material in voxel')
        

openmc.lib.finalize()



# constructing the operator, note we pass in the flux and micro xs
operator = openmc.deplete.IndependentOperator(
    materials=openmc.Materials(material_in_voxel),
    fluxes=[flux[0] for flux in selective_flux_in_each_group],
    micros=selective_micro_xs,
    reduce_chain=True,  # reduced to only the isotopes present in depletable materials and their possible progeny
    reduce_chain_level=4,
    normalization_mode="source-rate"
)

# This section defines the neutron pulse schedule.
# If the method made use of the CoupledOperator then there would need to be a
# transport simulation for each timestep. However as the IndependentOperator is
# used then just a single transport simulation is done, thus speeding up the
# simulation considerably.
hour_in_seconds = 60*60
timesteps_and_source_rates = [
    (1, 1e18),  # 1 second
    (hour_in_seconds, 0),  # 1 hour
    (1, 1e18),  # 1 second
    (hour_in_seconds, 0),  # 2 hour
    (1, 1e18),  # 1 second
    (hour_in_seconds, 0),  # 3 hour
    (1, 1e18),  # 1 second
    (hour_in_seconds, 0),  # 4 hour
    (1, 1e18),  # 1 second
    (hour_in_seconds, 0),  # 4 hour
    (1, 1e18),  # 1 second
    (hour_in_seconds, 0),  # 4 hour
    (1, 1e18),  # 1 second
    (hour_in_seconds, 0),  # 5 hour
]

timesteps = [item[0] for item in timesteps_and_source_rates]
source_rates = [item[1] for item in timesteps_and_source_rates]

integrator = openmc.deplete.PredictorIntegrator(
    operator=operator,
    timesteps=timesteps,
    source_rates=source_rates,
    timestep_units='s'
)

# # this runs the depletion calculations for the timesteps
# # this does the neutron activation simulations and produces a depletion_results.h5 file
integrator.integrate(
    path=statepoints_folder / "neutrons" / "depletion_results.h5"
)

# # Now we have done the neutron activation simulations we can start the work needed for the decay gamma simulations.

my_gamma_settings = openmc.Settings()
my_gamma_settings.run_mode = "fixed source"
my_gamma_settings.batches = 100
my_gamma_settings.particles = p_particles

# # First we add make dose tally on a regular mesh

# creates a regular mesh that surrounds the geometry
mesh_photon = openmc.RegularMesh().from_domain(
    my_geometry,
    dimension=[10, 10, 10],  # 10 voxels in each axis direction (x, y, z)
)

# adding a dose tally on a regular mesh
# AP, PA, LLAT, RLAT, ROT, ISO are ICRP incident dose field directions, AP is front facing
energies, pSv_cm2 = openmc.data.dose_coefficients(particle="photon", geometry="AP")
dose_filter = openmc.EnergyFunctionFilter(
    energies, pSv_cm2, interpolation="cubic"  # interpolation method recommended by ICRP
)
particle_filter = openmc.ParticleFilter(["photon"])
mesh_filter = openmc.MeshFilter(mesh_photon)
dose_tally = openmc.Tally()
dose_tally.filters = [mesh_filter, dose_filter, particle_filter]
dose_tally.scores = ["flux"]
dose_tally.name = "photon_dose_on_mesh"

my_gamma_tallies = openmc.Tallies([dose_tally])

cells = model_neutron.geometry.get_all_cells()

# # this section makes the photon sources from each active material at each
# # timestep and runs the photon simulations
results = openmc.deplete.Results(statepoints_folder / "neutrons" / "depletion_results.h5")

for i_cool in range(1, len(timesteps)):

    # we can loop through the materials in each step
    # from the material ID we can get the mesh voxel id
    # then we can make a MeshSource
    # https://docs.openmc.org/en/develop/pythonapi/generated/openmc.MeshSource.html

    # range starts at 1 to skip the first step as that is an irradiation step and there is no
    # decay gamma source from the stable material at that time
    # also there are no decay products in this first timestep for this model

        photon_sources_for_timestep = []
        strengths_for_timestep = []
        print(f"making photon source for timestep {i_cool}")


        mat_number_offset

        step = results[i_cool]
        activated_mat_ids = step.volume.keys()
        print(activated_mat_ids)
        for activated_mat_id in activated_mat_ids:
            # gets the energy and probabilities for the 
            activated_mat = step.get_material(activated_mat_id)
            energy = activated_mat.get_decay_photon_energy(
                clip_tolerance = 1e-6,  # cuts out a small fraction of the very low energy (and hence negligible dose contribution) photons
                units = 'Bq',
            )
            strength = energy.integral()

            if strength > 0.:  
                source = openmc.IndependentSource(
                    energy=energy,
                    particle="photon",
                    strength=strength
                )
            else:
                source = openmc.IndependentSource() # how to make an empty source, source strength is set to 0

            photon_sources_for_timestep.append(source)
            strengths_for_timestep.append(strength)
        
        reshaped_photon_source_of_timestep = np.array(photon_sources_for_timestep).reshape(regular_mesh.dimension)
        mesh_source = openmc.MeshSource(
            regular_mesh, reshaped_photon_source_of_timestep
        )
        mesh_source.strength = 1# strengths_for_timestep

        my_gamma_settings.source = mesh_source
        model_gamma = openmc.Model(my_geometry, my_materials, my_gamma_settings, my_gamma_tallies)

        model_gamma.run(cwd=statepoints_folder / "photons" / f"photon_at_time_{i_cool}")


pico_to_micro = 1e-6
seconds_to_hours = 60*60

# # You may wish to plot the dose tally on a mesh, this package makes it easy to include the geometry with the mesh tally
from openmc_regular_mesh_plotter import plot_mesh_tally
for i_cool in range(1, len(timesteps)):
    with openmc.StatePoint(statepoints_folder / "photons" / f"photon_at_time_{i_cool}" / f'statepoint.{my_gamma_settings.batches}.h5') as statepoint:
        photon_tally = statepoint.get_tally(name="photon_dose_on_mesh")

        # normalising this tally is a little different to other examples as the source strength has been using units of photons per second.
        # tally.mean is in units of pSv-cm3/source photon.
        # as source strength is in photons_per_second this changes units to pSv-/second

        # multiplication by pico_to_micro converts from (pico) pSv/s to (micro) uSv/s
        # dividing by mesh voxel volume is not needed as the volume_normalization in the ploting function does this
        # could do the mesh volume scaling on the plot and vtk functions but doing it here instead
        scaling_factor = (seconds_to_hours * pico_to_micro)

        plot = plot_mesh_tally(
            tally=photon_tally,
            basis="xz",
            # score='flux', # only one tally so can make use of default here
            value="mean",
            colorbar_kwargs={
                'label': "Decay photon dose [µSv/h]",
            },
            norm=LogNorm(),
            volume_normalization=True,  # this is done in the scaling_factor
            scaling_factor=scaling_factor,
        )
        plot.figure.savefig(f'mesh_shut_down_dose_map_timestep_{i_cool}')
