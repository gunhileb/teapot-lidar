import math
import numpy as np

class SbetRow:
    """
    A data row from an SBET file. Contains the original coordinates as lat/lon, and transformed (to 5972) as x and y. The heading is in radians,
    0 means straight north, positive PI/2 means straight east, negative PI/2 straight west.
    """

    def __init__(self, row, sow=0, index=0, original=None, x=None, y=None):

        if row is None and x is not None and y is not None:
            self.x = x
            self.y = y
            self.alt = 0
            self.sow = 0
            self.lat = 0
            self.lon = 0
            self.age = 0
            self.index = 0
            self.roll = 0
            self.pitch = 0
            self.heading = 0
            return

        if original is not None:

            if type(original) is not dict:
                original = original.__dict__

            for key in original:
                self.__dict__[key] = original[key]

            return

        self.sow = row["time"]
        self.lat = row["lat"]
        self.lon = row["lon"]
        self.alt = row["alt"]
        self.alt_raw = row["alt"]
        self.age = sow - row["time"]
        self.roll = row["roll"]
        self.pitch = row["pitch"]
        self.heading = row["heading"]
        self.index = index
        self.x = -1
        self.y = -1

    def __str__(self, include_lat_lon=True):
        return f'ix={self.index}' + (f', lat={self.lat}, lon={self.lon}, roll={self.roll}, pitch={self.pitch}, heading={self.heading}' if include_lat_lon else '') + f', alt={self.alt}, x={self.x}, y={self.y}, time={self.sow}, age={self.age}'

    def calculate_transformed(self, transformer, gps_epoch):
        if gps_epoch is None:
            self.x, self.y = transformer.transform(self.lon, self.lat)
            self.alt = self.alt_raw
        else:
            self.x, self.y, self.alt, _ = transformer.transform(self.lon, self.lat, self.alt_raw, gps_epoch)

        return self

    def clone(self):
        return SbetRow(None, None, None, self)

    def json(self, actual = False):
        json = {
            "x": self.x,
            "y": self.y,
            "z": self.alt,
            "roll": self.roll,
            "pitch": self.pitch,
            "heading": self.heading
        }

        if actual:
            json["age"] = self.age
            json["index"] = self.index

        if "frame_ix" in self.__dict__:
            json["frame_ix"] = self.frame_ix

        return json

    def get_csv_headers(self):
        return ["index", "time", "lat", "lon", "alt", "roll", "pitch", "heading", "x", "y"]

    def get_csv(self):
        return [self.index, self.sow, self.lat, self.lon, self.alt, self.roll, self.pitch, self.heading, self.x, self.y]

    def distance2d(self, p):
        dx = p.x - self.x
        dy = p.y - self.y
        return math.sqrt(dx*dx + dy*dy)

    def translate(self, t):
        self.x += t[0]
        self.y += t[1]
        self.alt += t[2]
        return self

    def set(self, t):
        self.x = t[0]
        self.y = t[1]
        self.alt = t[2]
        return self

    def np(self):
        return np.array([self.x, self.y, self.alt])

    def short_str(self):
        return f"{self.x:.2f}, {self.y:.2f}"