import pandas as pd
import numpy as np
import struct
import dpkt
import laspy
from laspy.file import File
import datetime


def read_sbet(file):
    data = []
    with open(file, 'rb') as f:
        while True:
            record = f.read(17*8)
            if not record: break
            data.append(struct.unpack('<17d', record))

    columns = ['time', 'latitude', 'longitude', 'altitude', 'x_velocity', 'y_velocity', 'z_velocity',
               'roll', 'pitch', 'platform_heading', 'wander_angle', 'x_body_accel', 'y_body_accel',
               'z_body_accel', 'x_body_ang_rate', 'y_body_ang_rate', 'z_body_ang_rate']

    return pd.DataFrame(data, columns=columns)


def read_pcap(file):
    data = []

    with open(file, 'rb') as f:
        pcap = dpkt.pcap.Reader(f)
        for timestamp, buf in pcap:
            eth = dpkt.ethernet.Ethernet(buf)
            if isinstance(eth.data, dpkt.ip.IP):
                data.append((timestamp, eth.data))

    return data


def interpolate_sbet(sbet_df, timestamps):
    interpolated_data = []
    for t in timestamps:
        print(t)
        before_filtered = sbet_df[sbet_df['time'] <= t]
        after_filtered = sbet_df[sbet_df['time'] >= t]
        
        if before_filtered.empty or after_filtered.empty:
            print("skip")
            # Skip interpolation if there's no 'before' or 'after' record for the current timestamp
            continue

        before = before_filtered.iloc[-1]
        after = after_filtered.iloc[0]

        if np.isclose(before['time'], after['time']):
            interpolated_data.append(before)
        else:
            factor = (t - before['time']) / (after['time'] - before['time'])
            interpolated_row = before + factor * (after - before)
            interpolated_data.append(interpolated_row)

    return pd.DataFrame(interpolated_data)

# regner om fra unix time til gps seconds of week. Lidar bruker unix og sbet bruker seconds of week (SoW)
def timestamp_unix2sow(unix, gps_week):
    # Correction by Erlend: subtract epoch unix time as well!
    # Another correction (?) by Erlend: removed subtraction of DELTA_UNIX_GPS -- this makes PCAP and SBET correspond.
    sow = unix - 315964800 - (gps_week * 604800)
    return sow
    
def timestamp_sow2unix(sow, gps_week):
    unix = sow + 315964800 + (gps_week * 604800)
    return unix

sbet_file = "..\\Navigasjon\\Navigasjon\\ntnu-sbet.out"
sbet_df = read_sbet(sbet_file)

pcap_file = "..\\pcap\\pcap\\OS-1-128_992035000186_1024x10_20220421_133421.pcap"
pcap_data = read_pcap(pcap_file)
print(len(pcap_data))

gpsweek = 2206
sbet_df["time"] = timestamp_sow2unix(sbet_df["time"], gpsweek)

timestamps = [t for t, _ in pcap_data]
interpolated_sbet_df = interpolate_sbet(sbet_df, timestamps)