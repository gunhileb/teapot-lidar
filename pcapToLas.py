from pcap.bufferedPcapReader import BufferedPcapReader
from pcap.pcapReader import PcapReader
from pcap.pcapReaderHelper import PcapReaderHelper
from utils.open3dVisualizer import Open3DVisualizer
import argparse
import open3d as o3d
import numpy as np
import os
from ouster import client
from itertools import islice
import laspy


class PcapToLas:
    def __init__(self, pcap_path, metadata_path, las_dir, las_base, args):
            """Initialize a PcapToLas by reading metadata and setting
            up a package source from the pcap file.
            """

            self.reader = PcapReader(pcap_path, metadata_path, 0, args)

            # create an iterator of LidarScans from pcap
            scans = iter(client.Scans(self.reader.source))

            for idx, scan in enumerate(scans):

                # Using the look-up-table from pcapReader
                xyz = self.reader.xyzLut(scan.field(client.ChanField.RANGE))

                # Creating a las file
                las = laspy.create()

                # Getting the sbet-row with information of the position and heading at the given timestamp
                sbet_row = self.reader.sbet.get_position(scan.timestamp[0], gps_week=self.reader.gps_week)

                # Computing the heading
                heading = -sbet_row.heading + np.pi/2

                las.x_raw = xyz[:,:,0].flatten()
                las.y_raw = xyz[:, :, 1].flatten()
                las.z_raw = xyz[:, :, 2].flatten()

                # Rotate the points using the heading from the sbet-file. 
                # Rotation is done around origo, as this is the raw lidar data.
                las.x_rotated = las.x_raw * np.cos(heading) - las.y_raw * np.sin(heading) 
                las.y_rotated = las.x_raw * np.sin(heading) + las.y_raw * np.cos(heading)

                # Adding offset using the coordinate from the sbet-file. 
                las.x = las.x_rotated + sbet_row.x
                las.y = las.y_rotated + sbet_row.y
                las.z = las.z_raw + sbet_row.alt

                las_path = os.path.join(las_dir, f'{las_base}_{idx:06d}.{"las"}')
                print(f'write frame #{idx} to file: {las_path}')
                
                # Writing to file
                las.write(las_path)

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    PcapReaderHelper.add_path_arguments(parser, browsing_only=False)
    parser.add_argument('--las_dir', type=str, default="output_data", required=False, help="las files will be saved in this directory.")
    parser.add_argument('--las_base', type = str, default = "00", required = False, help="base name for las-files")
    args = parser.parse_args()

    reader = PcapToLas(args.pcap[0], args.json[0] if args.json is not None else None, args.las_dir, args.las_base, args)