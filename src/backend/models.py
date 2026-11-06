"""models.py - the objects: buildings, zones and meters

Current Program - uses ONE zone ("Whole building") with ONE electricity meter per building
The classes are already built for FUTURE DEV - many zones per building, many sensors per zone
"""

from abc import ABC, abstractmethod
from math import isfinite

from backend.errors import ModelError

class Meter:
    """One measuring device inside a zone (electricity meter for current program; thermometer, CO2 sensor for later dev)"""

    def __init__(self, kind, unit, source = ""):
        self.kind = kind        # What meter measures --> e.g. electricity, temperature, presence,...
        self.unit = unit        # Unit of measure --> e.g. kWh
        self.source = source    # where data comes from --> e.g CSV column name
        self.id = None          # to be filled in by database when the meter is saved

    def __repr__(self):
        return f"{type(self).__name__}({self.kind!r}, {self.unit!r})" # tell python how to display object (!r = value as writen in code)


class EnergyMeter(Meter):
    """Electricity meter = sends kWh used in each 15 min interval"""

    def __init__(self, source = ""):
        super().__init__(kind = "electricity", unit = "kWh", source = source)


class Zone:
    """A part of a building (e.g. floor, wing or room)
    - one zone (whole building) for current program
    - multi-zones for later dev"""

    def __init__(self, name):
        self.name = name
        self.meters = []        # a zone HAS multiple meters (list)
        self.id = None

    def add_meter(self, meter):
        self.meters.append(meter)
        return meter


class Building(ABC):
    """Abstract base class - cannot make a plain building, only a Home, Business, ..."""

    building_type = "building"      # every subclass overwrites this value

    def __init__(self, name, floor_area_m2):
        if not isinstance(floor_area_m2, (int, float)) or not isfinite(floor_area_m2) or floor_area_m2 <= 0:
            raise ModelError(f"{name} : floor area must be > 0; but got {floor_area_m2}")

        self.name = name
        self.floor_area_m2 = float(floor_area_m2)
        self.zones = []         # a building HAS multiple zones (list)
        self.id = None

    def add_zone(self, zone):
        self.zones.append(zone)
        return zone

    def meters(self, kind = None):
        """All meters in all zones (or only all of one kind)"""
        found = []
        for zone in self.zones:
            # look in every zone
            for meter in zone.meters:
                # at every meter in that zone
                if kind is None or meter.kind == kind:
                    # add all meters to list (if no kind asked for) or add only kind asked for if matches
                    found.append(meter)
        return found

    @abstractmethod     # every subclass must write this method
    def is_open(self, ts):
        """True - if people normally use building at local time, ts"""

    def __repr__(self):
        return f"{type(self).__name__} ({self.name!r}, {self.floor_area_m2} m2)"


class Home(Building):
    building_type = "home"

    def is_open(self, ts):
        return 6 <= ts.hour < 23        # awake between 06:00-23:00 every day

class Business(Building):
    building_type = "business"

    def is_open(self, ts):
        # ts.weekday() --> 0 = Monday ... 6 = Sunday
        return ts.weekday() < 5 and 7 <= ts.hour < 19       # open on Mon-Fri between 07:00-19:00

class PublicBuilding(Building):
    building_type = "public"

    def is_open(self, ts):
        return ts.weekday() < 5 and 7 <= ts.hour < 17       # open on Mon-Fri between 07:00-17:00

# create a lookup table - dict that maps building type (text format) to its class
# {"home" : Home, "business" : Business,...}
BUILDING_CLASSES = {cls.building_type: cls for cls in (Home, Business, PublicBuilding)}
# How it is used:
#                   property = BUILDING_CLASSES["home"] --> property is now the class Home


def make_building(building_type, name, floor_area_m2):
    """Act like a factory - turning text "home" into a Home object, "business" into a Business,..."""
    try:
        cls = BUILDING_CLASSES[building_type]

    except KeyError:
        # Catch any unknown type and raise a clear ValueError
        raise ModelError(f"Unknown building type {building_type!r}") from None
        # from None --> hide internal KeyError and produces a clearer error message

    return cls(name, floor_area_m2)
