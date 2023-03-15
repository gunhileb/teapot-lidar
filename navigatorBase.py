import numpy as np
import json
import os
from tqdm import tqdm
import open3d as o3d
import laspy
from datetime import datetime
from taskTimer import TaskTimer
from algorithmHelper import AlgorithmHelper
from pcapReaderHelper import PcapReaderHelper
from open3dVisualizer import Open3DVisualizer
from plotter import Plotter
import argparse

class NavigatorBase:

    def __init__(self, args, min_frame_limit = 1):
        self.timer = TaskTimer()

        self.reader = PcapReaderHelper.from_lists(args.pcap, args.json, args.skip_every_frame, args=args)
        self.voxel_size = args.voxel_size
        self.matcher = AlgorithmHelper.get_algorithm(args.algorithm)
        self.remove_vehicle = True
        self.frame_limit = args.frames
        self.preview_always = args.preview == "always"
        self.preview_at_end = args.preview == "always" or args.preview =="end"
        self.no_preview = self.preview_always == False and self.preview_at_end == False
        self.save_path = args.save_to
        self.downsample_timer = args.downsample_after
        self.downsample_cloud_after_frames = args.downsample_after
        self.merged_frame_is_dirty = True
        self.save_screenshots_to = args.save_screenshots_to
        self.save_frame_pairs_to = args.save_frame_pairs_to
        self.save_frame_pair_threshold = args.save_frame_pair_threshold
        self.previous_transformation = None
        self.skip_start = args.skip_start
        self.build_cloud_timer = args.build_cloud_after
        self.build_cloud_after = args.build_cloud_after
        self.build_cloud = args.build_cloud_after > 0
        
        self.tqdm_config = {}
        self.print_summary_at_end = False

        self.current_coordinate = None
        
        self.time("setup")

        if self.frame_limit <= min_frame_limit:
            self.frame_limit = self.reader.count_frames(True)
            self.time("frame counting")

    def skip_initial_frames(self):
        if self.skip_start > 0:
            self.frame_limit -= self.skip_start
            for _ in tqdm(range(0, self.skip_start), ascii=True, desc="Skipping frames", **self.tqdm_config):
                self.reader.next_frame(False, self.timer)

    @staticmethod
    def print_cloud_info(title, cloud, prefix = ""):
        mf = np.asarray(cloud.points)

        print(prefix + title + ":")

        if len(mf) < 1:
            print("    > Empty array")
            return

        mins = np.amin(mf, axis=0)
        maxs = np.amax(mf, axis=0)

        print(prefix + "    > X: {:.2f} - {:.2f}".format(mins[0], maxs[0]))
        print(prefix + "    > Y: {:.2f} - {:.2f}".format(mins[1], maxs[1]))
        print(prefix + "    > Z: {:.2f} - {:.2f}".format(mins[2], maxs[2]))

    def ensure_merged_frame_is_downsampled(self):

        if self.voxel_size <= 0:
            return

        if not self.merged_frame_is_dirty:
            return

        self.merged_frame = self.merged_frame.voxel_down_sample(voxel_size=self.voxel_size)
        self.merged_frame_is_dirty = False
        self.time("cloud downsampling")

    @staticmethod
    def ensure_dir(file_path):
        directory = os.path.dirname(file_path)
        if len(directory) < 1: 
            return
        if not os.path.exists(directory):
            os.makedirs(directory)

    def get_results(self):
        data = self.plot.get_json(self.timer)

        data["movement"] = np.asarray(self.movement_path.points).tolist()
        data["algorithm"] = self.matcher.name

        return data

    @staticmethod
    def save_data(path, data):

        with open(path, 'w') as f:
            json.dump(data, f, indent=4)

    @staticmethod
    def save_cloud_as_las(path, cloud):

        xyz = np.asarray(cloud.points)

        las = laspy.create(point_format=3, file_version="1.4")
        
        xmin = np.floor(np.min(xyz[:,0]))
        ymin = np.floor(np.min(xyz[:,1]))
        zmin = np.floor(np.min(xyz[:,2]))

        las.header.offset = [xmin, ymin, zmin]
        las.header.scale = [0.001, 0.001, 0.001]
        las.x = xyz[:,0]
        las.y = xyz[:,1]
        las.z = xyz[:,2]

        las.write(path)

    def check_save_frame_pair(self, source, target, reg):
        """ Saves the frame pair if enabled and fitness is below threshold. """

        if self.save_frame_pairs_to is None: 
            return

        if reg.fitness >= self.save_frame_pair_threshold:
            return

        filenameBase = os.path.join(self.save_frame_pairs_to, str(reg.fitness) + "_" + os.path.basename(self.reader.pcap_path).replace(".pcap", "") + "_" + datetime.now().strftime('%Y-%m-%d_%H-%M-%S_%f%z'))
        self.ensure_dir(filenameBase)
        o3d.io.write_point_cloud(filenameBase + "_a.pcd", source, compressed=True)
        o3d.io.write_point_cloud(filenameBase + "_b.pcd", target, compressed=True)
    
    def time(self, key):
        return self.timer.time(key)

    def check_save_screenshot(self, index, ensure_dir = False):
        if self.save_screenshots_to is None:
            return
        
        screenshot_path = os.path.join(self.save_screenshots_to, str(index) + ".png")

        if ensure_dir:
            self.ensure_dir(screenshot_path)

        self.vis.capture_screen_image(screenshot_path)

        self.time("saved screenshot")

    def initialize_plot_and_visualization(self):
        # Initialize the visualizer
        self.vis = Open3DVisualizer()

        if self.preview_always:
            # Initiate non-blocking visualizer window
            self.vis.refresh_non_blocking()

            # Show the first frame and reset the view
            if self.merged_frame is not None:
                self.vis.show_frame(self.merged_frame)
            self.vis.set_follow_vehicle_view()

            if self.actual_movement_path is not None:
                self.vis.add_geometry(self.actual_movement_path)

            self.check_save_screenshot(0, True)

        self.plot = Plotter(self.preview_always)

    def finish_plot_and_visualization(self):
        
        if self.print_summary_at_end:
            self.plot.print_summary(self.timer)

        # Then continue showing the visualization in a blocking way until the user stops it.
        if self.preview_at_end:
            if self.merged_frame is not None:
                self.vis.show_frame(self.merged_frame)

            if self.movement_path is not None:
                self.vis.remove_geometry(self.movement_path)
                self.vis.add_geometry(self.movement_path)

            if self.actual_movement_path is not None:
                self.vis.remove_geometry(self.actual_movement_path)
                self.vis.add_geometry(self.actual_movement_path)

            self.vis.reset_view()

            self.vis.run()

        self.plot.destroy()

    def update_plot(self, reg, registration_time, movement, actual_coordinate):
        self.plot.timeUsages.append(registration_time)
        self.plot.rmses.append(reg.inlier_rmse)
        self.plot.fitnesses.append(reg.fitness)
        self.plot.distances.append(np.sqrt(np.dot(movement, movement)))

        if self.current_coordinate is not None:

            self.actual_coordinates.append(actual_coordinate)
            self.estimated_coordinates.append(self.current_coordinate.clone())

            dx = actual_coordinate.x
            dy = actual_coordinate.y
            dz = actual_coordinate.alt

            self.plot.position_error_x.append(dx)
            self.plot.position_error_y.append(dy)
            self.plot.position_error_z.append(dz)
            self.plot.position_error_2d.append(np.sqrt(dx*dx+dy*dy))
            self.plot.position_error_3d.append(np.sqrt(dx*dx+dy*dy+dz*dz))
            self.plot.position_age.append(actual_coordinate.age)

    def check_results_saving(self, save_cloud = False):

        results = self.get_results()
        
        results["estimated_coordinates"] = [x.json() for x in self.estimated_coordinates]
        results["actual_coordinates"] = [x.json(True) for x in self.actual_coordinates]
        
        if self.save_path is not None:

            self.ensure_dir(os.path.join(self.save_path, "plot.png"))
            self.plot.save_plot(os.path.join(self.save_path, "plot.png"))

            if save_cloud and self.build_cloud:
                self.save_cloud_as_las(os.path.join(self.save_path, "cloud.laz"), self.merged_frame)
                o3d.io.write_point_cloud(os.path.join(self.save_path, "cloud.pcd"), self.merged_frame, compressed=True)

            self.time("results saving")
            
            self.save_data(os.path.join(self.save_path, "data.json"), results)

    def to_cloud(self, points, translate=None, voxel_size=None, color=None):
        """ Creates an Open3D PointCloud object (o3d.geometry.PointCloud) from a given numpy array of points.
        Supports various regularly used ways of transforming the cloud.
        """

        cloud = o3d.geometry.PointCloud()

        if translate is not None:
            points += np.array(translate)

        cloud.points = o3d.utility.Vector3dVector(points)

        if voxel_size is not None:
            cloud = cloud.voxel_down_sample(voxel_size=voxel_size)

        if color is not None:
            cloud.paint_uniform_color(color)

        return cloud

    @staticmethod
    def create_parser():
        parser = argparse.ArgumentParser()
        PcapReaderHelper.add_path_arguments(parser)
        return parser

    @staticmethod
    def add_standard_and_parse_args(parser):
        parser.add_argument('--algorithm', type=str, default="NICP", required=False, help="Use this registration algorithm (see names in algorithmHelper.py).")
        parser.add_argument('--frames', type=int, default=-1, required=False, help="If given a number larger than 1, only this many frames will be read from the PCAP file.")
        parser.add_argument('--build-cloud-after', type=int, default=1, required=False, help="How often registered frames should be added to the generated point cloud. 0 or lower deactivates the generated point cloud. 1 or higher generates a point cloud with details (and time usage) decreasing with higher numbers.")
        parser.add_argument('--skip-every-frame', type=int, default=0, required=False, help="If given a positive number larger than 0, this many frames will be skipped between every frame read from the PCAP file.")
        parser.add_argument('--skip-start', type=int, default=0, required=False, help="If given a positive number larger than 0, this many frames will be skipped before starting processing frames.")
        parser.add_argument('--voxel-size', type=float, default=0.1, required=False, help="The voxel size used for cloud downsampling. If less than or equal to zero, downsampling will be disabled.")
        parser.add_argument('--downsample-after', type=int, default=10, required=False, help="The cloud will be downsampled (which is an expensive operation for large clouds, so don't do it too often) after this many registered frames have been added. If this number is higher than the number of frames being read, it will be downsampled once at the end of the process (unless downsampling is disabled, see --voxel-size).")
        parser.add_argument('--preview', type=str, default="always", choices=['always', 'end', 'never'], help="Show constantly updated point cloud and data plot previews while processing ('always'), show them only at the end ('end'), or don't show them at all ('never').")
        parser.add_argument('--save-to', type=str, default=None, required=False, help="If given, final results will be stored in this folder.")
        parser.add_argument('--save-screenshots-to', type=str, default=None, required=False, help="If given, point cloud screenshots will be saved in this directory with their indices as filenames (0.png, 1.png, 2.png, etc). Only works if --preview is set to 'always'.")
        parser.add_argument('--save-frame-pairs-to', type=str, default=None, required=False, help="If given, frame pairs with a registered fitness below --save-frame-pair-threshold will be saved to the given directory for manual inspection.")
        parser.add_argument('--save-frame-pair-threshold', type=float, default=0.97, required=False, help="If --save-frame-pairs-to is given, frame pairs with a registered fitness value below this value will be saved.")

        args = parser.parse_args()

        if args.save_screenshots_to is not None and args.preview != "always":
            raise ValueError("Cannot save cloud screenshots without --preview being set to 'always'.")

        return args